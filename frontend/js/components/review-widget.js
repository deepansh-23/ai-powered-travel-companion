/**
 * Reviews: floating "Rate us" side tab + quick-review panel, "Rate this service"
 * strips, the Home page top-3 reviews and shared helpers used by the Reviews page.
 *
 * One review can cover several services: it is saved once per selected service
 * (same rating and comment), so it also shows up under each service filter.
 */

import { api } from "../api.js";
import { toast } from "./toast.js";
import { escapeHtml, formatDateTime } from "../utils/formatters.js";
import { authManager } from "./auth.js";

export const REVIEW_SERVICES = [
  "Overall Website",
  "Itinerary Planner",
  "Places Near You",
  "Area Guide",
  "Quiet Work Cafés",
  "24/7 Medical Care"
];

// Reviews of the website as a whole / the main planner (shown on Home)
export const GENERAL_SERVICES = ["Overall Website", "Itinerary Planner", "General Discovery"];

const PAGE_SERVICE = {
  "itinerary.html": "Itinerary Planner",
  "places.html": "Places Near You",
  "area.html": "Area Guide",
  "cafes.html": "Quiet Work Cafés",
  "medical.html": "24/7 Medical Care"
};

export function pageDefaultService() {
  const file = (location.pathname.split("/").pop() || "index.html").toLowerCase();
  return PAGE_SERVICE[file] || "Overall Website";
}

function pagesPrefix() {
  return location.pathname.includes("/pages/") ? "" : "pages/";
}

/** Multi-select service chips. Returns { getSelected, setSelected }. */
export function renderServiceChips(container, selected = []) {
  const chosen = new Set(selected);
  const draw = () => {
    container.innerHTML = REVIEW_SERVICES.map(name => `
      <button type="button" class="review-chip" data-service="${escapeHtml(name)}" aria-pressed="${chosen.has(name)}">
        ${chosen.has(name) ? "✓ " : ""}${escapeHtml(name)}
      </button>`).join("");
  };
  container.addEventListener("click", (e) => {
    const btn = e.target.closest(".review-chip");
    if (!btn) return;
    const name = btn.dataset.service;
    if (chosen.has(name)) chosen.delete(name);
    else chosen.add(name);
    draw();
  });
  draw();
  return {
    getSelected: () => REVIEW_SERVICES.filter(n => chosen.has(n)),
    setSelected: (list) => { chosen.clear(); (list || []).forEach(n => chosen.add(n)); draw(); }
  };
}

/** Star picker: returns { getRating, setRating }. */
export function renderStarPicker(container, initial = 5) {
  let rating = initial;
  const draw = () => {
    container.innerHTML = [1, 2, 3, 4, 5].map(n => `
      <button type="button" class="review-star-btn ${n <= rating ? "on" : ""}" data-star="${n}" aria-label="${n} star${n > 1 ? "s" : ""}" aria-pressed="${n === rating}">★</button>`).join("");
  };
  container.addEventListener("click", (e) => {
    const btn = e.target.closest(".review-star-btn");
    if (!btn) return;
    rating = parseInt(btn.dataset.star, 10);
    draw();
  });
  draw();
  return { getRating: () => rating, setRating: (n) => { rating = n; draw(); } };
}

/** Saves one review for every selected service. Throws a readable Error on failure. */
export async function submitReview({ rating, comment, services }) {
  if (!authManager.isLoggedIn()) throw new Error("Please log in to post a review.");
  if (!services || services.length === 0) throw new Error("Please select at least one service to review.");
  if (!comment || comment.trim().length < 2) throw new Error("Please write a short comment.");
  const saved = await api.submitFeedbackMulti({ rating, comment: comment.trim(), services });
  window.dispatchEvent(new CustomEvent("slg:reviews-updated"));
  return saved;
}

export function starsText(n) {
  return "★".repeat(n) + "☆".repeat(5 - n);
}

// ---------------------------------------------------------------------------
// Floating tab + panel
// ---------------------------------------------------------------------------
let panelApi = null;

function buildPanel() {
  const tab = document.createElement("button");
  tab.type = "button";
  tab.className = "review-tab";
  tab.id = "reviewTab";
  tab.setAttribute("aria-haspopup", "dialog");
  tab.setAttribute("aria-expanded", "false");
  tab.innerHTML = `<span class="review-tab-star" aria-hidden="true">★</span><span>Rate us</span>`;

  const panel = document.createElement("div");
  panel.className = "review-panel";
  panel.id = "reviewPanel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Write a review");
  panel.innerHTML = `
    <div class="review-panel-head">
      <h2>Rate Smart Local Guide</h2>
      <button type="button" class="review-panel-close" aria-label="Close review window">&times;</button>
    </div>
    <div class="review-panel-body" id="rpLoginNote" hidden style="text-align:center;">
      <p>Please log in to write a review. Reading reviews is open to everyone.</p>
      <a class="btn btn-primary" id="rpLoginLink" href="#">Log in or create account</a>
    </div>
    <div class="review-panel-body" id="rpForm">
      <div>
        <span class="review-label">Your rating</span>
        <div class="review-stars" id="rpStars"></div>
      </div>
      <div>
        <span class="review-label">What are you reviewing? <span class="review-hint">(pick one or more)</span></span>
        <div class="review-service-chips" id="rpServices"></div>
      </div>
      <div>
        <label class="review-label" for="rpComment">Your review</label>
        <textarea id="rpComment" class="review-textarea" maxlength="1500" placeholder="What worked well? What could be better?"></textarea>
      </div>
      <div id="rpStatus" class="review-status" role="status" aria-live="polite"></div>
      <button type="button" class="btn btn-primary" id="rpSubmit">Post review</button>
      <a href="${pagesPrefix()}reviews.html" class="review-hint" style="text-align:center;">Read all reviews →</a>
    </div>
  `;
  document.body.appendChild(tab);
  document.body.appendChild(panel);

  const stars = renderStarPicker(panel.querySelector("#rpStars"), 5);
  const chips = renderServiceChips(panel.querySelector("#rpServices"), [pageDefaultService()]);
  const status = panel.querySelector("#rpStatus");
  const comment = panel.querySelector("#rpComment");
  const submit = panel.querySelector("#rpSubmit");

  const setStatus = (msg, kind = "") => { status.textContent = msg; status.className = `review-status ${kind}`; };

  const open = (services) => {
    if (services && services.length) chips.setSelected(services);
    const loggedIn = authManager.isLoggedIn();
    panel.querySelector("#rpForm").hidden = !loggedIn;
    panel.querySelector("#rpLoginNote").hidden = loggedIn;
    panel.querySelector("#rpLoginLink").href = authManager.loginUrl();
    panel.classList.add("open");
    tab.setAttribute("aria-expanded", "true");
    setStatus("");
    if (loggedIn) comment.focus();
  };
  const close = () => {
    panel.classList.remove("open");
    tab.setAttribute("aria-expanded", "false");
  };

  tab.addEventListener("click", () => (panel.classList.contains("open") ? close() : open()));
  panel.querySelector(".review-panel-close").addEventListener("click", () => { close(); tab.focus(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && panel.classList.contains("open")) close(); });

  submit.addEventListener("click", async () => {
    submit.disabled = true;
    setStatus("Saving…");
    try {
      const saved = await submitReview({
        rating: stars.getRating(),
        comment: comment.value,
        services: chips.getSelected()
      });
      setStatus(`Thank you! Saved for ${saved.length} service${saved.length > 1 ? "s" : ""}.`, "ok");
      comment.value = "";
      toast.success("Thanks for your review!");
      setTimeout(close, 1400);
    } catch (err) {
      setStatus(err.message, "error");
    } finally {
      submit.disabled = false;
    }
  });

  return { open, close };
}

/** Public: open the panel (optionally preselecting services). */
export function openReviewPanel(services) {
  if (!panelApi) panelApi = buildPanel();
  panelApi.open(services);
}

// ---------------------------------------------------------------------------
// "Rate this service" strips: shown ONLY once that service has produced results
// ---------------------------------------------------------------------------
const readyServices = new Set();

function syncRateStrips() {
  document.querySelectorAll("[data-rate-service]").forEach(el => {
    el.hidden = !readyServices.has(el.dataset.rateService);
  });
}

/** A service finished generating its results: reveal its "Rate this service" strip. */
export function announceServiceReady(service) {
  readyServices.add(service);
  syncRateStrips();
}

/** A service was reset / is searching again: hide its strip until new results exist. */
export function announceServiceReset(service) {
  readyServices.delete(service);
  syncRateStrips();
}

function mountRatePrompts() {
  document.querySelectorAll("[data-rate-service]").forEach(el => {
    const service = el.dataset.rateService;
    el.hidden = !readyServices.has(service);
    el.innerHTML = `
      <div><strong>How was ${escapeHtml(service)}?</strong><div class="review-hint">Your review helps other travellers.</div></div>
      <button type="button" class="btn btn-primary btn-sm">★ Rate ${escapeHtml(service)}</button>`;
    el.querySelector("button").addEventListener("click", () => openReviewPanel([service]));
  });
}

// ---------------------------------------------------------------------------
// Home page: top 3 general reviews
// ---------------------------------------------------------------------------
export function renderReviewCard(item, showService = true) {
  return `
    <article class="review-card">
      <div class="review-stars-static" aria-label="${item.rating} out of 5 stars">${starsText(item.rating)}</div>
      <p>${escapeHtml(item.comment)}</p>
      <div class="review-card-meta">
        ${showService && item.service_used ? `<span class="badge badge-primary">${escapeHtml(item.service_used)}</span>` : "<span></span>"}
        <span class="text-muted">${escapeHtml(item.username || "Traveller")} · ${escapeHtml(formatDateTime(item.created_at))}</span>
      </div>
    </article>`;
}

async function loadHomeTopReviews() {
  const grid = document.getElementById("homeReviewsGrid");
  if (!grid) return;
  try {
    const all = await api.getFeedback();
    const general = (all || []).filter(r => GENERAL_SERVICES.includes(r.service_used));
    // best rated first, newest first among equals
    general.sort((a, b) => (b.rating - a.rating) || String(b.created_at).localeCompare(String(a.created_at)));
    const top = general.slice(0, 3);
    grid.innerHTML = top.length
      ? top.map(r => renderReviewCard(r)).join("")
      : `<div class="empty-state"><p>No reviews yet. Be the first to rate Smart Local Guide!</p></div>`;
  } catch (_) {
    grid.innerHTML = `<div class="empty-state"><p>Reviews could not be loaded right now.</p></div>`;
  }
}

export function initReviews() {
  panelApi = buildPanel();
  mountRatePrompts();

  document.querySelectorAll("[data-open-review]").forEach(btn => {
    btn.addEventListener("click", () => {
      const preset = btn.dataset.openReview ? btn.dataset.openReview.split("|") : undefined;
      openReviewPanel(preset);
    });
  });

  loadHomeTopReviews();
  window.addEventListener("slg:reviews-updated", loadHomeTopReviews);
}
