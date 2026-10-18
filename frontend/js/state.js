/**
 * AI Powered Travel Companion - State Management
 * Single source of truth for UI state, active filters, selection, and theme.
 */

class AppState {
  constructor() {
    this.theme = localStorage.getItem("slg_theme") || "warm";
    this.travelMode = localStorage.getItem("slg_travel_mode") || "walking";
    this.bannerDismissed = sessionStorage.getItem("slg_banner_dismissed") === "true";

    this.center = null;
    this.allPlaces = [];
    this.activeFilters = new Set(["all"]);
    this.selectedPlace = null;
    this.currentRoute = null;
    this.isRouteLoading = false;

    this.listeners = new Map();
  }

  // Subscribe to changes on a specific topic
  subscribe(topic, callback) {
    if (!this.listeners.has(topic)) {
      this.listeners.set(topic, new Set());
    }
    this.listeners.get(topic).add(callback);
    return () => this.listeners.get(topic).delete(callback);
  }

  notify(topic, data) {
    if (this.listeners.has(topic)) {
      this.listeners.get(topic).forEach(cb => {
        try {
          cb(data);
        } catch (err) {
          console.error(`Error in state listener for topic '${topic}':`, err);
        }
      });
    }
  }

  // Theme Management
  setTheme(themeName) {
    this.theme = themeName;
    localStorage.setItem("slg_theme", themeName);
    document.documentElement.setAttribute("data-theme", themeName);
    this.notify("theme", themeName);
  }

  // Travel Mode (walking vs driving)
  setTravelMode(mode) {
    this.travelMode = mode;
    localStorage.setItem("slg_travel_mode", mode);
    this.notify("travelMode", mode);
  }

  // Dismiss sample banner
  dismissBanner() {
    this.bannerDismissed = true;
    sessionStorage.setItem("slg_banner_dismissed", "true");
    this.notify("bannerDismissed", true);
  }

  // Set Search Results
  setResults(center, places) {
    this.center = center;
    this.allPlaces = places || [];
    this.activeFilters = new Set(["all"]);
    this.selectedPlace = null;
    this.currentRoute = null;
    this.notify("results", { center: this.center, places: this.allPlaces });
  }

  // Filter Management
  setFilter(filterKey, isSingleSelect = false) {
    if (filterKey === "all") {
      this.activeFilters.clear();
      this.activeFilters.add("all");
    } else {
      this.activeFilters.delete("all");
      if (this.activeFilters.has(filterKey)) {
        this.activeFilters.delete(filterKey);
      } else {
        if (isSingleSelect) {
          this.activeFilters.clear();
        }
        this.activeFilters.add(filterKey);
      }
      if (this.activeFilters.size === 0) {
        this.activeFilters.add("all");
      }
    }

    // Check if currently selected place is filtered out
    if (this.selectedPlace) {
      const isVisible = this.isPlaceVisible(this.selectedPlace);
      if (!isVisible) {
        this.clearSelection();
      }
    }

    this.notify("filters", this.activeFilters);
  }

  isPlaceVisible(place) {
    if (this.activeFilters.has("all")) return true;
    const cat = (place.category || place.service_type || "").toLowerCase();
    if (this.activeFilters.has(cat)) return true;

    // Check amenities if cafe
    if (place.amenities && Array.isArray(place.amenities)) {
      const activeAmenities = Array.from(this.activeFilters).filter(f => f !== "all");
      return activeAmenities.every(a => place.amenities.map(x => x.toLowerCase()).includes(a.toLowerCase()));
    }
    return false;
  }

  getVisiblePlaces() {
    return this.allPlaces.filter(p => this.isPlaceVisible(p));
  }

  // Selection
  selectPlace(place) {
    if (this.selectedPlace && this.selectedPlace.id === place.id) {
      // Toggle off when clicking same place
      this.clearSelection();
      return;
    }
    this.selectedPlace = place;
    this.notify("selection", place);
  }

  clearSelection() {
    this.selectedPlace = null;
    this.currentRoute = null;
    this.isRouteLoading = false;
    this.notify("selection", null);
  }

  setRoute(route, isLoading = false) {
    this.currentRoute = route;
    this.isRouteLoading = isLoading;
    this.notify("route", { route, isLoading });
  }
}

export const state = new AppState();
