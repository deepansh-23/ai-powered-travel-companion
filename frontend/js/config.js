/**
 * Smart Local Guide - Public Frontend Configuration
 * Contains non-secret settings only (Section 50.3 & 50.12).
 * Never contains secret API keys.
 */

window.APP_CONFIG = {
  // Backend API URL (auto-detects origin or falls back to port 8000)
  API_BASE_URL: window.location.port === "8000" || window.location.port === ""
    ? "" 
    : "http://127.0.0.1:8000",

  // Basemap style URLs (Keyless OpenStreetMap vector tiles via CARTO)
  MAP_STYLES: {
    light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
  },

  // Map Default Center: Connaught Place, New Delhi [lng, lat]
  // (matches the mock dataset default in geocoding_service.py)
  DEFAULT_CENTER: [77.2167, 28.6315],
  DEFAULT_ZOOM: 14,
  MAX_BOUNDS_PADDING: 48,

  // Default travel mode for routing
  DEFAULT_ROUTE_MODE: "walking"
};
