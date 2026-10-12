/**
 * Place Cards Component (Authoritative Section 50.2 specification).
 */

import { formatDistance } from "../utils/geo.js";
import { escapeHtml } from "../utils/formatters.js";

// Standard SVG icons for categories
const CATEGORY_ICONS = {
  museum: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 22h16M2 10h20M12 2l10 7H2l10-7zM6 10v9M10 10v9M14 10v9M18 10v9"/></svg>`,
  attraction: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="12 6 12 12 16 14"/></svg>`,
  hotel: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
  restaurant: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 2v8a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V2"/><path d="M6 2v20M18 14v8"/></svg>`,
  park: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m8 14 4-7 4 7M9 18h6M12 18v4M3 22h18"/></svg>`,
  shopping: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4zM3 6h18M16 10a4 4 0 0 1-8 0"/></svg>`,
  view: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`,
  cafe: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 8h1a4 4 0 1 1 0 8h-1M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4Z"/><line x1="6" y1="2" x2="6" y2="4"/><line x1="10" y1="2" x2="10" y2="4"/><line x1="14" y1="2" x2="14" y2="4"/></svg>`,
  medical: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 6v12M6 12h12M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"/></svg>`,
  hospital: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 6v12M6 12h12M4 4h16v16H4z"/></svg>`
};

export function renderPlaceCard(place, isSelected = false, onSelectCallback = null) {
  const card = document.createElement("article");
  card.className = `place-card ${isSelected ? "selected" : ""}`;
  card.id = `card-${place.id}`;
  if (isSelected) {
    card.setAttribute("aria-current", "true");
  }

  // 1. Icon & Category
  const catKey = (place.category || "attraction").toLowerCase();
  const iconSvg = CATEGORY_ICONS[catKey] || CATEGORY_ICONS.attraction;

  // 2. Distance formatting
  const distText = formatDistance(place.distance_m);
  const distHtml = distText
    ? `<span class="card-distance" title="Straight-line distance" aria-label="Straight-line distance ${distText}">${escapeHtml(distText)}</span>`
    : (place.latitude === null ? `<span class="card-distance text-muted" title="Location on map unavailable">Map N/A</span>` : "");

  // 3. Rating row: number + count OR "Rating unavailable"
  let ratingHtml = `<div class="card-rating-row">`;
  if (place.rating !== null && place.rating !== undefined) {
    const starCount = place.rating_count ? ` <span class="text-muted">(${place.rating_count.toLocaleString()})</span>` : "";
    ratingHtml += `
      <span class="rating-stars" aria-label="Rating ${place.rating} out of 5">★ ${place.rating}</span>
      ${starCount}
    `;
  } else {
    ratingHtml += `<span class="rating-unavailable">Rating unavailable</span>`;
  }
  ratingHtml += `</div>`;

  // 4. Badges (Cafes amenities or Medical 24/7)
  let badgesHtml = "";
  if (place.amenities && place.amenities.length > 0) {
    badgesHtml = `<div class="card-badges-row">` + place.amenities.map(a => {
      const label = a.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
      return `<span class="badge badge-primary">${escapeHtml(label)}</span>`;
    }).join("") + `</div>`;
  } else if (place.service_type) {
    badgesHtml = `<div class="card-badges-row">`;
    if (place.is_24_7 === true) {
      badgesHtml += `<span class="badge badge-247" aria-label="Verified 24/7 service">✓ 24/7 Verified</span>`;
    }
    badgesHtml += `</div>`;
  }

  // 5. Description clamping & Read More toggle
  const desc = escapeHtml(place.description || "");
  const isLongDesc = desc.length > 180;
  const descHtml = `
    <div class="card-description" id="desc-${place.id}">${desc}</div>
    ${isLongDesc ? `<button class="btn-read-more" data-target="desc-${place.id}" aria-expanded="false">Read more</button>` : ""}
  `;

  // 6. Address
  const addressHtml = place.address
    ? `<div class="card-address">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
        <span>${escapeHtml(place.address)}</span>
      </div>`
    : "";

  // 7. Footer: Valid website link, phone link, and Google Maps directions (Section 18)
  let footerLinksHtml = "";
  if (place.website) {
    footerLinksHtml += `<a href="${escapeHtml(place.website)}" target="_blank" rel="noopener noreferrer" class="card-action-link" aria-label="Visit website for ${escapeHtml(place.name)} (opens in new tab)">Visit Website &rarr;</a>`;
  }
  if (place.phone) {
    footerLinksHtml += `<a href="tel:${escapeHtml(place.phone)}" class="card-phone-link" aria-label="Call ${escapeHtml(place.name)}">📞 ${escapeHtml(place.phone)}</a>`;
  }

  // Google Maps Directions link (Section 18)
  let directionsUrl = "";
  if (place.latitude !== null && place.longitude !== null && place.latitude !== undefined && place.longitude !== undefined) {
    directionsUrl = `https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}`;
  } else if (place.address) {
    directionsUrl = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(place.address)}`;
  } else if (place.name) {
    directionsUrl = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(place.name)}`;
  }

  if (directionsUrl) {
    footerLinksHtml += `<a href="${directionsUrl}" target="_blank" rel="noopener noreferrer" class="card-directions-link" aria-label="Get directions to ${escapeHtml(place.name)} on Google Maps">🗺️ Get Directions</a>`;
  }

  const sourceLabel = place.source ? `Source: ${escapeHtml(place.source)}` : "Source: sample-data";


  card.innerHTML = `
    <span class="card-selected-badge" aria-label="Selected destination">✓ Selected</span>
    <div class="card-header-row">
      <div class="card-title-group">
        <div class="card-category-icon" aria-hidden="true">${iconSvg}</div>
        <button class="card-place-btn" aria-label="Select ${escapeHtml(place.name)} on map">${escapeHtml(place.name)}</button>
      </div>
      ${distHtml}
    </div>
    ${ratingHtml}
    <div class="card-category-label">${escapeHtml(place.service_type || place.category || "Place")}</div>
    ${badgesHtml}
    ${descHtml}
    ${addressHtml}
    <hr class="card-divider" />
    <div class="card-footer-row">
      ${footerLinksHtml}
    </div>
    <div class="card-source-line">${sourceLabel}</div>
  `;

  // Read More Toggle
  const readMoreBtn = card.querySelector(".btn-read-more");
  if (readMoreBtn) {
    readMoreBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const targetDesc = card.querySelector(`#${readMoreBtn.dataset.target}`);
      if (targetDesc) {
        const isExp = targetDesc.classList.toggle("expanded");
        readMoreBtn.textContent = isExp ? "Show less" : "Read more";
        readMoreBtn.setAttribute("aria-expanded", isExp);
      }
    });
  }

  // Card click / Place Button selection
  const selectAction = () => {
    if (onSelectCallback) onSelectCallback(place);
  };

  card.querySelector(".card-place-btn").addEventListener("click", selectAction);
  card.addEventListener("click", (e) => {
    // Only select if not clicking links or read-more
    if (!e.target.closest("a") && !e.target.closest(".btn-read-more")) {
      selectAction();
    }
  });

  return card;
}
