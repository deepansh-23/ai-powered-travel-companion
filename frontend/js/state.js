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
    this._amenityKeys = new Set();           // every amenity name that appears, so chips can be told apart from types
    this.allPlaces.forEach(p => (Array.isArray(p.amenities) ? p.amenities : []).forEach(a => this._amenityKeys.add(String(a).toLowerCase())));
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

  // Chips are of two kinds: a type (category on Places, service type on Medical) and an amenity (Cafes).
  // Several type chips mean "any of these types"; several amenity chips mean "has all of these amenities".
  // If both kinds are active, a place must satisfy both.
  isPlaceVisible(place) {
    if (this.activeFilters.has("all")) return true;
    const active = Array.from(this.activeFilters).filter(f => f !== "all");
    const types = [place.category, place.service_type].filter(Boolean).map(x => String(x).toLowerCase());
    const amenities = Array.isArray(place.amenities) ? place.amenities.map(x => String(x).toLowerCase()) : [];
    const amenityKeys = this._amenityKeys || new Set();
    const wantedAmenities = active.filter(f => amenityKeys.has(f));
    const wantedTypes = active.filter(f => !amenityKeys.has(f));
    const typeOk = wantedTypes.length === 0 || wantedTypes.some(f => types.includes(f));
    const amenityOk = wantedAmenities.every(f => amenities.includes(f));
    return typeOk && amenityOk;
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

// ============================================================================
// Unified, User-Scoped Workspace Persistence (Cross-Page & Cross-Tab)
// Keys: travel_workspace:v1:<user_id_or_guest>:<service_name>
// ============================================================================

export const WORKSPACE_VERSION = "v1";
const WORKSPACE_PREFIX = `travel_workspace:${WORKSPACE_VERSION}:`;
const SCOPE_HINT_KEY = "slg_workspace_scope";
const HANDOFF_PREFIX = "travel_workspace_handoff:";

let _activeScope = null;

function _safeGet(storage, key) {
  try {
    return storage ? storage.getItem(key) : null;
  } catch (_) {
    return null;
  }
}

function _safeSet(storage, key, val) {
  try {
    if (!storage) return false;
    storage.setItem(key, val);
    return true;
  } catch (_) {
    return false;
  }
}

function _safeRemove(storage, key) {
  try {
    if (storage) storage.removeItem(key);
  } catch (_) {}
}

function _getLocalStorage() {
  try { return typeof localStorage !== "undefined" ? localStorage : null; } catch (_) { return null; }
}

function _getSessionStorage() {
  try { return typeof sessionStorage !== "undefined" ? sessionStorage : null; } catch (_) { return null; }
}

function _normalizeScope(scope) {
  const clean = String(scope || "").trim().replace(/[^A-Za-z0-9_.-]/g, "_");
  return clean || "guest";
}

/** Return true if the workspace scope is already known (set by auth or cached in this tab). */
export function hasResolvedWorkspaceScope() {
  if (_activeScope) return true;
  if (typeof window !== "undefined" && window.__slgWorkspaceScope) return true;
  return !!_safeGet(_getSessionStorage(), SCOPE_HINT_KEY);
}

/** Return the active workspace scope (<user_id> or "guest"). */
export function getWorkspaceScope() {
  if (_activeScope) return _activeScope;
  if (typeof window !== "undefined" && window.__slgWorkspaceScope) {
    _activeScope = _normalizeScope(window.__slgWorkspaceScope);
    return _activeScope;
  }
  const hint = _safeGet(_getSessionStorage(), SCOPE_HINT_KEY);
  return hint ? _normalizeScope(hint) : "guest";
}

/** Set the active workspace scope once auth resolves (user id or "guest"). */
export function setWorkspaceScope(scope) {
  const normalized = _normalizeScope(scope);
  const changed = _activeScope !== normalized;
  _activeScope = normalized;
  if (typeof window !== "undefined") {
    window.__slgWorkspaceScope = normalized;
  }
  _safeSet(_getSessionStorage(), SCOPE_HINT_KEY, normalized);
  return changed;
}

/** Build the versioned, user-scoped storage key for a service. */
export function workspaceKey(serviceKey, scope = null) {
  const s = scope ? _normalizeScope(scope) : getWorkspaceScope();
  return `${WORKSPACE_PREFIX}${s}:${serviceKey}`;
}

/**
 * Save state for a service into user-scoped localStorage (falling back to sessionStorage
 * on QuotaExceededError or restricted environments).
 */
export function saveServiceState(serviceKey, data, { merge = false, legacySessionKey = null } = {}) {
  if (!serviceKey) return false;
  const ls = _getLocalStorage();
  const ss = _getSessionStorage();
  const key = workspaceKey(serviceKey);

  let payload = data;
  if (merge && data && typeof data === "object" && !Array.isArray(data)) {
    const existing = loadServiceState(serviceKey, { legacySessionKey, consumeHandoff: false });
    if (existing && typeof existing === "object" && !Array.isArray(existing)) {
      payload = { ...existing, ...data };
    }
  }

  let serialized;
  try {
    serialized = JSON.stringify(payload);
  } catch (_) {
    return false;
  }

  let ok = _safeSet(ls, key, serialized);
  if (!ok) {
    // Fallback to sessionStorage if localStorage quota is exceeded or blocked
    ok = _safeSet(ss, key, serialized);
  }
  if (legacySessionKey) {
    _safeSet(ss, legacySessionKey, serialized);
  }
  return ok;
}

/**
 * Load persisted workspace state for a service.
 * Priority:
 *   1. One-time explicit handoff (e.g., History -> Restore or Saved Sessions -> Resume)
 *   2. User-scoped localStorage (cross-tab & cross-page)
 *   3. User-scoped sessionStorage fallback
 *   4. Optional legacy sessionStorage key (backward compatibility / guest-to-login continuity)
 */
export function loadServiceState(serviceKey, { legacySessionKey = null, consumeHandoff = true } = {}) {
  if (!serviceKey) return null;
  const ls = _getLocalStorage();
  const ss = _getSessionStorage();

  const parse = (raw) => {
    if (!raw) return null;
    try { return JSON.parse(raw); } catch (_) { return null; }
  };

  // 1. Explicit navigation handoff wins over cached workspace state
  const handoffKey = `${HANDOFF_PREFIX}${serviceKey}`;
  const handoffRaw = _safeGet(ss, handoffKey);
  if (handoffRaw) {
    const parsed = parse(handoffRaw);
    if (consumeHandoff) _safeRemove(ss, handoffKey);
    if (parsed !== null) {
      // Promote explicit selection into the user's active workspace
      saveServiceState(serviceKey, parsed, { legacySessionKey });
      return parsed;
    }
  }

  // 1b. Guest-to-login continuity: if the visitor just logged in to save a guest result, honor that snapshot
  if (legacySessionKey && _safeGet(ss, `slg_${serviceKey}_guest_unsaved`) === "1") {
    const guestSnap = parse(_safeGet(ss, legacySessionKey));
    if (guestSnap !== null) return guestSnap;
  }

  // 2. User-scoped localStorage (survives page navigations, reloads, and new tabs)
  const key = workspaceKey(serviceKey);
  const fromLs = parse(_safeGet(ls, key));
  if (fromLs !== null) return fromLs;

  // 3. User-scoped sessionStorage fallback
  const fromSs = parse(_safeGet(ss, key));
  if (fromSs !== null) return fromSs;

  // 4. Legacy sessionStorage key fallback
  if (legacySessionKey) {
    const fromLegacy = parse(_safeGet(ss, legacySessionKey));
    if (fromLegacy !== null) return fromLegacy;
  }

  return null;
}

/** Clear persisted state for a single service without affecting other services. */
export function clearServiceState(serviceKey, { legacySessionKey = null } = {}) {
  if (!serviceKey) return;
  const ls = _getLocalStorage();
  const ss = _getSessionStorage();
  const key = workspaceKey(serviceKey);
  _safeRemove(ls, key);
  _safeRemove(ss, key);
  _safeRemove(ss, `${HANDOFF_PREFIX}${serviceKey}`);
  if (legacySessionKey) {
    _safeRemove(ss, legacySessionKey);
  }
}

/** Clear all workspace keys belonging to the active (or specified) user scope. */
export function clearUserWorkspace(scope = null) {
  const targetPrefix = `${WORKSPACE_PREFIX}${scope ? _normalizeScope(scope) : getWorkspaceScope()}:`;
  const wipe = (storage) => {
    if (!storage) return;
    try {
      const keys = [];
      for (let i = 0; i < storage.length; i++) {
        const k = storage.key(i);
        if (k && (k.startsWith(targetPrefix) || k.startsWith(HANDOFF_PREFIX) || k === SCOPE_HINT_KEY)) {
          keys.push(k);
        }
      }
      keys.forEach(k => _safeRemove(storage, k));
    } catch (_) {}
  };
  wipe(_getLocalStorage());
  wipe(_getSessionStorage());
  if (!scope) {
    _activeScope = null;
    if (typeof window !== "undefined") window.__slgWorkspaceScope = null;
  }
}

/**
 * Mark an explicit handoff (History -> Restore or Saved Sessions -> Resume) so the
 * destination page loads this exact state instead of older cached workspace data.
 */
export function setExplicitServiceHandoff(serviceKey, data, { legacySessionKey = null } = {}) {
  if (!serviceKey) return false;
  const ss = _getSessionStorage();
  let serialized;
  try {
    serialized = JSON.stringify(data);
  } catch (_) {
    return false;
  }
  _safeSet(ss, `${HANDOFF_PREFIX}${serviceKey}`, serialized);
  saveServiceState(serviceKey, data, { legacySessionKey });
  return true;
}

/** Check whether a service currently has an unconsumed explicit handoff pending. */
export function hasExplicitServiceHandoff(serviceKey) {
  return !!_safeGet(_getSessionStorage(), `${HANDOFF_PREFIX}${serviceKey}`);
}

/**
 * Creates a debounced workspace persister with automatic lifecycle flush on
 * pagehide, beforeunload, and visibilitychange (hidden).
 */
export function createServicePersister(serviceKey, collectFn, { debounceMs = 250, legacySessionKey = null, shouldSave = null } = {}) {
  let timer = null;
  let disposed = false;

  const saveNow = () => {
    if (disposed) return false;
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    try {
      if (shouldSave && !shouldSave()) return false;
      const data = collectFn();
      if (data === undefined || data === null) return false;
      return saveServiceState(serviceKey, data, { legacySessionKey });
    } catch (_) {
      return false;
    }
  };

  const scheduleSave = () => {
    if (disposed) return;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      saveNow();
    }, debounceMs);
  };

  const clear = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    clearServiceState(serviceKey, { legacySessionKey });
  };

  const onHide = () => {
    if (typeof document !== "undefined" && document.visibilityState === "hidden") {
      saveNow();
    }
  };
  const onUnload = () => saveNow();

  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("pagehide", onUnload);
    window.addEventListener("beforeunload", onUnload);
  }
  if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
    document.addEventListener("visibilitychange", onHide);
  }

  const dispose = () => {
    disposed = true;
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    if (typeof window !== "undefined" && typeof window.removeEventListener === "function") {
      window.removeEventListener("pagehide", onUnload);
      window.removeEventListener("beforeunload", onUnload);
    }
    if (typeof document !== "undefined" && typeof document.removeEventListener === "function") {
      document.removeEventListener("visibilitychange", onHide);
    }
  };

  return { scheduleSave, saveNow, clear, dispose };
}
