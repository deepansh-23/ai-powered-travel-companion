/**
 * "Save session": keep a half-finished page (an itinerary in step 3, a search...) in the
 * user's account and resume it later, even after logging out and back in.
 *
 * Saved sessions are different from History: History keeps FINISHED results automatically,
 * a saved session keeps work in progress when the user presses "Save session".
 */

import { api } from "../api.js";
import { authManager } from "./auth.js";
import { toast } from "./toast.js";
import { escapeHtml, formatDateTime } from "../utils/formatters.js";

export const SERVICES = {
  itinerary: { label: "Itinerary Planner", page: "itinerary.html", key: "slg_session_itinerary" },
  area: { label: "Area Guide", page: "area.html", key: "slg_area_state" },
  places: { label: "Places Near You", page: "places.html", key: "slg_places_state" },
  cafes: { label: "Quiet Work Cafés", page: "cafes.html", key: "slg_cafes_state" },
  medical: { label: "24/7 Medical Care", page: "medical.html", key: "slg_medical_state" }
};

const draftKey = (service) => `slg_draft_id_${service}`;
const inPages = () => location.pathname.includes("/pages/");

/** Next "Save session" on this page should start a NEW draft (e.g. after Generate New). */
export function forgetDraft(service) {
  sessionStorage.removeItem(draftKey(service));
}

/** Load a saved session into the browser and open its page. */
export async function resumeSession(id) {
  const full = await api.getSession(id);
  const svc = SERVICES[full.service];
  if (!svc) throw new Error("Unknown service in saved session.");
  sessionStorage.setItem(svc.key, JSON.stringify(full.state));
  sessionStorage.setItem(draftKey(full.service), full.id); // further saves update this draft
  const target = (inPages() ? "" : "pages/") + svc.page;
  if (location.pathname.endsWith(svc.page)) location.reload();
  else window.location.href = target;
}

/** Draw a list of saved sessions with Resume / Delete buttons. */
export function renderSessionsList(container, sessions, { showService = false, onChange } = {}) {
  if (!sessions.length) {
    container.innerHTML = `<p class="text-muted">No saved sessions yet. Press "Save session" while you are in the middle of something.</p>`;
    return;
  }
  container.innerHTML = sessions.map(s => `
    <div class="draft-row" data-id="${escapeHtml(s.id)}">
      <div class="draft-info">
        ${showService ? `<span class="badge badge-primary">${escapeHtml((SERVICES[s.service] || {}).label || s.service)}</span>` : ""}
        <strong>${escapeHtml(s.title)}</strong>
        <div class="text-muted draft-meta">Saved ${escapeHtml(formatDateTime(s.updated_at))}</div>
      </div>
      <div class="draft-actions">
        <button type="button" class="btn btn-primary btn-sm" data-act="resume">Resume</button>
        <button type="button" class="btn btn-secondary btn-sm" data-act="delete">Delete</button>
      </div>
    </div>`).join("");

  container.querySelectorAll(".draft-row").forEach(row => {
    const id = row.dataset.id;
    row.querySelector('[data-act="resume"]').addEventListener("click", async (e) => {
      e.target.disabled = true;
      try { await resumeSession(id); } catch (err) { toast.error(err.message); e.target.disabled = false; }
    });
    row.querySelector('[data-act="delete"]').addEventListener("click", async () => {
      if (!window.confirm("Delete this saved session?")) return;
      try {
        await api.deleteSession(id);
        row.remove();
        if (onChange) onChange();
      } catch (err) {
        toast.error(err.message);
      }
    });
  });
}

/**
 * Wire one page: the "Save session" button and the "you have saved sessions" banner.
 *  buildSave() -> { hasContent, title, state }
 *  hasActiveState() -> true when the page already shows work (then no banner is needed)
 */
export function initSavedSessions({ service, saveButtonId, hasActiveState, buildSave }) {
  const button = document.getElementById(saveButtonId);

  if (button) {
    button.addEventListener("click", async () => {
      if (authManager.isGuest()) {
        toast.info("Saving sessions needs a free account (not available in guest mode). Log in to save your work.");
        return;
      }
      if (!authManager.isLoggedIn()) {
        toast.info("Please log in to save your session.");
        setTimeout(() => authManager.goToLogin(), 700);
        return;
      }
      const draft = buildSave();
      if (!draft.hasContent) {
        toast.info("Nothing to save yet. Fill in or search something first.");
        return;
      }
      button.disabled = true;
      try {
        const saved = await api.saveSession({
          id: sessionStorage.getItem(draftKey(service)) || null,
          service,
          title: draft.title,
          state: draft.state
        });
        sessionStorage.setItem(draftKey(service), saved.id);
        toast.success("Session saved. Find it under History → Saved sessions, or resume it from this page.");
      } catch (err) {
        toast.error(err.message);
      } finally {
        button.disabled = false;
      }
    });
  }

  async function showBanner() {
    if (!authManager.isLoggedIn() || hasActiveState()) return;
    try {
      const sessions = await api.listSessions(service);
      if (!sessions || !sessions.length) return;
      let box = document.getElementById("draftBanner");
      if (!box) {
        box = document.createElement("section");
        box.id = "draftBanner";
        box.className = "draft-banner";
        const header = document.querySelector(".main-content .page-header");
        if (header) header.insertAdjacentElement("afterend", box);
        else document.querySelector(".main-content").prepend(box);
      }
      box.innerHTML = `<h2 class="draft-banner-title">Continue where you left off</h2><div id="draftBannerList"></div>`;
      renderSessionsList(box.querySelector("#draftBannerList"), sessions.slice(0, 3), {
        onChange: () => { if (!box.querySelector(".draft-row")) box.remove(); }
      });
    } catch (_) {}
  }

  if (authManager.ready) showBanner();
  else window.addEventListener("slg:auth-ready", showBanner, { once: true });
}
