// Places / cafes / medical filter chips: state.isPlaceVisible and setFilter behaviour.
import assert from "node:assert/strict";

const store = new Map();
globalThis.sessionStorage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) };
globalThis.localStorage = globalThis.sessionStorage;
globalThis.window = globalThis.window || { addEventListener() {}, matchMedia: () => ({ matches: false, addEventListener() {} }) };
globalThis.document = globalThis.document || { documentElement: { setAttribute() {}, getAttribute() { return null; } }, addEventListener() {} };

const { state } = await import("../js/state.js");
const names = (list) => list.map((p) => p.name).sort();
const center = { latitude: 1, longitude: 1, label: "x", kind: "search_area" };

// ---------------- Places Near You: several category chips mean "any of these"
const places = [
  { id: "1", name: "Fort", category: "attraction" }, { id: "2", name: "Museum A", category: "museum" },
  { id: "3", name: "Bistro", category: "restaurant" }, { id: "4", name: "Mall", category: "shopping" },
  { id: "5", name: "Museum B", category: "Museum" },
];
state.setResults(center, places);
assert.equal(state.getVisiblePlaces().length, 5);
state.setFilter("museum");
assert.deepEqual(names(state.getVisiblePlaces()), ["Museum A", "Museum B"]);          // case does not matter
state.setFilter("restaurant");
assert.deepEqual(names(state.getVisiblePlaces()), ["Bistro", "Museum A", "Museum B"]);  // OR across categories
state.setFilter("museum");                                                              // toggle one off
assert.deepEqual(names(state.getVisiblePlaces()), ["Bistro"]);
state.setFilter("restaurant");                                                          // nothing selected: back to All
assert.ok(state.activeFilters.has("all") && state.getVisiblePlaces().length === 5);
state.setFilter("all");

// ---------------- Medical: chips are SERVICE TYPES even though each place also has a (different) category
const medical = [
  { id: "m1", name: "City Hospital", category: "hospital", service_type: "24/7 hospitals" },
  { id: "m2", name: "Night Pharmacy", category: "pharmacy", service_type: "Late-night pharmacies" },
  { id: "m3", name: "Care Clinic", category: "clinic", service_type: "Clinics" },
];
state.setResults(center, medical);
state.setFilter("24/7 hospitals");
assert.deepEqual(names(state.getVisiblePlaces()), ["City Hospital"]);
state.setFilter("late-night pharmacies");
assert.deepEqual(names(state.getVisiblePlaces()), ["City Hospital", "Night Pharmacy"]);

// ---------------- Cafes: several amenity chips mean "has all of these"
const cafes = [
  { id: "c1", name: "Quiet", category: "cafe", amenities: ["wifi", "power_outlets", "quiet"] },
  { id: "c2", name: "Wifi Only", category: "cafe", amenities: ["wifi"] },
  { id: "c3", name: "Plain", category: "cafe", amenities: [] },
];
state.setResults(center, cafes);
state.setFilter("wifi");
assert.deepEqual(names(state.getVisiblePlaces()), ["Quiet", "Wifi Only"]);
state.setFilter("power_outlets");
assert.deepEqual(names(state.getVisiblePlaces()), ["Quiet"]);                          // AND across amenities
state.setFilter("all");
assert.equal(state.getVisiblePlaces().length, 3);

// ---------------- a selected place that a new filter hides is deselected
state.setResults(center, places);
state.selectPlace(places[0]);
assert.ok(state.selectedPlace);
state.setFilter("museum");
assert.equal(state.selectedPlace, null);

console.log("nearby filters: all assertions passed");
