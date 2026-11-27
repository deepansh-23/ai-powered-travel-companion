/**
 * Filter Chips Component (Section 50.1 & 50.4).
 */

import { state } from "../state.js";
import { escapeHtml, titleCase } from "../utils/formatters.js";

export function renderFilterChips(container, countsObj, onToggleCallback) {
  if (!container) return;
  container.innerHTML = "";

  // 1. Total places count for "All" chip
  let totalCount = 0;
  Object.values(countsObj || {}).forEach(cnt => { totalCount += cnt; });

  const syncChipVisuals = () => {
    container.querySelectorAll(".filter-chip[data-filter-key]").forEach(btn => {
      const k = btn.dataset.filterKey;
      const active = state.activeFilters.has(k);
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-checked", String(active));
    });
  };

  const allChip = document.createElement("button");
  const isAllActive = state.activeFilters.has("all");
  allChip.className = `filter-chip ${isAllActive ? "active" : ""}`;
  allChip.dataset.filterKey = "all";
  allChip.setAttribute("role", "checkbox");
  allChip.setAttribute("aria-checked", String(isAllActive));
  allChip.innerHTML = `
    <span>All</span>
    <span class="chip-count">${totalCount}</span>
  `;
  allChip.addEventListener("click", () => {
    state.setFilter("all");
    syncChipVisuals();
    if (onToggleCallback) onToggleCallback();
  });
  container.appendChild(allChip);

  // 2. Individual Category / Amenity / Service chips
  Object.entries(countsObj || {}).forEach(([key, count]) => {
    const chip = document.createElement("button");
    const lowerKey = key.toLowerCase();
    const isActive = state.activeFilters.has(lowerKey);
    chip.className = `filter-chip ${isActive ? "active" : ""}`;
    chip.dataset.filterKey = lowerKey;
    chip.setAttribute("role", "checkbox");
    chip.setAttribute("aria-checked", String(isActive));

    chip.innerHTML = `
      <span>${escapeHtml(titleCase(key))}</span>
      <span class="chip-count">${count}</span>
    `;

    chip.addEventListener("click", () => {
      state.setFilter(lowerKey);
      syncChipVisuals();
      if (onToggleCallback) onToggleCallback();
    });

    container.appendChild(chip);
  });
}
