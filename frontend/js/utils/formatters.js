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
