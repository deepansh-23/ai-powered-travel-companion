/**
 * Geographic frontend formatting and bounds calculation utilities.
 * Distances are calculated by the backend; this utility only formats them (Section 50.2).
 */

export function formatDistance(meters) {
  if (meters === null || meters === undefined || isNaN(meters)) {
    return "";
  }
  const m = Math.round(Number(meters));
  if (m < 1000) {
    return `${m} m`;
  }
  const km = (m / 1000.0).toFixed(1);
  return `${km} km`;
}

export function computeBounds(coordinatesList) {
  if (!coordinatesList || coordinatesList.length === 0) {
    return null;
  }
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;

  for (const [lng, lat] of coordinatesList) {
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }

  return [[minLng, minLat], [maxLng, maxLat]];
}
