/**
 * Text and HTML formatting utilities.
 */

export function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export function truncateText(text, maxChars = 140) {
  if (!text) return "";
  if (text.length <= maxChars) return text;
  return text.substring(0, maxChars).trim() + "…";
}

export function titleCase(text) {
  if (!text) return "";
  return text
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, c => c.toUpperCase());
}

/** ISO timestamps from the server (UTC) are shown in the visitor's own timezone. */
export function formatDateTime(value) {
  if (!value) return "";
  const text = String(value);
  if (!text.includes("T")) return text; // older "YYYY-MM-DD HH:MM" values are shown as saved
  const d = new Date(text);
  if (isNaN(d.getTime())) return text;
  return d.toLocaleString([], { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
