"""Server-side Google reCAPTCHA verification service (Section 25).
Secret key remains strictly on the server and is never exposed to the frontend.
"""

import hashlib
import hmac
import logging
import time
from typing import Optional, Dict, Any, List
import httpx
from fastapi import HTTPException, status
from app.services.usage_service import usage_recorder

from app.config import settings

logger = logging.getLogger(__name__)

RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"

# Both providers use the same "secret + response (+ remoteip) -> success" protocol.
PROVIDERS = {
    "recaptcha": {
        "verify_url": RECAPTCHA_VERIFY_URL,
        "script_url": "https://www.google.com/recaptcha/api.js?render=explicit",
    },
    "turnstile": {
        "verify_url": "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        "script_url": "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit",
    },
}

_PLACEHOLDERS = {"your_recaptcha_site_key_here", "your_recaptcha_secret_key_here"}

# What the provider's error codes mean, in words a site owner can act on. These are written to the SERVER LOG
# (never shown to visitors, who only get a short "please try again").
_ERROR_HELP = {
    "missing-input-secret": "The secret key is missing on the server (RECAPTCHA_SECRET_KEY).",
    "invalid-input-secret": "The secret key is wrong, or it does not belong to the site key. Copy BOTH keys from the same "
                            "key in the reCAPTCHA / Turnstile console, and check CAPTCHA_PROVIDER matches that provider.",
    "missing-input-response": "The browser sent no CAPTCHA answer.",
    "invalid-input-response": "The CAPTCHA answer was not valid (it expired or was altered).",
    "timeout-or-duplicate": "The CAPTCHA answer was already used or took more than 2 minutes. Each tick can be used once.",
    "bad-request": "The provider rejected the request as malformed.",
    "hostname-mismatch": "The CAPTCHA was solved on a domain that is not in the key's allowed domain list.",
    "browser-error": "The visitor's browser reported an error while loading the CAPTCHA.",
}


class CaptchaService:
    # ---- configuration -------------------------------------------------
    def provider(self) -> Dict[str, str]:
        return PROVIDERS.get(settings.CAPTCHA_PROVIDER, PROVIDERS["recaptcha"])

    def config_problem(self) -> Optional[str]:
        """Why the CAPTCHA is off or cannot work, in plain words (None when it looks fine)."""
        site, secret = (settings.RECAPTCHA_SITE_KEY or "").strip(), (settings.RECAPTCHA_SECRET_KEY or "").strip()
        has_site = bool(site) and site not in _PLACEHOLDERS
        has_secret = bool(secret) and secret not in _PLACEHOLDERS
        if not has_site and not has_secret:
            return "No CAPTCHA keys are set, so the CAPTCHA is switched off."
        if has_site and not has_secret:
            return "RECAPTCHA_SECRET_KEY is missing, so the CAPTCHA is switched off. Set both keys."
        if has_secret and not has_site:
            return "RECAPTCHA_SITE_KEY is missing, so the CAPTCHA is switched off. Set both keys."
        provider = settings.CAPTCHA_PROVIDER
        if provider == "recaptcha" and site.startswith("0x"):
            return "The site key looks like a Cloudflare Turnstile key, but CAPTCHA_PROVIDER is 'recaptcha'. Set CAPTCHA_PROVIDER=turnstile."
        if provider == "turnstile" and site.startswith("6L"):
            return "The site key looks like a Google reCAPTCHA key, but CAPTCHA_PROVIDER is 'turnstile'. Set CAPTCHA_PROVIDER=recaptcha."
        return None

    def is_enabled(self) -> bool:
        """True only when BOTH keys are configured (real values, not placeholders)."""
        site, secret = settings.RECAPTCHA_SITE_KEY, settings.RECAPTCHA_SECRET_KEY
        return bool(site and secret and site not in _PLACEHOLDERS and secret not in _PLACEHOLDERS)

    # ---- application session (signed, expiring; secret never leaves server) ----
    def issue_session_token(self) -> str:
        expires = int(time.time()) + int(settings.CAPTCHA_SESSION_HOURS) * 3600
        sig = hmac.new(
            (settings.RECAPTCHA_SECRET_KEY or "").encode(), str(expires).encode(), hashlib.sha256
        ).hexdigest()
        return f"{expires}.{sig}"

    def is_valid_session_token(self, token: Optional[str]) -> bool:
        if not token or "." not in token or not settings.RECAPTCHA_SECRET_KEY:
            return False
        expires_str, sig = token.split(".", 1)
        try:
            expires = int(expires_str)
        except ValueError:
            return False
        expected = hmac.new(
            settings.RECAPTCHA_SECRET_KEY.encode(), expires_str.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(sig, expected) and expires > time.time()

    async def verify_token(self, token: Optional[str], remote_ip: Optional[str] = None) -> Dict[str, Any]:
        """Verify reCAPTCHA token against Google's verification endpoint.
        Returns dict with success: bool and error_codes/details.
        """
        secret = settings.RECAPTCHA_SECRET_KEY

        # Dev / test bypass: only when running in MOCK_MODE. In live mode a
        # missing secret fails closed so the CAPTCHA can never be skipped.
        if not secret or secret == "your_recaptcha_secret_key_here":
            if not settings.MOCK_MODE:
                return {
                    "success": False,
                    "error_codes": ["captcha-not-configured"],
                    "message": "CAPTCHA is not configured on the server (RECAPTCHA_SECRET_KEY missing)."
                }
            if token and token.strip() == "invalid-test-token":
                return {
                    "success": False,
                    "error_codes": ["invalid-input-response"],
                    "message": "Invalid test CAPTCHA token."
                }
            # When no secret is configured in dev, allow valid tokens
            if not token or not token.strip():
                return {
                    "success": False,
                    "error_codes": ["missing-input-response"],
                    "message": "CAPTCHA token is required."
                }
            return {
                "success": True,
                "message": "CAPTCHA verified (development/test bypass mode)."
            }

        if not token or not token.strip():
            return {
                "success": False,
                "error_codes": ["missing-input-response"],
                "message": "CAPTCHA token is required."
            }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                data = {
                    "secret": secret,
                    "response": token.strip()
                }
                if remote_ip:
                    data["remoteip"] = remote_ip

                with usage_recorder.track("recaptcha", "verify") as _u:
                    response = await client.post(self.provider()["verify_url"], data=data)
                    _u.status = getattr(response, "status_code", None)
                result = response.json()
                success = result.get("success", False)
                if not success:
                    codes: List[str] = list(result.get("error-codes", []) or [])
                    self._log_failure(codes)
                    return {
                        "success": False,
                        "error_codes": codes,
                        "message": "CAPTCHA verification failed. Please tick the box again."
                    }
                return {
                    "success": True,
                    "score": result.get("score"),
                    "action": result.get("action")
                }
        except Exception as exc:
            logger.error(f"Error during CAPTCHA verification (could not reach {self.provider()['verify_url']}): {exc}")
            return {
                "success": False,
                "error_codes": ["verification-network-error"],
                "message": "The security check service could not be reached. Please try again in a moment."
            }

    @staticmethod
    def _log_failure(codes: List[str]) -> None:
        """Put the provider's reason in the server log so a misconfiguration is visible, not silent."""
        if not codes:
            logger.warning("CAPTCHA verification failed (the provider gave no reason).")
            return
        for code in codes:
            logger.warning("CAPTCHA verification failed: %s - %s", code, _ERROR_HELP.get(code, "see the provider's documentation."))


captcha_service = CaptchaService()


async def enforce_captcha(token: Optional[str], ip: Optional[str], action: str = "continue") -> None:
    """Server-side human check for one protected action (for example posting a review).

    A no-op when no CAPTCHA keys are configured (local development). Otherwise the token must be present and
    accepted by the provider; a token works only once, so the page asks for a fresh tick every time.
    Raises HTTP 400 with a readable message.
    """
    if not captcha_service.is_enabled():
        return
    if not token or not str(token).strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Please tick the CAPTCHA box to {action}.")
    result = await captcha_service.verify_token(token, ip)
    if not result.get("success"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result.get("message", "CAPTCHA verification failed. Please try again."))
