/**
 * Door-to-Door Itinerary Planner Controller (Sections 3, 4, 6, 7, 7A, 9, 10, 11, 15, 16, 19, 20, 23).
 * Integrates SerpApi Google Flights, RailRadar trains, SerpApi Google Hotels, and time-aware itineraries.
 */

import { api } from "../api.js";
import { toast } from "../components/toast.js";
import { modal } from "../components/modal.js";
import { escapeHtml, titleCase } from "../utils/formatters.js";
import { announceServiceReady, announceServiceReset } from "../components/review-widget.js";

const DEFAULT_CUISINES = [
  "Local Street Food", "Indian", "North Indian / Mughlai", "South Indian",
  "Punjabi", "Rajasthani", "Bengali", "Gujarati", "Italian", "Chinese",
  "Continental / European", "Mediterranean", "Thai", "Japanese / Sushi"
];

const DEFAULT_BAKERIES = [
  "Specialty Coffee & Pour Over", "Artisan Sourdough & Breads",
  "French Pastries & Croissants", "Cakes & Cupcakes", "Tea & Herbal Infusions",
  "Vegan Bakery", "Cheesecakes", "Traditional Regional Sweets"
];

class ItineraryPlannerController {
  constructor() {
    this.currentStep = 1;

    // Search state
    this.source = "";
    this.destination = "";
    this.outboundDate = "";
    this.returnDate = "";
    this.travelers = 1;
    this.preference = "best-overall";

    // Transport state
    this.transportData = null;
    this.selectedOutbound = null;
    this.selectedReturn = null;

    // Hotel state
    this.hotelData = [];
    this.selectedHotel = null;
    this.hotelSkipped = false;

    // Local preferences & Final plan state
    this.finalItinerary = null;
    this.isGenerating = false;
  }

  init() {
    this.initDates();
    this.initBudgetSync();
    this.initChipSelection();
    this.initTagPickers();
    this.attachEventListeners();
    this.restoreSessionState();
  }

  initDates() {
    const depInput = document.getElementById("itineraryDepDate");
    const retInput = document.getElementById("itineraryRetDate");
    if (!depInput || !retInput) return;

    const today = new Date();
    const future7 = new Date(today);
    future7.setDate(today.getDate() + 7);
    const future10 = new Date(today);
    future10.setDate(today.getDate() + 10);

    const toIso = (d) => d.toISOString().split("T")[0];
    const todayStr = toIso(today);

    depInput.min = todayStr;
    retInput.min = todayStr;

    if (!depInput.value) depInput.value = toIso(future7);
    if (!retInput.value) retInput.value = toIso(future10);

    depInput.addEventListener("change", () => {
      retInput.min = depInput.value;
      if (retInput.value && retInput.value < depInput.value) {
        retInput.value = depInput.value;
      }
    });
  }

  setStep(stepNum) {
    this.currentStep = stepNum;
    // "Rate this service" appears only while the finished itinerary is on screen
    if (stepNum === 5 && this.finalItinerary) announceServiceReady("Itinerary Planner");
    else announceServiceReset("Itinerary Planner");
    for (let i = 1; i <= 5; i++) {
      const badge = document.getElementById(`stepBadge${i}`);
      if (!badge) continue;
      badge.classList.remove("active", "completed");
      if (i === stepNum) badge.classList.add("active");
      else if (i < stepNum) badge.classList.add("completed");
    }

    const s1 = document.getElementById("step1Card");
    const s2 = document.getElementById("step2Section");
    const s3 = document.getElementById("step3Section");
    const s4 = document.getElementById("step4Section");
    const s5 = document.getElementById("itineraryResults");
    const headerActions = document.getElementById("headerActions");

    if (s1) s1.style.display = (stepNum === 1) ? "block" : "none";
    if (s2) s2.style.display = (stepNum === 2) ? "block" : "none";
    if (s3) s3.style.display = (stepNum === 3) ? "block" : "none";
    if (s4) s4.style.display = (stepNum === 4) ? "block" : "none";
    if (s5) s5.style.display = (stepNum === 5) ? "block" : "none";

    if (headerActions) {
      headerActions.style.display = (stepNum > 1) ? "block" : "none";
    }

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  attachEventListeners() {
    // 1. Step 1: Transport Search Form
    const transportForm = document.getElementById("transportSearchForm");
    if (transportForm) {
      transportForm.addEventListener("submit", (e) => {
        e.preventDefault();
        this.handleTransportSearch();
      });
    }

    // 2. Step 2: Proceed to Hotels
    const btnProceedToHotels = document.getElementById("btnProceedToHotels");
    if (btnProceedToHotels) {
      btnProceedToHotels.addEventListener("click", () => {
        this.handleProceedToHotels();
      });
    }

    // 3. Step 3: Hotel Controls
    const btnSkipHotel = document.getElementById("btnSkipHotel");
    if (btnSkipHotel) {
      btnSkipHotel.addEventListener("click", () => {
        this.selectedHotel = null;
        this.hotelSkipped = true;
        this.setStep(4);
      });
    }

    const btnBackToTransport = document.getElementById("btnBackToTransport");
    if (btnBackToTransport) {
      btnBackToTransport.addEventListener("click", () => {
        this.setStep(2);
      });
    }

    const btnProceedToLocalPrefs = document.getElementById("btnProceedToLocalPrefs");
    if (btnProceedToLocalPrefs) {
      btnProceedToLocalPrefs.addEventListener("click", () => {
        this.setStep(4);
      });
    }

    const hotelSortSelect = document.getElementById("hotelSortSelect");
    if (hotelSortSelect) {
      hotelSortSelect.addEventListener("change", () => {
        this.searchHotels();
      });
    }

    // 4. Step 4: Back to Hotels & Generate Final Itinerary
    const btnBackToHotels = document.getElementById("btnBackToHotels");
    if (btnBackToHotels) {
      btnBackToHotels.addEventListener("click", () => {
        this.setStep(3);
      });
    }

    const localPrefsForm = document.getElementById("localPrefsForm");
    if (localPrefsForm) {
      localPrefsForm.addEventListener("submit", (e) => {
        e.preventDefault();
        this.handleGenerateFinalItinerary();
      });
    }

    // Generate New Trip control (Section 20)
    const btnGenerateNewTrip = document.getElementById("btnGenerateNewTrip");
    if (btnGenerateNewTrip) {
      btnGenerateNewTrip.addEventListener("click", () => {
        this.resetActiveState();
      });
    }
  }

  resetActiveState() {
    sessionStorage.removeItem("slg_session_itinerary");
    this.selectedOutbound = null;
    this.selectedReturn = null;
    this.selectedHotel = null;
    this.hotelSkipped = false;
    this.finalItinerary = null;
    this.setStep(1);
    toast.info("Started new trip planning.");
  }

  // --- Step 1 & 2: Transport Search & Selection ---

  async handleTransportSearch() {
    const srcInput = document.getElementById("itinerarySource");
    const dstInput = document.getElementById("itineraryDest");
    const depInput = document.getElementById("itineraryDepDate");
    const retInput = document.getElementById("itineraryRetDate");
    const travelersInput = document.getElementById("itineraryTravelers");
    const prefSelect = document.getElementById("itineraryPreference");

    this.source = srcInput ? srcInput.value.trim() : "";
    this.destination = dstInput ? dstInput.value.trim() : "";
    this.outboundDate = depInput ? depInput.value : "";
    this.returnDate = retInput ? retInput.value : "";
    this.travelers = travelersInput ? parseInt(travelersInput.value, 10) : 1;
    this.preference = prefSelect ? prefSelect.value : "best-overall";

    if (!this.source || !this.destination) {
      toast.error("Please enter both origin and destination cities.");
      return;
    }

    if (this.source.toLowerCase() === this.destination.toLowerCase()) {
      toast.error("Origin and destination cannot be identical.");
      return;
    }

    const btn = document.getElementById("btnSearchTransport");
    const origBtnHtml = btn ? btn.innerHTML : "";
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<span>Searching Flights & Trains…</span>`;
    }

    try {
      toast.info(`Searching outbound and return transport (${this.source} ↔ ${this.destination})…`);
      const payload = {
        source: this.source,
        destination: this.destination,
        outbound_date: this.outboundDate,
        return_date: this.returnDate,
        travelers: this.travelers,
        preference: this.preference,
        currency: "INR"
      };

      this.transportData = await api.searchTransport(payload);

      // Render outbound and return transport options
      this.renderTransportLeg("outbound", this.transportData.outbound);
      if (this.transportData.return_leg) {
        this.renderTransportLeg("return", this.transportData.return_leg);
      }

      const summaryBadge = document.getElementById("transportRouteSummaryBadge");
      if (summaryBadge) {
        summaryBadge.textContent = `${this.source} → ${this.destination} (${this.outboundDate} to ${this.returnDate})`;
      }

      this.setStep(2);
      this.persistSessionState();
      toast.success("Found verified travel options!");
    } catch (err) {
      console.error("Transport search failed:", err);
      toast.error("Transport search error: " + err.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = origBtnHtml;
      }
    }
  }

  renderTransportLeg(legType, legData) {
    const container = document.getElementById(`${legType}TransportList`);
    const statusSpan = document.getElementById(legType === "outbound" ? "selectedOutboundStatus" : "selectedReturnStatus");
    if (!container) return;

    container.innerHTML = "";

    const allOptions = [...(legData.flights || []), ...(legData.trains || [])];

    const notices = [legData.airport_notice, legData.rail_notice]
      .filter((n, i, arr) => n && arr.indexOf(n) === i);

    if (allOptions.length === 0) {
      const text = notices.length ? notices : ["No transport options found for this route."];
      container.innerHTML = `
        <div class="empty-state" style="padding:16px;">
          ${text.map(n => `<p>${escapeHtml(n)}</p>`).join("")}
          <p style="font-size:0.85rem;color:var(--color-text-muted);">Check the spelling of the city names (for example "Bengaluru" or "Bangalore") and try again from step 1.</p>
        </div>
      `;
      return;
    }

    if (notices.length) {
      const info = document.createElement("div");
      info.style.cssText = "font-size:0.85rem;color:var(--color-text-secondary);margin-bottom:10px;";
      info.innerHTML = notices.map(n => `ℹ️ ${escapeHtml(n)}`).join("<br>");
      container.appendChild(info);
    }

    allOptions.forEach(opt => {
      const card = document.createElement("div");
      card.className = "transport-option-card";
      card.id = `transport-${opt.id}`;

      const isFlight = opt.mode === "flight";
      const icon = isFlight ? "✈️" : "🚆";
      const badgeHtml = opt.recommendation_badge ?
        `<span class="transport-badge">${escapeHtml(opt.recommendation_badge)}</span>` : "";

      const bookingToken = opt.raw_provider_data && opt.raw_provider_data.booking_token;
      let bookingBtn = "";
      if (isFlight && bookingToken) {
        bookingBtn = `<button type="button" class="btn btn-secondary btn-sm btn-booking-options" title="Fetch provider booking links (no in-app payment)">Book Flight ↗</button>`;
      } else if (opt.booking_url) {
        bookingBtn = `<a href="${escapeHtml(opt.booking_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" onclick="event.stopPropagation();" title="External provider link (no in-app payment)">${isFlight ? "View Flights" : "Book Train"} ↗</a>`;
      }

      const priceText = opt.price
        ? `₹${Math.round(opt.price).toLocaleString()}`
        : (isFlight ? "Price N/A" : "Fare not provided");

      card.innerHTML = `
        <div class="transport-card-header">
          <div>
            <div class="transport-op-name">${icon} ${escapeHtml(opt.operator)}</div>
            <div class="transport-op-num">${escapeHtml(opt.number || opt.cabin_or_class || "")} • ${opt.stops === 0 ? "Non-stop" : `${opt.stops} stop(s)`}</div>
          </div>
          ${badgeHtml}
        </div>

        <div class="transport-timing-row">
          <div class="transport-time-col">
            <div class="transport-time-val">${escapeHtml(opt.departure_time.split(' ').pop())}</div>
            <div class="transport-place-val" title="${escapeHtml(opt.origin)}">${escapeHtml(opt.origin)}</div>
          </div>
          <div class="transport-duration-col">
            <div>⏱️ ${escapeHtml(opt.duration_formatted || `${opt.duration_minutes}m`)}</div>
            <div style="font-size:0.75rem;color:var(--color-text-muted);">${escapeHtml(opt.layover_details || "Direct")}</div>
          </div>
          <div class="transport-time-col">
            <div class="transport-time-val">${escapeHtml(opt.arrival_time.split(' ').pop())}</div>
            <div class="transport-place-val" title="${escapeHtml(opt.destination)}">${escapeHtml(opt.destination)}</div>
          </div>
        </div>

        ${opt.recommendation_reason ? `<div class="transport-reason-note">${escapeHtml(opt.recommendation_reason)}</div>` : ""}

        <div class="transport-price-row">
          <div>
            <div class="transport-price-val">${priceText}</div>
            <div class="transport-price-sub">Live Quote / Traveller</div>
          </div>
          <div style="display:flex;gap:6px;align-items:center;">
            ${bookingBtn}
            <button type="button" class="btn btn-primary btn-sm btn-select-opt">
              Select
            </button>
          </div>
        </div>
      `;

      card.addEventListener("click", () => {
        this.selectTransportOption(legType, opt);
      });

      const bookingOptsBtn = card.querySelector(".btn-booking-options");
      if (bookingOptsBtn) {
        bookingOptsBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          this.showFlightBookingOptions(opt);
        });
      }

      container.appendChild(card);
    });

    // Auto-select top recommendation if available
    if (legData.top_recommendation) {
      this.selectTransportOption(legType, legData.top_recommendation);
    }
  }

  async showFlightBookingOptions(opt) {
    const raw = opt.raw_provider_data || {};
    modal.open({
      title: `Book ${opt.operator} ${opt.number || ""}`.trim(),
      bodyHtml: `<p>Fetching provider booking options…</p>`,
      footerHtml: `<button class="btn btn-secondary btn-sm btn-close-modal">Close</button>`
    });
    const body = document.getElementById("modalBody");
    try {
      const res = await api.getFlightBookingOptions(raw.booking_token, raw.search_params || {});
      const options = (res && res.options) || [];
      if (!options.length) {
        body.innerHTML = `<p>The provider returned no booking links for this flight.${opt.booking_url ? ` <a href="${escapeHtml(opt.booking_url)}" target="_blank" rel="noopener noreferrer">View on Google Flights ↗</a>` : ""}</p>`;
        return;
      }
      body.innerHTML = `
        <p style="font-size:0.85rem;color:var(--color-text-muted);">You will leave Smart Local Guide to book on the provider's site. No payment is taken here. Prices can change.</p>
        ${options.map((o, i) => `
          <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--color-border);">
            <div><strong>${escapeHtml(o.book_with || "Provider")}</strong>${o.option_title ? `<div style="font-size:0.8rem;color:var(--color-text-muted);">${escapeHtml(o.option_title)}</div>` : ""}</div>
            <div style="display:flex;align-items:center;gap:10px;">
              ${o.price ? `<span>₹${Number(o.price).toLocaleString("en-IN")}${(raw.search_params && raw.search_params.adults > 1) ? ` <small style="color:var(--color-text-muted);">total, ${raw.search_params.adults} travellers</small>` : ""}</span>` : ""}
              <button type="button" class="btn btn-primary btn-sm btn-open-booking" data-idx="${i}">Book ↗</button>
            </div>
          </div>`).join("")}`;
      body.querySelectorAll(".btn-open-booking").forEach(btn => {
        btn.addEventListener("click", () => this.openBookingOption(options[Number(btn.dataset.idx)]));
      });
    } catch (err) {
      body.innerHTML = `<p>Could not load booking options: ${escapeHtml(err.message)}</p>`;
    }
  }

  openBookingOption(option) {
    if (!option || !option.url) return;
    if (!option.post_data) {
      window.open(option.url, "_blank", "noopener,noreferrer");
      return;
    }
    // Provider booking_request = URL + POST data: submit it as a form in a new tab
    const form = document.createElement("form");
    form.method = "POST";
    form.action = option.url;
    form.target = "_blank";
    form.style.display = "none";
    new URLSearchParams(option.post_data).forEach((value, key) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = key;
      input.value = value;
      form.appendChild(input);
    });
    document.body.appendChild(form);
    form.submit();
    form.remove();
  }

  selectTransportOption(legType, opt) {
    if (legType === "outbound") {
      this.selectedOutbound = opt;
      const statusSpan = document.getElementById("selectedOutboundStatus");
      if (statusSpan) {
        statusSpan.innerHTML = `<span style="color:var(--color-primary);">✓ Selected: ${escapeHtml(opt.operator)} (₹${opt.price || 0})</span>`;
      }
      document.querySelectorAll("#outboundTransportList .transport-option-card").forEach(c => {
        c.classList.toggle("selected", c.id === `transport-${opt.id}`);
      });
    } else {
      this.selectedReturn = opt;
      const statusSpan = document.getElementById("selectedReturnStatus");
      if (statusSpan) {
        statusSpan.innerHTML = `<span style="color:var(--color-primary);">✓ Selected: ${escapeHtml(opt.operator)} (₹${opt.price || 0})</span>`;
      }
      document.querySelectorAll("#returnTransportList .transport-option-card").forEach(c => {
        c.classList.toggle("selected", c.id === `transport-${opt.id}`);
      });
    }

    const btnProceed = document.getElementById("btnProceedToHotels");
    if (btnProceed) {
      // Must have selected outbound, and return if return requested
      const hasOutbound = !!this.selectedOutbound;
      const hasReturn = !this.returnDate || !!this.selectedReturn;
      btnProceed.disabled = !(hasOutbound && hasReturn);
    }

    this.persistSessionState();
  }

  // --- Step 3: Hotel Search & Selection ---

  async handleProceedToHotels() {
    this.setStep(3);
    await this.searchHotels();
  }

  async searchHotels() {
    const container = document.getElementById("hotelListContainer");
    const sortSelect = document.getElementById("hotelSortSelect");
    const sortBy = sortSelect ? sortSelect.value : "relevance";

    if (!container) return;
    container.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1;">
        <p>Searching verified Google Hotels in ${escapeHtml(this.destination)}…</p>
      </div>
    `;

    try {
      const payload = {
        destination: this.destination,
        check_in_date: this.outboundDate,
        check_out_date: this.returnDate || this.outboundDate,
        travelers: this.travelers,
        sort_by: sortBy,
        currency: "INR"
      };

      const res = await api.searchHotels(payload);
      this.hotelData = res.hotels || [];
      this.renderHotelsList(this.hotelData);
      this.persistSessionState();
    } catch (err) {
      console.error("Hotel search error:", err);
      container.innerHTML = `
        <div class="error-state" style="grid-column:1/-1;">
          <p>Hotel search unavailable: ${escapeHtml(err.message)}</p>
          <button class="btn btn-secondary btn-sm" id="btnRetryHotels">Retry Hotels</button>
        </div>
      `;
      const retryBtn = container.querySelector("#btnRetryHotels");
      if (retryBtn) retryBtn.addEventListener("click", () => this.searchHotels());
    }
  }

  renderHotelsList(hotels) {
    const container = document.getElementById("hotelListContainer");
    if (!container) return;

    container.innerHTML = "";
    if (hotels.length === 0) {
      container.innerHTML = `
        <div class="empty-state" style="grid-column:1/-1;">
          <h3>No hotels returned</h3>
          <p>You can skip accommodation to continue generating your local activities.</p>
        </div>
      `;
      return;
    }

    hotels.forEach(h => {
      const card = document.createElement("article");
      card.className = "hotel-card";
      card.id = `hotel-${h.id}`;
      if (this.selectedHotel && this.selectedHotel.id === h.id) {
        card.classList.add("selected");
      }

      const labelsHtml = (h.recommendation_labels || []).map(l => {
        let cls = "hotel-tag";
        if (l === "Cheapest") cls += " cheapest";
        else if (l === "Best Rated") cls += " best-rated";
        else if (l === "Best Value") cls += " best-value";
        return `<span class="${cls}">${escapeHtml(l)}</span>`;
      }).join("");

      const priceText = h.nightly_price ? `₹${Math.round(h.nightly_price).toLocaleString()} / night` : "No price data";
      const totalText = h.total_price ? `(Total: ₹${Math.round(h.total_price).toLocaleString()})` : "";
      const ratingText = h.rating ? `★ ${h.rating} ${h.review_count ? `(${h.review_count.toLocaleString()} reviews)` : ""}` : "Unrated";

      card.innerHTML = `
        <div>
          <div class="hotel-labels-row" style="margin-bottom:6px;">${labelsHtml}</div>
          <h3 style="font-size:1.1rem;margin-bottom:4px;color:var(--color-text-primary);">${escapeHtml(h.name)}</h3>
          <div style="font-size:0.85rem;color:var(--color-text-muted);margin-bottom:6px;">
            ${h.star_class ? `${h.star_class}-Star • ` : ""}${escapeHtml(ratingText)}
          </div>
          <p style="font-size:0.825rem;color:var(--color-text-secondary);margin-bottom:8px;">${escapeHtml(h.address)}</p>
          ${h.free_cancellation ? `<span class="badge badge-primary" style="font-size:0.75rem;">✓ Free Cancellation</span>` : ""}
        </div>

        ${h.recommendation_reason ? `<div class="transport-reason-note" style="margin:4px 0;">${escapeHtml(h.recommendation_reason)}</div>` : ""}

        <div style="border-top:1px solid var(--color-border);padding-top:10px;margin-top:auto;">
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px;">
            <div style="font-size:1.15rem;font-weight:800;color:var(--color-primary);">${priceText}</div>
            <div style="font-size:0.75rem;color:var(--color-text-muted);">${totalText}</div>
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">
            <button type="button" class="btn btn-secondary btn-sm btn-hotel-details" style="flex:1;">
              Price Comparison
            </button>
            <button type="button" class="btn btn-primary btn-sm btn-select-hotel" style="flex:1;">
              ${(this.selectedHotel && this.selectedHotel.id === h.id) ? "Selected ✓" : "Select Hotel"}
            </button>
          </div>
        </div>
      `;

      card.querySelector(".btn-select-hotel").addEventListener("click", () => {
        this.selectHotel(h);
      });

      card.querySelector(".btn-hotel-details").addEventListener("click", () => {
        this.openHotelPriceComparisonModal(h);
      });

      container.appendChild(card);
    });
  }

  selectHotel(h) {
    this.selectedHotel = h;
    this.hotelSkipped = false;
    document.querySelectorAll("#hotelListContainer .hotel-card").forEach(c => {
      const isSel = c.id === `hotel-${h.id}`;
      c.classList.toggle("selected", isSel);
      const selBtn = c.querySelector(".btn-select-hotel");
      if (selBtn) selBtn.textContent = isSel ? "Selected ✓" : "Select Hotel";
    });

    const proceedLabel = document.getElementById("hotelProceedLabel");
    if (proceedLabel) {
      proceedLabel.textContent = `Continue with ${h.name} →`;
    }

    this.persistSessionState();
    toast.success(`Selected hotel: ${h.name}`);
  }

  async openHotelPriceComparisonModal(hotel) {
    const propertyToken = (hotel.raw_provider_data && hotel.raw_provider_data.property_token) || hotel.id;

    modal.open({
      title: `${hotel.name} — Booking Sites Price Comparison`,
      bodyHtml: `
        <div style="text-align:center;padding:20px;">
          <p>Fetching live rate quotes across booking sites…</p>
        </div>
      `
    });

    try {
      let sources = hotel.price_sources || [];
      if (!sources || sources.length === 0) {
        const res = await api.getHotelDetails({
          property_token: propertyToken,
          check_in_date: this.outboundDate,
          check_out_date: this.returnDate || this.outboundDate,
          currency: "INR",
          adults: this.travelers
        });
        sources = res.price_sources || [];
      }

      if (!sources || sources.length === 0) {
        modal.open({
          title: hotel.name,
          bodyHtml: `
            <p>Single direct provider quote available: <b>₹${Math.round(hotel.nightly_price || 0).toLocaleString()} / night</b>.</p>
            ${hotel.booking_url ? `<a href="${escapeHtml(hotel.booking_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary" style="margin-top:12px;">Visit Booking Page ↗</a>` : ""}
          `
        });
        return;
      }

      let rowsHtml = sources.map(s => {
        const cheapBadge = s.is_cheapest ? `<span class="hotel-tag cheapest" style="margin-left:6px;">Cheapest</span>` : "";
        const bookBtn = s.booking_url ?
          `<a href="${escapeHtml(s.booking_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm">Book on ${escapeHtml(s.source_name)} ↗</a>` :
          `<span class="text-muted">Direct</span>`;
        return `
          <tr>
            <td style="font-weight:600;">${escapeHtml(s.source_name)}${cheapBadge}</td>
            <td style="font-weight:700;color:var(--color-primary);">₹${Math.round(s.price).toLocaleString()}</td>
            <td style="text-align:right;">${bookBtn}</td>
          </tr>
        `;
      }).join("");

      modal.open({
        title: `${hotel.name} — Price Comparison`,
        bodyHtml: `
          <p style="font-size:0.85rem;color:var(--color-text-muted);margin-bottom:12px;">
            Live quotes from SerpApi Google Hotels for ${this.outboundDate} to ${this.returnDate}. External deep links take you to authorized partner sites.
          </p>
          <table class="cost-table" style="width:100%;">
            <thead>
              <tr>
                <th>Booking Partner</th>
                <th>Rate / Night</th>
                <th style="text-align:right;">Action</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml}
            </tbody>
          </table>
        `
      });

    } catch (err) {
      modal.open({
        title: hotel.name,
        bodyHtml: `<p class="error-text">Could not retrieve provider price sources: ${escapeHtml(err.message)}</p>`
      });
    }
  }

  // --- Step 4 & 5: Local Preferences & Final Itinerary ---

  initBudgetSync() {
    const slider = document.getElementById("itineraryBudgetSlider");
    const input = document.getElementById("itineraryBudgetInput");
    if (!slider || !input) return;

    slider.addEventListener("input", (e) => {
      input.value = e.target.value;
    });
    input.addEventListener("input", (e) => {
      let val = parseFloat(e.target.value);
      if (!isNaN(val)) slider.value = Math.min(Math.max(val, 1000), 100000);
    });
  }

  initChipSelection() {
    document.querySelectorAll(".chip-selection-grid .select-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        chip.classList.toggle("active");
      });
    });
  }

  initTagPickers() {
    this.cuisinePicker = this.setupTagPicker(
      "cuisineTagPicker", "cuisineTags", "cuisinePreferences", "cuisineDropdown", DEFAULT_CUISINES
    );
    this.bakeryPicker = this.setupTagPicker(
      "bakeryTagPicker", "bakeryTags", "bakeryPreferences", "bakeryDropdown", DEFAULT_BAKERIES
    );
  }

  setupTagPicker(containerId, tagsId, inputId, dropdownId, defaultList) {
    const container = document.getElementById(containerId);
    const tagsBox = document.getElementById(tagsId);
    const input = document.getElementById(inputId);
    const dropdown = document.getElementById(dropdownId);
    if (!container || !tagsBox || !input || !dropdown) {
      return { getTags: () => [] };
    }

    const selectedTags = new Set();

    const renderTags = () => {
      tagsBox.innerHTML = "";
      selectedTags.forEach(tag => {
        const pill = document.createElement("span");
        pill.className = "tag-pill";
        pill.innerHTML = `<span>${escapeHtml(tag)}</span><button type="button" class="tag-pill-remove">&times;</button>`;
        pill.querySelector(".tag-pill-remove").addEventListener("click", () => {
          selectedTags.delete(tag);
          renderTags();
        });
        tagsBox.appendChild(pill);
      });
    };

    const populateDropdown = (query = "") => {
      dropdown.innerHTML = "";
      const lower = query.toLowerCase();
      const filtered = defaultList.filter(item => item.toLowerCase().includes(lower));
      if (filtered.length === 0) {
        dropdown.style.display = "none";
        return;
      }
      filtered.forEach(item => {
        const row = document.createElement("div");
        row.className = "tag-picker-item";
        if (selectedTags.has(item)) row.classList.add("selected");
        row.textContent = item;
        row.addEventListener("click", () => {
          // Multi-select: toggle this option and KEEP the list open so several
          // can be picked in a row. It only closes when clicking elsewhere.
          if (selectedTags.has(item)) selectedTags.delete(item);
          else selectedTags.add(item);
          renderTags();
          input.value = "";
          populateDropdown("");
          input.focus();
        });
        dropdown.appendChild(row);
      });
      dropdown.style.display = "flex";
    };

    input.addEventListener("focus", () => populateDropdown(input.value));
    input.addEventListener("input", () => populateDropdown(input.value));
    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") dropdown.style.display = "none";
    });

    // The little arrow button opens / closes the list
    const toggleBtn = container.querySelector(".tag-picker-toggle");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (dropdown.style.display === "none") {
          populateDropdown("");
          input.focus();
        } else {
          dropdown.style.display = "none";
        }
      });
    }

    // Close only when the click is outside this picker. composedPath() is read
    // at click time, so it still works after the list was re-rendered.
    document.addEventListener("click", (e) => {
      const path = e.composedPath ? e.composedPath() : [];
      const inside = path.length ? path.includes(container) : container.contains(e.target);
      if (!inside) dropdown.style.display = "none";
    });

    return {
      getTags: () => Array.from(selectedTags),
      setTags: (tags) => {
        selectedTags.clear();
        (tags || []).forEach(t => selectedTags.add(t));
        renderTags();
      }
    };
  }

  async handleGenerateFinalItinerary() {
    const resultsContainer = document.getElementById("itineraryResults");
    const budgetInput = document.getElementById("itineraryBudgetInput");
    const foodTypeSelect = document.getElementById("foodType");
    const paceSelect = document.getElementById("itineraryPace");
    const transportSelect = document.getElementById("itineraryLocalTransport");
    const submitBtn = document.getElementById("btnGenerateItinerary");

    const budgetPerDay = budgetInput ? parseFloat(budgetInput.value) : 3000;
    const foodType = foodTypeSelect ? foodTypeSelect.value : "no-preference";
    const pace = paceSelect ? paceSelect.value : "moderate";
    const localTransport = transportSelect ? transportSelect.value : "public";

    const selectedInterests = Array.from(
      document.querySelectorAll(".chip-selection-grid .select-chip.active")
    ).map(c => c.dataset.value || c.textContent.trim());

    const foodPreferences = [
      ...(this.cuisinePicker?.getTags() || []),
      ...(this.bakeryPicker?.getTags() || [])
    ];

    // Compute duration from departure and return dates
    let durationDays = 3;
    if (this.outboundDate && this.returnDate) {
      const d1 = new Date(this.outboundDate);
      const d2 = new Date(this.returnDate);
      const diffDays = Math.round((d2 - d1) / (1000 * 60 * 60 * 24)) + 1;
      if (diffDays > 0) durationDays = Math.min(Math.max(diffDays, 1), 14);
    }

    const payload = {
      destination: this.destination,
      source: this.source,
      departure_date: this.outboundDate,
      return_date: this.returnDate,
      duration_days: durationDays,
      budget_per_person_per_day: budgetPerDay,
      travelers_count: this.travelers,
      travel_group_type: "group",
      radius_km: 6.0,
      interests: selectedInterests,
      food_type: foodType,
      food_preferences: foodPreferences,
      pace,
      transportation: localTransport,
      selected_outbound_transport: this.selectedOutbound,
      selected_return_transport: this.selectedReturn,
      selected_hotel: this.selectedHotel
    };

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span>Generating Time-Aware Itinerary…</span>`;
    }

    resultsContainer.innerHTML = `
      <div class="empty-state">
        <div class="skeleton" style="width:60px;height:60px;border-radius:50%;margin:0 auto 16px auto;"></div>
        <h3>Synthesizing door-to-door itinerary for ${escapeHtml(this.destination)}…</h3>
        <p>Grounding schedule around ${escapeHtml(this.selectedOutbound?.operator || 'outbound transit')} arrival and hotel accommodation.</p>
      </div>
    `;

    this.setStep(5);

    try {
      this.finalItinerary = await api.generateItinerary(payload);
      this.renderFinalItinerary(resultsContainer, this.finalItinerary);

      // Save to persistent History (Section 21)
      api.createHistory({
        feature_type: "itinerary",
        title: `Trip: ${this.source} → ${this.destination} (${durationDays} Days)`,
        preview: `${this.selectedOutbound?.operator || 'Transport'} + ${this.selectedHotel?.name || 'Hotel'} • ${this.finalItinerary.estimated_budget_total}`,
        payload: {
          ...this.finalItinerary,
          source: this.source,
          destination: this.destination,
          departure_date: this.outboundDate,
          return_date: this.returnDate,
          travellers: this.travelers,
          preference: this.preference,
          duration_days: durationDays,
          selected_outbound_transport: this.selectedOutbound,
          selected_return_transport: this.selectedReturn,
          selected_hotel: this.selectedHotel,
          hotel_skipped: this.hotelSkipped
        }
      }).catch(e => console.warn("Auto-save history notice:", e));

      this.persistSessionState();
      toast.success("Door-to-door itinerary generated successfully!");
    } catch (err) {
      console.error("Itinerary generation failed:", err);
      resultsContainer.innerHTML = `
        <div class="error-state">
          <h3>Failed to generate itinerary</h3>
          <p>${escapeHtml(err.message)}</p>
          <button class="btn btn-primary btn-sm" id="btnRetryGen">Retry Itinerary</button>
        </div>
      `;
      const retryBtn = document.getElementById("btnRetryGen");
      if (retryBtn) retryBtn.addEventListener("click", () => this.handleGenerateFinalItinerary());
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `<span>Generate Door-to-Door Itinerary</span>`;
      }
    }
  }

  renderFinalItinerary(container, data) {
    container.innerHTML = "";

    // 1. Header with PDF download and actions
    const headerRow = document.createElement("div");
    headerRow.style.cssText = "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:20px;";
    headerRow.innerHTML = `
      <div>
        <h2 style="font-size:1.6rem;font-family:var(--font-heading);margin-bottom:4px;color:var(--color-text-primary);">
          ${escapeHtml(data.title)}
        </h2>
        <div style="font-size:0.9rem;color:var(--color-text-muted);">
          ${escapeHtml(data.trip_overview)}
        </div>
      </div>
      <div style="display:flex;gap:10px;">
        <button type="button" class="btn btn-secondary btn-sm" id="btnDownloadItineraryPdf">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          <span>Download PDF</span>
        </button>
      </div>
    `;
    container.appendChild(headerRow);

    // Attach PDF download handler (Section 23)
    headerRow.querySelector("#btnDownloadItineraryPdf").addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      btn.innerHTML = `<span>Generating PDF…</span>`;
      try {
        toast.info("Generating publication-quality PDF…");
        const pdfBlob = await api.downloadPdf(data.title, {
          title: data.title,
          destination: data.destination,
          source: data.source,
          duration_days: data.duration_days,
          trip_overview: data.trip_overview,
          outbound_transport: data.selected_outbound_transport,
          return_transport: data.selected_return_transport,
          hotel: data.selected_hotel,
          days: data.days,
          cost_breakdown: data.cost_breakdown,
          estimated_budget_total: data.estimated_budget_total
        });

        // Trigger browser file download directly
        const blobUrl = window.URL.createObjectURL(pdfBlob);
        const a = document.createElement("a");
        a.style.display = "none";
        a.href = blobUrl;
        a.download = `${data.destination.replace(/\s+/g, '_')}_Itinerary.pdf`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(blobUrl);
        a.remove();

        toast.success("PDF downloaded successfully!");
      } catch (err) {
        console.error("PDF download error:", err);
        toast.error("PDF download failed: " + err.message);
      } finally {
        btn.disabled = false;
        btn.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          <span>Download PDF</span>
        `;
      }
    });

    // Mock-mode notice: sample places are for UI testing only, never real data
    if (data.data_mode === "mock") {
      const mockBanner = document.createElement("div");
      mockBanner.className = "sample-data-banner";
      mockBanner.setAttribute("role", "status");
      mockBanner.style.cssText = "margin-bottom:16px;padding:12px 16px;border-radius:var(--radius-md);background:var(--color-warning-light, #FEF3C7);border:1px solid var(--color-warning, #D97706);font-size:0.9rem;";
      mockBanner.textContent = "Sample data: MOCK_MODE is on, so the places, days and prices below are demo content (not real places for this destination). Set MOCK_MODE=false in .env for real results.";
      container.appendChild(mockBanner);
    }

    // 2. Journey & Hotel Summary Cards
    const journeyCard = document.createElement("div");
    journeyCard.className = "journey-summary-card";

    const ob = data.selected_outbound_transport;
    const ib = data.selected_return_transport;
    const htl = data.selected_hotel;

    journeyCard.innerHTML = `
      <h3 style="font-size:1.15rem;color:var(--color-primary);margin-bottom:12px;">🚆 Verified Journey & Accommodation</h3>
      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:16px;">
        <div style="background:var(--color-surface-soft);padding:12px;border-radius:var(--radius-md);">
          <strong>Outbound Transit:</strong><br/>
          ${ob ? `${escapeHtml(ob.operator)} (${escapeHtml(ob.number || '')})<br/>${escapeHtml(ob.departure_time)} → ${escapeHtml(ob.arrival_time)}<br/><span style="color:var(--color-primary);font-weight:700;">₹${ob.price || 0} (Live Quote)</span>` : 'Not specified'}
          ${ob && ob.booking_url ? `<br/><a href="${escapeHtml(ob.booking_url)}" target="_blank" rel="noopener noreferrer" style="font-size:0.8rem;color:var(--color-accent);font-weight:600;">Provider Booking Link ↗</a>` : ''}
        </div>
        <div style="background:var(--color-surface-soft);padding:12px;border-radius:var(--radius-md);">
          <strong>Return Transit:</strong><br/>
          ${ib ? `${escapeHtml(ib.operator)} (${escapeHtml(ib.number || '')})<br/>${escapeHtml(ib.departure_time)} → ${escapeHtml(ib.arrival_time)}<br/><span style="color:var(--color-primary);font-weight:700;">₹${ib.price || 0} (Live Quote)</span>` : 'One-way / Not specified'}
          ${ib && ib.booking_url ? `<br/><a href="${escapeHtml(ib.booking_url)}" target="_blank" rel="noopener noreferrer" style="font-size:0.8rem;color:var(--color-accent);font-weight:600;">Provider Booking Link ↗</a>` : ''}
        </div>
        <div style="background:var(--color-surface-soft);padding:12px;border-radius:var(--radius-md);">
          <strong>Accommodation:</strong><br/>
          ${htl ? `<b>${escapeHtml(htl.name)}</b> (★ ${htl.rating || 'N/A'})<br/>${escapeHtml(htl.address || '')}<br/><span style="color:var(--color-primary);font-weight:700;">₹${htl.nightly_price || 0}/night (Total: ₹${htl.total_price || 0})</span>` : '<em>Not selected (self-arranged)</em>'}
          ${htl && htl.booking_url ? `<br/><a href="${escapeHtml(htl.booking_url)}" target="_blank" rel="noopener noreferrer" style="font-size:0.8rem;color:var(--color-accent);font-weight:600;">Hotel Booking Link ↗</a>` : ''}
        </div>
      </div>
    `;
    container.appendChild(journeyCard);

    // 3. Day-by-Day Itinerary Schedule
    const daysContainer = document.createElement("div");
    daysContainer.className = "itinerary-days-stack";

    (data.days || []).forEach(day => {
      const dayEl = document.createElement("div");
      dayEl.className = "itinerary-day-card";
      dayEl.style.cssText = "background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-lg);padding:18px;margin-bottom:16px;box-shadow:var(--shadow-sm);";

      // How to get to a stop, from the PREVIOUS stop (not the user's current location)
      const renderDirections = (d) => {
        if (!d) return "";
        const chips = [
          d.distance_km != null ? `<span class="badge badge-secondary">📏 ~${d.distance_km} km</span>` : "",
          d.mode ? `<span class="badge badge-secondary">🚦 ${escapeHtml(d.mode)}</span>` : "",
          d.minutes != null ? `<span class="badge badge-secondary">⏱️ ~${d.minutes} min</span>` : ""
        ].join(" ");
        return `
          <div class="stop-directions">
            <div class="stop-directions-title">🧭 How to get here</div>
            <p class="stop-directions-text">${escapeHtml(d.summary || "")}</p>
            <div class="stop-directions-chips">${chips}</div>
            <a href="${escapeHtml(d.maps_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm stop-directions-link" aria-label="Open map from ${escapeHtml(d.from_name || "previous stop")}">
              🗺️ Open map: ${escapeHtml(d.from_name || "previous stop")} → here ↗
            </a>
            <div class="stop-directions-note">${escapeHtml(d.estimate_note || "")}</div>
          </div>
        `;
      };

      const renderPlaceStop = (p) => `
        <div class="stop-card">
          <span class="stop-label place">📍 Place to Visit</span>
          <h4 class="stop-name">${escapeHtml(p.name)}</h4>
          ${p.category ? `<div class="stop-meta">${escapeHtml(titleCase(String(p.category)))}${p.duration ? ` · ${escapeHtml(p.duration)}` : ""}${p.admission ? ` · ${escapeHtml(p.admission)}` : ""}</div>` : ""}
          ${p.address ? `<div class="stop-address">📮 ${escapeHtml(p.address)}</div>` : ""}
          ${renderDirections(p.directions)}
        </div>
      `;

      const renderSegment = (segTitle, seg) => {
        if (!seg) return "";
        return `
          <section class="itinerary-segment">
            <h4 class="segment-heading">${segTitle} <span class="segment-time">${escapeHtml(seg.time_window || '')}</span></h4>
            <div class="segment-title">${escapeHtml(seg.title || '')}</div>
            <p class="segment-description">${escapeHtml(seg.description || '')}</p>
            ${seg.transport_note ? `<div class="stop-meta">🚌 Local transit tip: ${escapeHtml(seg.transport_note)}</div>` : ''}
            ${(seg.places || []).map(renderPlaceStop).join("")}
          </section>
        `;
      };

      const renderFood = (title, f) => {
        if (!f) return "";
        return `
          <section class="itinerary-segment">
            <div class="stop-card restaurant">
              <span class="stop-label restaurant">🍴 ${title} · Restaurant</span>
              <h4 class="stop-name">${escapeHtml(f.name)}</h4>
              <div class="stop-meta">${escapeHtml(f.cuisine || "")}${f.price_level ? ` · ${escapeHtml(f.price_level)}` : ""}</div>
              ${f.address ? `<div class="stop-address">📮 ${escapeHtml(f.address)}</div>` : ""}
              <p class="segment-description">Must try: <em>${escapeHtml(f.recommendation || "")}</em></p>
              ${renderDirections(f.directions)}
            </div>
          </section>
        `;
      };

      const startLabel = htl
        ? `<span class="stop-label hotel">🏨 Hotel / Stay</span> <b>${escapeHtml(htl.name)}</b>${htl.address ? ` — ${escapeHtml(htl.address)}` : ""}`
        : "";

      dayEl.innerHTML = `
        <div class="day-card-header">
          <h3 class="day-card-title">Day ${day.day_number}: ${escapeHtml(day.theme)}</h3>
          <span class="badge badge-primary">${escapeHtml(day.estimated_day_cost)}</span>
        </div>
        ${startLabel ? `<div class="day-start-point">${startLabel}<div class="stop-meta">Each stop below shows how to reach it from the stop before it. The first stop is measured from here.</div></div>` : ""}
        ${renderSegment("🌅 Morning", day.morning)}
        ${renderFood("Lunch", day.food_stop_lunch)}
        ${renderSegment("☀️ Afternoon", day.afternoon)}
        ${renderFood("Dinner", day.food_stop_dinner)}
        ${renderSegment("🌙 Evening", day.evening)}
      `;

      daysContainer.appendChild(dayEl);
    });
    container.appendChild(daysContainer);

    // 4. Consolidated Cost Summary Table (Section 16)
    const costCard = document.createElement("div");
    costCard.className = "cost-breakdown-card";
    const cb = data.cost_breakdown || {};

    costCard.innerHTML = `
      <h3 style="font-size:1.25rem;color:var(--color-text-primary);margin-bottom:8px;">Itemized Cost Summary</h3>
      <p style="font-size:0.85rem;color:var(--color-text-muted);margin-bottom:12px;">Clearly distinguishes actual provider live quotes from estimated expenses.</p>
      <table class="cost-table">
        <thead>
          <tr>
            <th>Expense Category</th>
            <th>Type</th>
            <th>Rate / Amount</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Outbound Transport (${ob ? escapeHtml(ob.operator) : 'None'})</td>
            <td><span class="badge badge-primary">Provider Live Quote</span></td>
            <td><b>${ob ? `₹${(ob.price || 0).toLocaleString()}` : '₹0'}</b></td>
          </tr>
          <tr>
            <td>Return Transport (${ib ? escapeHtml(ib.operator) : 'None'})</td>
            <td><span class="badge badge-primary">Provider Live Quote</span></td>
            <td><b>${ib ? `₹${(ib.price || 0).toLocaleString()}` : '₹0'}</b></td>
          </tr>
          <tr>
            <td>Accommodation (${htl ? escapeHtml(htl.name) : 'Not selected'})</td>
            <td><span class="badge ${htl ? 'badge-primary' : 'badge-secondary'}">${htl ? 'Provider Live Quote' : 'Not Selected'}</span></td>
            <td><b>${htl ? `₹${(htl.total_price || 0).toLocaleString()}` : '₹0 (Not selected)'}</b></td>
          </tr>
          <tr>
            <td>Local Dining, Sights & Transit</td>
            <td><span class="badge badge-secondary">Estimate</span></td>
            <td>₹${(cb.food_and_activities_estimate || 0).toLocaleString()}</td>
          </tr>
          <tr class="total-row">
            <td>Consolidated Trip Total</td>
            <td>Overall Consolidated</td>
            <td>₹${(cb.overall_total_estimate || 0).toLocaleString()}</td>
          </tr>
          <tr>
            <td><b>Per-Person Estimate</b></td>
            <td>Scaled for ${data.travelers_count || this.travelers} traveller(s)</td>
            <td style="font-weight:700;color:var(--color-primary);">₹${(cb.per_person_estimate || 0).toLocaleString()} / person</td>
          </tr>
        </tbody>
      </table>
    `;
    container.appendChild(costCard);
    announceServiceReady("Itinerary Planner");
  }

  // --- Session Persistence (Section 19) ---

  persistSessionState() {
    const data = {
      currentStep: this.currentStep,
      source: this.source,
      destination: this.destination,
      outboundDate: this.outboundDate,
      returnDate: this.returnDate,
      travelers: this.travelers,
      preference: this.preference,
      transportData: this.transportData,
      selectedOutbound: this.selectedOutbound,
      selectedReturn: this.selectedReturn,
      selectedHotel: this.selectedHotel,
      hotelSkipped: this.hotelSkipped,
      finalItinerary: this.finalItinerary
    };
    try {
      sessionStorage.setItem("slg_session_itinerary", JSON.stringify(data));
    } catch (_) {}
  }

  restoreSessionState() {
    try {
      const raw = sessionStorage.getItem("slg_session_itinerary");
      if (!raw) return;
      const data = JSON.parse(raw);
      if (!data || !data.destination) return;

      this.source = data.source || "";
      this.destination = data.destination || "";
      this.outboundDate = data.outboundDate || "";
      this.returnDate = data.returnDate || "";
      this.travelers = data.travelers || 1;
      this.preference = data.preference || "best-overall";
      this.transportData = data.transportData;
      this.selectedOutbound = data.selectedOutbound;
      this.selectedReturn = data.selectedReturn;
      this.selectedHotel = data.selectedHotel;
      this.hotelSkipped = data.hotelSkipped;
      this.finalItinerary = data.finalItinerary;

      // Restore form inputs
      const srcInput = document.getElementById("itinerarySource");
      const dstInput = document.getElementById("itineraryDest");
      const depInput = document.getElementById("itineraryDepDate");
      const retInput = document.getElementById("itineraryRetDate");
      const travelersInput = document.getElementById("itineraryTravelers");
      const prefSelect = document.getElementById("itineraryPreference");

      if (srcInput) srcInput.value = this.source;
      if (dstInput) dstInput.value = this.destination;
      if (depInput) depInput.value = this.outboundDate;
      if (retInput) retInput.value = this.returnDate;
      if (travelersInput) travelersInput.value = this.travelers;
      if (prefSelect) prefSelect.value = this.preference;

      if (this.finalItinerary) {
        const resultsContainer = document.getElementById("itineraryResults");
        this.renderFinalItinerary(resultsContainer, this.finalItinerary);
        this.setStep(5);
      } else if (this.transportData) {
        this.renderTransportLeg("outbound", this.transportData.outbound);
        if (this.transportData.return_leg) {
          this.renderTransportLeg("return", this.transportData.return_leg);
        }
        if (this.selectedOutbound) {
          this.selectTransportOption("outbound", this.selectedOutbound);
        }
        if (this.selectedReturn) {
          this.selectTransportOption("return", this.selectedReturn);
        }
        this.setStep(2);
      }
    } catch (err) {
      console.warn("Failed to restore itinerary session state:", err);
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const controller = new ItineraryPlannerController();
  controller.init();
});