/**
 * Human-verification gate (Section 25).
 *
 * Browser -> CAPTCHA widget (Google reCAPTCHA v2 checkbox or Cloudflare Turnstile)
 *         -> backend verifies the token with the provider (secret stays on the server)
 *         -> backend starts an application session (HttpOnly cookie)
 *
 * Shown once per session. If the server later answers 403 "Human verification
 * required" (for example the session expired) the gate is shown again.
 */

import { api } from "../api.js";
import { toast } from "./toast.js";

const OVERLAY_ID = "captchaOverlay";

class CaptchaManager {
  constructor() {
    this.sessionVerified = sessionStorage.getItem("slg_captcha_verified") === "true";
    this.config = null;
    this.widgetId = null;
    this.token = null;

    // api.js raises this when a protected endpoint answers 403
    window.addEventListener("slg:captcha-required", () => this.requireVerification());
  }

  isVerified() {
    return this.sessionVerified;
  }

  markVerified() {
    this.sessionVerified = true;
    sessionStorage.setItem("slg_captcha_verified", "true");
  }

  markUnverified() {
    this.sessionVerified = false;
    sessionStorage.removeItem("slg_captcha_verified");
  }

  async initSiteProtection() {
    try {
      this.config = await api.getCaptchaConfig();
      if (!this.config.enabled) {
        // Keys not configured (local development): no gate.
        this.markVerified();
        return;
      }
      // The server is the source of truth, not sessionStorage.
      const status = await api.getCaptchaStatus();
      if (status.verified) {
        this.markVerified();
        return;
      }
      this.markUnverified();
      this.renderVerificationModal();
    } catch (err) {
      console.warn("CAPTCHA check skipped:", err);
    }
  }

  async requireVerification() {
    if (document.getElementById(OVERLAY_ID)) return;
    try {
      if (!this.config) this.config = await api.getCaptchaConfig();
      if (!this.config.enabled) return;
      this.markUnverified();
      this.renderVerificationModal();
    } catch (_) {}
  }

  loadScript(url) {
    return new Promise((resolve, reject) => {
      if (document.querySelector(`script[data-captcha-src="${url}"]`)) {
        resolve();
        return;
      }
      const s = document.createElement("script");
      s.src = url;
      s.async = true;
      s.defer = true;
      s.dataset.captchaSrc = url;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error("Could not load the security check. Check your internet connection."));
      document.head.appendChild(s);
    });
  }

  /** Resolves with the provider's global object once its render() is usable. */
  waitForProvider() {
    const provider = this.config.provider === "turnstile" ? "turnstile" : "grecaptcha";
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const tick = () => {
        const api_ = window[provider];
        if (api_ && typeof api_.render === "function") return resolve(api_);
        if (api_ && typeof api_.ready === "function") {
          api_.ready(() => resolve(window[provider]));
          return;
        }
        if (Date.now() - started > 8000) return reject(new Error("Security check did not load."));
        setTimeout(tick, 100);
      };
      tick();
    });
  }

  /**
   * Draws the CAPTCHA checkbox inside `container` (used by the login / sign-up forms).
   * Resolves {enabled:false} when no CAPTCHA keys are configured.
   */
  async mountWidget(container, { onToken, onExpire, onError } = {}) {
    if (!this.config) this.config = await api.getCaptchaConfig();
    if (!this.config.enabled) return { enabled: false, reset() {} };
    await this.loadScript(this.config.script_url);
    const provider = await this.waitForProvider();
    const globalName = this.config.provider === "turnstile" ? "turnstile" : "grecaptcha";
    const widgetId = provider.render(container, {
      sitekey: this.config.site_key,
      callback: (token) => onToken && onToken(token),
      "expired-callback": () => onExpire && onExpire(),
      "error-callback": () => onError && onError()
    });
    return {
      enabled: true,
      reset() {
        try { window[globalName].reset(widgetId); } catch (_) {}
      }
    };
  }

  renderVerificationModal() {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay open";
    overlay.id = OVERLAY_ID;
    overlay.style.zIndex = "1000";

    overlay.innerHTML = `
      <div class="modal-dialog" style="max-width:440px;">
       <div class="modal-body" style="text-align:center;padding:28px 24px;">
        <div style="margin-bottom:14px;color:var(--color-primary);">
          <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        </div>
        <h3 style="margin-bottom:8px;">Security Verification</h3>
        <p style="font-size:0.9rem;color:var(--color-text-secondary);margin-bottom:16px;">
          Please confirm you are human to use Smart Local Guide.
        </p>
        <div id="captchaWidgetContainer" style="display:flex;justify-content:center;margin-bottom:12px;min-height:78px;"></div>
        <p id="captchaMessage" role="alert" style="font-size:0.85rem;color:var(--color-danger, #B91C1C);min-height:1.2em;margin-bottom:10px;"></p>
        <button id="btnVerifyCaptcha" class="btn btn-primary" style="width:100%;" disabled>
          Verify Session
        </button>
       </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const btn = overlay.querySelector("#btnVerifyCaptcha");
    const msg = overlay.querySelector("#captchaMessage");
    const container = overlay.querySelector("#captchaWidgetContainer");
    this.token = null;
    this.widgetId = null;

    const provider = this.config.provider === "turnstile" ? "turnstile" : "grecaptcha";

    this.loadScript(this.config.script_url)
      .then(() => this.waitForProvider())
      .then((p) => {
        this.widgetId = p.render(container, {
          sitekey: this.config.site_key,
          callback: (token) => {
            this.token = token;
            msg.textContent = "";
            btn.disabled = false;
          },
          "expired-callback": () => {
            this.token = null;
            btn.disabled = true;
          },
          "error-callback": () => {
            this.token = null;
            btn.disabled = true;
            msg.textContent = "The security check hit an error. Please try again.";
          }
        });
      })
      .catch((err) => {
        msg.textContent = err.message;
      });

    btn.addEventListener("click", async () => {
      if (!this.token) return;
      btn.disabled = true;
      btn.textContent = "Verifying…";
      try {
        await api.verifyCaptcha(this.token);
        this.markVerified();
        overlay.remove();
        toast.success("Security verification completed.");
      } catch (err) {
        msg.textContent = err.message || "Verification failed. Please try again.";
        btn.textContent = "Verify Session";
        this.token = null;
        // A token can only be used once: reset the widget for a fresh attempt
        try {
          const p = window[provider];
          if (p && typeof p.reset === "function") p.reset(this.widgetId);
        } catch (_) {}
      }
    });
  }
}

export const captchaManager = new CaptchaManager();
