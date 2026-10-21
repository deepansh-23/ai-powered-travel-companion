/**
 * "Your trip on the map": every place coloured by day, plus a pin for each hotel.
 * collectTripPoints is pure (no DOM) so it can be tested; renderTripMap needs MapLibre and
 * quietly does nothing when the library or any coordinates are missing.
 */

import { dayColor } from "../pages/itinerary-extras.js";
import { escapeHtml } from "../utils/formatters.js";

export function collectTripPoints(data) {
  const places = [];
  for (const d of data.days || []) {
    for (const seg of [d.morning, d.afternoon, d.evening]) {
      for (const p of (seg && seg.places) || []) {
        if (p && p.name && p.latitude != null && p.longitude != null) {
          places.push({ name: p.name, day: d.day_number, area: d.area || "", lat: p.latitude, lon: p.longitude });
        }
      }
    }
    for (const f of [d.food_stop_lunch, d.food_stop_dinner]) {
      if (f && f.name && f.latitude != null && f.longitude != null) {
        places.push({ name: f.name, day: d.day_number, area: d.area || "", lat: f.latitude, lon: f.longitude, food: true });
      }
    }
  }
  const hotels = (data.selected_hotels || [])
    .filter((h) => h && h.name && h.latitude != null && h.longitude != null)
    .map((h) => ({ name: h.name, area: h.area || "", lat: h.latitude, lon: h.longitude }));
  return { places, hotels };
}

export function renderTripMap(container, data) {
  const pts = collectTripPoints(data);
  if (!container || typeof maplibregl === "undefined" || !pts.places.length) return null;
  const cfg = window.APP_CONFIG || {};
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  const style = cfg.MAP_STYLES ? (dark ? cfg.MAP_STYLES.dark : cfg.MAP_STYLES.light) : null;
  if (!style) return null;

  container.innerHTML = `<div class="trip-map-canvas" role="img" aria-label="Map of the places in your trip"></div><div class="trip-map-legend"></div>`;
  const canvas = container.querySelector(".trip-map-canvas");
  try {
    const map = new maplibregl.Map({ container: canvas, style, center: [pts.places[0].lon, pts.places[0].lat], zoom: 9, attributionControl: false });
    map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: "© OpenStreetMap | CARTO" }), "bottom-right");
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    const bounds = new maplibregl.LngLatBounds();

    for (const p of pts.places) {
      const el = document.createElement("div");
      el.className = "trip-pin" + (p.food ? " food" : "");
      el.style.setProperty("--day-color", dayColor(p.day));
      el.textContent = p.food ? "🍴" : String(p.day);
      new maplibregl.Marker({ element: el }).setLngLat([p.lon, p.lat])
        .setPopup(new maplibregl.Popup({ offset: 16 }).setHTML(`<b>${escapeHtml(p.name)}</b><br>Day ${p.day}${p.area ? " · " + escapeHtml(p.area) : ""}`))
        .addTo(map);
      bounds.extend([p.lon, p.lat]);
    }
    for (const h of pts.hotels) {
      const el = document.createElement("div");
      el.className = "trip-pin hotel";
      el.textContent = "🏨";
      new maplibregl.Marker({ element: el }).setLngLat([h.lon, h.lat])
        .setPopup(new maplibregl.Popup({ offset: 16 }).setHTML(`<b>${escapeHtml(h.name)}</b><br>Your hotel${h.area ? " in " + escapeHtml(h.area) : ""}`))
        .addTo(map);
      bounds.extend([h.lon, h.lat]);
    }
    map.on("load", () => map.fitBounds(bounds, { padding: 50, maxZoom: 14, duration: 0 }));

    const days = [...new Set(pts.places.map((p) => p.day))].sort((a, b) => a - b);
    container.querySelector(".trip-map-legend").innerHTML =
      days.map((d) => `<span class="trip-legend-item"><i style="background:${dayColor(d)}"></i>Day ${d}</span>`).join("") +
      (pts.hotels.length ? `<span class="trip-legend-item">🏨 Hotel</span>` : "") + `<span class="trip-legend-item">🍴 Food stop</span>`;
    return map;
  } catch (err) {
    console.warn("Trip map unavailable:", err);
    container.innerHTML = "";
    return null;
  }
}
