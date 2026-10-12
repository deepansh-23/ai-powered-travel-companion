/**
 * Login state for every page: navbar "Log in / username + Log out", protected pages
 * (<body data-requires-login>) and what happens when the session ends.
 *
 * The session itself is an HttpOnly cookie set by the server: JavaScript never sees
 * the password or the session token.
 */

import { api } from "../api.js";
import { toast } from "./toast.js";
import { escapeHtml } from "../utils/formatters.js";

const inPages = () => location.pathname.includes("/pages/");
const pagePath = (file) => (inPages() ? file : `pages/${file}`);
const homePath = () => (inPages() ? "../index.html" : "index.html");

class AuthManager {
  constructor() {
    this.user = null;
    this.accountsAvailable = true;
    this.ready = false;
    window.addEventListener("slg:login-required", () => this.handleLoginRequired());
  }

  isLoggedIn() {
    return this.user !== null;
  }

  loginUrl(next) {
    const target = next || location.pathname + location.search;
    return `${pagePath("login.html")}?next=${encodeURIComponent(target)}`;
  }

  goToLogin(next) {
    window.location.href = this.loginUrl(next);
  }

  handleLoginRequired() {
    this.user = null;
    window.__slgLoggedIn = false;
    toast.error("Please log in to continue.");
    this.renderNav();
    if (!location.pathname.endsWith("login.html")) {
      setTimeout(() => this.goToLogin(), 600);
    }
  }

  /** Ask the server who is logged in, draw the navbar, protect gated pages. */
  async init() {
    try {
      const me = await api.getMe();
      this.user = me.authenticated ? me.user : null;
      this.accountsAvailable = me.accounts_available !== false;
    } catch (_) {
      this.user = null;
    }
    window.__slgLoggedIn = this.user !== null;
    this.ready = true;
    this.renderNav();

    const gated = document.body.hasAttribute("data-requires-login");
    if (gated && !this.user) {
      this.goToLogin(); // page stays hidden until we know the visitor may see it
      return false;
    }
    document.body.classList.add("auth-ready");
    window.dispatchEvent(new CustomEvent("slg:auth-ready", { detail: { user: this.user } }));
    return true;
  }

  async logout() {
    try {
      await api.logout();
    } catch (_) {}
    // Nothing of this user may stay in the browser for the next person
    Object.keys(sessionStorage).filter((k) => k.startsWith("slg_")).forEach((k) => sessionStorage.removeItem(k));
    window.location.href = homePath();
  }

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
        box.innerHTML = `
          <span class="auth-user" title="Logged in as ${escapeHtml(this.user.username)}">👤 ${escapeHtml(this.user.username)}</span>
          <button type="button" class="btn btn-secondary btn-sm" id="btnLogout">Log out</button>`;
        box.querySelector("#btnLogout").addEventListener("click", () => this.logout());
      } else {
        box.innerHTML = `<a class="btn btn-primary btn-sm" href="${this.loginUrl()}">Log in</a>`;
      }
    }

    const drawer = document.getElementById("mobileDrawer");
    if (drawer) {
      let item = document.getElementById("drawerAuth");
      if (!item) {
        item = document.createElement("a");
        item.id = "drawerAuth";
        item.className = "nav-link";
        drawer.appendChild(item);
      }
      if (this.user) {
        item.textContent = `Log out (${this.user.username})`;
        item.href = "#";
        item.onclick = (e) => { e.preventDefault(); this.logout(); };
      } else {
        item.textContent = "Log in / Create account";
        item.href = this.loginUrl();
        item.onclick = null;
      }
    }
  }
}

export const authManager = new AuthManager();
