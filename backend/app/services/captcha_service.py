"""Server-side Google reCAPTCHA verification service (Section 25).
Secret key remains strictly on the server and is never exposed to the frontend.
"""

import hashlib
import hmac
import logging
import time
from typing import Optional, Dict, Any
import httpx

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


class CaptchaService:
    # ---- configuration -------------------------------------------------
    def provider(self) -> Dict[str, str]:
        return PROVIDERS.get(settings.CAPTCHA_PROVIDER, PROVIDERS["recaptcha"])

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

                response = await client.post(self.provider()["verify_url"], data=data)
                result = response.json()
                success = result.get("success", False)
                if not success:
                    return {
                        "success": False,
                        "error_codes": result.get("error-codes", []),
                        "message": "CAPTCHA verification failed. Please tick the box again."
                    }
                return {
                    "success": True,
                    "score": result.get("score"),
                    "action": result.get("action")
                }
        except Exception as exc:
            logger.error(f"Error during reCAPTCHA verification: {exc}")
            return {
                "success": False,
                "error_codes": ["verification-network-error"],
                "message": f"Verification service error: {str(exc)}"
            }


captcha_service = CaptchaService()
