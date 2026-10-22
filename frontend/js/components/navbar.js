/**
 * Navbar & Navigation Component (Section 6 & 21).
 */

import { state } from "../state.js";
import { hasLongRunningRequest } from "../api.js";
import { toast } from "./toast.js";

/**
 * While something is running (e.g. an itinerary is being generated), opening another service must not
 * kill it. Links to other pages then open in a new tab, so the first tab keeps working and the traveller
 * can use places, history, reviews and everything else in parallel.
 */
function keepRunningWorkAlive() {
  document.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest && e.target.closest("a[href]");
    if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
    const href = a.getAttribute("href") || "";
    if (!href || href.startsWith("#") || /^(mailto:|tel:|javascript:)/i.test(href)) return;
    let url;
    try { url = new URL(a.href, window.location.href); } catch (_) { return; }
    if (url.origin !== window.location.origin) return;
    if (url.pathname === window.location.pathname) return;
    if (!hasLongRunningRequest()) return;
    e.preventDefault();
    window.open(url.href, "_blank", "noopener");
    try { toast.info("Your request is still running, so this opened in a new tab. Nothing is lost."); } catch (_) { /* toast is optional */ }
  }, true);

  // Reload / closing the tab / the back button would also cancel the running request: ask first.
  window.addEventListener("beforeunload", (e) => {
    if (hasLongRunningRequest()) { e.preventDefault(); e.returnValue = ""; }
  });
}

export function initNavbar() {
  keepRunningWorkAlive();
  const currentPath = window.location.pathname.toLowerCase();

  // Highlight active link
  let otherServicesActive = false;
  document.querySelectorAll(".nav-link, .nav-dropdown-item").forEach(link => {
    const href = link.getAttribute("href");
    if (!href) return;
    const lowerHref = href.toLowerCase();
    const isCurrent = currentPath.endsWith(lowerHref) ||
      (lowerHref.includes("index.html") && (currentPath.endsWith("/") || currentPath.endsWith("/index.html"))) ||
      (lowerHref.includes("itinerary.html") && currentPath.includes("itinerary")) ||
      (lowerHref.includes("history.html") && currentPath.includes("history")) ||
      (lowerHref.includes("reviews.html") && currentPath.includes("reviews")) ||
      (lowerHref.includes("places.html") && currentPath.includes("places")) ||
      (lowerHref.includes("area.html") && currentPath.includes("area")) ||
      (lowerHref.includes("cafes.html") && currentPath.includes("cafes")) ||
      (lowerHref.includes("medical.html") && currentPath.includes("medical"));

    if (isCurrent) {
      link.classList.add("active");
      if (link.classList.contains("nav-dropdown-item")) {
        otherServicesActive = true;
      }
    }
  });

  if (otherServicesActive) {
    document.querySelectorAll(".nav-dropdown-btn").forEach(btn => btn.classList.add("active"));
  }


  // Setup Theme Selector
  const themeSelect = document.getElementById("themeSelect");
  if (themeSelect) {
    themeSelect.value = state.theme;
    themeSelect.addEventListener("change", (e) => {
      state.setTheme(e.target.value);
    });
  }

  // Setup Mobile Nav Drawer
  const mobileToggle = document.getElementById("mobileNavToggle");
  const mobileDrawer = document.getElementById("mobileDrawer");
  if (mobileToggle && mobileDrawer) {
    mobileToggle.addEventListener("click", () => {
      const isOpen = mobileDrawer.classList.toggle("open");
      mobileToggle.setAttribute("aria-expanded", isOpen);
    });
  }
}
