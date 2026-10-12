/**
 * Shared Nearby Explorer Controller (Authoritative Section 50).
 * Powers Places Near You, Quiet Work Cafés, and 24/7 Medical Care from one single implementation.
 */

import { state } from "../state.js";
import { api } from "../api.js";
import { SharedMapComponent } from "./map.js";
import { renderPlaceCard } from "./cards.js";
import { renderFilterChips } from "./filter-chips.js";
import { renderLoadingSkeletons } from "./loader.js";
import { toast } from "./toast.js";
import { announceServiceReady, announceServiceReset } from "./review-widget.js";

const RATE_SERVICE_NAMES = {
  places: "Places Near You",
  cafes: "Quiet Work Cafés",
  medical: "24/7 Medical Care"
};
import { escapeHtml } from "../utils/formatters.js";

export class NearbyExplorerController {
  constructor(config) {
    this.config = config;
    this.mapComponent = null;
    this.routeAbortController = null;
    this.currentSearchAbort = null;
  }

  init() {
    // 1. Initialize Map
    this.mapComponent = new SharedMapComponent(this.config.mapContainerId, {
      onSelectPlace: (place) => this.handleSelectPlace(place)
    });
    this.mapComponent.init();

    // 2. Setup Form & Location Listeners
    this.setupEventListeners();

    // 3. Setup Esc key to deselect
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && state.selectedPlace) {
        state.clearSelection();
      }
    });

    // 4. No auto-search on page load — the user enters their own location
    // and searches explicitly (Section 50.6 & product rule: don't assume
    // a default city). Show a neutral prompt state until then.
    this.renderInitialPrompt();

    // 5. Session persistence + Generate New (Sections 19, 20, 22)
    this.setupGenerateNew();
    this.restoreFromSession();
  }

  // ---- Session state (temporary, per tab) — separate from persistent History ----
  get storageKey() {
    return `slg_${this.config.pageType}_state`;
  }

  saveSnapshot(snapshot) {
    try {
      sessionStorage.setItem(this.storageKey, JSON.stringify(snapshot));
    } catch (_) {}
  }

  loadSnapshot() {
    try {
      const raw = sessionStorage.getItem(this.storageKey);
      return raw ? JSON.parse(raw) : null;
    } catch (_) {
      return null;
    }
  }

  restoreFromSession() {
    const snap = this.loadSnapshot();
    if (snap) this.applySnapshot(snap);
  }

  /**
   * Rebuilds the full service UI (inputs, chips, cards, map markers, selection)
   * from a stored snapshot. Used by both session restore and History -> Restore.
   */
  applySnapshot(snap) {
    if (!snap) return;

    const input = document.getElementById(this.config.locationInputId);
    const label = snap.typed_location || snap.location || "";
    if (input && label) input.value = label;

    const radiusSelect = document.getElementById(this.config.radiusSelectId);
    if (radiusSelect && snap.radius_km) {
      const wanted = String(snap.radius_km);
      if (Array.from(radiusSelect.options).some(o => o.value === wanted)) {
        radiusSelect.value = wanted;
      }
    }

    // Older history records only stored {location, radius_km}: re-run that search.
    if (!Array.isArray(snap.places) || !snap.center) {
      if (label) {
        if (snap.latitude != null && snap.longitude != null) {
          this.performSearch(null, snap.latitude, snap.longitude);
        } else {
          this.performSearch(label);
        }
      }
      return;
    }

    this._lastCounts = snap.counts || {};
    state.setResults(snap.center, snap.places);

    const chipsContainer = document.getElementById(this.config.chipsContainerId);
    renderFilterChips(chipsContainer, this._lastCounts, () => this.renderVisibleResults());
    this.renderVisibleResults();
    this.updateResultsHeader(snap.places.length);
    this.announceRateState(snap.places.length > 0);

    if (snap.data_mode === "mock" && !state.bannerDismissed) {
      this.showSampleDataBanner();
    }

    if (snap.selected_place_id) {
      const sel = snap.places.find(p => p.id === snap.selected_place_id);
      if (sel) state.selectPlace(sel);
    }
  }

  persistSelection(place) {
    const snap = this.loadSnapshot();
    if (!snap) return;
    snap.selected_place_id = place ? place.id : null;
    this.saveSnapshot(snap);
  }

  setupGenerateNew() {
    const btn = document.getElementById("btnGenerateNew");
    if (btn) btn.addEventListener("click", () => this.generateNew());
  }

  /** Resets only THIS service's active input/result state. History is untouched. */
  generateNew() {
    if (this.currentSearchAbort) this.currentSearchAbort.abort();
    if (this.routeAbortController) this.routeAbortController.abort();
    try {
      sessionStorage.removeItem(this.storageKey);
    } catch (_) {}
    state.clearSelection();
    state.setResults(null, []);
    this._lastCounts = {};
    if (this.mapComponent) {
      this.mapComponent.renderMarkers(null, []);
      this.mapComponent.clearRoute();
    }
    const input = document.getElementById(this.config.locationInputId);
    if (input) {
      input.value = "";
      input.focus();
    }
    document.querySelectorAll(".sample-data-banner").forEach(b => b.remove());
    this.renderInitialPrompt();
  }

  renderInitialPrompt() {
    const cardsContainer = document.getElementById(this.config.resultsContainerId);
    if (cardsContainer) {
      cardsContainer.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1;">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <h3>Search for a location to get started</h3>
          <p>Enter a city or area above, or use your current location, to find nearby ${escapeHtml(this.config.emptyPromptLabel || "results")}.</p>
        </div>
      `;
    }
    const chipsContainer = document.getElementById(this.config.chipsContainerId);
    if (chipsContainer) chipsContainer.innerHTML = "";
    this.updateResultsHeader(0);
    this.announceRateState(false);
  }

  setupEventListeners() {
    const form = document.getElementById(this.config.searchFormId);
    if (form) {
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        const input = document.getElementById(this.config.locationInputId);
        this.performSearch(input ? input.value : "");
      });
    }

    const radiusSelect = document.getElementById(this.config.radiusSelectId);
    if (radiusSelect) {
      radiusSelect.addEventListener("change", () => {
        const input = document.getElementById(this.config.locationInputId);
        this.performSearch(input ? input.value : "");
      });
    }

    // "Use my location" button (Section 50.6: explicit permission & explanation)
    const btnUseLoc = document.getElementById(this.config.btnUseLocationId);
    if (btnUseLoc) {
      btnUseLoc.addEventListener("click", () => this.handleUseMyLocation());
    }

    // Subscribe to state selection changes to keep Map and Cards in sync
    state.subscribe("selection", (place) => {
      this.syncSelectionUI(place);
    });

    // Subscribe to state route changes
    state.subscribe("route", ({ route, isLoading }) => {
      this.renderRoutePanel(route, isLoading);
      if (route) {
        this.mapComponent.drawRoute(route);
      } else {
        this.mapComponent.clearRoute();
      }
    });
  }

  handleUseMyLocation() {
    if (!navigator.geolocation) {
      toast.error("Geolocation is not supported by your browser. Please type a city name.");
      return;
    }

    toast.info("Requesting your location to find nearby places…");

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        const input = document.getElementById(this.config.locationInputId);
        if (input) input.value = "Current Location";
        this.performSearch(null, lat, lon);
      },
      (err) => {
        let msg = "Location permission was denied or unavailable. You can type a city name instead.";
        if (err.code === 2) msg = "Location position unavailable. Please enter a city name.";
        else if (err.code === 3) msg = "Location request timed out. Please enter a city name.";
        toast.error(msg);
      },
      { timeout: 10000, enableHighAccuracy: true }
    );
  }

  announceRateState(hasResults) {
    const name = RATE_SERVICE_NAMES[this.config.pageType];
    if (!name) return;
    if (hasResults) announceServiceReady(name);
    else announceServiceReset(name);
  }

  async performSearch(typedLocation = "", lat = null, lon = null) {
    this.announceRateState(false);
    // Require an explicit location (typed, geolocated, or an already-set
    // search center from a prior search) before running a search — this
    // stops the radius/theme controls from silently falling back to the
    // backend's default demo city before the user has searched at all.
    const hasQuery = (typedLocation && typedLocation.trim()) || (lat !== null && lon !== null);
    if (!hasQuery && !state.center) {
      toast.error("Please enter a city or area, or use your location, to search.");
      return;
    }

    if (this.currentSearchAbort) {
      this.currentSearchAbort.abort();
    }
    this.currentSearchAbort = new AbortController();

    const cardsContainer = document.getElementById(this.config.resultsContainerId);
    renderLoadingSkeletons(cardsContainer, 6);

    const radiusSelect = document.getElementById(this.config.radiusSelectId);
    const radius = radiusSelect ? parseFloat(radiusSelect.value) : 3.0;

    const payload = {
      location: typedLocation || undefined,
      latitude: lat !== null ? lat : undefined,
      longitude: lon !== null ? lon : undefined,
      radius_km: radius,
      limit: 30
    };

    try {
      const data = await this.config.fetchApiMethod(payload, this.currentSearchAbort.signal);

      // Extract places from response envelope (places, cafes, or medical)
      const placesList = data.places || data.cafes || data.medical || [];
      const countsObj = data.counts_by_category || data.counts_by_amenity || data.counts_by_service_type || {};

      // Update Shared App State
      this._lastCounts = countsObj;
      state.setResults(data.center, placesList);

      // Render Filter Chips
      const chipsContainer = document.getElementById(this.config.chipsContainerId);
      renderFilterChips(chipsContainer, countsObj, () => {
        this.renderVisibleResults();
      });

      // Render Cards & Map Markers
      this.renderVisibleResults();

      // Update Results Header Count
      this.updateResultsHeader(placesList.length);
      this.announceRateState(placesList.length > 0);

      // Sample Data Banner (Section 50.7)
      if (data.data_mode === "mock" && !state.bannerDismissed) {
        this.showSampleDataBanner();
      }

      // Auto-save to history (Section 13 & 23) — mirrors Itinerary/Area behavior
      const centerLabel = data.center ? data.center.label : (typedLocation || "your location");
      const snapshot = {
        location: centerLabel,
        typed_location: typedLocation || (lat !== null ? "Current Location" : ""),
        latitude: lat,
        longitude: lon,
        radius_km: radius,
        center: data.center,
        places: placesList,
        counts: countsObj,
        data_mode: data.data_mode,
        selected_place_id: null,
        saved_at: new Date().toISOString()
      };
      this.saveSnapshot(snapshot);

      api.createHistory({
        feature_type: this.config.pageType,
        title: `${this.config.historyTitlePrefix || "Search"}: ${centerLabel}`,
        preview: `${placesList.length} result${placesList.length === 1 ? "" : "s"} within ${radius} km`,
        payload: snapshot
      }).catch(() => {});

    } catch (err) {
      if (err.name === "AbortError") return;
      console.error("Search error:", err);
      if (cardsContainer) {
        cardsContainer.innerHTML = `
          <div class="error-state" style="grid-column: 1 / -1;">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <h3>Unable to load results</h3>
            <p>${escapeHtml(err.message || "Please check your network and try again.")}</p>
            <button class="btn btn-primary btn-sm" id="btnRetrySearch">Try Again</button>
          </div>
        `;
        const retryBtn = cardsContainer.querySelector("#btnRetrySearch");
        if (retryBtn) retryBtn.addEventListener("click", () => this.performSearch(typedLocation, lat, lon));
      }
    }
  }

  renderVisibleResults() {
    const visiblePlaces = state.getVisiblePlaces();
    const cardsContainer = document.getElementById(this.config.resultsContainerId);

    // Update map markers
    this.mapComponent.renderMarkers(state.center, visiblePlaces);

    if (!cardsContainer) return;
    cardsContainer.innerHTML = "";

    if (visiblePlaces.length === 0) {
      cardsContainer.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1;">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m10 15 4-6"/><path d="m14 15-4-6"/></svg>
          <h3>No places match your active filters</h3>
          <p>Try selecting other categories or show all places.</p>
          <button class="btn btn-primary btn-sm" id="btnResetFilters">Show All</button>
        </div>
      `;
      const resetBtn = cardsContainer.querySelector("#btnResetFilters");
      if (resetBtn) {
        resetBtn.addEventListener("click", () => {
          state.setFilter("all");
          const chipsContainer = document.getElementById(this.config.chipsContainerId);
          renderFilterChips(chipsContainer, this._lastCounts, () => this.renderVisibleResults());
          this.renderVisibleResults();
        });
      }
      this.updateResultsHeader(0);
      return;
    }

    // Render Cards
    visiblePlaces.forEach(place => {
      const isSelected = state.selectedPlace && state.selectedPlace.id === place.id;
      const cardEl = renderPlaceCard(place, isSelected, (p) => this.handleSelectPlace(p));
      cardsContainer.appendChild(cardEl);
    });

    this.updateResultsHeader(visiblePlaces.length);
  }

  updateResultsHeader(visibleCount) {
    const badge = document.getElementById("resultsCountBadge");
    if (badge) {
      badge.textContent = `${visibleCount} place${visibleCount === 1 ? "" : "s"}`;
    }
  }

  handleSelectPlace(place) {
    state.selectPlace(place);
  }

  syncSelectionUI(selectedPlace) {
    this.persistSelection(selectedPlace);

    // 1. Sync Map
    this.mapComponent.syncSelection(selectedPlace);

    // 2. Sync Cards highlight
    document.querySelectorAll(".place-card").forEach(c => {
      c.classList.remove("selected");
      c.removeAttribute("aria-current");
    });

    if (selectedPlace) {
      const selectedCard = document.getElementById(`card-${selectedPlace.id}`);
      if (selectedCard) {
        selectedCard.classList.add("selected");
        selectedCard.setAttribute("aria-current", "true");
        // Scroll card into view smoothly
        selectedCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }

      // Fetch route if place has valid coordinates and center exists
      // (strict null check: a coordinate of exactly 0 is valid and must not
      // be treated as "missing" — Section 50.5)
      const hasValidCoords = selectedPlace.latitude !== null && selectedPlace.longitude !== null &&
        selectedPlace.latitude !== undefined && selectedPlace.longitude !== undefined;
      if (hasValidCoords && state.center) {
        this.fetchRouteForPlace(selectedPlace);
      } else {
        state.setRoute(null);
      }
    } else {
      state.setRoute(null);
    }
  }

  async fetchRouteForPlace(place) {
    if (this.routeAbortController) {
      this.routeAbortController.abort();
    }
    this.routeAbortController = new AbortController();

    state.setRoute(null, true); // Route is loading

    try {
      const route = await api.getRoute(
        { lat: state.center.latitude, lon: state.center.longitude },
        { lat: place.latitude, lon: place.longitude },
        state.travelMode,
        this.routeAbortController.signal
      );
      state.setRoute(route, false);
    } catch (err) {
      if (err.name === "AbortError") return;
      console.warn("Route fetch error:", err);
      state.setRoute(null, false);
    }
  }

  renderRoutePanel(route, isLoading) {
    const panel = document.getElementById(this.config.routePanelId);
    if (!panel) return;

    if (!route && !isLoading) {
      panel.style.display = "none";
      panel.innerHTML = "";
      return;
    }

    panel.style.display = "flex";

    if (isLoading) {
      panel.innerHTML = `
        <div class="route-summary-info">
          <span class="route-badge">Calculating route…</span>
          <span class="route-summary-text text-muted">Finding best ${state.travelMode} path…</span>
        </div>
      `;
      return;
    }

    const isApprox = route.is_approximate;
    const badgeText = isApprox ? "Straight-line Fallback" : route.mode.toUpperCase();
    const destName = state.selectedPlace ? state.selectedPlace.name : "Destination";
    const destCoords = state.selectedPlace ? `${state.selectedPlace.latitude},${state.selectedPlace.longitude}` : "";

    panel.innerHTML = `
      <div class="route-summary-info">
        <span class="route-badge" style="${isApprox ? 'background:var(--color-accent-light);color:var(--color-accent);' : ''}">${badgeText}</span>
        <span class="route-summary-text">${escapeHtml(route.summary)} to ${escapeHtml(destName)}</span>
      </div>
      <div class="route-actions">
        <div class="mode-toggle-group">
          <button class="mode-btn ${state.travelMode === 'walking' ? 'active' : ''}" id="btnModeWalk">Walk</button>
          <button class="mode-btn ${state.travelMode === 'driving' ? 'active' : ''}" id="btnModeDrive">Drive</button>
        </div>
        <a href="https://www.google.com/maps/dir/?api=1&destination=${destCoords}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" aria-label="Open directions in external maps">
          Get directions ↗
        </a>
        <button class="btn-close-route" id="btnCloseRoute" aria-label="Clear route and selection">&times;</button>
      </div>
    `;

    panel.querySelector("#btnModeWalk").addEventListener("click", () => {
      state.setTravelMode("walking");
      if (state.selectedPlace) this.fetchRouteForPlace(state.selectedPlace);
    });

    panel.querySelector("#btnModeDrive").addEventListener("click", () => {
      state.setTravelMode("driving");
      if (state.selectedPlace) this.fetchRouteForPlace(state.selectedPlace);
    });

    panel.querySelector("#btnCloseRoute").addEventListener("click", () => {
      state.clearSelection();
    });
  }

  showSampleDataBanner() {
    const existing = document.querySelector(".sample-data-banner");
    if (existing) return;

    const banner = document.createElement("div");
    banner.className = "sample-data-banner";
    banner.setAttribute("role", "status");

    banner.innerHTML = `
      <div class="banner-content">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
        <span><strong>Sample data mode:</strong> Showing verified demonstration data. Names, ratings and contact details are illustrative.</span>
      </div>
      <button class="dismiss-btn" id="dismissSampleBanner" aria-label="Dismiss banner">&times;</button>
    `;

    document.body.prepend(banner);

    banner.querySelector("#dismissSampleBanner").addEventListener("click", () => {
      state.dismissBanner();
      banner.remove();
    });
  }
}
