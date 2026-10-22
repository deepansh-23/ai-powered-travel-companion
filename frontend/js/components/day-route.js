/**
 * One day as a route: a small horizontal flowchart plus a "See on map" view with a numbered path.
 * buildDayStops is pure (no DOM) so it can be tested; the map needs MapLibre and quietly does
 * nothing when the library or the coordinates are missing.
 *
 * Order of stops follows the day itself: hotel -> morning places -> lunch -> afternoon places
 * -> dinner -> evening places -> back to the hotel.
 */

import { escapeHtml } from "../utils/formatters.js";

const hasXY = (o) => o && o.latitude != null && o.longitude != null;

export function buildDayStops(day, hotel = null) {
  const stops = [];
  const add = (kind, o, extra = {}) => {
    if (!o || !o.name) return;
    stops.push({ kind, name: o.name, lat: hasXY(o) ? o.latitude : null, lon: hasXY(o) ? o.longitude : null, ...extra });
  };
  if (hotel && hotel.name) add("hotel", hotel, { label: "Hotel", start: true });
  for (const p of (day.morning && day.morning.places) || []) add("place", p);
  if (day.food_stop_lunch && !day.food_stop_lunch.skipped) add("food", day.food_stop_lunch, { label: "Lunch" });
  for (const p of (day.afternoon && day.afternoon.places) || []) add("place", p);
  if (day.food_stop_dinner && !day.food_stop_dinner.skipped) add("food", day.food_stop_dinner, { label: "Dinner" });
  for (const p of (day.evening && day.evening.places) || []) add("place", p);
  if (hotel && hotel.name && day.return_to_hotel) add("hotel", hotel, { label: "Back to hotel", end: true });
  // numbers: 1, 2, 3 ... in visiting order (the starting hotel is "Start", the closing hotel keeps its own number)
  let n = 0;
  for (const s of stops) s.num = s.start ? 0 : ++n;
  return stops;
}

const ICON = { hotel: "🏨", food: "🍴", place: "📍" };

/** Small horizontal flowchart: Start → 1 → 2 → ... Scrolls sideways on narrow screens. */
export function buildDayFlowHtml(stops) {
  if (!stops || stops.length < 2) return "";
  const nodes = stops.map((s) => `
    <li class="dayflow-node dayflow-${s.kind}" title="${escapeHtml(s.name)}">
      <span class="dayflow-num">${s.start ? "★" : s.num}</span>
      <span class="dayflow-text"><b>${escapeHtml(s.label || (s.kind === "place" ? "Visit" : ""))}</b><small>${escapeHtml(s.name)}</small></span>
    </li>`).join('<li class="dayflow-arrow" aria-hidden="true">→</li>');
  return `<ol class="dayflow" aria-label="Order of your day">${nodes}</ol>`;
}

/** Draws the numbered stops joined by a highlighted path. Returns the map, or null when it cannot be drawn. */
export function renderDayMap(container, stops, color = "#2563EB") {
  const pts = (stops || []).filter((s) => s.lat != null && s.lon != null);
  if (!container || typeof maplibregl === "undefined" || pts.length < 1) return null;
  const cfg = window.APP_CONFIG || {};
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  const style = cfg.MAP_STYLES ? (dark ? cfg.MAP_STYLES.dark : cfg.MAP_STYLES.light) : null;
  if (!style) return null;

  container.innerHTML = `<div class="day-map-canvas" role="img" aria-label="Map of this day with the visiting order"></div>`;
  try {
    const map = new maplibregl.Map({
      container: container.firstElementChild, style, center: [pts[0].lon, pts[0].lat], zoom: 12, attributionControl: false,
    });
    map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: "© OpenStreetMap | CARTO" }), "bottom-right");
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    const bounds = new maplibregl.LngLatBounds();

    pts.forEach((s) => {
      const el = document.createElement("div");
      el.className = "day-pin" + (s.kind === "food" ? " food" : s.kind === "hotel" ? " hotel" : "");
      el.style.setProperty("--day-color", color);
      el.textContent = s.start ? "🏨" : s.kind === "hotel" ? "🏨" : String(s.num);
      new maplibregl.Marker({ element: el }).setLngLat([s.lon, s.lat])
        .setPopup(new maplibregl.Popup({ offset: 16 }).setHTML(
          `<b>${s.start ? "Start: " : s.num + ". "}${escapeHtml(s.name)}</b>${s.label ? "<br>" + escapeHtml(s.label) : ""}`))
        .addTo(map);
      bounds.extend([s.lon, s.lat]);
    });

    map.on("load", () => {
      if (pts.length > 1) {
        map.addSource("day-path", { type: "geojson", data: { type: "Feature", geometry: { type: "LineString", coordinates: pts.map((s) => [s.lon, s.lat]) } } });
        map.addLayer({ id: "day-path-casing", type: "line", source: "day-path", layout: { "line-join": "round", "line-cap": "round" }, paint: { "line-color": "#ffffff", "line-width": 8, "line-opacity": 0.85 } });
        map.addLayer({ id: "day-path-line", type: "line", source: "day-path", layout: { "line-join": "round", "line-cap": "round" }, paint: { "line-color": color, "line-width": 4.5 } });
      }
      map.fitBounds(bounds, { padding: 55, maxZoom: 15, duration: 0 });
    });
    return map;
  } catch (err) {
    console.warn("Day map unavailable:", err);
    container.innerHTML = "";
    return null;
  }
}
