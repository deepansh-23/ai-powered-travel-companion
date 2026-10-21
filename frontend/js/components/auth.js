/**
 * Login state for every page: the welcome screen (Log in / Continue as guest), the navbar
 * account menu, protected pages and what happens when the session ends.
 *
 * Two kinds of visitor can use the planning tools:
 *   - a logged-in user (history, saved sessions, reviews and their account work), and
 *   - a guest (planner, places, cafés, medical and area guide work; nothing is saved).
 *
 * The session itself is an HttpOnly cookie set by the server: JavaScript never sees
 * the password or the session token.
 */

import { api } from "../api.js";
import { toast } from "./toast.js";
import { modal } from "./modal.js";
import { captchaManager } from "./captcha.js";
import { escapeHtml } from "../utils/formatters.js";

const inPages = () => location.pathname.includes("/pages/");
const pagePath = (file) => (inPages() ? file : `pages/${file}`);
const homePath = () => (inPages() ? "../index.html" : "index.html");

export const APP_NAME = "AI Powered Travel Companion";
export const APP_TAGLINE = "Explore Your City with Intelligence and Ease";

export const GUEST_LIMITS_NOTE =
  "As a guest you can search places, cafés and medical care, and use the Area Guide. " +
  "Not available as a guest: the Itinerary Planner, saved History and sessions, and posting reviews (nothing is stored).";

class AuthManager {
  constructor() {
    this.user = null;
    this.guest = false;
    this.accountsAvailable = true;
    this.ready = false;
    window.addEventListener("slg:login-required", () => this.handleLoginRequired());
  }

  isLoggedIn() {
    return this.user !== null;
  }

  isGuest() {
    return this.user === null && this.guest;
  }

  loginUrl(next) {
    const target = next || location.pathname + location.search;
    return `${pagePath("login.html")}?next=${encodeURIComponent(target)}`;
  }

  goToLogin(next) {
    window.location.href = this.loginUrl(next);
  }

  /** The server said "not logged in": show the right screen, without reloading the page. */
  handleLoginRequired() {
    const wasGuest = this.guest;
    this.user = null;
    this.guest = false;
    window.__slgLoggedIn = false;
    this.renderNav();
    if (location.pathname.endsWith("login.html")) return;
    if (document.body.hasAttribute("data-requires-login")) {
      this.showAccountRequired();
    } else if (!wasGuest) {
      this.showWelcomeScreen(); // the session ended: choose Log in or guest again
    }
    const now = Date.now();
    if (!this._loginToastAt || now - this._loginToastAt > 4000) {
      this._loginToastAt = now;
      toast.info(wasGuest ? "That needs a free account. Please log in." : "Please log in or continue as a guest.");
    }
  }

  /** Friendly "this page needs an account" card in place of the page content (History, Itinerary Planner). */
  showAccountRequired() {
    const main = document.querySelector("main.main-content") || document.querySelector("main");
    if (!main) return;
    const feature = document.body.dataset.feature || "This page";
    const guestLine = this.guest
      ? "You are in a guest session. Guests can still search places, cafés and medical care, and use the Area Guide."
      : "It only takes a minute to create a free account.";
    main.innerHTML = `
      <div class="account-required">
        <div class="account-required-icon" aria-hidden="true">🔒</div>
        <h1>${escapeHtml(feature)} is for members</h1>
        <p>Log in or create a free account to use ${escapeHtml(feature)}. ${escapeHtml(guestLine)}</p>
        <div class="account-required-actions">
          <a class="btn btn-primary" href="${this.loginUrl()}">Log in</a>
          <a class="btn btn-secondary" href="${pagePath("login.html")}?tab=register&next=${encodeURIComponent(location.pathname + location.search)}">Create a free account</a>
          <a class="btn btn-secondary" href="${homePath()}">Back to home</a>
        </div>
      </div>`;
    document.body.classList.add("auth-ready"); // the page content is now this card, so show it
  }

  /** Ask the server who is here, draw the navbar, show the welcome screen, protect gated pages. */
  async init() {
    try {
      const me = await api.getMe();
      this.user = me.authenticated ? me.user : null;
      this.guest = !!me.guest && !this.user;
      this.accountsAvailable = me.accounts_available !== false;
    } catch (_) {
      this.user = null;
      this.guest = false;
    }
    window.__slgLoggedIn = this.user !== null;
    window.__slgGuest = this.isGuest();
    this.ready = true;
    this.renderNav();

    const onLoginPage = location.pathname.endsWith("login.html");
    const hasSession = this.user !== null || this.guest;

    // First visit (no login, no guest choice): centred welcome screen, nothing else usable
    if (!hasSession && !onLoginPage) {
      this.showWelcomeScreen();
      return false;
    }

    // History and the Itinerary Planner need a real account (guests see a friendly card, no redirect loop)
    if (document.body.hasAttribute("data-requires-login") && !this.user) {
      this.showAccountRequired();
      return false;
    }

    document.body.classList.add("auth-ready");
    window.dispatchEvent(new CustomEvent("slg:auth-ready", { detail: { user: this.user, guest: this.isGuest() } }));
    return true;
  }

  // ------------------------------------------------------------------ welcome screen
  showWelcomeScreen() {
    if (document.getElementById("welcomeGate")) return;
    document.body.classList.add("welcome-open");
    const gate = document.createElement("div");
    gate.id = "welcomeGate";
    gate.className = "welcome-gate";
    gate.setAttribute("role", "dialog");
    gate.setAttribute("aria-modal", "true");
    gate.setAttribute("aria-labelledby", "welcomeTitle");
    gate.innerHTML = `
      <div class="welcome-card">
        <div class="welcome-logo" aria-hidden="true">🧭</div>
        <h1 id="welcomeTitle" class="welcome-title">${escapeHtml(APP_NAME)}</h1>
        <p class="welcome-tagline">${escapeHtml(APP_TAGLINE)}</p>

        <div class="welcome-actions">
          <a class="btn btn-primary welcome-btn" id="welcomeLogin" href="${this.loginUrl()}">Log in</a>
          <button type="button" class="btn btn-secondary welcome-btn" id="welcomeGuest">Continue as guest</button>
        </div>
        <div class="welcome-captcha" id="welcomeCaptcha"></div>
        <div class="welcome-error" id="welcomeError" role="alert" hidden></div>

        <p class="welcome-create">New here? <a href="${pagePath("login.html")}?tab=register&next=${encodeURIComponent(location.pathname + location.search)}">Create a free account</a></p>

        <div style="margin-top:12px;padding-top:10px;border-top:1px dashed var(--color-border,#e5e7eb);text-align:center;">
          <button type="button" class="btn-link" id="welcomeAdminLogin" style="background:none;border:none;color:var(--color-text-muted,#6b7280);font-size:0.84rem;cursor:pointer;padding:4px 8px;border-radius:4px;display:inline-flex;align-items:center;gap:5px;">
            <span aria-hidden="true">🛡️</span> Admin Login
          </button>
        </div>

        <div class="welcome-note" id="welcomeNote">
          <strong>Guest session</strong>
          <span>${escapeHtml(GUEST_LIMITS_NOTE)}</span>
        </div>
      </div>`;
    document.body.appendChild(gate);

    const guestBtn = gate.querySelector("#welcomeGuest");
    const adminLoginBtn = gate.querySelector("#welcomeAdminLogin");
    const errorBox = gate.querySelector("#welcomeError");
    const showError = (text) => { errorBox.textContent = text || ""; errorBox.hidden = !text; };
    let captchaToken = null;
    let widget = null;

    if (adminLoginBtn) {
      adminLoginBtn.addEventListener("click", () => this.openAdminLoginDialog());
    }

    captchaManager.mountWidget(gate.querySelector("#welcomeCaptcha"), {
      onToken: (t) => { captchaToken = t; },
      onExpire: () => { captchaToken = null; },
      onError: () => showError("The security check had a problem. Please reload the page.")
    }).then((w) => { widget = w; }).catch((err) => showError(err.message));

    guestBtn.addEventListener("click", async () => {
      showError("");
      if (widget && widget.enabled && !captchaToken) {
        showError("Please tick the 'I'm not a robot' box first.");
        return;
      }
      guestBtn.disabled = true;
      guestBtn.textContent = "Starting…";
      try {
        await api.startGuest(captchaToken);
        window.location.reload(); // the page now loads as a guest
      } catch (err) {
        showError(err.message);
        if (widget) { captchaToken = null; widget.reset(); }
        guestBtn.disabled = false;
        guestBtn.textContent = "Continue as guest";
      }
    });
    gate.querySelector("#welcomeLogin").focus();
  }

  // ------------------------------------------------------------------ dedicated admin login
  openAdminLoginDialog() {
    modal.open({
      title: "Administrator Portal",
      bodyHtml: `
        <div class="adm-login-portal">
          <p style="margin-top:0;margin-bottom:14px;color:var(--color-text-muted,#6b7280);font-size:0.88rem;">
            Access restricted to authorized platform administrators.
          </p>

          <!-- Step 1: Username -->
          <div id="admStep1">
            <div class="form-group" style="margin-bottom:12px;">
              <label class="form-label" for="admUsername">Username</label>
              <input class="form-input" id="admUsername" type="text" autocomplete="username" maxlength="100" placeholder="Enter administrator username">
            </div>
            <div class="auth-message error" id="admError1" role="alert" style="margin-top:8px;" hidden></div>
            <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px;">
              <button type="button" class="btn btn-secondary btn-sm btn-close-modal">Cancel</button>
              <button type="button" class="btn btn-primary btn-sm" id="btnAdmNext">Next &rarr;</button>
            </div>
          </div>

          <!-- Step 2: Password & CAPTCHA (secure verification) -->
          <div id="admStep2" hidden>
            <div class="form-group" style="margin-bottom:12px;">
              <label class="form-label" for="admPassword">Password</label>
              <input class="form-input" id="admPassword" type="password" autocomplete="current-password" maxlength="128" placeholder="Enter administrator password">
            </div>
            <div style="margin:12px 0;" id="admCaptchaContainer"></div>
            <div class="auth-message error" id="admError2" role="alert" style="margin-top:8px;" hidden></div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px;">
              <button type="button" class="btn btn-secondary btn-sm" id="btnAdmBack">&larr; Back</button>
              <button type="button" class="btn btn-primary btn-sm" id="btnAdmSubmit">Authenticate</button>
            </div>
          </div>
        </div>`,
      footerHtml: ``
    });

    const step1 = document.getElementById("admStep1");
    const step2 = document.getElementById("admStep2");
    const uInput = document.getElementById("admUsername");
    const pInput = document.getElementById("admPassword");
    const err1 = document.getElementById("admError1");
    const err2 = document.getElementById("admError2");
    const nextBtn = document.getElementById("btnAdmNext");
    const backBtn = document.getElementById("btnAdmBack");
    const submitBtn = document.getElementById("btnAdmSubmit");
    const captchaContainer = document.getElementById("admCaptchaContainer");

    if (uInput) uInput.focus();

    let captchaToken = null;
    let widget = null;

    const showErr1 = (m) => { err1.textContent = m || ""; err1.hidden = !m; };
    const showErr2 = (m) => { err2.textContent = m || ""; err2.hidden = !m; };

    const goToStep2 = () => {
      const uname = (uInput.value || "").trim();
      if (!uname) {
        showErr1("Please enter your administrator username.");
        return;
      }
      showErr1("");
      step1.hidden = true;
      step2.hidden = false;
      if (pInput) pInput.focus();

      if (!widget && captchaContainer) {
        captchaManager.mountWidget(captchaContainer, {
          onToken: (t) => { captchaToken = t; },
          onExpire: () => { captchaToken = null; },
          onError: () => showErr2("Security check failed to initialize.")
        }).then((w) => { widget = w; }).catch((err) => showErr2(err.message));
      }
    };

    if (nextBtn) nextBtn.addEventListener("click", goToStep2);
    if (uInput) uInput.addEventListener("keydown", (e) => { if (e.key === "Enter") goToStep2(); });

    if (backBtn) {
      backBtn.addEventListener("click", () => {
        showErr2("");
        step2.hidden = true;
        step1.hidden = false;
        if (uInput) uInput.focus();
      });
    }

    const doSubmit = async () => {
      const uname = (uInput.value || "").trim();
      const pwd = pInput.value || "";
      if (!pwd) {
        showErr2("Please enter your password.");
        return;
      }
      if (widget && widget.enabled && !captchaToken) {
        showErr2("Please complete the security check.");
        return;
      }
      showErr2("");
      submitBtn.disabled = true;
      submitBtn.textContent = "Verifying…";

      try {
        await api.adminLogin(uname, pwd, captchaToken);
        modal.close();
        toast.success("Administrator authenticated. Entering dashboard…");
        setTimeout(() => { window.location.href = "/admin/"; }, 400);
      } catch (err) {
        showErr2(err.message || "Invalid administrator credentials.");
        submitBtn.disabled = false;
        submitBtn.textContent = "Authenticate";
        if (widget) {
          captchaToken = null;
          widget.reset();
        }
      }
    };

    if (submitBtn) submitBtn.addEventListener("click", doSubmit);
    if (pInput) pInput.addEventListener("keydown", (e) => { if (e.key === "Enter") doSubmit(); });
  }

  // ------------------------------------------------------------------ logout / delete account
  async logout() {
    try {
      await api.logout();
    } catch (_) {}
    // Nothing of this user may stay in the browser for the next person
    Object.keys(sessionStorage).filter((k) => k.startsWith("slg_")).forEach((k) => sessionStorage.removeItem(k));
    window.location.href = homePath();
  }

  openDeleteAccountDialog() {
    modal.open({
      title: "Delete your account",
      bodyHtml: `
        <p><strong>This cannot be undone.</strong> Deleting your account permanently removes your login,
        your History, and your saved sessions. Reviews you wrote stay on the Reviews page but are no longer linked to you.</p>
        <div class="form-group" style="margin-top:12px;">
          <label class="form-label" for="deleteAccountPassword">Enter your password to confirm</label>
          <input class="form-input" id="deleteAccountPassword" type="password" autocomplete="current-password" maxlength="128">
        </div>
        <div class="auth-message" id="deleteAccountMessage" role="alert" aria-live="polite"></div>`,
      footerHtml: `
        <button type="button" class="btn btn-secondary btn-sm btn-close-modal">Cancel</button>
        <button type="button" class="btn btn-danger btn-sm" id="btnConfirmDelete">Delete my account</button>`
    });
    const input = document.getElementById("deleteAccountPassword");
    const msg = document.getElementById("deleteAccountMessage");
    const confirmBtn = document.getElementById("btnConfirmDelete");
    if (input) input.focus();
    const run = async () => {
      if (!input.value) {
        msg.className = "auth-message error";
        msg.textContent = "Enter your password to confirm.";
        return;
      }
      confirmBtn.disabled = true;
      confirmBtn.textContent = "Deleting…";
      try {
        await api.deleteAccount(input.value);
        Object.keys(sessionStorage).filter((k) => k.startsWith("slg_")).forEach((k) => sessionStorage.removeItem(k));
        modal.close();
        toast.success("Your account has been deleted.");
        setTimeout(() => { window.location.href = homePath(); }, 900);
      } catch (err) {
        msg.className = "auth-message error";
        msg.textContent = err.message;
        input.value = "";
        confirmBtn.disabled = false;
        confirmBtn.textContent = "Delete my account";
      }
    };
    confirmBtn.addEventListener("click", run);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
  }

  // ------------------------------------------------------------------ navbar
  renderNav() {
    const actions = document.querySelector(".navbar-actions");
    if (actions) {
      let box = document.getElementById("authNav");
      if (!box) {
        box = document.createElement("div");
        box.id = "authNav";
        box.className = "auth-nav";
        actions.prepend(box);
      }
      if (this.user) {
        const adminItemHtml = this.user.is_admin === true
          ? `<a href="/admin/" class="auth-menu-item" role="menuitem" id="btnAdminDashboard" style="font-weight:600;color:var(--color-primary,#2563eb);display:flex;align-items:center;gap:6px;"><span>🛡️</span> Admin Dashboard</a>`
          : ``;
        box.innerHTML = `
          <div class="auth-menu">
            <button type="button" class="btn btn-secondary btn-sm auth-menu-btn" id="authMenuBtn" aria-haspopup="true" aria-expanded="false" title="Logged in as ${escapeHtml(this.user.username)}">
              <span class="auth-user">👤 ${escapeHtml(this.user.username)}</span><span class="auth-user-short" aria-hidden="true">👤</span> ▾
            </button>
            <div class="auth-menu-list" id="authMenuList" role="menu" hidden>
              ${adminItemHtml}
              <button type="button" class="auth-menu-item" role="menuitem" id="btnLogout">Log out</button>
              <button type="button" class="auth-menu-item danger" role="menuitem" id="btnDeleteAccount">Delete account</button>
            </div>
          </div>`;
        const menuBtn = box.querySelector("#authMenuBtn");
        const list = box.querySelector("#authMenuList");
        menuBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          list.hidden = !list.hidden;
          menuBtn.setAttribute("aria-expanded", String(!list.hidden));
        });
        document.addEventListener("click", () => { list.hidden = true; menuBtn.setAttribute("aria-expanded", "false"); });
        box.querySelector("#btnLogout").addEventListener("click", () => this.logout());
        box.querySelector("#btnDeleteAccount").addEventListener("click", () => { list.hidden = true; this.openDeleteAccountDialog(); });
      } else if (this.guest) {
        box.innerHTML = `
          <span class="badge badge-secondary guest-badge" title="${escapeHtml(GUEST_LIMITS_NOTE)}">Guest</span>
          <a class="btn btn-primary btn-sm" href="${this.loginUrl()}">Log in</a>
          <button type="button" class="btn btn-secondary btn-sm" id="btnEndGuest">End guest session</button>`;
        box.querySelector("#btnEndGuest").addEventListener("click", () => this.logout());
      } else {
        box.innerHTML = `<a class="btn btn-primary btn-sm" href="${this.loginUrl()}">Log in</a>`;
      }
    }

    const drawer = document.getElementById("mobileDrawer");
    if (drawer) {
      ["drawerAdmin", "drawerAuth", "drawerDelete"].forEach((id) => { const el = document.getElementById(id); if (el) el.remove(); });
      const add = (id, text, href, onclick) => {
        const a = document.createElement("a");
        a.id = id;
        a.className = "nav-link";
        a.textContent = text;
        a.href = href;
        if (onclick) a.onclick = (e) => { e.preventDefault(); onclick(); };
        drawer.appendChild(a);
      };
      if (this.user) {
        if (this.user.is_admin === true) {
          add("drawerAdmin", "🛡️ Admin Dashboard", "/admin/");
        }
        add("drawerAuth", `Log out (${this.user.username})`, "#", () => this.logout());
        add("drawerDelete", "Delete account", "#", () => this.openDeleteAccountDialog());
      } else if (this.guest) {
        add("drawerAuth", "Log in (leave guest mode)", this.loginUrl());
        add("drawerDelete", "End guest session", "#", () => this.logout());
      } else {
        add("drawerAuth", "Log in / Create account", this.loginUrl());
      }
    }
  }
}

export const authManager = new AuthManager();
