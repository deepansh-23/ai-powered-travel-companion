/**
 * Applies the admin-controlled site settings to the public pages:
 *  - announcement banner
 *  - maintenance mode: visitors get a full-screen message; admins keep working and see a banner
 *  - guest mode / registration switched off: the matching buttons are hidden
 * Uses only the public, non-secret settings endpoint. Text is inserted with textContent (never
 * innerHTML). Any failure is ignored so the site keeps working.
 */

const BANNER_ID = "siteNoticeBanner";
const OVERLAY_ID = "siteMaintenanceOverlay";

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

function showMaintenanceOverlay() {
  if (document.getElementById(OVERLAY_ID)) return;
  const box = document.createElement("div");
  box.id = OVERLAY_ID;
  box.setAttribute("role", "alertdialog");
  box.setAttribute("aria-label", "Site under maintenance");
  box.style.cssText = [
    "position:fixed", "inset:0", "z-index:3000", "display:flex", "align-items:center",
    "justify-content:center", "padding:24px", "text-align:center", "background:#0f172a", "color:#f8fafc",
    "font:400 16px/1.6 Inter,system-ui,sans-serif",
  ].join(";");
  const inner = document.createElement("div");
  inner.style.maxWidth = "480px";
  const icon = document.createElement("div");
  icon.textContent = "🛠️";
  icon.style.fontSize = "56px";
  const h = document.createElement("h1");
  h.textContent = "We'll be right back";
  h.style.cssText = "margin:12px 0 8px;font-size:28px;color:#fff";
  const p = document.createElement("p");
  p.textContent = "AI Powered Travel Companion is under maintenance. Please try again in a few minutes.";
  const a = document.createElement("a");
  a.href = "/pages/login.html?next=/admin/";
  a.textContent = "Admin sign in";
  a.style.cssText = "display:inline-block;margin-top:18px;color:#93c5fd;font-size:14px";
  inner.append(icon, h, p, a);
  box.append(inner);
  document.body.append(box);
}

function hideFeatureButtons(s) {
  const css = [];
  if (s.guest_mode_enabled === false) css.push("#welcomeGuest{display:none!important}");
  if (s.allow_registration === false) css.push("#tabRegister,#panelRegister{display:none!important}");
  if (!css.length) return;
  const style = document.createElement("style");
  style.textContent = css.join("\n");
  document.head.append(style);
}

async function viewerIsAdmin() {
  try {
    const res = await fetch("/api/auth/me", { credentials: "include" });
    if (!res.ok) return false;
    const me = await res.json();
    return !!(me.authenticated && me.user && me.user.is_admin);
  } catch {
    return false;
  }
}

export async function initSiteNotice() {
  try {
    const res = await fetch("/api/settings/public", { credentials: "include", cache: "no-store" });
    if (!res.ok) return;
    const s = await res.json();
    hideFeatureButtons(s);

    if (s.maintenance_mode) {
      const onLoginPage = location.pathname.endsWith("login.html");
      if (!onLoginPage && !(await viewerIsAdmin())) {
        showMaintenanceOverlay();
        return;
      }
      showBanner("Maintenance mode is ON: visitors cannot use the site. You can because you are an admin.", "maintenance");
    } else if (s.public_notice_enabled && s.public_notice_text) {
      showBanner(s.public_notice_text, "notice");
    }
  } catch {
    /* offline or API down: no banner */
  }
}
