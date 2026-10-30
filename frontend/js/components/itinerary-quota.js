/**
 * Monthly itinerary allowance note.
 *
 * Shows a logged-in person how many itineraries they may generate this month and how many are left.
 * The number comes from the admin's setting, so it always matches what the server enforces.
 *  - Normal account with a limit  -> "You can generate N itineraries per month · X left"
 *  - Admin account                -> "Admin account: no limit on itineraries"
 *  - No limit set / guest / not logged in -> nothing is shown
 *
 * Every page that has <div data-itinerary-quota></div> gets the note. It refreshes itself after an
 * itinerary is generated (event "slg:quota-changed").
 */

import { api } from "../api.js";
import { authManager } from "./auth.js";
import { escapeHtml } from "../utils/formatters.js";

function render(box, q) {
  if (!q || q.guest) { box.hidden = true; return; }
  if (q.is_admin) {
    box.className = "quota-note quota-admin";
    box.innerHTML = `<span class="quota-icon" aria-hidden="true">🛡️</span><span><strong>Admin account:</strong> no limit on itineraries.</span>`;
    box.hidden = false;
    return;
  }
  if (q.unlimited) { box.hidden = true; return; }

  const plural = q.limit === 1 ? "itinerary" : "itineraries";
  const out = q.remaining <= 0;
  const left = out
    ? `You have used them all. The limit resets on <strong>${escapeHtml(q.resets_on_text || "the 1st")}</strong>.`
    : `<strong>${q.remaining}</strong> of ${q.limit} left this month.`;
  box.className = `quota-note ${out ? "quota-out" : q.remaining === 1 ? "quota-low" : ""}`.trim();
  box.innerHTML = `
    <span class="quota-icon" aria-hidden="true">${out ? "⛔" : "🗓️"}</span>
    <span>You can generate <strong>${q.limit}</strong> ${plural} per month. ${left}</span>`;
  box.hidden = false;
}

async function refresh() {
  const boxes = document.querySelectorAll("[data-itinerary-quota]");
  if (!boxes.length) return;
  if (!authManager.isLoggedIn()) { boxes.forEach(b => { b.hidden = true; }); return; }
  try {
    const q = await api.getItineraryQuota();
    boxes.forEach(b => render(b, q));
  } catch (_) {
    boxes.forEach(b => { b.hidden = true; });          // never break a page because of this note
  }
}

export function initItineraryQuota() {
  if (!document.querySelector("[data-itinerary-quota]")) return;
  if (authManager.ready) refresh();
  else window.addEventListener("slg:auth-ready", refresh, { once: true });
  window.addEventListener("slg:quota-changed", refresh);
}
