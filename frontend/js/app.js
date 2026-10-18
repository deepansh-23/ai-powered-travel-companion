/**
 * AI Powered Travel Companion - Global Application Initializer.
 */

import { state } from "./state.js";
import { initNavbar } from "./components/navbar.js";
import { authManager } from "./components/auth.js";
import { initReviews } from "./components/review-widget.js";

document.addEventListener("DOMContentLoaded", () => {
  // Apply saved theme
  document.documentElement.setAttribute("data-theme", state.theme);

  // Initialize Navbar
  initNavbar();

  // Accounts: who is logged in, navbar Log in / Log out, protected pages
  authManager.init();

  // Reviews: floating "Rate us" tab, rate-this-service strips, Home top reviews
  initReviews();
});

