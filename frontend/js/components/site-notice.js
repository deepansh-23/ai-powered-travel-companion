/**
 * Site notice: shows the admin-controlled announcement / maintenance banner.
 * Reads the public, non-secret settings endpoint. Text is inserted with textContent
 * (never innerHTML), and any failure is ignored so the site keeps working.
 */

const BANNER_ID = "siteNoticeBanner";

function showBanner(text, kind) {
  if (!text || document.getElementById(BANNER_ID)) return;
  const bar = document.createElement("div");
  bar.id = BANNER_ID;
  bar.setAttribute("role", "status");
  bar.style.cssText = [
    "position:sticky", "top:0", "z-index:2000", "padding:10px 16px", "text-align:center",
    "font:600 14px/1.4 Inter,system-ui,sans-serif", "color:#fff",
    kind === "maintenance" ? "background:#b45309" : "background:#2563eb",
  ].join(";");
  bar.textContent = text;
  document.body.prepend(bar);
}

export async function initSiteNotice() {
  try {
    const res = await fetch("/api/settings/public", { credentials: "include" });
    if (!res.ok) return;
    const s = await res.json();
    if (s.maintenance_mode) {
      showBanner("The site is under maintenance. Some features may be unavailable for a while.", "maintenance");
    } else if (s.public_notice_enabled && s.public_notice_text) {
      showBanner(s.public_notice_text, "notice");
    }
  } catch {
    /* offline or API down: no banner */
  }
}
