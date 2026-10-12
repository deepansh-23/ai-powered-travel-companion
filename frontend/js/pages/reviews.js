/**
 * Reviews & Community Feedback Page Controller (Section 24).
 * Fetches and persists reviews to SQLite backend.
 */

import { api } from "../api.js";
import { toast } from "../components/toast.js";
import { escapeHtml } from "../utils/formatters.js";
import { renderServiceChips, submitReview, REVIEW_SERVICES, GENERAL_SERVICES } from "../components/review-widget.js";

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("feedbackForm");
  const listContainer = document.getElementById("reviewsList");
  if (!listContainer) return;

  let allItems = [];
  let activeFilter = "All";
  const filterBar = document.getElementById("reviewFilterBar");
  const chipsBox = document.getElementById("reviewServiceChips");
  const serviceChips = chipsBox ? renderServiceChips(chipsBox, []) : null;

  function renderFilterBar() {
    if (!filterBar) return;
    // standard services first, then any other label found in saved reviews (e.g. older ones)
    const extra = [...new Set(allItems.map(i => i.service_used).filter(Boolean))].filter(n => !REVIEW_SERVICES.includes(n));
    const names = ["All", "General", ...REVIEW_SERVICES, ...extra];
    filterBar.innerHTML = names.map(n => {
      const count = n === "All" ? allItems.length
        : n === "General" ? allItems.filter(i => GENERAL_SERVICES.includes(i.service_used)).length
        : allItems.filter(i => i.service_used === n).length;
      return `<button type="button" class="review-chip" data-filter="${escapeHtml(n)}" aria-pressed="${n === activeFilter}">${escapeHtml(n)} (${count})</button>`;
    }).join("");
  }

  if (filterBar) {
    filterBar.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-filter]");
      if (!btn) return;
      activeFilter = btn.dataset.filter;
      renderFilterBar();
      renderList();
    });
  }

  async function loadReviews() {
    listContainer.innerHTML = `
      <div class="empty-state">
        <p>Loading community reviews…</p>
      </div>
    `;

    try {
      allItems = (await api.getFeedback()) || [];
      renderFilterBar();
      renderList();
    } catch (err) {
      listContainer.innerHTML = `
        <div class="error-state">
          <h3>Failed to load reviews</h3>
          <p>${escapeHtml(err.message)}</p>
        </div>
      `;
    }
  }

  function renderList() {
    {
      const items = allItems.filter(i =>
        activeFilter === "All" ? true
        : activeFilter === "General" ? GENERAL_SERVICES.includes(i.service_used)
        : i.service_used === activeFilter);
      listContainer.innerHTML = "";

      if (!items || items.length === 0) {
        listContainer.innerHTML = `
          <div class="empty-state">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            <h3>${allItems.length ? "No reviews for this filter yet" : "No reviews submitted yet"}</h3>
            <p>${allItems.length ? "Try another service filter, or write the first review for it." : "Be the first traveller to post feedback about your trip planning experience!"}</p>
          </div>
        `;
        return;
      }

      items.forEach(item => {
        const card = document.createElement("article");
        card.className = "history-card";
        card.id = `review-${item.id}`;

        const stars = "★".repeat(item.rating) + "☆".repeat(5 - item.rating);

        card.innerHTML = `
          <div class="history-main-info" style="width:100%;">
            <div class="history-meta" style="display:flex;justify-content:space-between;align-items:center;">
              <div>
                <span class="rating-stars" style="color:var(--color-accent);font-size:1.1rem;font-weight:700;">${stars}</span>
                ${item.service_used ? `<span class="badge badge-primary" style="margin-left:8px;">${escapeHtml(item.service_used)}</span>` : ""}
              </div>
              <span class="text-muted" style="font-size:0.8rem;">${escapeHtml(item.created_at)}</span>
            </div>
            <p style="margin-top:8px;font-size:0.95rem;line-height:1.5;color:var(--color-text-primary);">
              ${escapeHtml(item.comment)}
            </p>
          </div>
        `;
        listContainer.appendChild(card);
      });
    }
  }

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      const ratingSelect = document.getElementById("reviewRating");
      const commentInput = document.getElementById("reviewComment");
      const submitBtn = document.getElementById("btnSubmitReview");

      const rating = ratingSelect ? parseInt(ratingSelect.value, 10) : 5;
      const services = serviceChips ? serviceChips.getSelected() : [];
      const comment = commentInput ? commentInput.value.trim() : "";

      if (services.length === 0) {
        toast.error("Please select at least one service you used.");
        return;
      }
      if (!comment || comment.length < 2) {
        toast.error("Please enter a short comment or review.");
        commentInput?.focus();
        return;
      }

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<span>Submitting…</span>`;
      }

      try {
        const saved = await submitReview({ rating, comment, services });

        toast.success(`Thank you! Your review has been saved for ${saved.length} service${saved.length > 1 ? "s" : ""}.`);
        form.reset();
        serviceChips && serviceChips.setSelected([]);
        await loadReviews();
      } catch (err) {
        toast.error("Failed to submit review: " + err.message);
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = `<span>Post Feedback</span>`;
        }
      }
    });
  }

  loadReviews();
});
