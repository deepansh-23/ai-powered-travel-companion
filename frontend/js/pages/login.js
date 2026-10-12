/**
 * Login page: Log in, Create account, Forgot password (recovery code).
 * The CAPTCHA checkbox (when configured) is verified by the server on every attempt.
 */

import { api } from "../api.js";
import { authManager } from "../components/auth.js";
import { captchaManager } from "../components/captcha.js";
import { toast } from "../components/toast.js";

const $ = (id) => document.getElementById(id);

// Only ever return to a page on this site (prevents "open redirect" links)
function safeNext() {
  const raw = new URLSearchParams(location.search).get("next") || "";
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) {
    return "../index.html";
  }
  return raw;
}

const message = $("authMessage");
function showMessage(text, kind = "error") {
  message.textContent = text || "";
  message.className = `auth-message ${text ? kind : ""}`;
}

const PANELS = ["panelLogin", "panelRegister", "panelRecover", "panelRecoveryCode"];
const captchaState = {}; // panelId -> { widget, token }

function showPanel(id) {
  PANELS.forEach((p) => { $(p).hidden = p !== id; });
  $("tabLogin").classList.toggle("active", id === "panelLogin");
  $("tabRegister").classList.toggle("active", id === "panelRegister");
  $("tabLogin").setAttribute("aria-selected", String(id === "panelLogin"));
  $("tabRegister").setAttribute("aria-selected", String(id === "panelRegister"));
  document.querySelector(".auth-tabs").hidden = id === "panelRecoveryCode" || id === "panelRecover";
  showMessage("");
  mountCaptcha(id);
}

const CAPTCHA_BOX = { panelLogin: "captchaLogin", panelRegister: "captchaRegister", panelRecover: "captchaRecover" };

async function mountCaptcha(panelId) {
  const boxId = CAPTCHA_BOX[panelId];
  if (!boxId || captchaState[panelId]) return;
  captchaState[panelId] = { token: null, widget: null };
  try {
    captchaState[panelId].widget = await captchaManager.mountWidget($(boxId), {
      onToken: (t) => { captchaState[panelId].token = t; },
      onExpire: () => { captchaState[panelId].token = null; },
      onError: () => showMessage("The security check had a problem. Please reload the page and try again.")
    });
  } catch (err) {
    showMessage(err.message || "The security check could not load.");
  }
}

function captchaTokenFor(panelId) {
  const st = captchaState[panelId];
  if (st && st.widget && st.widget.enabled && !st.token) {
    showMessage("Please tick the 'I'm not a robot' box first.");
    return { ok: false };
  }
  return { ok: true, token: st ? st.token : null };
}

function resetCaptcha(panelId) {
  const st = captchaState[panelId];
  if (st && st.widget) { st.token = null; st.widget.reset(); }
}

async function withBusy(button, fn) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Please wait…";
  try {
    await fn();
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

// The server has just started a session: reflect that in the navbar right away
function markLoggedIn(user) {
  authManager.user = user;
  window.__slgLoggedIn = true;
  authManager.renderNav();
}

// ---------------------------------------------------------------- recovery code screen
let recoveryCodeShown = null;
let unsavedCodeGuard = null;

function showRecoveryCode(code, username, thenGoTo) {
  recoveryCodeShown = code;
  $("recoveryCodeValue").textContent = code;
  $("chkSavedCode").checked = false;
  $("btnContinue").disabled = true;
  showPanel("panelRecoveryCode");

  unsavedCodeGuard = (e) => { e.preventDefault(); e.returnValue = ""; };
  window.addEventListener("beforeunload", unsavedCodeGuard);

  $("chkSavedCode").onchange = () => { $("btnContinue").disabled = !$("chkSavedCode").checked; };
  $("btnContinue").onclick = () => {
    window.removeEventListener("beforeunload", unsavedCodeGuard);
    window.location.href = thenGoTo;
  };
  $("btnCopyCode").onclick = async () => {
    try {
      await navigator.clipboard.writeText(code);
      toast.success("Recovery code copied.");
    } catch (_) {
      const range = document.createRange();
      range.selectNodeContents($("recoveryCodeValue"));
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      toast.info("Press Ctrl+C to copy the selected code.");
    }
  };
  $("btnDownloadCode").onclick = () => {
    const text = `Smart Local Guide recovery code\nUsername: ${username}\nRecovery code: ${code}\n\nKeep this file private. It is the only way to reset your password.\n`;
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "smart-local-guide-recovery-code.txt";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
}

// ---------------------------------------------------------------- forms
function init() {
  if (authManager.isLoggedIn()) {
    window.location.replace(safeNext());
    return;
  }
  if (!authManager.accountsAvailable) $("authUnavailable").hidden = false;

  $("tabLogin").addEventListener("click", () => showPanel("panelLogin"));
  $("tabRegister").addEventListener("click", () => showPanel("panelRegister"));
  $("linkForgot").addEventListener("click", () => showPanel("panelRecover"));
  $("linkBackToLogin").addEventListener("click", () => showPanel("panelLogin"));

  document.querySelectorAll("[data-toggle-password]").forEach((box) => {
    box.addEventListener("change", () => {
      box.dataset.togglePassword.split(" ").forEach((id) => {
        $(id).type = box.checked ? "text" : "password";
      });
    });
  });

  $("panelLogin").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = $("loginUsername").value.trim();
    const password = $("loginPassword").value;
    if (!username || !password) return showMessage("Enter your username and password.");
    const cap = captchaTokenFor("panelLogin");
    if (!cap.ok) return;
    await withBusy(e.submitter || $("panelLogin").querySelector(".auth-submit"), async () => {
      try {
        await api.login(username, password, cap.token);
        window.location.href = safeNext();
      } catch (err) {
        showMessage(err.message);
        $("loginPassword").value = "";
        resetCaptcha("panelLogin");
      }
    });
  });

  $("panelRegister").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = $("regUsername").value.trim();
    const password = $("regPassword").value;
    if ($("regPassword2").value !== password) return showMessage("The two passwords do not match.");
    const cap = captchaTokenFor("panelRegister");
    if (!cap.ok) return;
    await withBusy(e.submitter || $("panelRegister").querySelector(".auth-submit"), async () => {
      try {
        const res = await api.register(username, password, cap.token);
        $("regPassword").value = $("regPassword2").value = "";
        markLoggedIn(res.user);
        showRecoveryCode(res.recovery_code, res.user.username, safeNext());
      } catch (err) {
        showMessage(err.message);
        resetCaptcha("panelRegister");
      }
    });
  });

  $("panelRecover").addEventListener("submit", async (e) => {
    e.preventDefault();
    const cap = captchaTokenFor("panelRecover");
    if (!cap.ok) return;
    await withBusy(e.submitter || $("panelRecover").querySelector(".auth-submit"), async () => {
      try {
        const res = await api.recoverAccount($("recUsername").value.trim(), $("recCode").value.trim(), $("recPassword").value, cap.token);
        $("recPassword").value = "";
        markLoggedIn(res.user);
        toast.success("Password changed. Here is your NEW recovery code.");
        showRecoveryCode(res.recovery_code, res.user.username, safeNext());
      } catch (err) {
        showMessage(err.message);
        resetCaptcha("panelRecover");
      }
    });
  });

  // Open on "Create account" when linked as login.html?tab=register
  const tab = new URLSearchParams(location.search).get("tab");
  showPanel(tab === "register" ? "panelRegister" : "panelLogin");
}

if (authManager.ready) init();
else window.addEventListener("slg:auth-ready", init, { once: true });
