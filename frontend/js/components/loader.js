/**
 * Skeletons and Loading States (Section 16 & 50.8).
 */

export function renderLoadingSkeletons(container, count = 6) {
  if (!container) return;
  let html = "";
  for (let i = 0; i < count; i++) {
    html += `
      <div class="place-card skeleton skeleton-card" aria-hidden="true"></div>
    `;
  }
  container.innerHTML = html;
}

export function renderMapSkeleton(container) {
  if (!container) return;
  container.innerHTML = `<div class="skeleton skeleton-map" aria-label="Loading map…"></div>`;
}
