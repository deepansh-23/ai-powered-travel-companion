/**
 * Door-to-Door Itinerary Planner Controller (Sections 3, 4, 6, 7, 7A, 9, 10, 11, 15, 16, 19, 20, 23).
 * Integrates SerpApi Google Flights, RailRadar trains, SerpApi Google Hotels, and time-aware itineraries.
 */

import { api } from "../api.js";
import { toast } from "../components/toast.js";
import { modal } from "../components/modal.js";
import { escapeHtml, titleCase } from "../utils/formatters.js";
import { announceServiceReady, announceServiceReset } from "../components/review-widget.js";
import { authManager } from "../components/auth.js";
import { initSavedSessions, forgetDraft } from "../components/saved-sessions.js";
import {
  stationOptionsHtml,
  buildDateStripHtml,
  buildFareAvailabilityHtml,
  buildTrainAdviceHtml,
  buildQuickVersionHtml,
  buildBudgetSummaryHtml,
  buildBudgetBreakdownHtml,
  buildDidYouMeanHtml,
  buildScopePanelHtml,
  scopeCountText,
  buildStayBlockHtml,
  buildTransfersHtml,
  buildStaysSummaryHtml,
  buildStayDoneHtml,
  buildStayUpcomingHtml,
  buildTransferChooserHtml,
  buildTransferPanelHtml,
  buildTransferSummaryLine,
  scoreHotels,
  buildMatchChipsHtml,
  buildHotelConnectorHtml,
  buildDayNotesHtml,
  buildFlightSiteLinksHtml,
  placeAboutHtml,
  recommendedAreas,
  scopeAdviceText,
  buildTripGlanceHtml,
  dayHighlights,
  dayColor
} from "./itinerary-extras.js";
import { renderTripMap } from "../components/trip-map.js";
import { attachPlaceAutocomplete } from "../components/place-autocomplete.js";

const DEFAULT_CUISINES = [
  "Local specialities", "Local Street Food", "Indian", "North Indian / Mughlai", "South Indian",
  "Punjabi", "Rajasthani", "Bengali", "Gujarati", "Italian", "Chinese",
  "Continental / European", "Mediterranean", "Thai", "Japanese / Sushi"
];

const DEFAULT_BAKERIES = [
  "Local specialities", "Specialty Coffee & Pour Over", "Artisan Sourdough & Breads",
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

    // Where the trip goes: city / state / country questions and the places to stay in
    this.scopeInfo = null;
    this.scopeFor = "";
    this.scopeState = { mode: "", selected: [], neighbourSelected: [], arrival: "" };
    this.transportDestination = "";
    this.rooms = null;
    this.prefs = {};

    // Plan without hotels, then one hotel per stay
    this.skeleton = null;
    this.stayHotels = {};
    this.stayChoices = {};
    this.stayOpen = null; // the stay whose hotel list is open (null = the first stay still undecided)
    this.transferChoices = {}; // to_stay -> {mode, option}: how the traveller moves between two stays
    this.transferData = {};    // to_stay -> {data, loading, error}: flights and trains found for that move
    this.transferTab = {};     // to_stay -> which tab is showing
    this._transferPromises = {};
    this.anchors = {};         // stay -> {lat, lon, label}: the airport or station the traveller arrives at

    // Optional train details (classes + exact stations)
    this.trainClasses = [];
    this.fromStationCode = "";
    this.toStationCode = "";
    this.stations = { from: [], to: [] };

    // Nearby-date price strips (cached so a page reload does not spend API calls again)
    this.dateStrips = { outbound: null, return: null };
    this._stripSeq = { outbound: 0, return: 0 };

    // Local preferences & Final plan state
    this.finalItinerary = null;
    this.isGenerating = false;
  }

  init() {
    this.initDates();
    this.initBudgetSync();
    this.initChipSelection();
    this.initTransportModes();
    this.initTagPickers();
    this.attachEventListeners();
    this.initTrainDetails();
    attachPlaceAutocomplete(document.getElementById("itinerarySource"));
    attachPlaceAutocomplete(document.getElementById("itineraryDest"));
    this.initScope();
    this.restoreSessionState();
    initSavedSessions({
      service: "itinerary",
      saveButtonId: "btnSaveSession",
      hasActiveState: () => !!sessionStorage.getItem("slg_session_itinerary"),
      buildSave: () => this.buildDraftForSaving()
    });
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
    // Screens are numbered by page section (3 = hotels, 4 = preferences) but the visitor now meets
    // preferences first, so the progress badges follow the order they are actually shown in.
    const position = { 1: 1, 2: 2, 4: 3, 3: 4, 5: 5 };
    const here = position[stepNum] || stepNum;
    for (let i = 1; i <= 5; i++) {
      const badge = document.getElementById(`stepBadge${i}`);
      if (!badge) continue;
      badge.classList.remove("active", "completed");
      if (i === here) badge.classList.add("active");
      else if (i < here) badge.classList.add("completed");
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

    // 2. Step 2: continue to preferences
    const btnProceedToHotels = document.getElementById("btnProceedToHotels");
    if (btnProceedToHotels) {
      btnProceedToHotels.addEventListener("click", () => this.setStep(4));
    }

    // 3. Preferences: back to transport, generate the plan (hotels come next)
    const btnBackToHotels = document.getElementById("btnBackToHotels");
    if (btnBackToHotels) {
      btnBackToHotels.addEventListener("click", () => this.setStep(2));
    }
    const localPrefsForm = document.getElementById("localPrefsForm");
    if (localPrefsForm) {
      localPrefsForm.addEventListener("submit", (e) => {
        e.preventDefault();
        this.handleGenerateFinalItinerary();
      });
    }

    // 4. Hotels per stay: back, finish
    const btnBackToPrefs = document.getElementById("btnBackToPrefsFromHotels");
    if (btnBackToPrefs) btnBackToPrefs.addEventListener("click", () => this.setStep(4));
    const btnFinalize = document.getElementById("btnFinalizeItinerary");
    if (btnFinalize) btnFinalize.addEventListener("click", () => this.handleFinalize());

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
    forgetDraft("itinerary");
    this.selectedOutbound = null;
    this.selectedReturn = null;
    this.selectedHotel = null;
    this.hotelSkipped = false;
    this.finalItinerary = null;
    this.skeleton = null;
    this.stayHotels = {};
    this.stayChoices = {};
    this.transferChoices = {};
    this.transferData = {};
    this._transferPromises = {};
    this.anchors = {};
    this.scopeInfo = null;
    this.scopeFor = "";
    this.scopeState = { mode: "", selected: [], neighbourSelected: [], arrival: "" };
    this.renderScopePanel();
    this.dateStrips = { outbound: null, return: null };
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
    const roomsInput = document.getElementById("itineraryRooms");
    this.rooms = roomsInput && roomsInput.value ? parseInt(roomsInput.value, 10) : null;

    if (!this.source || !this.destination) {
      toast.error("Please enter both origin and destination cities.");
      return;
    }

    if (this.source.toLowerCase() === this.destination.toLowerCase()) {
      toast.error("Origin and destination cannot be identical.");
      return;
    }

    this.readTrainPreferences();

    // City, state or country? A big place needs a few questions first (where to land, what to visit)
    if (!(await this.ensureScope())) return;
    this.transportDestination = this.transportCity();

    const btn = document.getElementById("btnSearchTransport");
    const origBtnHtml = btn ? btn.innerHTML : "";
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<span>Searching Flights & Trains…</span>`;
    }

    try {
      toast.info(`Searching outbound and return transport (${this.source} ↔ ${this.transportDestination})…`);
      const payload = {
        source: this.source,
        destination: this.transportDestination,
        outbound_date: this.outboundDate,
        return_date: this.returnDate,
        travelers: this.travelers,
        preference: this.preference,
        currency: "INR",
        train_classes: this.trainClasses,
        source_station_code: this.fromStationCode || null,
        destination_station_code: this.toStationCode || null
      };

      this.dateStrips = { outbound: null, return: null };
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

  renderTransportLeg(legType, legData, { fetchStrip = true } = {}) {
    const container = document.getElementById(`${legType}TransportList`);
    const statusSpan = document.getElementById(legType === "outbound" ? "selectedOutboundStatus" : "selectedReturnStatus");
    if (!container) return;

    container.innerHTML = "";

    // Nearby dates (flight prices, green/orange/red) above the options of this leg
    if (this.dateStrips[legType]) this.renderDateStrip(legType);
    else if (fetchStrip) this.loadDateStrip(legType);

    const allOptions = [...(legData.flights || []), ...(legData.trains || [])];

    const notices = [legData.airport_notice, legData.rail_notice]
      .filter((n, i, arr) => n && arr.indexOf(n) === i);

    if (allOptions.length === 0) {
      const text = notices.length ? notices : ["No transport options found for this route."];
      container.innerHTML = `
        <div class="empty-state" style="padding:16px;">
          ${text.map(n => `<p>${escapeHtml(n)}</p>`).join("")}
          <p style="font-size:0.85rem;color:var(--color-text-muted);">Check the spelling, or pick one of the suggestions below. You can also go back to step 1 and choose a nearby city.</p>
          <div class="dym-slot" id="${legType}DidYouMean"></div>
        </div>
      `;
      this.showDidYouMean(legType);
      return;
    }

    if (notices.length) {
      const info = document.createElement("div");
      info.style.cssText = "font-size:0.85rem;color:var(--color-text-secondary);margin-bottom:10px;";
      info.innerHTML = notices.map(n => `ℹ️ ${escapeHtml(n)}`).join("<br>");
      container.appendChild(info);
    }

    // Train recommendation from the real train data (AI summary or rule-based)
    if (legData.train_advice) {
      const adviceEl = document.createElement("div");
      adviceEl.innerHTML = buildTrainAdviceHtml(legData.train_advice);
      adviceEl.querySelectorAll(".train-pick-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          const picked = allOptions.find(o => o.id === btn.dataset.optionId);
          if (!picked) return;
          this.selectTransportOption(legType, picked);
          const el = document.getElementById(`transport-${picked.id}`);
          if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
        });
      });
      container.appendChild(adviceEl.firstElementChild || adviceEl);
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
        ? `₹${Math.round(opt.price).toLocaleString("en-IN")}`
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

        ${!isFlight ? buildFareAvailabilityHtml(opt.fare_availability) : ""}

        <div class="transport-price-row">
          <div>
            <div class="transport-price-val">${priceText}</div>
            <div class="transport-price-sub">${opt.price ? "per person · live quote" : (isFlight ? "per person" : "per person · not provided by the data source")}</div>
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

  /** When nothing can be found for a place, offer the closest real places as one-click choices. */
  async showDidYouMean(legType) {
    const slot = document.getElementById(`${legType}DidYouMean`);
    if (!slot) return;
    const route = this.legRoute(legType);
    // field ids always refer to the form: origin is the Source field on the outbound leg only
    const fieldOf = (isOrigin) => ((legType === "outbound") === isOrigin ? "itinerarySource" : "itineraryDest");
    const asks = [
      { typed: route.origin, field: fieldOf(true) },
      { typed: route.destination, field: fieldOf(false) }
    ];
    try {
      const groups = await Promise.all(asks.map(async (a) => {
        const res = await api.suggestPlaces(a.typed);
        const items = (res.suggestions || []).filter(x => x.label.toLowerCase() !== a.typed.toLowerCase()).slice(0, 4);
        return { ...a, items };
      }));
      slot.innerHTML = buildDidYouMeanHtml(groups);
      slot.querySelectorAll(".dym-chip").forEach(chip => {
        chip.addEventListener("click", () => {
          const input = document.getElementById(chip.dataset.field);
          if (input) input.value = chip.dataset.value;
          this.handleTransportSearch();
        });
      });
    } catch (_) { /* suggestions are optional */ }
  }

  // --- Optional train details: classes + exact stations ---

  initTrainDetails() {
    const details = document.getElementById("trainDetails");
    const findBtn = document.getElementById("btnFindStations");
    if (findBtn) findBtn.addEventListener("click", () => this.findStations());
    if (details) {
      details.addEventListener("toggle", () => {
        const both = document.getElementById("itinerarySource")?.value.trim() && document.getElementById("itineraryDest")?.value.trim();
        if (details.open && both && !this.stations.from.length && !this.stations.to.length) this.findStations();
      });
    }
    // New cities mean new stations
    ["itinerarySource", "itineraryDest"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener("change", () => this.clearStations(id === "itinerarySource" ? "from" : "to"));
    });
    this.applyTrainPreferencesToForm();
  }

  clearStations(which) {
    this.stations[which] = [];
    if (which === "from") this.fromStationCode = "";
    else this.toStationCode = "";
    const sel = document.getElementById(which === "from" ? "trainFromStation" : "trainToStation");
    if (sel) sel.innerHTML = stationOptionsHtml([]);
  }

  readTrainPreferences() {
    this.trainClasses = Array.from(document.querySelectorAll('input[name="trainClass"]:checked')).map(i => i.value);
    const from = document.getElementById("trainFromStation");
    const to = document.getElementById("trainToStation");
    this.fromStationCode = from ? from.value : "";
    this.toStationCode = to ? to.value : "";
  }

  applyTrainPreferencesToForm() {
    document.querySelectorAll('input[name="trainClass"]').forEach(i => { i.checked = this.trainClasses.includes(i.value); });
    const from = document.getElementById("trainFromStation");
    const to = document.getElementById("trainToStation");
    if (from) from.innerHTML = stationOptionsHtml(this.stations.from, this.fromStationCode);
    if (to) to.innerHTML = stationOptionsHtml(this.stations.to, this.toStationCode);
    const details = document.getElementById("trainDetails");
    if (details && (this.trainClasses.length || this.fromStationCode || this.toStationCode)) details.open = true;
  }

  async findStations() {
    const source = document.getElementById("itinerarySource")?.value.trim() || "";
    const dest = document.getElementById("itineraryDest")?.value.trim() || "";
    const hint = document.getElementById("stationHint");
    const btn = document.getElementById("btnFindStations");
    if (!source || !dest) {
      if (hint) hint.textContent = "Enter both the origin and the destination city first.";
      return;
    }
    if (btn) btn.disabled = true;
    if (hint) hint.textContent = "Looking up railway stations…";
    try {
      const [a, b] = await Promise.all([api.searchStations(source), api.searchStations(dest)]);
      this.stations.from = a.stations || [];
      this.stations.to = b.stations || [];
      const keepFrom = this.stations.from.some(s => s.code === this.fromStationCode) ? this.fromStationCode : "";
      const keepTo = this.stations.to.some(s => s.code === this.toStationCode) ? this.toStationCode : "";
      this.fromStationCode = keepFrom;
      this.toStationCode = keepTo;
      this.applyTrainPreferencesToForm();
      const notes = [a.notice, b.notice].filter((n, i, arr) => n && arr.indexOf(n) === i);
      if (hint) {
        hint.textContent = notes.length
          ? notes.join(" ")
          : `Found ${this.stations.from.length} station(s) near ${source} and ${this.stations.to.length} near ${dest}. Pick the ones you prefer.`;
      }
    } catch (err) {
      if (hint) hint.textContent = "Could not load stations: " + err.message;
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  // --- Nearby dates (flights) ---

  legDate(legType) {
    return legType === "outbound" ? this.outboundDate : this.returnDate;
  }

  legRoute(legType) {
    return legType === "outbound"
      ? { origin: this.source, destination: this.transportDestination || this.destination, fromCode: this.fromStationCode, toCode: this.toStationCode }
      : { origin: this.transportDestination || this.destination, destination: this.source, fromCode: this.toStationCode, toCode: this.fromStationCode };
  }

  ensureStripEl(legType) {
    const list = document.getElementById(`${legType}TransportList`);
    if (!list || !list.parentElement) return null;
    let el = document.getElementById(`${legType}DateStrip`);
    if (!el) {
      el = document.createElement("div");
      el.id = `${legType}DateStrip`;
      el.className = "date-strip";
      list.parentElement.insertBefore(el, list);
    }
    return el;
  }

  async loadDateStrip(legType) {
    const el = this.ensureStripEl(legType);
    const date = this.legDate(legType);
    if (!el || !date) { if (el) el.hidden = true; return; }
    el.hidden = false;
    const seq = ++this._stripSeq[legType];
    el.innerHTML = `<div class="date-strip-loading">Checking flight prices for nearby dates…</div>`;
    const route = this.legRoute(legType);
    try {
      const resp = await api.getFlightDatePrices({
        origin: route.origin,
        destination: route.destination,
        date,
        travelers: this.travelers,
        currency: "INR",
        earliest_date: legType === "return" ? (this.outboundDate || null) : null
      });
      if (seq !== this._stripSeq[legType]) return; // user already moved on
      this.dateStrips[legType] = resp;
      this.renderDateStrip(legType);
      this.persistSessionState();
    } catch (err) {
      if (seq !== this._stripSeq[legType]) return;
      el.innerHTML = `<div class="date-strip-empty">Nearby-date prices unavailable: ${escapeHtml(err.message)}</div>`;
    }
  }

  renderDateStrip(legType) {
    const el = this.ensureStripEl(legType);
    const resp = this.dateStrips[legType];
    if (!el || !resp) return;
    el.hidden = false;
    const isDisabled = (iso) => legType === "outbound"
      ? !!(this.returnDate && iso > this.returnDate)
      : !!(this.outboundDate && iso < this.outboundDate);
    el.innerHTML = buildDateStripHtml(resp, isDisabled);
    el.querySelectorAll(".date-chip:not([disabled])").forEach(chip => {
      chip.addEventListener("click", () => this.switchLegDate(legType, chip.dataset.date));
    });
  }

  async switchLegDate(legType, newDate) {
    if (!newDate || newDate === this.legDate(legType)) return;
    const list = document.getElementById(`${legType}TransportList`);
    const route = this.legRoute(legType);
    if (list) list.innerHTML = `<div class="empty-state" style="padding:16px;"><p>Searching flights and trains for ${escapeHtml(newDate)}…</p></div>`;
    try {
      const leg = await api.searchTransportLeg({
        origin: route.origin,
        destination: route.destination,
        date: newDate,
        travelers: this.travelers,
        preference: this.preference,
        currency: "INR",
        train_classes: this.trainClasses,
        origin_station_code: route.fromCode || null,
        destination_station_code: route.toCode || null
      });

      if (legType === "outbound") {
        this.outboundDate = newDate;
        this.selectedOutbound = null;
        this.transportData.outbound = leg;
        const dep = document.getElementById("itineraryDepDate");
        if (dep) dep.value = newDate;
      } else {
        this.returnDate = newDate;
        this.selectedReturn = null;
        this.transportData.return_leg = leg;
        const ret = document.getElementById("itineraryRetDate");
        if (ret) ret.value = newDate;
      }

      // Dates changed: an earlier hotel choice no longer matches
      if (this.selectedHotel || this.hotelData.length) {
        this.selectedHotel = null;
        this.hotelData = [];
        this.hotelSkipped = false;
      }
      this.dateStrips[legType] = null;
      const badge = document.getElementById("transportRouteSummaryBadge");
      if (badge) badge.textContent = `${this.source} → ${this.destination} (${this.outboundDate} to ${this.returnDate})`;

      this.renderTransportLeg(legType, leg);
      // The other leg's strip only needs its disabled dates refreshed
      const other = legType === "outbound" ? "return" : "outbound";
      if (this.dateStrips[other]) this.renderDateStrip(other);
      this.persistSessionState();
      toast.success(`Showing options for ${newDate}.`);
    } catch (err) {
      toast.error("Could not load that date: " + err.message);
      const original = legType === "outbound" ? this.transportData.outbound : this.transportData.return_leg;
      if (original) this.renderTransportLeg(legType, original, { fetchStrip: false });
    }
  }

  /** "Book Flight": opens straight away with flight-website links. The provider's own booking options are looked up quietly
   *  in the background and only appear if they work. A failed lookup never shows an error. */
  async showFlightBookingOptions(opt) {
    const raw = opt.raw_provider_data || {};
    const sites = buildFlightSiteLinksHtml(raw.search_params, "Book on a flight website");
    const googleLink = opt.booking_url
      ? `<p><a class="btn btn-primary btn-sm" href="${escapeHtml(opt.booking_url)}" target="_blank" rel="noopener noreferrer">View this flight on Google Flights ↗</a></p>`
      : "";
    const generic = (!sites && !googleLink)
      ? `<p><a class="btn btn-primary btn-sm" href="https://www.google.com/travel/flights" target="_blank" rel="noopener noreferrer">Open Google Flights ↗</a></p>`
      : "";
    modal.open({
      title: `Book ${opt.operator} ${opt.number || ""}`.trim(),
      bodyHtml: `
        <p style="font-size:0.9rem;color:var(--color-text-muted);">Choose where to book. You will leave AI Powered Travel Companion. No payment is taken here, and prices on the sites can differ.</p>
        <div id="providerBookingSlot"></div>
        ${googleLink}${sites}${generic}`,
      footerHtml: `<button class="btn btn-secondary btn-sm btn-close-modal">Close</button>`
    });

    if (!raw.booking_token || !raw.search_params) return;
    try {
      const res = await api.getFlightBookingOptions(raw.booking_token, raw.search_params);
      const options = (res && res.options) || [];
      const slot = document.getElementById("providerBookingSlot");
      if (!options.length || !slot) return;
      slot.innerHTML = `
        <div class="flight-sites-title" style="margin-top:6px;">Book directly</div>
        ${options.map((o, i) => `
          <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--color-border);">
            <div><strong>${escapeHtml(o.book_with || "Provider")}</strong>${o.option_title ? `<div style="font-size:0.8rem;color:var(--color-text-muted);">${escapeHtml(o.option_title)}</div>` : ""}</div>
            <div style="display:flex;align-items:center;gap:10px;">
              ${o.price ? `<span>₹${Number(o.price).toLocaleString("en-IN")}<small style="color:var(--color-text-muted);"> per person</small></span>` : ""}
              <button type="button" class="btn btn-primary btn-sm btn-open-booking" data-idx="${i}">Book ↗</button>
            </div>
          </div>`).join("")}`;
      slot.querySelectorAll(".btn-open-booking").forEach(btn => {
        btn.addEventListener("click", () => this.openBookingOption(options[Number(btn.dataset.idx)]));
      });
    } catch (_) {
      // Silent on purpose: the website links above already let the traveller book
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
        statusSpan.innerHTML = `<span style="color:var(--color-primary);">✓ Selected: ${escapeHtml(opt.operator)} (${opt.price ? "₹" + Math.round(opt.price).toLocaleString("en-IN") + " per person" : "fare not provided"})</span>`;
      }
      document.querySelectorAll("#outboundTransportList .transport-option-card").forEach(c => {
        c.classList.toggle("selected", c.id === `transport-${opt.id}`);
      });
    } else {
      this.selectedReturn = opt;
      const statusSpan = document.getElementById("selectedReturnStatus");
      if (statusSpan) {
        statusSpan.innerHTML = `<span style="color:var(--color-primary);">✓ Selected: ${escapeHtml(opt.operator)} (${opt.price ? "₹" + Math.round(opt.price).toLocaleString("en-IN") + " per person" : "fare not provided"})</span>`;
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

  // --- Where the trip goes: city, state or country ---

  initScope() {
    const dest = document.getElementById("itineraryDest");
    if (dest) dest.addEventListener("change", () => this.loadScope());
    // A different trip length changes how many places to stay in make sense
    ["itineraryDepDate", "itineraryRetDate"].forEach(id => {
      const el = document.getElementById(id);
      if (el) { el.addEventListener("change", () => this.syncScopeDays()); el.addEventListener("input", () => this.syncScopeDays()); }
    });
  }

  /** Re-works the advice, the recommended number of places and the "fits your N days" marks for the current dates. */
  syncScopeDays() {
    if (!this.scopeInfo) return;
    const days = this.tripDays();
    if (days === this.scopeInfo.days) return;
    this.scopeInfo.days = days;
    this.scopeInfo.recommended_areas = recommendedAreas(this.scopeInfo.kind, days);
    this.scopeInfo.advice = scopeAdviceText(this.scopeInfo.kind, this.scopeInfo.name, days);
    this.renderScopePanel();
  }

  tripDays() {
    const dep = document.getElementById("itineraryDepDate")?.value;
    const ret = document.getElementById("itineraryRetDate")?.value;
    if (!dep || !ret) return 3;
    const n = Math.round((new Date(ret) - new Date(dep)) / 86400000) + 1;
    return Math.min(14, Math.max(1, n));
  }

  isBigPlace() {
    return !!this.scopeInfo && (this.scopeInfo.kind === "state" || this.scopeInfo.kind === "country");
  }

  /** The city flights and trains are searched to (the landing city for a state or country). */
  transportCity() {
    return this.isBigPlace() ? (this.scopeState.arrival || this.destination) : this.destination;
  }

  /** Places to stay in, in visiting order, from the answers given in the "Plan your area" card. */
  areasList() {
    const info = this.scopeInfo;
    const st = this.scopeState;
    if (!info) return [this.destination];
    let list = [];
    if (this.isBigPlace()) {
      if (st.arrival) list.push(st.arrival);
      list.push(...st.selected);
      if (info.kind === "state" && st.mode === "neighbours") list.push(...st.neighbourSelected);
    } else {
      list.push(this.destination);
      if (st.mode === "nearby") list.push(...st.selected);
    }
    const seen = new Set();
    return list.filter(a => a && !seen.has(a.toLowerCase()) && seen.add(a.toLowerCase()));
  }

  async loadScope(force = false) {
    const panel = document.getElementById("scopePanel");
    const dest = (document.getElementById("itineraryDest")?.value || "").trim();
    if (!panel) return;
    if (dest.length < 2) {
      this.scopeInfo = null;
      this.scopeFor = "";
      this.renderScopePanel();
      return;
    }
    if (!force && dest === this.scopeFor && this.scopeInfo) return;
    const keep = force && this.scopeInfo ? { mode: this.scopeState.mode, arrival: this.scopeState.arrival } : null;
    panel.hidden = false;
    panel.innerHTML = `<div class="scope-card"><div class="scope-advice">Checking how big “${escapeHtml(dest)}” is…</div></div>`;
    try {
      const info = await api.getItineraryScope({ destination: dest, duration_days: this.tripDays() });
      if ((document.getElementById("itineraryDest")?.value || "").trim() !== dest) return; // user typed something else meanwhile
      info.days = this.tripDays();
      info.ai_days = info.days; // the trip length these suggestions were made for
      this.scopeInfo = info;
      this.scopeFor = dest;
      // for a state or a country the start city is filled in with the suggested one (capital or main-airport city)
      this.scopeState = { mode: (info.modes[0] || {}).value || "", selected: [], neighbourSelected: [], arrival: info.default_arrival || "" };
      if (keep) { this.scopeState.mode = keep.mode || this.scopeState.mode; this.scopeState.arrival = keep.arrival || this.scopeState.arrival; }
      this.renderScopePanel();
    } catch (_) {
      // The questions are a help, not a requirement: plan the place as typed
      this.scopeInfo = null;
      this.scopeFor = dest;
      this.renderScopePanel();
    }
  }

  renderScopePanel() {
    const panel = document.getElementById("scopePanel");
    if (!panel) return;
    if (!this.scopeInfo) { panel.hidden = true; panel.innerHTML = ""; return; }
    panel.hidden = false;
    const days = this.tripDays();
    const stale = this.scopeInfo.source === "ai" && this.scopeInfo.ai_days && Math.abs(days - this.scopeInfo.ai_days) >= 3;
    panel.innerHTML = buildScopePanelHtml(this.scopeInfo, this.scopeState, { days, refreshDays: stale ? days : null });
    const refreshBtn = panel.querySelector("#scopeRefresh");
    if (refreshBtn) refreshBtn.addEventListener("click", () => this.loadScope(true));
    const refreshCount = () => {
      const el = panel.querySelector("#scopeCount");
      if (el) el.textContent = scopeCountText(this.scopeInfo, this.areasList().length);
    };
    panel.querySelectorAll('input[name="scopeMode"]').forEach(r => {
      r.addEventListener("change", () => { this.scopeState.mode = r.value; this.renderScopePanel(); });
    });
    panel.querySelectorAll(".scope-check").forEach(c => {
      c.addEventListener("change", () => {
        const set = new Set(this.scopeState.selected);
        c.checked ? set.add(c.value) : set.delete(c.value);
        this.scopeState.selected = [...set];
        refreshCount();
      });
    });
    panel.querySelectorAll(".scope-ncheck").forEach(c => {
      c.addEventListener("change", () => {
        const set = new Set(this.scopeState.neighbourSelected);
        c.checked ? set.add(c.value) : set.delete(c.value);
        this.scopeState.neighbourSelected = [...set];
        refreshCount();
      });
    });
    panel.querySelectorAll(".scope-arrival-chip").forEach(chip => {
      chip.addEventListener("click", () => { this.scopeState.arrival = chip.dataset.city; this.renderScopePanel(); });
    });
    const arrival = panel.querySelector("#scopeArrival");
    if (arrival) {
      attachPlaceAutocomplete(arrival);
      const take = () => { this.scopeState.arrival = arrival.value.trim(); refreshCount(); };
      arrival.addEventListener("input", take);
      arrival.addEventListener("change", take);
    }
    refreshCount();
  }

  /** Makes sure the "Plan your area" questions were answered before searching. Returns false to stop. */
  async ensureScope() {
    if (!(this.scopeInfo && this.scopeFor === this.destination)) await this.loadScope();
    this.syncScopeDays();
    if (!this.isBigPlace()) return true;
    const input = document.getElementById("scopeArrival");
    if (input) this.scopeState.arrival = input.value.trim();
    if (!this.scopeState.arrival) {
      toast.info(`${this.scopeInfo.name} is large. Tell us which city you will land in, and pick the places you would like to visit.`);
      const panel = document.getElementById("scopePanel");
      if (panel) panel.scrollIntoView({ behavior: "smooth", block: "center" });
      if (input) input.focus();
      return false;
    }
    if (this.scopeState.arrival.toLowerCase() === this.source.toLowerCase()) {
      toast.error("The landing city cannot be the same as your starting city.");
      return false;
    }
    return true;
  }

  // --- Step 4: one hotel for each stay, near the places of those days ---

  startHotelStep() {
    this.stayHotels = {};
    this.stayChoices = {};
    this.stayOpen = null;
    this.transferChoices = {};
    this.transferData = {};
    this.transferTab = {};
    this._transferPromises = {};
    this.anchors = {};
    const first = this.selectedOutbound;
    if (first && String(first.mode).toLowerCase() === "flight") this.loadAnchor(0, first.destination);
    this.renderStayBlocks();
    this.setStep(3);
  }

  renderStayBlocks() {
    const container = document.getElementById("stayBlocksContainer");
    const notices = document.getElementById("stayNotices");
    const sk = this.skeleton;
    if (!container || !sk) return;

    if (notices) {
      const msgs = (sk.notices || []).map(n => `<div class="date-strip-notice">ℹ️ ${escapeHtml(n)}</div>`).join("");
      notices.innerHTML = msgs + buildTransfersHtml(sk.transfers);
    }

    container.innerHTML = "";
    const needing = (sk.stay_blocks || []).filter(b => b.needs_hotel);
    // One stay is open at a time: the one being changed, otherwise the first stay without a decision
    const firstUndecided = needing.find(b => this.stayChoices[b.index] === undefined);
    const openIdx = (this.stayOpen !== null && this.stayOpen !== undefined)
      ? this.stayOpen
      : (firstUndecided ? firstUndecided.index : null);

    let previousHotel = null; // the hotel of the stay before, so a change of hotel is shown clearly
    (sk.stay_blocks || []).forEach(b => {
      const chosenHere = this.stayChoices[b.index];
      if (b.needs_hotel && chosenHere && previousHotel && chosenHere.name !== previousHotel.name) {
        const hop = document.createElement("div");
        hop.innerHTML = buildHotelConnectorHtml(previousHotel, chosenHere);
        container.appendChild(hop.firstElementChild);
      }
      if (b.needs_hotel && chosenHere) previousHotel = chosenHere;
      if (!b.needs_hotel) {
        const note = document.createElement("div");
        note.className = "stay-block stay-none";
        note.textContent = `Day ${b.start_day} (${b.area}) is your departure day, so no overnight stay is needed.`;
        container.appendChild(note);
        return;
      }
      const decided = this.stayChoices[b.index] !== undefined;
      const inbound = this.inboundTransfer(b.index);
      const travel = this.transferChoices[b.index];
      const inboundLine = travel ? buildTransferSummaryLine(travel) : "";
      const wrap = document.createElement("div");
      if (b.index !== openIdx) {
        wrap.innerHTML = decided ? buildStayDoneHtml(b, this.stayChoices[b.index], inboundLine) : buildStayUpcomingHtml(b);
        const card = wrap.firstElementChild;
        container.appendChild(card);
        card.querySelector(".stay-change").addEventListener("click", () => {
          this.stayOpen = b.index;
          this.renderStayBlocks();
          this.focusStay(b.index);
        });
        return;
      }
      if (inbound && !travel) {
        // a long move: first choose how to get there, then the hotel
        wrap.innerHTML = buildTransferChooserHtml(b, inbound, this.transferTab[b.index] || this.defaultTransferTab(inbound));
        container.appendChild(wrap.firstElementChild);
        this.wireTravelChooser(container.lastElementChild, b, inbound);
        return;
      }
      wrap.innerHTML = buildStayBlockHtml(b, this.stayChoices[b.index], inboundLine);
      const el = wrap.firstElementChild;
      container.appendChild(el);
      const changeTravel = el.querySelector(".stay-change-travel");
      if (changeTravel) changeTravel.addEventListener("click", () => {
        delete this.transferChoices[b.index];
        delete this.anchors[b.index];
        this.stayOpen = b.index;
        this.renderStayBlocks();
      });
      el.querySelector(".stay-find").addEventListener("click", () => this.searchStayHotels(b.index));
      el.querySelector(".stay-skip").addEventListener("click", () => this.skipStayHotel(b.index));
      el.querySelector(".stay-sort").addEventListener("change", () => {
        if (this.stayHotels[b.index]) this.searchStayHotels(b.index);
      });
      if (this.stayHotels[b.index] && this.stayHotels[b.index].hotels) this.renderStayHotels(b.index);
      else if (!this.stayHotels[b.index]) this.searchStayHotels(b.index); // open stays load their hotels by themselves
    });
  }

  // --- Travelling between two stays (long moves) ---

  inboundTransfer(blockIndex) {
    return ((this.skeleton && this.skeleton.transfers) || []).find(t => t.to_stay === blockIndex && t.needs_choice) || null;
  }

  defaultTransferTab(transfer) {
    return transfer.distance_km >= 350 ? "flight" : "train";
  }

  /** One search per journey, shared by every re-draw of the chooser (so it never gets stuck on "searching"). */
  loadTransferOptions(idx, transfer) {
    if (this._transferPromises[idx]) return this._transferPromises[idx];
    this.transferData[idx] = { data: null, loading: true, error: false };
    this._transferPromises[idx] = (async () => {
      if (!transfer.date) { this.transferData[idx] = { data: null, loading: false, error: false }; return; }
      try {
        const data = await api.searchTransportLeg({
          origin: transfer.from_area,
          destination: transfer.to_area,
          date: transfer.date,
          travelers: this.travelers,
          preference: "best-overall",
          currency: "INR",
          train_classes: this.trainClasses
        });
        this.transferData[idx] = { data, loading: false, error: false };
      } catch (_) {
        this.transferData[idx] = { data: null, loading: false, error: true };
      }
    })();
    return this._transferPromises[idx];
  }

  wireTravelChooser(el, block, transfer) {
    const idx = block.index;
    const panel = el.querySelector("[data-panel]");
    const paint = () => {
      if (!document.contains(el)) return; // the page moved on
      const tab = this.transferTab[idx] || this.defaultTransferTab(transfer);
      el.querySelectorAll(".transfer-tab").forEach(b => {
        b.classList.toggle("active", b.dataset.tab === tab);
        b.setAttribute("aria-selected", String(b.dataset.tab === tab));
      });
      const st = this.transferData[idx] || {};
      panel.innerHTML = buildTransferPanelHtml(tab, st.data || null, transfer, st);
      panel.querySelectorAll(".transfer-select").forEach(btn => btn.addEventListener("click", () => this.chooseTransfer(idx, btn, st.data)));
      panel.querySelectorAll(".transfer-book").forEach(btn => btn.addEventListener("click", () => {
        const opt = ((st.data && st.data.flights) || []).find(o => o.id === btn.dataset.id);
        if (opt) this.showFlightBookingOptions(opt);
      }));
    };
    el.querySelectorAll(".transfer-tab").forEach(b => b.addEventListener("click", () => { this.transferTab[idx] = b.dataset.tab; paint(); }));
    this.loadTransferOptions(idx, transfer).then(paint);
    paint();
  }

  chooseTransfer(idx, btn, data) {
    const kind = btn.dataset.kind;
    let choice = { mode: kind };
    if (kind === "flight" || kind === "train") {
      const list = (data && (kind === "flight" ? data.flights : data.trains)) || [];
      const option = list.find(o => o.id === btn.dataset.id);
      if (!option) return;
      choice = { mode: kind, option };
      if (kind === "flight") this.loadAnchor(idx, option.destination);
    }
    this.transferChoices[idx] = choice;
    this.persistSessionState();
    this.renderStayBlocks();
    this.focusStay(idx);
  }

  /** Looks up where the airport is, so hotels can be ranked by closeness to it. Quietly does nothing if unknown. */
  async loadAnchor(idx, terminalName) {
    const name = String(terminalName || "").replace(/^.*\((.*)\)$/, "$1").trim();
    if (!name) return;
    try {
      const res = await api.getTerminalLocation(name);
      if (res && res.found) {
        this.anchors[idx] = { lat: res.latitude, lon: res.longitude, label: name };
        if (this.stayHotels[idx] && this.stayHotels[idx].hotels) this.renderStayHotels(idx); // re-rank with the new information
      }
    } catch (_) { /* ranking works without it */ }
  }

  focusStay(index) {
    const el = this.stayEl(index);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  stayEl(index) {
    return document.querySelector(`#stayBlocksContainer .stay-block[data-index="${index}"]`);
  }

  async searchStayHotels(index) {
    const block = (this.skeleton.stay_blocks || []).find(b => b.index === index);
    const el = this.stayEl(index);
    if (!block || !el) return;
    const slot = el.querySelector(".stay-hotels");
    const sort = el.querySelector(".stay-sort").value;
    if (!this.stayHotels[index]) this.stayHotels[index] = { hotels: null, loading: true };
    slot.innerHTML = `<div class="empty-state" style="grid-column:1/-1;"><p>Searching hotels near ${escapeHtml(block.search_query)}…</p></div>`;
    try {
      const res = await api.searchHotels({
        destination: block.search_query,
        check_in_date: block.check_in || this.outboundDate,
        check_out_date: block.check_out || this.returnDate || this.outboundDate,
        travelers: this.travelers,
        sort_by: sort === "best_match" ? "relevance" : sort,
        currency: "INR"
      });
      this.stayHotels[index] = { hotels: res.hotels || [], notice: res.notice || "" };
      this.renderStayHotels(index);
    } catch (err) {
      delete this.stayHotels[index]; // allow another try
      slot.innerHTML = `<div class="empty-state" style="grid-column:1/-1;"><p class="error-text">Could not load hotels: ${escapeHtml(err.message)}</p><p>Press “Find hotels near here” to try again.</p></div>`;
    }
  }

  renderStayHotels(index) {
    const el = this.stayEl(index);
    if (!el) return;
    const slot = el.querySelector(".stay-hotels");
    const data = this.stayHotels[index];
    const block = (this.skeleton.stay_blocks || []).find(b => b.index === index);
    slot.innerHTML = "";
    if (!data || !data.hotels.length) {
      slot.innerHTML = `<div class="empty-state" style="grid-column:1/-1;"><h3>No hotels returned</h3><p>${escapeHtml(data && data.notice ? data.notice : "Try again, or choose “No hotel needed” for this stay.")}</p></div>`;
      return;
    }
    const chosen = this.stayChoices[index];
    const sortValue = el.querySelector(".stay-sort").value;
    const centroid = block && block.centroid ? { lat: block.centroid.lat, lon: block.centroid.lon } : null;
    const ranked = scoreHotels(data.hotels, { centroid, anchor: this.anchors[index] || null });
    const infoById = new Map(ranked.map(r => [r.hotel.id, r]));
    const ordered = sortValue === "best_match" ? ranked.map(r => r.hotel) : data.hotels;
    ordered.forEach(h => slot.appendChild(this.buildHotelCard(h, !!(chosen && chosen.id === h.id), index, block, infoById.get(h.id))));
  }

  buildHotelCard(h, isSelected, index, block, info = null) {
    const card = document.createElement("article");
    card.className = "hotel-card" + (isSelected ? " selected" : "");
    card.id = `hotel-${index}-${h.id}`;
    const labelsHtml = (h.recommendation_labels || []).map(l => {
      let cls = "hotel-tag";
      if (l === "Cheapest") cls += " cheapest";
      else if (l === "Best Rated") cls += " best-rated";
      else if (l === "Best Value") cls += " best-value";
      return `<span class="${cls}">${escapeHtml(l)}</span>`;
    }).join("");
    const priceText = h.nightly_price ? `₹${Math.round(h.nightly_price).toLocaleString("en-IN")} / night` : "No price data";
    const totalText = h.total_price ? `(Stay total: ₹${Math.round(h.total_price).toLocaleString("en-IN")})` : "";
    const ratingText = h.rating ? `★ ${h.rating} ${h.review_count ? `(${h.review_count.toLocaleString()} reviews)` : ""}` : "Unrated";
    card.innerHTML = `
      <div>
        <div class="hotel-labels-row" style="margin-bottom:6px;">${labelsHtml}</div>
        <h3 style="font-size:1.1rem;margin-bottom:4px;color:var(--color-text-primary);">${escapeHtml(h.name)}</h3>
        <div style="font-size:0.85rem;color:var(--color-text-muted);margin-bottom:6px;">${h.star_class ? `${h.star_class}-Star • ` : ""}${escapeHtml(ratingText)}</div>
        <p style="font-size:0.825rem;color:var(--color-text-secondary);margin-bottom:8px;">${escapeHtml(h.address)}</p>
        ${h.free_cancellation ? `<span class="badge badge-primary" style="font-size:0.75rem;">✓ Free Cancellation</span>` : ""}
        ${buildMatchChipsHtml(info)}
      </div>
      ${h.recommendation_reason ? `<div class="transport-reason-note" style="margin:4px 0;">${escapeHtml(h.recommendation_reason)}</div>` : ""}
      <div style="border-top:1px solid var(--color-border);padding-top:10px;margin-top:auto;">
        <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px;">
          <div style="font-size:1.15rem;font-weight:800;color:var(--color-primary);">${priceText}</div>
          <div style="font-size:0.75rem;color:var(--color-text-muted);">${totalText}</div>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          <button type="button" class="btn btn-secondary btn-sm btn-hotel-details" style="flex:1;">Price Comparison</button>
          <button type="button" class="btn btn-primary btn-sm btn-select-hotel" style="flex:1;">${isSelected ? "Selected ✓" : "Select Hotel"}</button>
        </div>
      </div>`;
    card.querySelector(".btn-select-hotel").addEventListener("click", () => this.chooseStayHotel(index, h));
    card.querySelector(".btn-hotel-details").addEventListener("click", () =>
      this.openHotelPriceComparisonModal(h, block ? { check_in: block.check_in, check_out: block.check_out } : null));
    return card;
  }

  /** Where to go after a decision: the next undecided stay opens, the finished one shrinks to its card. */
  afterStayDecision() {
    this.stayOpen = null;
    this.renderStayBlocks();
    const next = (this.skeleton.stay_blocks || []).find(b => b.needs_hotel && this.stayChoices[b.index] === undefined);
    if (next) this.focusStay(next.index);
  }

  chooseStayHotel(index, hotel) {
    this.stayChoices[index] = hotel;
    this.afterStayDecision();
    this.persistSessionState();
    toast.success(`Stay ${index + 1}: ${hotel.name}`);
  }

  skipStayHotel(index) {
    this.stayChoices[index] = null;
    this.afterStayDecision();
    this.persistSessionState();
  }

  /** Adds the chosen hotels to the plan (server refreshes directions and the budget) and shows the result. */
  async handleFinalize() {
    const sk = this.skeleton;
    const resultsContainer = document.getElementById("itineraryResults");
    if (!sk || !resultsContainer) return;
    const needing = (sk.stay_blocks || []).filter(b => b.needs_hotel);
    const unchosenTravel = (sk.transfers || []).filter(t => t.needs_choice && !this.transferChoices[t.to_stay]);
    if (unchosenTravel.length) {
      toast.info(`No travel chosen for ${unchosenTravel.map(t => `${t.from_area} → ${t.to_area}`).join(", ")}. A cab estimate will be used.`);
    }
    const missing = needing.filter(b => this.stayChoices[b.index] === undefined);
    if (missing.length) {
      toast.info(`No hotel chosen for ${missing.map(b => `Stay ${b.index + 1}`).join(", ")}. It will be left out of the budget.`);
    }
    resultsContainer.innerHTML = `
      <div class="empty-state"><h3>Putting your trip together…</h3><p>Adding your hotels, refreshing directions and calculating the budget.</p></div>`;
    this.setStep(5);
    try {
      const data = await api.finalizeItinerary({
        itinerary: sk,
        stay_hotels: needing.map(b => ({ block_index: b.index, hotel: this.stayChoices[b.index] || null })),
        travelers_count: this.travelers,
        rooms: this.rooms,
        budget_per_person_per_day: this.prefs.budgetPerDay || 3000,
        transportation: this.prefs.localTransport || "public",
        transport_modes: this.prefs.localModes || null,
        transfer_choices: Object.entries(this.transferChoices).map(([to, c]) => ({ to_stay: Number(to), mode: c.mode, option: c.option || null }))
      });
      Object.assign(data, {
        source: this.source,
        destination: data.destination || this.destination,
        departure_date: this.outboundDate,
        return_date: this.returnDate
      });
      this.finalItinerary = data;
      this.renderFinalItinerary(resultsContainer, data);
      this.persistSessionState();
      announceServiceReady("Itinerary Planner");
      const names = (data.selected_hotels || []).map(h => h.name).filter(Boolean);
      api.createHistory({
        feature_type: "itinerary",
        title: `Trip: ${this.source} → ${this.destination} (${data.duration_days} Days)`,
        preview: `${this.selectedOutbound?.operator || "Transport"} + ${names.length ? names.join(", ") : "No hotel"} • ${data.estimated_budget_total}`,
        payload: {
          ...data,
          travellers: this.travelers,
          preference: this.preference,
          selected_outbound_transport: this.selectedOutbound,
          selected_return_transport: this.selectedReturn
        }
      }).catch(e => console.warn("Auto-save history notice:", e));
      toast.success("Your itinerary is ready!");
    } catch (err) {
      resultsContainer.innerHTML = `
        <div class="empty-state">
          <h3>Could not finish the itinerary</h3>
          <p class="error-text">${escapeHtml(err.message)}</p>
          <button type="button" class="btn btn-primary" id="btnRetryFinalize">Try again</button>
          <button type="button" class="btn btn-secondary" id="btnBackToStays">&larr; Back to hotels</button>
        </div>`;
      resultsContainer.querySelector("#btnRetryFinalize").addEventListener("click", () => this.handleFinalize());
      resultsContainer.querySelector("#btnBackToStays").addEventListener("click", () => this.setStep(3));
    }
  }

  async openHotelPriceComparisonModal(hotel, dates = null) {
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
          check_in_date: (dates && dates.check_in) || this.outboundDate,
          check_out_date: (dates && dates.check_out) || this.returnDate || this.outboundDate,
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

  /** Local transport: any combination of walking / public transit / taxi (at least one stays on). */
  initTransportModes() {
    const grid = document.getElementById("localTransportModes");
    if (!grid) return;
    grid.querySelectorAll(".mode-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        const active = grid.querySelectorAll(".mode-chip.active");
        if (chip.classList.contains("active") && active.length === 1) {
          toast.info("Keep at least one way of getting around selected.");
          return;
        }
        chip.classList.toggle("active");
        chip.setAttribute("aria-pressed", String(chip.classList.contains("active")));
      });
    });
  }

  selectedTransportModes() {
    const modes = Array.from(document.querySelectorAll("#localTransportModes .mode-chip.active")).map(c => c.dataset.value);
    return modes.length ? modes : ["walking", "public"];
  }

  /** The single value older screens and saved trips understand. */
  primaryTransport(modes) {
    if (modes.includes("public")) return "public";
    if (modes.includes("taxi")) return "driving";
    return "walking";
  }

  setTransportModes(modes) {
    const want = new Set(modes);
    document.querySelectorAll("#localTransportModes .mode-chip").forEach(chip => {
      const on = want.has(chip.dataset.value);
      chip.classList.toggle("active", on);
      chip.setAttribute("aria-pressed", String(on));
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
    const transportModes = this.selectedTransportModes();
    const submitBtn = document.getElementById("btnGenerateItinerary");

    const budgetPerDay = budgetInput ? parseFloat(budgetInput.value) : 3000;
    const foodType = foodTypeSelect ? foodTypeSelect.value : "no-preference";
    const pace = paceSelect ? paceSelect.value : "moderate";
    const localTransport = this.primaryTransport(transportModes);

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
      transport_modes: transportModes,
      selected_outbound_transport: this.selectedOutbound,
      selected_return_transport: this.selectedReturn,
      rooms: this.rooms,
      areas: this.areasList(),
      scope_kind: this.scopeInfo ? this.scopeInfo.kind : null,
      arrival_city: this.isBigPlace() ? this.scopeState.arrival : null
    };
    this.prefs = { budgetPerDay, localTransport, localModes: transportModes, durationDays };

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span>Planning your trip…</span>`;
    }

    resultsContainer.innerHTML = `
      <div class="empty-state">
        <div class="skeleton" style="width:60px;height:60px;border-radius:50%;margin:0 auto 16px auto;"></div>
        <h3>Synthesizing door-to-door itinerary for ${escapeHtml(this.destination)}…</h3>
        <p>Planning real places day by day around your ${escapeHtml(this.selectedOutbound?.operator || 'outbound transit')} arrival. Hotels come next.</p>
      </div>
    `;

    this.setStep(5);

    try {
      // The plan comes first (no hotels); the traveller then picks a hotel for each stay
      this.skeleton = await api.generateItinerary(payload);
      this.finalItinerary = null;
      this.persistSessionState();
      const needsHotel = (this.skeleton.stay_blocks || []).some(b => b.needs_hotel);
      if (needsHotel) {
        this.startHotelStep();
        toast.success("Your plan is ready. Now choose where to stay.");
      } else {
        await this.handleFinalize();
      }
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
        submitBtn.innerHTML = `<span>Generate My Itinerary</span>`;
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

    // Attach PDF download handler (Section 23): the same code serves the button at the bottom
    headerRow.querySelector("#btnDownloadItineraryPdf").addEventListener("click", (e) => this.downloadFullPdf(data, e.currentTarget));

    // Mock-mode notice: sample places are for UI testing only, never real data
    if (data.data_mode === "mock") {
      const mockBanner = document.createElement("div");
      mockBanner.className = "sample-data-banner";
      mockBanner.setAttribute("role", "status");
      mockBanner.style.cssText = "margin-bottom:16px;padding:12px 16px;border-radius:var(--radius-md);background:var(--color-warning-light, #FEF3C7);border:1px solid var(--color-warning, #D97706);font-size:0.9rem;";
      mockBanner.textContent = "Sample data: MOCK_MODE is on, so the places, days and prices below are demo content (not real places for this destination). Set MOCK_MODE=false in .env for real results.";
      container.appendChild(mockBanner);
    }

    // A picture first: route, stays, numbers, and a map of everything that is planned
    const glance = document.createElement("div");
    glance.innerHTML = buildTripGlanceHtml(data);
    container.appendChild(glance.firstElementChild);
    const mapBox = document.createElement("div");
    mapBox.className = "trip-map";
    container.appendChild(mapBox);
    renderTripMap(mapBox, data);

    // 2. Journey & Hotel Summary Cards
    const journeyCard = document.createElement("div");
    journeyCard.className = "journey-summary-card";

    const ob = data.selected_outbound_transport;
    const ib = data.selected_return_transport;
    const htl = data.selected_hotel;
    const hasStays = (data.stay_blocks || []).some(b => b.needs_hotel);
    // The hotel a given day starts from (each stay can have its own)
    const hotelForDay = (n) => {
      const b = (data.stay_blocks || []).find(x => n >= x.start_day && n <= x.end_day);
      return hasStays ? (b && b.hotel ? b.hotel : null) : htl;
    };

    journeyCard.innerHTML = `
      <h3 style="font-size:1.15rem;color:var(--color-primary);margin-bottom:12px;">🚆 Verified Journey & Accommodation</h3>
      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:16px;">
        <div style="background:var(--color-surface-soft);padding:12px;border-radius:var(--radius-md);">
          <strong>Outbound Transit:</strong><br/>
          ${ob ? `${escapeHtml(ob.operator)} (${escapeHtml(ob.number || '')})<br/>${escapeHtml(ob.departure_time)} → ${escapeHtml(ob.arrival_time)}<br/><span style="color:var(--color-primary);font-weight:700;">${ob.price ? "₹" + Math.round(ob.price).toLocaleString("en-IN") + " per person (live quote)" : "Fare not provided"}</span>` : 'Not specified'}
          ${ob && ob.booking_url ? `<br/><a href="${escapeHtml(ob.booking_url)}" target="_blank" rel="noopener noreferrer" style="font-size:0.8rem;color:var(--color-accent);font-weight:600;">Provider Booking Link ↗</a>` : ''}
        </div>
        <div style="background:var(--color-surface-soft);padding:12px;border-radius:var(--radius-md);">
          <strong>Return Transit:</strong><br/>
          ${ib ? `${escapeHtml(ib.operator)} (${escapeHtml(ib.number || '')})<br/>${escapeHtml(ib.departure_time)} → ${escapeHtml(ib.arrival_time)}<br/><span style="color:var(--color-primary);font-weight:700;">${ib.price ? "₹" + Math.round(ib.price).toLocaleString("en-IN") + " per person (live quote)" : "Fare not provided"}</span>` : 'One-way / Not specified'}
          ${ib && ib.booking_url ? `<br/><a href="${escapeHtml(ib.booking_url)}" target="_blank" rel="noopener noreferrer" style="font-size:0.8rem;color:var(--color-accent);font-weight:600;">Provider Booking Link ↗</a>` : ''}
        </div>
        <div style="background:var(--color-surface-soft);padding:12px;border-radius:var(--radius-md);">
          <strong>Accommodation:</strong><br/>
          ${hasStays ? buildStaysSummaryHtml(data) : htl ? `<b>${escapeHtml(htl.name)}</b> (★ ${htl.rating || 'N/A'})<br/>${escapeHtml(htl.address || '')}<br/><span style="color:var(--color-primary);font-weight:700;">₹${htl.nightly_price || 0}/night (Total: ₹${htl.total_price || 0})</span>` : '<em>Not selected (self-arranged)</em>'}
          ${!hasStays && htl && htl.booking_url ? `<br/><a href="${escapeHtml(htl.booking_url)}" target="_blank" rel="noopener noreferrer" style="font-size:0.8rem;color:var(--color-accent);font-weight:600;">Hotel Booking Link ↗</a>` : ''}
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
        const hasBoth = d.walk_minutes != null && d.drive_minutes != null;
        const chips = [
          d.distance_km != null ? `<span class="badge badge-secondary">📏 ~${d.distance_km} km</span>` : "",
          hasBoth ? `<span class="badge badge-secondary">🚶 ~${d.walk_minutes} min walk</span>` : "",
          hasBoth ? `<span class="badge badge-secondary">🚗 ~${d.drive_minutes} min by car/auto</span>` : "",
          d.mode ? `<span class="badge badge-primary">👍 Suggested: ${escapeHtml(d.mode)}</span>` : "",
          (!hasBoth && d.minutes != null) ? `<span class="badge badge-secondary">⏱️ ~${d.minutes} min</span>` : ""
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
          ${placeAboutHtml(p)}
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

      const dayHotel = hotelForDay(day.day_number);
      const startLabel = dayHotel
        ? `<span class="stop-label hotel">🏨 Hotel / Stay</span> <b>${escapeHtml(dayHotel.name)}</b>${dayHotel.address ? ` — ${escapeHtml(dayHotel.address)}` : ""}`
        : "";

      dayEl.style.setProperty("--day-color", dayColor(day.day_number));
      const highlights = dayHighlights(day);
      dayEl.innerHTML = `
        <div class="day-card-header">
          <h3 class="day-card-title">Day ${day.day_number}${day.area ? " · " + escapeHtml(day.area) : ""}: ${escapeHtml(day.theme)}</h3>
          <span class="badge badge-primary">${escapeHtml(day.estimated_day_cost)}</span>
        </div>
        ${highlights.length ? `<div class="day-highlights">✨ Today: ${highlights.map(h => `<span>${escapeHtml(h)}</span>`).join("")}</div>` : ""}
        ${buildDayNotesHtml(day.notes, ["arrival", "hotel_change"])}
        ${startLabel ? `<div class="day-start-point">${startLabel}<div class="stop-meta">Each stop shows how long it takes to get there from the one before. The first stop is measured from here.</div></div>` : ""}
        ${renderSegment("🌅 Morning", day.morning)}
        ${renderFood("Lunch", day.food_stop_lunch)}
        ${renderSegment("☀️ Afternoon", day.afternoon)}
        ${renderFood("Dinner", day.food_stop_dinner)}
        ${renderSegment("🌙 Evening", day.evening)}
        ${buildDayNotesHtml(day.notes, ["departure"])}
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
    // Newer itineraries carry a full breakdown: headline numbers + a button for the details
    if (cb.detail) {
      costCard.innerHTML = `
        <h3 style="font-size:1.25rem;color:var(--color-text-primary);margin-bottom:8px;">Trip budget</h3>
        <p style="font-size:0.9rem;color:var(--color-text-muted);margin-bottom:12px;">Flight and hotel numbers are provider quotes; everything else is an estimate from your daily budget.</p>
        ${buildBudgetSummaryHtml(cb)}
        <button type="button" class="btn btn-primary" id="btnBudgetBreakdown" aria-expanded="false" style="margin-top:12px;">View total price breakdown</button>
        <div id="budgetBreakdown" hidden>${buildBudgetBreakdownHtml(cb)}</div>`;
      const toggle = costCard.querySelector("#btnBudgetBreakdown");
      const panel = costCard.querySelector("#budgetBreakdown");
      toggle.addEventListener("click", () => {
        panel.hidden = !panel.hidden;
        toggle.textContent = panel.hidden ? "View total price breakdown" : "Hide price breakdown";
        toggle.setAttribute("aria-expanded", String(!panel.hidden));
      });
    }
    container.appendChild(costCard);

    // 5. Short version for use while travelling (view first, then download as PDF)
    container.appendChild(this.buildQuickVersionSection(data));
    container.appendChild(this.buildBottomActions(data));
    announceServiceReady("Itinerary Planner");
  }

  async downloadFullPdf(data, btn) {
    const original = btn.innerHTML;
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
        hotels: data.selected_hotels,
        days: data.days,
        cost_breakdown: data.cost_breakdown,
        estimated_budget_total: data.estimated_budget_total
      });
      const blobUrl = window.URL.createObjectURL(pdfBlob);
      const a = document.createElement("a");
      a.style.display = "none";
      a.href = blobUrl;
      a.download = `${String(data.destination || "Trip").replace(/\s+/g, "_")}_Itinerary.pdf`;
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
      btn.innerHTML = original;
    }
  }

  /** Download buttons at the very end, so nobody has to scroll back up. */
  buildBottomActions(data) {
    const bar = document.createElement("div");
    bar.className = "itinerary-bottom-actions";
    bar.innerHTML = `
      <button type="button" class="btn btn-primary" id="btnDownloadPdfBottom">⬇ Download full PDF</button>
      <button type="button" class="btn btn-secondary" id="btnBackToTop">↑ Back to top</button>`;
    bar.querySelector("#btnDownloadPdfBottom").addEventListener("click", (e) => this.downloadFullPdf(data, e.currentTarget));
    bar.querySelector("#btnBackToTop").addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
    return bar;
  }

  /** "Quick version" card at the end of the itinerary: shorter view with map links, then its own PDF. */
  buildQuickVersionSection(data) {
    const wrap = document.createElement("section");
    wrap.className = "quick-version-section";
    wrap.setAttribute("aria-label", "Quick version of the itinerary");
    wrap.innerHTML = `
      <div class="quick-cta">
        <div>
          <strong>📱 Need something shorter for the road?</strong>
          <p>Get a one-glance version with only the places, meals and map links. You can read it here first, then download it as a PDF.</p>
        </div>
        <button type="button" class="btn btn-primary" id="btnQuickVersion">Generate quick version</button>
      </div>
      <div id="quickVersionResult" hidden></div>`;

    const result = wrap.querySelector("#quickVersionResult");
    const openBtn = wrap.querySelector("#btnQuickVersion");

    openBtn.addEventListener("click", () => {
      result.innerHTML = `
        ${buildQuickVersionHtml(data)}
        <div class="qv-actions">
          <button type="button" class="btn btn-primary btn-sm" id="btnQuickPdf">⬇ Download quick version (PDF)</button>
          <button type="button" class="btn btn-secondary btn-sm" id="btnHideQuick">Hide quick version</button>
        </div>`;
      result.hidden = false;
      openBtn.textContent = "Refresh quick version";
      result.scrollIntoView({ behavior: "smooth", block: "start" });

      result.querySelector("#btnHideQuick").addEventListener("click", () => {
        result.hidden = true;
        result.innerHTML = "";
        openBtn.textContent = "Generate quick version";
      });

      const pdfBtn = result.querySelector("#btnQuickPdf");
      pdfBtn.addEventListener("click", async () => {
        const original = pdfBtn.innerHTML;
        pdfBtn.disabled = true;
        pdfBtn.textContent = "Preparing PDF…";
        try {
          const blob = await api.downloadPdf(`${data.title} (Quick Version)`, {
            mode: "short",
            title: `${data.title} (Quick Version)`,
            destination: data.destination,
            source: data.source,
            departure_date: data.departure_date,
            return_date: data.return_date,
            duration_days: data.duration_days,
            outbound_transport: data.selected_outbound_transport,
            return_transport: data.selected_return_transport,
            hotel: data.selected_hotel,
            hotels: data.selected_hotels,
            days: data.days,
            estimated_budget_total: data.estimated_budget_total
          });
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.style.display = "none";
          a.href = url;
          a.download = `${String(data.destination || "Trip").replace(/\s+/g, "_")}_Quick_Itinerary.pdf`;
          document.body.appendChild(a);
          a.click();
          window.URL.revokeObjectURL(url);
          a.remove();
          toast.success("Quick version downloaded.");
        } catch (err) {
          console.error("Quick PDF error:", err);
          toast.error("Quick PDF failed: " + err.message);
        } finally {
          pdfBtn.disabled = false;
          pdfBtn.innerHTML = original;
        }
      });
    });
    return wrap;
  }

  // --- Session Persistence (Section 19) ---

  /** Everything on the page right now: inputs, selections, hotel list, preferences, result. */
  collectDraftState() {
    const val = (id) => { const el = document.getElementById(id); return el ? el.value : ""; };
    // Before the first search the typed values only exist in the form fields
    const live = this.currentStep === 1;
    const interests = Array.from(document.querySelectorAll(".chip-selection-grid .select-chip.active"))
      .map(c => c.dataset.value || c.textContent.trim());

    return {
      currentStep: this.currentStep,
      source: live ? val("itinerarySource").trim() : this.source,
      destination: live ? val("itineraryDest").trim() : this.destination,
      outboundDate: live ? val("itineraryDepDate") : this.outboundDate,
      returnDate: live ? val("itineraryRetDate") : this.returnDate,
      travelers: live ? (parseInt(val("itineraryTravelers"), 10) || 1) : this.travelers,
      preference: live ? (val("itineraryPreference") || this.preference) : this.preference,
      transportData: this.transportData,
      trainClasses: this.trainClasses,
      fromStationCode: this.fromStationCode,
      toStationCode: this.toStationCode,
      stations: this.stations,
      dateStrips: this.dateStrips,
      selectedOutbound: this.selectedOutbound,
      selectedReturn: this.selectedReturn,
      hotelData: this.hotelData,
      selectedHotel: this.selectedHotel,
      hotelSkipped: this.hotelSkipped,
      finalItinerary: this.finalItinerary,
      skeleton: this.skeleton,
      stayChoices: this.stayChoices,
      transferChoices: this.transferChoices,
      anchors: this.anchors,
      scope: { info: this.scopeInfo, for: this.scopeFor, state: this.scopeState },
      transportDestination: this.transportDestination,
      rooms: this.rooms,
      tripPrefs: this.prefs,
      prefs: {
        budget: val("itineraryBudgetInput"),
        foodType: val("foodType"),
        pace: val("itineraryPace"),
        localTransportModes: this.selectedTransportModes(),
        hotelSort: val("hotelSortSelect"),
        interests,
        cuisines: this.cuisinePicker ? this.cuisinePicker.getTags() : [],
        bakery: this.bakeryPicker ? this.bakeryPicker.getTags() : []
      }
    };
  }

  /** Title + state for the "Save session" button. */
  buildDraftForSaving() {
    const state = this.collectDraftState();
    const route = [state.source, state.destination].filter(Boolean).join(" → ") || "New trip";
    const dates = state.outboundDate ? ` (${state.outboundDate}${state.returnDate ? " to " + state.returnDate : ""})` : "";
    const stepNames = ["", "route", "transport", "hotel", "preferences", "final itinerary"];
    return {
      hasContent: !!(state.source || state.destination),
      title: `${route}${dates} · step ${state.currentStep} of 5: ${stepNames[state.currentStep] || ""}`,
      state
    };
  }

  persistSessionState() {
    try {
      sessionStorage.setItem("slg_session_itinerary", JSON.stringify(this.collectDraftState()));
    } catch (_) {}
  }

  applyPrefs(prefs) {
    if (!prefs) return;
    const set = (id, v) => { const el = document.getElementById(id); if (el && v !== undefined && v !== "") el.value = v; };
    set("itineraryBudgetInput", prefs.budget);
    set("itineraryBudgetSlider", prefs.budget);
    set("foodType", prefs.foodType);
    set("itineraryPace", prefs.pace);
    if (Array.isArray(prefs.localTransportModes)) this.setTransportModes(prefs.localTransportModes);
    else if (prefs.localTransport) {
      // trips saved before multi-select
      this.setTransportModes({ public: ["walking", "public"], walking: ["walking"], driving: ["taxi"] }[prefs.localTransport] || ["walking", "public"]);
    }
    set("hotelSortSelect", prefs.hotelSort);
    if (Array.isArray(prefs.interests)) {
      document.querySelectorAll(".chip-selection-grid .select-chip").forEach(chip => {
        chip.classList.toggle("active", prefs.interests.includes(chip.dataset.value || chip.textContent.trim()));
      });
    }
    if (this.cuisinePicker && prefs.cuisines) this.cuisinePicker.setTags(prefs.cuisines);
    if (this.bakeryPicker && prefs.bakery) this.bakeryPicker.setTags(prefs.bakery);
  }

  restoreSessionState() {
    try {
      const raw = sessionStorage.getItem("slg_session_itinerary");
      if (!raw) return;
      const data = JSON.parse(raw);
      if (!data || (!data.destination && !data.source)) return;

      this.source = data.source || "";
      this.destination = data.destination || "";
      this.outboundDate = data.outboundDate || "";
      this.returnDate = data.returnDate || "";
      this.travelers = data.travelers || 1;
      this.preference = data.preference || "best-overall";
      this.transportData = data.transportData;
      this.trainClasses = Array.isArray(data.trainClasses) ? data.trainClasses : [];
      this.fromStationCode = data.fromStationCode || "";
      this.toStationCode = data.toStationCode || "";
      this.stations = data.stations || { from: [], to: [] };
      this.dateStrips = data.dateStrips || { outbound: null, return: null };
      this.applyTrainPreferencesToForm();
      this.selectedOutbound = data.selectedOutbound;
      this.selectedReturn = data.selectedReturn;
      this.selectedHotel = data.selectedHotel;
      this.hotelSkipped = data.hotelSkipped;
      this.finalItinerary = data.finalItinerary;
      this.hotelData = data.hotelData || [];
      this.skeleton = data.skeleton || null;
      this.stayChoices = data.stayChoices || {};
      this.transferChoices = data.transferChoices || {};
      this.anchors = data.anchors || {};
      this.transportDestination = data.transportDestination || "";
      this.rooms = data.rooms || null;
      this.prefs = data.tripPrefs || {};
      if (data.scope && data.scope.info) {
        this.scopeInfo = data.scope.info;
        this.scopeFor = data.scope.for || "";
        this.scopeState = data.scope.state || this.scopeState;
        this.renderScopePanel();
      }
      const roomsInput = document.getElementById("itineraryRooms");
      if (roomsInput && this.rooms) roomsInput.value = this.rooms;
      this.applyPrefs(data.prefs);

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
        this.renderTransportLeg("outbound", this.transportData.outbound, { fetchStrip: false });
        if (this.transportData.return_leg) {
          this.renderTransportLeg("return", this.transportData.return_leg, { fetchStrip: false });
        }
        if (this.selectedOutbound) {
          this.selectTransportOption("outbound", this.selectedOutbound);
        }
        if (this.selectedReturn) {
          this.selectTransportOption("return", this.selectedReturn);
        }

        const step = data.currentStep || 2;
        if (this.skeleton && step === 3) {
          this.renderStayBlocks();
          this.setStep(3);
        } else if (step === 4) {
          this.setStep(4);
        } else {
          this.setStep(2);
        }
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