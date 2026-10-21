/**
 * History Page Initializer (Section 13).
 */

import { api } from "../api.js";
import { renderHistoryItem } from "../components/history.js";
import { toast } from "../components/toast.js";
import { escapeHtml } from "../utils/formatters.js";
import { renderSessionsList } from "../components/saved-sessions.js";

function startHistoryPage() {
  const container = document.getElementById("historyList");
  const filterButtons = document.querySelectorAll(".history-filter-btn");

  let currentFilter = "all";

  // Saved sessions (work in progress) live above the finished History items
  async function loadSavedSessions() {
    const box = document.getElementById("savedSessionsList");
    if (!box) return;
    try {
      const sessions = await api.listSessions();
      renderSessionsList(box, sessions, { showService: true, onChange: loadSavedSessions });
    } catch (err) {
      box.innerHTML = `<p class="text-muted">Saved sessions could not be loaded: ${escapeHtml(err.message)}</p>`;
    }
  }
  loadSavedSessions();

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
}

// Only a logged-in user gets here: guests are shown the "needs an account" card by the auth manager,
// so nothing below runs (and no API call is made) for them.
document.addEventListener("DOMContentLoaded", () => {
  if (document.body.classList.contains("auth-ready")) startHistoryPage();
  else window.addEventListener("slg:auth-ready", startHistoryPage, { once: true });
});
