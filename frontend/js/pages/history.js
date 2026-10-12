/**
 * History Page Initializer (Section 13).
 */

import { api } from "../api.js";
import { renderHistoryItem } from "../components/history.js";
import { toast } from "../components/toast.js";
import { escapeHtml } from "../utils/formatters.js";

document.addEventListener("DOMContentLoaded", () => {
  const container = document.getElementById("historyList");
  const filterButtons = document.querySelectorAll(".history-filter-btn");

  let currentFilter = "all";

  filterButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      filterButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentFilter = btn.dataset.type;
      loadHistory();
    });
  });

  async function loadHistory() {
    container.innerHTML = `
      <div class="empty-state">
        <p>Loading history records…</p>
      </div>
    `;

    try {
      const items = await api.getHistory(currentFilter);
      container.innerHTML = "";

      if (!items || items.length === 0) {
        container.innerHTML = `
          <div class="empty-state">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 14 14"/></svg>
            <h3>No history items found</h3>
            <p>Searches and itineraries you create will automatically appear here for later review.</p>
          </div>
        `;
        return;
      }

      items.forEach(item => {
        const el = renderHistoryItem(item, () => {
          loadHistory();
        });
        container.appendChild(el);
      });

    } catch (err) {
      container.innerHTML = `
        <div class="error-state">
          <h3>Failed to load history</h3>
          <p>${escapeHtml(err.message)}</p>
        </div>
      `;
    }
  }

  loadHistory();
});
