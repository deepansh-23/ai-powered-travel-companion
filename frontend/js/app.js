/**
 * Smart Local Guide - Global Application Initializer.
 */

import { state } from "./state.js";
import { initNavbar } from "./components/navbar.js";
import { captchaManager } from "./components/captcha.js";
import { initReviews } from "./components/review-widget.js";

document.addEventListener("DOMContentLoaded", () => {
  // Apply saved theme
  document.documentElement.setAttribute("data-theme", state.theme);

  // Initialize Navbar
  initNavbar();

  // Initialize Security / CAPTCHA Protection (Section 25)
  captchaManager.initSiteProtection();

  // Reviews: floating "Rate us" tab, rate-this-service strips, Home top reviews
  initReviews();
});

