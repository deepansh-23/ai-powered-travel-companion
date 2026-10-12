/**
 * Reusable MapLibre GL JS Component (Authoritative Section 50).
 * Shared across Places Near You, Quiet Work Cafés, and 24/7 Medical Care.
 */

import { state } from "../state.js";
import { computeBounds } from "../utils/geo.js";
import { escapeHtml } from "../utils/formatters.js";

export class SharedMapComponent {
  constructor(containerId, options = {}) {
    this.containerId = containerId;
    this.container = document.getElementById(containerId);
    this.options = options;

    this.map = null;
    this.isLoaded = false;
    this.markers = new Map(); // place.id -> maplibre marker
    this.centerMarker = null;
    this.activePopup = null;
    this.currentBounds = null;

    this.onSelectPlaceCallback = options.onSelectPlace || null;

    // Listen to theme switch to update basemap style
    state.subscribe("theme", (newTheme) => {
      this.updateMapTheme(newTheme);
    });
  }

  init() {
    if (!this.container) return;
    if (typeof maplibregl === "undefined") {
      this.showMapFailed("MapLibre GL library could not be loaded.");
      return;
    }

    const isDark = state.theme === "dark";
    const styleUrl = isDark ? window.APP_CONFIG.MAP_STYLES.dark : window.APP_CONFIG.MAP_STYLES.light;

    try {
      this.map = new maplibregl.Map({
        container: this.containerId,
        style: styleUrl,
        center: window.APP_CONFIG.DEFAULT_CENTER,
        zoom: window.APP_CONFIG.DEFAULT_ZOOM,
        attributionControl: false // custom attribution added below to ensure visibility
      });

      // Add standard attribution (Section 50.3: required attribution must stay visible)
      this.map.addControl(new maplibregl.AttributionControl({
        compact: true,
        customAttribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> | CARTO'
      }), "bottom-right");

      this.map.on("load", () => {
        this.isLoaded = true;
        this.setupRouteLayers();
        this.renderFloatingControls();
        this.renderLegend();

        // Deselect on empty map click (Section 50.5)
        this.map.on("click", (e) => {
          // If clicked directly on map canvas and not marker
          if (e.originalEvent.target === this.map.getCanvas()) {
            state.clearSelection();
          }
        });

        // Re-spread overlapping markers whenever the view changes, so
        // nearby places (e.g. several cafés in the same small market)
        // never render as one indistinguishable stacked blob.
        this.map.on("zoomend", () => this._declutterMarkers());
        this.map.on("moveend", () => this._declutterMarkers());

        // Trigger pending render if places were set before map finished loading
        if (this._pendingRender) {
          const { center, places } = this._pendingRender;
          this._pendingRender = null;
          this.renderMarkers(center, places);
        }
      });

      this.map.on("error", (e) => {
        console.warn("MapLibre tile or resource error:", e);
      });

    } catch (err) {
      console.error("Map initialization failed:", err);
      this.showMapFailed("Basemap tiles could not load. Your results remain fully accessible below.");
    }
  }

  showMapFailed(msg) {
    if (!this.container) return;
    this.container.innerHTML = `
      <div class="map-failed-card" role="alert">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <h4>Map unavailable</h4>
        <p>${escapeHtml(msg)}</p>
        <button class="btn btn-secondary btn-sm" id="btnRetryMap">Retry map</button>
      </div>
    `;
    const retryBtn = this.container.querySelector("#btnRetryMap");
    if (retryBtn) {
      retryBtn.addEventListener("click", () => {
        this.container.innerHTML = "";
        this.init();
      });
    }
  }

  updateMapTheme(themeName) {
    if (!this.map || !this.isLoaded) return;
    const isDark = themeName === "dark";
    const styleUrl = isDark ? window.APP_CONFIG.MAP_STYLES.dark : window.APP_CONFIG.MAP_STYLES.light;

    this.map.setStyle(styleUrl);
    this.map.once("style.load", () => {
      this.setupRouteLayers();
      // Re-apply existing route if any
      if (state.currentRoute) {
        this.drawRoute(state.currentRoute);
      }
    });
  }

  setupRouteLayers() {
    if (!this.map.getSource("route-source")) {
      this.map.addSource("route-source", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
    }

    // Outer casing (wide white line) so it stands out against any basemap (Section 50.5)
    if (!this.map.getLayer("route-casing")) {
      this.map.addLayer({
        id: "route-casing",
        type: "line",
        source: "route-source",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": "#ffffff",
          "line-width": 7,
          "line-opacity": 0.95
        }
      });
    }

    // Inner line (primary/accent color)
    if (!this.map.getLayer("route-line")) {
      this.map.addLayer({
        id: "route-line",
        type: "line",
        source: "route-source",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": "#0F766E",
          "line-width": 4
        }
      });
    }
  }

  renderLegend() {
    const legend = document.createElement("div");
    legend.className = "map-legend";
    // Each swatch mirrors the ACTUAL marker shape used on the map (not a
    // generic dot standing in for it) so the legend never mismatches what's
    // drawn — this was the first source of visual confusion reported.
    legend.innerHTML = `
      <div class="legend-item">
        <span class="legend-swatch-center" aria-hidden="true">
          <svg viewBox="0 0 32 40" xmlns="http://www.w3.org/2000/svg">
            <path d="M16 0C7.16 0 0 7.16 0 16C0 26.5 16 40 16 40C16 40 32 26.5 32 16C32 7.16 24.84 0 16 0Z" fill="#E76F51" stroke="#FFFFFF" stroke-width="2"/>
            <path d="M16 8L18.47 13.01L24 13.81L20 17.71L20.94 23.21L16 20.61L11.06 23.21L12 17.71L8 13.81L13.53 13.01L16 8Z" fill="#FFFFFF"/>
          </svg>
        </span>
        <span>Center</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot-result" aria-hidden="true"></span>
        <span>Place</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot-selected" aria-hidden="true"></span>
        <span>Selected</span>
      </div>
    `;
    this.container.appendChild(legend);
  }

  renderFloatingControls() {
    const controls = document.createElement("div");
    controls.className = "map-floating-controls";

    controls.innerHTML = `
      <button class="map-control-btn" id="mapZoomIn" aria-label="Zoom in" title="Zoom in">+</button>
      <button class="map-control-btn" id="mapZoomOut" aria-label="Zoom out" title="Zoom out">−</button>
      <button class="map-control-btn" id="mapRecenter" aria-label="Recenter map" title="Fit visible places">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/></svg>
      </button>
    `;

    controls.querySelector("#mapZoomIn").addEventListener("click", () => this.map.zoomIn());
    controls.querySelector("#mapZoomOut").addEventListener("click", () => this.map.zoomOut());
    controls.querySelector("#mapRecenter").addEventListener("click", () => this.fitToVisible());

    this.container.appendChild(controls);
  }

  renderMarkers(center, places) {
    if (!this.map || !this.isLoaded) {
      this._pendingRender = { center, places };
      return;
    }

    // Clear old markers
    this.markers.forEach(m => m.remove());
    this.markers.clear();
    if (this.centerMarker) {
      this.centerMarker.remove();
      this.centerMarker = null;
    }

    const boundsPoints = [];

    // 1. Center / Search Origin Marker (Section 50.3: Coral pin with star)
    if (center && center.latitude && center.longitude) {
      const centerEl = document.createElement("div");
      centerEl.className = "center-marker";
      const centerLabel = center.kind === "user_location" ? "You are here" : "Search centre";
      centerEl.setAttribute("aria-label", `${centerLabel}: ${center.label}`);
      centerEl.setAttribute("title", `${centerLabel}: ${center.label}`);

      // Coral Pin with Star SVG
      centerEl.innerHTML = `
        <svg viewBox="0 0 32 40" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M16 0C7.16 0 0 7.16 0 16C0 26.5 16 40 16 40C16 40 32 26.5 32 16C32 7.16 24.84 0 16 0Z" fill="#E76F51" stroke="#FFFFFF" stroke-width="2"/>
          <path d="M16 8L18.47 13.01L24 13.81L20 17.71L20.94 23.21L16 20.61L11.06 23.21L12 17.71L8 13.81L13.53 13.01L16 8Z" fill="#FFFFFF"/>
        </svg>
      `;

      this.centerMarker = new maplibregl.Marker({ element: centerEl, anchor: "bottom" })
        .setLngLat([center.longitude, center.latitude])
        .addTo(this.map);

      boundsPoints.push([center.longitude, center.latitude]);
    }

    // 2. Result Markers (Section 50.3: Only validated coordinates become markers)
    places.forEach(place => {
      if (place.latitude === null || place.longitude === null) {
        return; // Place without valid coordinates does not get a marker
      }

      const markerBtn = document.createElement("button");
      markerBtn.className = "marker-btn";
      markerBtn.id = `marker-${place.id}`;
      markerBtn.setAttribute("aria-label", `Place: ${place.name}`);
      markerBtn.innerHTML = `<div class="result-marker" aria-hidden="true"></div>`;

      markerBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (this.onSelectPlaceCallback) {
          this.onSelectPlaceCallback(place);
        }
      });

      const marker = new maplibregl.Marker({ element: markerBtn })
        .setLngLat([place.longitude, place.latitude])
        .addTo(this.map);

      this.markers.set(place.id, marker);
      boundsPoints.push([place.longitude, place.latitude]);
    });

    // 3. Fit bounds
    if (boundsPoints.length > 0) {
      this.currentBounds = computeBounds(boundsPoints);
      this.fitToVisible();
    }

    // Spread any markers that land on top of each other (common for places
    // that are genuinely very close together, e.g. several cafés in the
    // same small market). fitToVisible()'s animation fires moveend/zoomend
    // when it completes, which re-triggers this — but also run it once
    // right away in case bounds didn't change (reduced-motion / single
    // marker / no animation) so declutter still happens immediately.
    this._declutterMarkers();
  }

  /**
   * Detects result markers whose on-screen pixel positions are within a
   * small radius of each other at the current zoom level, and nudges each
   * one apart in a small circle so every place stays individually visible
   * and clickable instead of rendering as one indistinguishable stack.
   * This only offsets the inner `.result-marker` dot (a child of the
   * element MapLibre itself positions) via a CSS transform — it never
   * touches the marker's real lng/lat, so routes, popups, and
   * accessibility labels still reflect the place's true location.
   */
  _declutterMarkers() {
    if (!this.map || !this.isLoaded || this.markers.size === 0) return;

    const COLLISION_PX = 22; // markers closer than this (in screen pixels) are considered overlapping
    const entries = Array.from(this.markers.entries()); // [[id, marker], ...]

    const points = entries.map(([id, marker]) => {
      const { x, y } = this.map.project(marker.getLngLat());
      return { id, marker, x, y };
    });

    const visited = new Set();
    const clusters = [];

    for (let i = 0; i < points.length; i++) {
      if (visited.has(points[i].id)) continue;
      const cluster = [points[i]];
      visited.add(points[i].id);

      for (let j = i + 1; j < points.length; j++) {
        if (visited.has(points[j].id)) continue;
        const dx = points[i].x - points[j].x;
        const dy = points[i].y - points[j].y;
        if (Math.sqrt(dx * dx + dy * dy) < COLLISION_PX) {
          cluster.push(points[j]);
          visited.add(points[j].id);
        }
      }
      clusters.push(cluster);
    }

    clusters.forEach(cluster => {
      if (cluster.length === 1) {
        // No collision: reset to its true, un-offset position. Set via CSS
        // custom properties (not `transform` directly) so the existing
        // hover/selected scale effects in map.css keep working on top of
        // this offset instead of being overwritten by it.
        const inner = cluster[0].marker.getElement().querySelector(".result-marker");
        if (inner) {
          inner.style.removeProperty("--declutter-x");
          inner.style.removeProperty("--declutter-y");
        }
        return;
      }

      // Arrange every marker in the cluster evenly around a small circle
      // so each one is independently visible and clickable. Radius grows
      // slightly with cluster size so larger clusters don't re-overlap.
      const radius = 14 + Math.min(cluster.length, 8) * 2;
      cluster.forEach((pt, idx) => {
        const angle = (idx / cluster.length) * 2 * Math.PI;
        const dx = Math.round(Math.cos(angle) * radius);
        const dy = Math.round(Math.sin(angle) * radius);
        const inner = pt.marker.getElement().querySelector(".result-marker");
        if (inner) {
          inner.style.setProperty("--declutter-x", `${dx}px`);
          inner.style.setProperty("--declutter-y", `${dy}px`);
        }
      });
    });
  }

  syncSelection(selectedPlace) {
    if (!this.map || !this.isLoaded) return;

    if (this.activePopup) {
      this.activePopup.remove();
      this.activePopup = null;
    }

    if (!selectedPlace) {
      // Clear route line
      this.clearRoute();
      // Restore all markers to un-dimmed state
      this.markers.forEach(m => {
        const el = m.getElement();
        el.classList.remove("selected", "dimmed");
      });
      return;
    }

    // Highlight selected marker; keep all other markers fully visible and usable (Section 17)
    this.markers.forEach((m, id) => {
      const el = m.getElement();
      el.classList.remove("dimmed");
      if (id === selectedPlace.id) {
        el.classList.add("selected");

        // Show popup on selected marker
        this.activePopup = new maplibregl.Popup({ offset: 16, closeButton: false })
          .setLngLat([selectedPlace.longitude, selectedPlace.latitude])
          .setHTML(`
            <div class="popup-title">${escapeHtml(selectedPlace.name)}</div>
            <div class="popup-meta">${escapeHtml(selectedPlace.service_type || selectedPlace.category || "Place")}</div>
          `)
          .addTo(this.map);

      } else {
        el.classList.remove("selected");
      }
    });


    // Center/pan smoothly to selected place if coordinates exist
    // (strict null check: a coordinate of exactly 0, e.g. near the prime
    // meridian, must not be treated as "missing" — Section 50.5)
    if (selectedPlace.latitude !== null && selectedPlace.longitude !== null &&
      selectedPlace.latitude !== undefined && selectedPlace.longitude !== undefined) {
      const prefersReducedMotion = window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      this.map.easeTo({
        center: [selectedPlace.longitude, selectedPlace.latitude],
        zoom: Math.max(this.map.getZoom(), 14.5),
        duration: prefersReducedMotion ? 0 : 400
      });
    }
  }

  drawRoute(routeData) {
    if (!this.map || !this.isLoaded) return;
    const source = this.map.getSource("route-source");
    if (!source) return;

    if (!routeData || !routeData.geometry) {
      this.clearRoute();
      return;
    }

    const feature = {
      type: "Feature",
      geometry: routeData.geometry,
      properties: {}
    };

    source.setData({
      type: "FeatureCollection",
      features: [feature]
    });

    // Adjust style if route is approximate (dashed line)
    if (routeData.is_approximate) {
      this.map.setPaintProperty("route-line", "line-dasharray", [2, 2]);
      this.map.setPaintProperty("route-line", "line-color", "#E76F51");
    } else {
      this.map.setPaintProperty("route-line", "line-dasharray", [1, 0]);
      this.map.setPaintProperty("route-line", "line-color", "#0F766E");
    }

    // Fit map to both endpoints with padding (Section 50.5)
    const coords = routeData.geometry.coordinates;
    if (coords && coords.length >= 2) {
      const bounds = computeBounds(coords);
      if (bounds) {
        const prefersReducedMotion = window.matchMedia &&
          window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        this.map.fitBounds(bounds, { padding: 60, maxZoom: 16, duration: prefersReducedMotion ? 0 : 400 });
      }
    }
  }

  clearRoute() {
    const source = this.map && this.map.getSource("route-source");
    if (source) {
      source.setData({ type: "FeatureCollection", features: [] });
    }
  }

  fitToVisible() {
    if (!this.map || !this.currentBounds) return;
    const prefersReducedMotion = window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.map.fitBounds(this.currentBounds, {
      padding: window.APP_CONFIG.MAX_BOUNDS_PADDING,
      maxZoom: 16,
      duration: prefersReducedMotion ? 0 : 400
    });
  }
}