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

  const allChip = document.createElement("button");
  const isAllActive = state.activeFilters.has("all");
  allChip.className = `filter-chip ${isAllActive ? "active" : ""}`;
  allChip.setAttribute("role", "checkbox");
  allChip.setAttribute("aria-checked", isAllActive);
  allChip.innerHTML = `
    <span>All</span>
    <span class="chip-count">${totalCount}</span>
  `;
  allChip.addEventListener("click", () => {
    state.setFilter("all");
    if (onToggleCallback) onToggleCallback();
  });
  container.appendChild(allChip);

  // 2. Individual Category / Amenity / Service chips
  Object.entries(countsObj || {}).forEach(([key, count]) => {
    const chip = document.createElement("button");
    const isActive = state.activeFilters.has(key.toLowerCase());
    chip.className = `filter-chip ${isActive ? "active" : ""}`;
    chip.setAttribute("role", "checkbox");
    chip.setAttribute("aria-checked", isActive);

    chip.innerHTML = `
      <span>${escapeHtml(titleCase(key))}</span>
      <span class="chip-count">${count}</span>
    `;

    chip.addEventListener("click", () => {
      state.setFilter(key.toLowerCase());
      if (onToggleCallback) onToggleCallback();
    });

    container.appendChild(chip);
  });
}
