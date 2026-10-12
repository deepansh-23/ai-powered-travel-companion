/**
 * Navbar & Navigation Component (Section 6 & 21).
 */

import { state } from "../state.js";

export function initNavbar() {
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
