/**
 * Guest sessions do not keep History. After a guest gets results, this shows a clear warning with
 * a Log in button. The results already live in this tab's session storage, so after logging in the
 * page restores them as they were, and they are then saved to History once.
 */

import { api } from "../api.js";
import { authManager } from "./auth.js";
import { escapeHtml } from "../utils/formatters.js";
import { toast } from "./toast.js";

const unsavedKey = (pageKey) => `slg_${pageKey}_guest_unsaved`;

/** Call after a successful search/guide. Shows the warning for guests, does nothing for members. */
export function noteGuestResult(pageKey, anchorEl) {
  if (!authManager.isGuest()) return;
  try { sessionStorage.setItem(unsavedKey(pageKey), "1"); } catch (_) {}
  showGuestBanner(anchorEl);
}

export function showGuestBanner(anchorEl) {
  if (!anchorEl || !anchorEl.parentNode) return;
  document.querySelectorAll(".guest-save-banner").forEach((n) => n.remove());
  const el = document.createElement("div");
  el.className = "guest-save-banner";
  el.setAttribute("role", "status");
  el.innerHTML = `
    <span class="guest-save-icon" aria-hidden="true">⚠️</span>
    <span class="guest-save-text"><b>Guest session:</b> this result is not saved to History and cannot be viewed later.
      Log in to keep it. Your results will be right here when you come back.</span>
    <a class="btn btn-primary btn-sm" href="${escapeHtml(authManager.loginUrl())}">Log in to save</a>`;
  anchorEl.parentNode.insertBefore(el, anchorEl);
}

/**
 * Run once the page knows who is logged in. If results were made as a guest and the visitor has
 * since logged in, save them to History now. buildItem() returns the history record (or null).
 */
export function saveGuestWorkAfterLogin(pageKey, buildItem) {
  const run = async () => {
    if (!authManager.isLoggedIn()) return;
    let flagged = false;
    try { flagged = sessionStorage.getItem(unsavedKey(pageKey)) === "1"; } catch (_) {}
    if (!flagged) return;
    const item = buildItem();
    try { sessionStorage.removeItem(unsavedKey(pageKey)); } catch (_) {}
    if (!item) return;
    try {
      await api.createHistory(item);
      toast.success("Your results were saved to History.");
    } catch (_) { /* History is a bonus: never block the page */ }
  };
  if (authManager.ready) run();
  else window.addEventListener("slg:auth-ready", run, { once: true });
}
