/**
 * Tests for the unified user-scoped workspace persistence layer in frontend/js/state.js.
 * Run with: node frontend/tests/workspace-persistence.test.mjs
 */

import assert from "node:assert/strict";

class MemoryStorage {
  constructor({ throwOnSet = false } = {}) {
    this._map = new Map();
    this.throwOnSet = throwOnSet;
  }
  get length() { return this._map.size; }
  key(i) { return Array.from(this._map.keys())[i] ?? null; }
  getItem(k) { return this._map.has(k) ? this._map.get(k) : null; }
  setItem(k, v) {
    if (this.throwOnSet) {
      const err = new Error("QuotaExceededError");
      err.name = "QuotaExceededError";
      throw err;
    }
    this._map.set(k, String(v));
  }
  removeItem(k) { this._map.delete(k); }
  clear() { this._map.clear(); }
}

const winListeners = new Map();
const docListeners = new Map();
const addListener = (map, ev, fn) => {
  if (!map.has(ev)) map.set(ev, new Set());
  map.get(ev).add(fn);
};
const removeListener = (map, ev, fn) => { map.get(ev)?.delete(fn); };
const emit = (map, ev) => { map.get(ev)?.forEach(fn => fn()); };

const ls = new MemoryStorage();
const ss = new MemoryStorage();

globalThis.localStorage = ls;
globalThis.sessionStorage = ss;
globalThis.window = {
  addEventListener: (ev, fn) => addListener(winListeners, ev, fn),
  removeEventListener: (ev, fn) => removeListener(winListeners, ev, fn),
};
globalThis.document = {
  visibilityState: "visible",
  documentElement: { setAttribute() {} },
  addEventListener: (ev, fn) => addListener(docListeners, ev, fn),
  removeEventListener: (ev, fn) => removeListener(docListeners, ev, fn),
};

const {
  workspaceKey,
  setWorkspaceScope,
  getWorkspaceScope,
  hasResolvedWorkspaceScope,
  saveServiceState,
  loadServiceState,
  clearServiceState,
  clearUserWorkspace,
  setExplicitServiceHandoff,
  createServicePersister,
} = await import("../js/state.js");

// 0. Before auth resolves on a fresh tab, hasResolvedWorkspaceScope() is false
assert.equal(hasResolvedWorkspaceScope(), false);

// 1. User-scoped versioned key format & cross-user isolation
setWorkspaceScope("user-alice");
assert.equal(hasResolvedWorkspaceScope(), true);
assert.equal(getWorkspaceScope(), "user-alice");
assert.equal(workspaceKey("itinerary"), "travel_workspace:v1:user-alice:itinerary");

saveServiceState("itinerary", { source: "Delhi", destination: "Goa", currentStep: 5 });
saveServiceState("places", { typed_location: "Connaught Place", radius_km: 5 });
assert.deepEqual(loadServiceState("itinerary"), { source: "Delhi", destination: "Goa", currentStep: 5 });

// Switching to another user must NOT see Alice's data
setWorkspaceScope("user-bob");
assert.equal(loadServiceState("itinerary"), null);
assert.equal(loadServiceState("places"), null);
saveServiceState("itinerary", { source: "Mumbai", destination: "Jaipur" });

// Switching back to Alice sees Alice's data intact
setWorkspaceScope("user-alice");
assert.equal(loadServiceState("itinerary").destination, "Goa");

// 2. Single-service clear does not affect other services
clearServiceState("itinerary");
assert.equal(loadServiceState("itinerary"), null);
assert.equal(loadServiceState("places").typed_location, "Connaught Place");

// 3. Explicit handoff (History Restore / Saved Session Resume) wins over cached state
saveServiceState("area", { area_input: "Old Area", area_name: "Old Area" });
setExplicitServiceHandoff("area", { area_input: "Soho", area_name: "Soho" }, { legacySessionKey: "slg_area_state" });
const restoredArea = loadServiceState("area", { legacySessionKey: "slg_area_state", consumeHandoff: true });
assert.equal(restoredArea.area_name, "Soho");
// Also promoted into active workspace for future loads
assert.equal(loadServiceState("area").area_name, "Soho");

// 4. Guest-to-login continuity when slg_<service>_guest_unsaved === "1"
saveServiceState("cafes", { location: "Old Logged-in Cafe" });
ss.setItem("slg_cafes_guest_unsaved", "1");
ss.setItem("slg_cafes_state", JSON.stringify({ location: "Fresh Guest Cafe", places: [{ id: "1" }] }));
const guestCafes = loadServiceState("cafes", { legacySessionKey: "slg_cafes_state" });
assert.equal(guestCafes.location, "Fresh Guest Cafe");
ss.removeItem("slg_cafes_guest_unsaved");

// 5. QuotaExceededError falls back safely to sessionStorage
ls.throwOnSet = true;
const ok = saveServiceState("reviews", { activeFilter: "Area Guide", draft: { rating: 4, comment: "Great!" } });
assert.equal(ok, true);
assert.equal(loadServiceState("reviews").activeFilter, "Area Guide");
ls.throwOnSet = false;

// 6. Malformed JSON does not crash and returns null
ls.setItem(workspaceKey("history"), "{broken json!!");
assert.equal(loadServiceState("history"), null);

// 7. createServicePersister flushes immediately on visibilitychange (hidden) and pagehide
let currentText = "Draft comment";
const persister = createServicePersister("review_widget", () => ({ comment: currentText }), { debounceMs: 5000 });
persister.scheduleSave();
assert.equal(loadServiceState("review_widget"), null); // still debounced
globalThis.document.visibilityState = "hidden";
emit(docListeners, "visibilitychange");
assert.equal(loadServiceState("review_widget").comment, "Draft comment");

currentText = "Updated before unload";
emit(winListeners, "pagehide");
assert.equal(loadServiceState("review_widget").comment, "Updated before unload");
persister.dispose();

// 8. Logout cleanup wipes ONLY the active user's workspace, preserving other users' localStorage
clearUserWorkspace();
assert.equal(loadServiceState("places"), null);
setWorkspaceScope("user-bob");
assert.equal(loadServiceState("itinerary").destination, "Jaipur");

console.log("workspace persistence: all assertions passed");
