/**
 * History Component (Section 13, 21, 22, 23).
 * Provides rich UI state reconstruction and direct binary PDF export.
 */

import { api } from "../api.js";
import { modal } from "./modal.js";
import { toast } from "./toast.js";
import { escapeHtml, formatDateTime } from "../utils/formatters.js";

export function renderHistoryItem(item, onDeleteCallback) {
  const card = document.createElement("div");
  card.className = "history-card";
  card.id = `history-${item.id}`;

  const badgeClass = item.feature_type === "medical" ? "badge-emergency" : "badge-primary";

  card.innerHTML = `
    <div class="history-main-info">
      <div class="history-meta">
        <span class="badge ${badgeClass}">${escapeHtml(item.feature_type.toUpperCase())}</span>
        <span class="text-muted">${escapeHtml(formatDateTime(item.created_at))}</span>
      </div>
      <h4>${escapeHtml(item.title)}</h4>
      <p style="font-size:0.9rem;margin-top:4px;">${escapeHtml(item.preview)}</p>
    </div>
    <div class="history-actions">
      <button class="btn btn-secondary btn-sm btn-view-hist" aria-label="View history item">View</button>
      <button class="btn btn-secondary btn-sm btn-pdf-hist" aria-label="Export history item to PDF">PDF</button>
      <button class="btn btn-secondary btn-sm btn-del-hist" aria-label="Delete history item" style="color:var(--color-danger);">&times;</button>
    </div>
  `;

  // View modal with reconstructed UI state (Section 22)
  card.querySelector(".btn-view-hist").addEventListener("click", () => {
    openReconstructedModal(item);
  });

  // Export PDF (Section 23 - Binary download)
  card.querySelector(".btn-pdf-hist").addEventListener("click", async () => {
    await triggerPdfDownload(item.title, item.payload);
  });

  // Delete
  card.querySelector(".btn-del-hist").addEventListener("click", async () => {
    if (!confirm(`Delete history entry "${item.title}"?`)) return;
    try {
      await api.deleteHistory(item.id);
      card.remove();
      toast.success("History item deleted.");
      if (onDeleteCallback) onDeleteCallback();
    } catch (err) {
      toast.error("Failed to delete history item: " + err.message);
    }
  });

  return card;
}

/**
 * Triggers binary PDF download from backend.
 */
async function triggerPdfDownload(title, payload) {
  try {
    toast.info("Preparing PDF document…");
    const blob = await api.downloadPdf(title, payload);
    const downloadUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.style.display = "none";
    a.href = downloadUrl;
    const safeTitle = (title || "trip_itinerary").toLowerCase().replace(/[^a-z0-9]/g, "_");
    a.download = `${safeTitle}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
    toast.success("PDF downloaded successfully!");
  } catch (err) {
    toast.error("Failed to generate PDF: " + err.message);
  }
}

/**
 * Reconstructs original service UI/state inside the modal dialog (Section 22).
 */
function openReconstructedModal(item) {
  const isInsidePages = window.location.pathname.includes("/pages/");
  const payload = item.payload || {};
  let bodyHtml = "";
  let footerHtml = "";

  const type = (item.feature_type || "").toLowerCase();

  if (type === "itinerary") {
    bodyHtml = buildItineraryHtml(payload, item);
    const targetUrl = isInsidePages ? "itinerary.html" : "pages/itinerary.html";
    footerHtml = `
      <button class="btn btn-secondary btn-sm" id="modalHistDownloadPdf">📥 Download PDF</button>
      <button class="btn btn-primary btn-sm" id="modalHistRestoreBtn">🚀 Restore in Planner</button>
      <button class="btn btn-secondary btn-sm btn-close-modal">Close</button>
    `;
  } else if (type === "places" || type === "cafes" || type === "medical") {
    bodyHtml = buildPlacesHtml(payload, type);
    const pageMap = { places: "places.html", cafes: "cafes.html", medical: "medical.html" };
    const targetUrl = isInsidePages ? pageMap[type] : `pages/${pageMap[type]}`;
    footerHtml = `
      <button class="btn btn-primary btn-sm" id="modalHistRestoreBtn">Open Service Page</button>
      <button class="btn btn-secondary btn-sm btn-close-modal">Close</button>
    `;
  } else if (type === "area") {
    bodyHtml = buildAreaGuideHtml(payload);
    const targetUrl = isInsidePages ? "area.html" : "pages/area.html";
    footerHtml = `
      <button class="btn btn-primary btn-sm" id="modalHistRestoreBtn">Open Area Guide</button>
      <button class="btn btn-secondary btn-sm btn-close-modal">Close</button>
    `;
  } else {
    bodyHtml = `
      <div style="font-size:0.9rem;color:var(--color-text-muted);margin-bottom:12px;">Saved on: ${escapeHtml(formatDateTime(item.created_at))}</div>
      <p style="margin-bottom:16px;">${escapeHtml(item.preview)}</p>
      <pre style="background:var(--color-surface-soft);padding:14px;border-radius:var(--radius-md);overflow-x:auto;font-size:0.85rem;border:1px solid var(--color-border);">${escapeHtml(JSON.stringify(payload, null, 2))}</pre>
    `;
    footerHtml = `<button class="btn btn-secondary btn-sm btn-close-modal">Close</button>`;
  }

  modal.open({
    title: item.title,
    bodyHtml,
    footerHtml
  });

  // Attach event handlers for modal actions
  const pdfBtn = document.getElementById("modalHistDownloadPdf");
  if (pdfBtn) {
    pdfBtn.addEventListener("click", () => {
      triggerPdfDownload(item.title, item.payload);
    });
  }

  const restoreBtn = document.getElementById("modalHistRestoreBtn");
  if (restoreBtn) {
    restoreBtn.addEventListener("click", () => {
      const go = (page) => {
        window.location.href = isInsidePages ? page : `pages/${page}`;
      };
      if (type === "itinerary") {
        // Same key + shape that itinerary.js restoreSessionState() reads
        const session = {
          source: payload.source,
          destination: payload.destination,
          outboundDate: payload.departure_date,
          returnDate: payload.return_date,
          travelers: payload.travellers || 1,
          preference: payload.preference || "best-overall",
          transportData: null,
          selectedOutbound: payload.selected_outbound_transport || null,
          selectedReturn: payload.selected_return_transport || null,
          selectedHotel: payload.selected_hotel || null,
          hotelSkipped: !payload.selected_hotel,
          finalItinerary: payload.days ? payload : null
        };
        sessionStorage.setItem("slg_session_itinerary", JSON.stringify(session));
        go("itinerary.html");
      } else if (type === "places" || type === "cafes" || type === "medical") {
        // Same key + snapshot shape that NearbyExplorerController reads
        sessionStorage.setItem(`slg_${type}_state`, JSON.stringify(payload));
        go(`${type}.html`);
      } else if (type === "area") {
        sessionStorage.setItem("slg_area_state", JSON.stringify(payload));
        go("area.html");
      }
    });
  }
}

/**
 * Builds rich HTML reconstruction for Itinerary state.
 * Reads the real shapes: TransportOption (number, duration_formatted, price),
 * HotelOption (nightly_price, total_price), cost_breakdown and ItineraryDay.
 */
function buildItineraryHtml(p, item) {
  const money = (v) => (v === null || v === undefined ? "—" : `₹${Number(v).toLocaleString("en-IN")}`);
  const source = p.source || "";
  const dest = p.destination || "";
  const depDate = p.departure_date || "";
  const retDate = p.return_date || "";
  const travellers = p.travellers || 1;
  const outT = p.selected_outbound_transport;
  const retT = p.selected_return_transport;
  const hotel = p.selected_hotel;
  const days = Array.isArray(p.days) ? p.days : [];
  const cost = p.cost_breakdown;

  let html = `
    <div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px;">
      <span class="badge badge-primary">📍 ${escapeHtml(source)} ➔ ${escapeHtml(dest)}</span>
      ${depDate ? `<span class="badge badge-secondary">🗓️ ${escapeHtml(depDate)} to ${escapeHtml(retDate || depDate)}</span>` : ""}
      <span class="badge badge-secondary">👥 ${travellers} Traveller${travellers > 1 ? "s" : ""}</span>
      ${p.data_mode === "mock" ? `<span class="badge badge-secondary">Mock data</span>` : ""}
      <span class="badge badge-secondary">Saved: ${escapeHtml(formatDateTime(item.created_at) || "Recent")}</span>
    </div>
  `;

  const transportLine = (label, t) => {
    if (!t) return "";
    const price = t.price ? ` | ${money(t.price)} (provider quote)` : " | fare not provided";
    return `<div style="font-size:0.88rem;margin-bottom:6px;">
      <strong>${label} (${escapeHtml((t.mode || "transport").toUpperCase())}):</strong>
      ${escapeHtml(t.operator || "")} ${escapeHtml(t.number || "")}
      &bull; ${escapeHtml(t.origin || "")} ${escapeHtml(t.departure_time || "")} ➔ ${escapeHtml(t.destination || "")} ${escapeHtml(t.arrival_time || "")}
      (${escapeHtml(t.duration_formatted || "")})${price}
    </div>`;
  };

  if (outT || retT) {
    html += `<div style="background:var(--color-surface-soft);padding:14px;border-radius:var(--radius-md);margin-bottom:16px;border:1px solid var(--color-border);">
      <h4 style="margin-bottom:8px;font-size:0.95rem;">🚆 Transport Selections</h4>
      ${transportLine("Outbound", outT)}${transportLine("Return", retT)}
    </div>`;
  }

  html += `<div style="background:var(--color-surface-soft);padding:14px;border-radius:var(--radius-md);margin-bottom:16px;border:1px solid var(--color-border);">
    <h4 style="margin-bottom:8px;font-size:0.95rem;">🏨 Accommodation</h4>
    ${hotel
      ? `<div style="font-size:0.88rem;"><strong>${escapeHtml(hotel.name || "")}</strong>
          ${hotel.rating ? `&bull; ⭐ ${escapeHtml(hotel.rating)}` : ""}
          ${hotel.nightly_price ? `&bull; ${money(hotel.nightly_price)} / night` : ""}
          ${hotel.total_price ? `&bull; ${money(hotel.total_price)} total` : ""}</div>
         ${hotel.amenities && hotel.amenities.length ? `<div style="font-size:0.8rem;color:var(--color-text-muted);margin-top:4px;">Amenities: ${escapeHtml(hotel.amenities.slice(0, 5).join(", "))}</div>` : ""}`
      : `<div style="font-size:0.88rem;"><em>Not selected</em></div>`}
  </div>`;

  if (cost) {
    html += `<div style="margin-bottom:16px;">
      <h4 style="margin-bottom:8px;font-size:0.95rem;">💰 Cost Summary</h4>
      <table class="cost-table" style="width:100%;font-size:0.85rem;">
        <tr><td>Outbound transport (provider quote)</td><td style="text-align:right;">${money(cost.outbound_transport_price)}</td></tr>
        <tr><td>Return transport (provider quote)</td><td style="text-align:right;">${money(cost.return_transport_price)}</td></tr>
        <tr><td>Accommodation</td><td style="text-align:right;">${cost.hotel_selected ? money(cost.hotel_total_price) : "not selected"}</td></tr>
        <tr><td>Food &amp; activities (estimate)</td><td style="text-align:right;">${money(cost.food_and_activities_estimate)}</td></tr>
        <tr style="font-weight:bold;border-top:1px solid var(--color-border);"><td>Estimated total</td><td style="text-align:right;color:var(--color-primary);">${money(cost.overall_total_estimate)}</td></tr>
        <tr><td>Per person</td><td style="text-align:right;">${money(cost.per_person_estimate)}</td></tr>
      </table>
    </div>`;
  }

  const seg = (label, s) => {
    if (!s) return "";
    const places = (s.places || []).map(pl => escapeHtml(pl.name)).join(", ");
    return `<div><strong>${label}</strong> <span style="color:var(--color-text-muted);">${escapeHtml(s.time_window || "")}</span> — ${escapeHtml(s.title || "")}${places ? `<div style="font-size:0.8rem;color:var(--color-text-secondary);">Places: ${places}</div>` : ""}</div>`;
  };
  const meal = (label, f) => (f ? `<div><strong>${label}</strong> — ${escapeHtml(f.name || "")} <span style="color:var(--color-text-muted);">(${escapeHtml(f.cuisine || "")})</span></div>` : "");

  if (days.length > 0) {
    html += `<h4 style="margin-bottom:10px;font-size:0.95rem;">📅 Daily Schedule</h4><div style="display:flex;flex-direction:column;gap:12px;">`;
    days.forEach(day => {
      html += `
        <div style="border:1px solid var(--color-border);border-radius:var(--radius-md);padding:12px;background:var(--color-surface);">
          <h5 style="color:var(--color-primary);margin-bottom:8px;">Day ${escapeHtml(day.day_number)}: ${escapeHtml(day.theme || "")}</h5>
          <div style="font-size:0.85rem;display:flex;flex-direction:column;gap:6px;">
            ${seg("Morning", day.morning)}
            ${meal("Lunch", day.food_stop_lunch)}
            ${seg("Afternoon", day.afternoon)}
            ${meal("Dinner", day.food_stop_dinner)}
            ${seg("Evening", day.evening)}
          </div>
        </div>`;
    });
    html += `</div>`;
  } else {
    html += `<p class="text-muted">This saved record has no day-by-day schedule.</p>`;
  }

  return html;
}

/**
 * Builds rich HTML reconstruction for Places / Cafes / Medical state.
 */
function buildPlacesHtml(p, type) {
  let places = [];
  if (Array.isArray(p.places)) places = p.places;
  else if (Array.isArray(p.items)) places = p.items;
  else if (Array.isArray(p)) places = p;

  if (places.length === 0) {
    return `<p class="text-muted">No places listed in this saved record.</p>`;
  }

  let html = `<div style="display:flex;flex-direction:column;gap:10px;max-height:60vh;overflow-y:auto;padding-right:4px;">`;
  places.forEach((place, idx) => {
    const name = place.name || "Unnamed Place";
    const address = place.address || place.formatted_address || "Address unavailable";
    const rating = place.rating ? `⭐ ${place.rating}` : "No rating";
    const phone = place.phone ? `📞 ${place.phone}` : "";
    const mapsQuery = encodeURIComponent(`${name} ${address}`);
    const directionsUrl = `https://www.google.com/maps/search/?api=1&query=${mapsQuery}`;

    html += `
      <div style="padding:12px;border:1px solid var(--color-border);border-radius:var(--radius-md);background:var(--color-surface);">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
          <strong>${idx + 1}. ${escapeHtml(name)}</strong>
          <span style="font-size:0.8rem;background:var(--color-surface-soft);padding:2px 8px;border-radius:var(--radius-full);">${escapeHtml(rating)}</span>
        </div>
        <p style="font-size:0.85rem;color:var(--color-text-secondary);margin:4px 0;">${escapeHtml(address)}</p>
        <div style="display:flex;gap:12px;align-items:center;margin-top:6px;font-size:0.8rem;">
          ${phone ? `<span>${escapeHtml(phone)}</span>` : ""}
          <a href="${directionsUrl}" target="_blank" rel="noopener noreferrer" style="color:var(--color-primary);font-weight:500;text-decoration:none;">🗺️ Get Directions</a>
        </div>
      </div>
    `;
  });
  html += `</div>`;
  return html;
}

/**
 * Builds rich HTML reconstruction for Area Guide state (real AreaSummaryResponse shape).
 */
function buildAreaGuideHtml(p) {
  const text = p.character_summary || p.summary;
  if (!text && !p.sections) {
    return `<p class="text-muted">This saved record only has the area name (${escapeHtml(p.area_input || p.area || "unknown")}). Use "Open Area Guide" to regenerate it.</p>`;
  }
  let html = "";
  if (text) {
    html += `<div style="padding:12px;background:var(--color-surface-soft);border-radius:var(--radius-md);margin-bottom:14px;border:1px solid var(--color-border);font-size:0.9rem;">
      ${p.region ? `<span class="badge badge-primary" style="margin-right:6px;">${escapeHtml(p.region)}</span>` : ""}${escapeHtml(text)}
    </div>`;
  }
  const qf = p.quick_facts;
  if (qf) {
    html += `<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;">
      ${Object.entries(qf).map(([k, v]) => `<span class="badge badge-secondary">${escapeHtml(k.replace(/_/g, " "))}: ${escapeHtml(v)}</span>`).join("")}
    </div>`;
  }
  const sections = Array.isArray(p.sections) ? p.sections : Object.values(p.sections || {});
  if (sections.length) {
    html += `<div style="display:flex;flex-direction:column;gap:10px;">`;
    sections.forEach(sec => {
      html += `
        <div style="padding:10px;border:1px solid var(--color-border);border-radius:var(--radius-md);">
          <strong style="color:var(--color-primary);font-size:0.9rem;">${escapeHtml(sec.title || "Section")}</strong>
          <p style="font-size:0.85rem;color:var(--color-text-secondary);margin-top:4px;">${escapeHtml(sec.summary || sec.content || "")}</p>
        </div>`;
    });
    html += `</div>`;
  }
  const list = (label, arr) => (Array.isArray(arr) && arr.length
    ? `<h5 style="margin:12px 0 4px;">${label}</h5><ul style="padding-left:20px;font-size:0.85rem;">${arr.map(x => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : "");
  html += list("Advantages", p.advantages) + list("Limitations", p.limitations) + list("Who it suits", p.suitability);
  return html;
}
