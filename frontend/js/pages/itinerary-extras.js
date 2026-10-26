/**
 * Pure HTML/data builders for the newer Itinerary Planner features. They contain no DOM
 * access or network calls, so they are easy to test and the controller stays small.
 *
 *  - nearby-date price chips for flights (green = cheap, orange = medium, red = expensive)
 *  - "Fare & Availability" block of a train card (real provider data only)
 *  - the train recommendation card
 *  - the short "quick version" of a finished itinerary (with map links)
 */

import { escapeHtml } from "../utils/formatters.js";

export const TRAIN_CLASSES = [
  { code: "SL", label: "Sleeper (SL)" },
  { code: "3A", label: "AC 3 Tier (3AC)" },
  { code: "2A", label: "AC 2 Tier (2AC)" },
  { code: "1A", label: "AC First Class (1AC)" }
];

const money = (v) => `₹${Math.round(v).toLocaleString("en-IN")}`;

// ---------------------------------------------------------------- stations
export function stationOptionLabel(s) {
  const city = s.city && s.city.toLowerCase() !== String(s.name).toLowerCase() ? ` (${s.city})` : "";
  return `${s.code} — ${s.name}${city}`;
}

export function stationOptionsHtml(stations, selected = "") {
  const auto = `<option value="">Automatic (main station of the city)</option>`;
  return auto + (stations || []).map((s) =>
    `<option value="${escapeHtml(s.code)}"${s.code === selected ? " selected" : ""}>${escapeHtml(stationOptionLabel(s))}</option>`
  ).join("");
}

// ---------------------------------------------------------------- nearby dates
const TIER_TEXT = { low: "Cheaper", medium: "Average", high: "Expensive", unknown: "No price" };

/**
 * @param resp      response of /api/transport/flight-dates
 * @param isDisabled (isoDate) => boolean   dates that make no sense (e.g. outbound after the return date)
 */
export function buildDateStripPromptHtml() {
  return `
    <div class="date-strip-head">
      <strong>Nearby dates</strong>
      <button type="button" class="btn btn-secondary btn-sm date-strip-load">💲 Compare prices for nearby dates</button>
    </div>
    <div class="date-strip-note">Flights are searched only for your chosen dates. Comparing nearby dates uses extra flight searches, so it runs only when you ask.</div>`;
}

export function buildDateStripHtml(resp, isDisabled = () => false) {
  const days = (resp && resp.days) || [];
  if (!days.length) {
    return `<div class="date-strip-empty">${escapeHtml((resp && resp.notice) || "Nearby dates could not be loaded.")}</div>`;
  }
  const chips = days.map((d) => {
    const tier = ["low", "medium", "high"].includes(d.tier) ? d.tier : "unknown";
    const disabled = !d.is_selected && isDisabled(d.date);
    const price = d.cheapest_price ? money(d.cheapest_price) : "—";
    const tags = [
      d.is_selected ? `<span class="date-chip-tag">Selected</span>` : "",
      d.is_cheapest ? `<span class="date-chip-tag best">Cheapest</span>` : ""
    ].join("");
    return `
      <button type="button" class="date-chip tier-${tier}${d.is_selected ? " selected" : ""}"
              data-date="${escapeHtml(d.date)}" ${d.is_selected || disabled ? "disabled" : ""}
              aria-pressed="${d.is_selected}" title="${escapeHtml(TIER_TEXT[tier])}${d.cheapest_price ? " · cheapest flight " + money(d.cheapest_price) : ""}">
        <span class="date-chip-date">${escapeHtml(d.label)}</span>
        <span class="date-chip-price">${price}</span>
        ${tags}
      </button>`;
  }).join("");
  const note = resp.note ? `<div class="date-strip-note">💡 ${escapeHtml(resp.note)}</div>` : "";
  const notice = resp.notice ? `<div class="date-strip-notice">ℹ️ ${escapeHtml(resp.notice)}</div>` : "";
  return `
    <div class="date-strip-head">
      <strong>Nearby dates</strong>
      <span class="date-strip-legend" aria-label="Colour meaning">
        <i class="lg low"></i>Cheap <i class="lg medium"></i>Medium <i class="lg high"></i>Expensive
      </span>
    </div>
    <div class="date-chip-row" role="group" aria-label="Choose a nearby date">${chips}</div>
    ${note}${notice}
    <div class="date-strip-foot">Cheapest flight per person on each day. Picking another date also refreshes the train options.</div>`;
}

// ---------------------------------------------------------------- train fare & availability
const AVAIL_TEXT = { AVAILABLE: "Available", RAC: "RAC", WL: "Waiting list" };

export function buildFareAvailabilityHtml(fa) {
  if (!fa || !(fa.classes || []).length) return "";
  const rows = fa.classes.map((c) => {
    let fare, avail;
    if (c.offered === false) {
      return `<tr class="fa-row-off"><td>${escapeHtml(c.label)}</td><td colspan="2">Not available on this train</td></tr>`;
    }
    fare = c.fare_per_person
      ? `<b>${money(c.fare_per_person)}</b> <span class="fa-verified" title="From the provider API">verified</span>`
      : `<span class="fa-missing">Not provided</span>`;
    avail = c.availability_status
      ? `<span class="fa-badge ${c.availability_status.toLowerCase()}">${escapeHtml(AVAIL_TEXT[c.availability_status] || c.availability_status)}</span>${c.availability_detail ? ` <small>${escapeHtml(c.availability_detail)}</small>` : ""}`
      : `<span class="fa-missing">Not provided</span>`;
    const verifiedClass = c.offered === true
      ? ` <span class="fa-verified" title="This train carries the class (RailRadar)">✔</span>`
      : ` <span class="fa-missing" title="Could not be verified">?</span>`;
    return `<tr><td>${escapeHtml(c.label)}${verifiedClass}</td><td>${fare}</td><td>${avail}</td></tr>`;
  }).join("");
  const link = fa.check_url
    ? `<a href="${escapeHtml(fa.check_url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation();">Check live fare &amp; availability on IRCTC ↗</a>`
    : "";
  return `
    <div class="fare-avail" onclick="event.stopPropagation();">
      <div class="fare-avail-title">🎫 Fare &amp; Availability <small>(per person, selected classes)</small></div>
      <table class="fare-avail-table">
        <thead><tr><th>Class</th><th>Fare</th><th>Seats</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      ${fa.notice ? `<div class="fare-avail-note">${escapeHtml(fa.notice)}</div>` : ""}
      <div class="fare-avail-foot">Only data returned by the provider is shown. Nothing here is estimated. ${link}</div>
    </div>`;
}

// ---------------------------------------------------------------- train advice
export function buildTrainAdviceHtml(advice) {
  if (!advice) return "";
  const picks = (advice.picks || []).map((p) => `
    <li class="train-pick">
      <div class="train-pick-head"><span class="train-pick-label">${escapeHtml(p.label)}</span> <strong>${escapeHtml(p.title)}</strong>
        <button type="button" class="btn btn-secondary btn-sm train-pick-btn" data-option-id="${escapeHtml(p.option_id)}">Select</button></div>
      <ul class="train-pick-reasons">${(p.reasons || []).map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
    </li>`).join("");
  const src = advice.source === "ai"
    ? `<span class="badge badge-primary" title="Written by AI using only the verified data above">AI summary</span>`
    : `<span class="badge badge-secondary" title="Built from the provider data with fixed rules">Rule-based</span>`;
  return `
    <div class="train-advice">
      <div class="train-advice-head"><strong>🚆 Train recommendation</strong> ${src}</div>
      <div class="train-advice-headline">${escapeHtml(advice.headline)}</div>
      <p class="train-advice-summary">${escapeHtml(advice.summary)}</p>
      ${picks ? `<ul class="train-pick-list">${picks}</ul>` : ""}
    </div>`;
}

// ---------------------------------------------------------------- quick version
export function mapUrlFor(item) {
  if (!item) return null;
  const d = item.directions;
  if (d && d.maps_url) return d.maps_url;
  if (!item.name) return null;
  const q = `${item.name} ${item.address || ""}`.trim();
  return "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(q);
}

/** One day -> ordered rows [{when, kind, name, detail, url}] (same shape as the PDF). */
export function quickRows(day) {
  const rows = [];
  const segment = (when, seg) => {
    if (!seg) return;
    const places = (seg.places || []).filter((p) => p && p.name);
    if (places.length) {
      places.forEach((p) => rows.push({
        when, kind: "visit", name: p.name,
        detail: [p.duration, p.admission].filter(Boolean).join(" | "), url: mapUrlFor(p)
      }));
    } else if (seg.title) {
      rows.push({ when, kind: "plan", name: seg.title, detail: seg.time_window || "", url: null });
    }
  };
  const meal = (when, f) => {
    if (!f || !f.name) return;
    rows.push({
      when, kind: "meal", name: f.name,
      detail: [f.cuisine, f.recommendation ? `Try: ${f.recommendation}` : ""].filter(Boolean).join(" | "), url: mapUrlFor(f)
    });
  };
  segment("Morning", day.morning);
  meal("Lunch", day.food_stop_lunch);
  segment("Afternoon", day.afternoon);
  meal("Dinner", day.food_stop_dinner);
  segment("Evening", day.evening);
  const rt = day.return_to_hotel;
  if (rt && rt.hotel_name) {
    const d = rt.directions || {};
    rows.push({
      when: "Night", kind: "hotel", name: `Back to ${rt.hotel_name}`,
      detail: [rt.leave_at ? `around ${rt.leave_at}` : "", d.distance_km != null ? `~${d.distance_km} km` : ""].filter(Boolean).join(" | "),
      url: d.maps_url || null
    });
  }
  return rows;
}

const legLine = (label, leg) => {
  if (!leg) return "";
  const op = leg.operator || leg.airline || "Selected";
  const price = leg.price ? ` · ${money(leg.price)} per person` : "";
  return `<li><b>${label}:</b> ${escapeHtml(op)}${leg.number ? " " + escapeHtml(leg.number) : ""} · ${escapeHtml(leg.departure_time || "")} → ${escapeHtml(leg.arrival_time || "")}${price}</li>`;
};

export function buildQuickVersionHtml(data) {
  const hotels = (data.selected_hotels && data.selected_hotels.length) ? data.selected_hotels : (data.selected_hotel ? [data.selected_hotel] : []);
  const stays = hotels.filter((h) => h && h.name).map((h) =>
    `<li><b>Stay${h.area ? " in " + escapeHtml(h.area) : ""}:</b> ${escapeHtml(h.name)}${h.address ? " · " + escapeHtml(h.address) : ""}</li>`).join("");
  const top = [
    legLine("Outbound", data.selected_outbound_transport),
    legLine("Return", data.selected_return_transport),
    stays
  ].join("");
  const days = (data.days || []).map((day) => {
    const rows = quickRows(day).map((r) => `
      <tr>
        <td class="qv-when">${escapeHtml(r.when)}</td>
        <td><b>${escapeHtml(r.name)}</b>${r.url ? ` <a class="qv-map" href="${escapeHtml(r.url)}" target="_blank" rel="noopener noreferrer">🗺️ Map ↗</a>` : ""}
          ${r.detail ? `<div class="qv-detail">${escapeHtml(r.detail)}</div>` : ""}</td>
      </tr>`).join("");
    return `
      <section class="qv-day">
        <h4>Day ${escapeHtml(day.day_number)}${day.area ? " · " + escapeHtml(day.area) : ""}: ${escapeHtml(day.theme || "")} ${day.estimated_day_cost ? `<small>(est. ${escapeHtml(day.estimated_day_cost)})</small>` : ""}</h4>
        <table class="qv-table"><tbody>${rows}</tbody></table>
      </section>`;
  }).join("");
  return `
    <div class="qv-card">
      <h3>${escapeHtml(data.title)} <span class="badge badge-primary">Quick version</span></h3>
      ${top ? `<ul class="qv-top">${top}</ul>` : ""}
      ${days}
      ${data.estimated_budget_total ? `<p class="qv-total"><b>Estimated total trip budget:</b> ${escapeHtml(data.estimated_budget_total)}</p>` : ""}
    </div>`;
}

// ---------------------------------------------------------------- budget
export function buildBudgetSummaryHtml(cb) {
  const d = cb && cb.detail;
  if (!d) return "";
  return `
    <div class="budget-summary">
      <div class="budget-tile main">
        <div class="budget-tile-label">Estimated trip total</div>
        <div class="budget-tile-value">${money(d.grand_total)}</div>
        <div class="budget-tile-sub">for ${d.travelers} traveller(s), ${d.days} day(s)</div>
      </div>
      <div class="budget-tile">
        <div class="budget-tile-label">Per person</div>
        <div class="budget-tile-value">${money(d.per_person_total)}</div>
        <div class="budget-tile-sub">total ÷ ${d.travelers}</div>
      </div>
      <div class="budget-tile">
        <div class="budget-tile-label">Live quotes</div>
        <div class="budget-tile-value">${money(d.live_total)}</div>
        <div class="budget-tile-sub">flights / hotel from providers</div>
      </div>
      <div class="budget-tile">
        <div class="budget-tile-label">Estimates</div>
        <div class="budget-tile-value">${money(d.estimate_total)}</div>
        <div class="budget-tile-sub">food, local travel, activities</div>
      </div>
    </div>`;
}

export function buildBudgetBreakdownHtml(cb) {
  const d = cb && cb.detail;
  if (!d) return "";
  const rows = d.lines.map((l) => `
    <tr>
      <td><b>${escapeHtml(l.label)}</b><div class="budget-note">${escapeHtml(l.note || "")}</div></td>
      <td><span class="badge ${l.kind === "live" ? "badge-primary" : "badge-secondary"}">${l.kind === "live" ? "Live quote" : "Estimate"}</span></td>
      <td class="num">${money(l.per_person)}</td>
      <td class="num"><b>${money(l.total)}</b></td>
    </tr>`).join("");
  const daily = d.daily.split.map((s) => `<tr><td>${escapeHtml(s.label)}</td><td class="num">${money(s.per_person_per_day)}</td></tr>`).join("");
  const missing = (d.missing || []).map((m) => `<li>${escapeHtml(m)}</li>`).join("");
  return `
    <div class="budget-panel">
      <table class="budget-table">
        <thead><tr><th>Item</th><th>Type</th><th class="num">Per person</th><th class="num">Group total</th></tr></thead>
        <tbody>${rows}
          <tr class="budget-total"><td colspan="2"><b>Estimated trip total</b></td><td class="num"><b>${money(d.per_person_total)}</b></td><td class="num"><b>${money(d.grand_total)}</b></td></tr>
        </tbody>
      </table>
      <h4 class="budget-h">A typical day (per person)</h4>
      <table class="budget-table small">
        <tbody>${daily}
          <tr class="budget-total"><td><b>Daily spending budget</b></td><td class="num"><b>${money(d.daily.per_person_per_day)}</b></td></tr>
        </tbody>
      </table>
      <p class="budget-foot">Flight and train prices are per person and are multiplied by ${d.travelers} traveller(s).
        The hotel is priced per room for ${d.nights} night(s) with ${d.rooms} room(s) assumed (one per two travellers).
        Estimates split the daily budget you chose and add a ${10}% cushion. Live quotes can change before you book.</p>
      ${missing ? `<ul class="budget-missing">${missing}</ul>` : ""}
    </div>`;
}

// ---------------------------------------------------------------- "did you mean"
export function buildDidYouMeanHtml(groups) {
  const blocks = (groups || []).filter((g) => g.items && g.items.length).map((g) => `
    <div class="dym-group">
      <div class="dym-title">Did you mean one of these instead of <b>${escapeHtml(g.typed)}</b>?</div>
      <div class="dym-chips">
        ${g.items.map((it) => `<button type="button" class="dym-chip" data-field="${escapeHtml(g.field)}" data-value="${escapeHtml(it.label)}">${escapeHtml(it.label)} <small>${escapeHtml(it.kind_label)}</small></button>`).join("")}
      </div>
    </div>`).join("");
  return blocks ? `<div class="dym">${blocks}</div>` : "";
}

// ---------------------------------------------------------------- Phase 2: plan scope (city / state / country)
const chipList = (items, checkedSet, cls, fit = 0, days = 0) => (items || []).map((it, i) => `
  <label class="scope-chip" title="${escapeHtml(it.note || "")}">
    <input type="checkbox" class="${cls}" value="${escapeHtml(it.name)}"${checkedSet.has(it.name) ? " checked" : ""}>
    <span><b>${escapeHtml(it.name)}</b>${it.note ? `<small>${escapeHtml(it.note)}</small>` : ""}${(fit > 0 && i < fit && items.length > fit) ? `<small class="scope-fit">★ fits your ${days} days</small>` : ""}</span>
  </label>`).join("");

/** The "Plan your area" questions. state = { mode, selected: [], neighbourSelected: [], arrival } */
export function buildScopePanelHtml(scope, state, extra = {}) {
  if (!scope) return "";
  const days = extra.days || 0;
  const fit = scope.kind === "city" || scope.kind === "area" ? Math.max(0, (scope.recommended_areas || 1) - 1) : (scope.recommended_areas || 1);
  const refresh = extra.refreshDays
    ? `<div class="scope-block"><button type="button" class="btn btn-secondary btn-sm" id="scopeRefresh">↻ Refresh suggestions for ${extra.refreshDays} days</button>
         <span class="scope-hint">Your trip length changed a lot since these were suggested.</span></div>` : "";
  const selected = new Set(state.selected || []);
  const nSelected = new Set(state.neighbourSelected || []);
  const isBig = scope.kind === "state" || scope.kind === "country";
  const modes = (scope.modes || []).map((m) => `
    <label class="scope-mode"><input type="radio" name="scopeMode" value="${escapeHtml(m.value)}"${state.mode === m.value ? " checked" : ""}> ${escapeHtml(m.label)}</label>`).join("");
  const showSuggestions = scope.kind === "country" || scope.kind === "state" || state.mode === "nearby";
  const showNeighbours = scope.kind === "state" && state.mode === "neighbours";
  const current = (state.arrival || "").trim().toLowerCase();
  const arrivalChips = (scope.arrival_options || []).map((o, i) => `
    <button type="button" class="scope-arrival-chip${o.name.toLowerCase() === current ? " active" : ""}" data-city="${escapeHtml(o.name)}">
      ${i === 0 && scope.default_arrival ? "★ " : ""}${escapeHtml(o.name)}${o.note ? `<small>${escapeHtml(o.note)}</small>` : ""}</button>`).join("");
  const arrival = isBig ? `
    <div class="scope-block">
      <label class="form-label" for="scopeArrival">Where will you land / start? <span class="scope-req">required</span></label>
      ${arrivalChips ? `<div class="scope-arrival-chips" role="group" aria-label="Suggested cities to start from">${arrivalChips}</div>` : ""}
      <input type="text" id="scopeArrival" class="form-input" value="${escapeHtml(state.arrival || "")}" placeholder="Or type another city with an airport or station">
      <div class="scope-hint">${scope.default_arrival ? `We suggest ${escapeHtml(scope.default_arrival)}${scope.default_arrival_note ? ` (${escapeHtml(scope.default_arrival_note)})` : ""}. Pick another start if you prefer. ` : ""}Flights and trains are searched to this city, and your trip starts here.</div>
    </div>` : "";
  const sugg = showSuggestions && (scope.suggestions || []).length ? `
    <div class="scope-block">
      <div class="form-label">${escapeHtml(scope.suggestions_title)}</div>
      <div class="scope-chips">${chipList(scope.suggestions, selected, "scope-check", fit, days)}</div>
      ${scope.source === "static" ? `<div class="scope-hint">Popular places from our built-in list. You can also type any city as your start above.</div>` : ""}
    </div>` : "";
  const neigh = showNeighbours && (scope.neighbours || []).length ? `
    <div class="scope-block">
      <div class="form-label">${escapeHtml(scope.neighbours_title)}</div>
      <div class="scope-chips">${chipList(scope.neighbours, nSelected, "scope-ncheck")}</div>
    </div>` : "";
  return `
    <div class="scope-card">
      <div class="scope-title">🧭 Plan your area: ${escapeHtml(scope.name)} <span class="badge badge-secondary">${escapeHtml(scope.kind)}</span></div>
      <p class="scope-advice">${escapeHtml(scope.advice)}</p>
      ${modes ? `<div class="scope-modes">${modes}</div>` : ""}
      ${arrival}${sugg}${neigh}
      ${refresh}
      <div class="scope-count" id="scopeCount"></div>
    </div>`;
}

export function scopeCountText(scope, areaCount) {
  if (!scope) return "";
  const rec = scope.recommended_areas || 1;
  if (areaCount <= 1) return `Staying in one place. Recommended for this trip length: up to ${rec}.`;
  if (areaCount <= rec) return `${areaCount} places to stay: a good fit for this trip length.`;
  return `${areaCount} places selected. That is more than the ${rec} recommended, so expect more travelling.`;
}

// ---------------------------------------------------------------- Phase 2: stays (hotel per group of days)
export function buildStayBlockHtml(block, choice, inboundLine = "") {
  const nights = `${block.nights} night${block.nights === 1 ? "" : "s"}`;
  const dates = block.check_in ? `${escapeHtml(block.check_in)} → ${escapeHtml(block.check_out)}` : `Day ${block.start_day}–${block.end_day}`;
  const places = (block.places || []).length ? `<div class="stay-places">📍 Around: ${(block.places).map(escapeHtml).join(", ")}</div>` : "";
  const picked = choice
    ? `<div class="stay-picked">✓ ${escapeHtml(choice.name)}${choice.nightly_price ? ` · ₹${Math.round(choice.nightly_price).toLocaleString("en-IN")} / night` : ""}</div>`
    : (choice === null ? `<div class="stay-picked skipped">No hotel for this stay</div>` : "");
  return `
    <section class="stay-block" data-index="${block.index}">
      <div class="stay-head">
        <div>
          <h3>Stay ${block.index + 1}: ${escapeHtml(block.area)}</h3>
          <div class="stay-meta">${nights} · ${dates} · Days ${block.start_day}–${block.end_day}</div>
          ${places}
          ${inboundLine ? `<div class="stay-inbound">${inboundLine} <button type="button" class="btn-link stay-change-travel">Change travel</button></div>` : ""}
          ${picked}
        </div>
        <div class="stay-actions">
          <select class="form-select stay-sort" aria-label="Sort hotels">
            <option value="best_match">Best match (distance, price, rating)</option>
            <option value="relevance">Recommended</option>
            <option value="lowest_price">Lowest price</option>
            <option value="highest_rating">Highest rating</option>
            <option value="most_reviewed">Most reviewed</option>
          </select>
          <button type="button" class="btn btn-primary btn-sm stay-find">Find hotels near here</button>
          <button type="button" class="btn btn-secondary btn-sm stay-skip">No hotel needed</button>
        </div>
      </div>
      <div class="stay-hotels cards-grid"></div>
    </section>`;
}

export function buildTransfersHtml(transfers, choices = {}) {
  if (!transfers || !transfers.length) return "";
  const rows = transfers.map((t) => {
    // the traveller's pick: either saved on the transfer (finished itinerary) or still in the planner (hotel step)
    const picked = t.choice ? { mode: t.choice.mode, option: t.choice } : choices[t.to_stay];
    const head = `<b>${escapeHtml(t.from_area)} → ${escapeHtml(t.to_area)}</b>`;
    if (picked && (picked.mode === "flight" || picked.mode === "train")) {
      // flight / train details only: times, duration, distance. No cab or road price estimate here.
      return `<li>${head}${buildFlightDetailHtml(picked, t)}</li>`;
    }
    if (picked && picked.mode === "other") return `<li>${head}<br>🚌 Bus, ferry or other (you arrange it) · about ${t.distance_km} km</li>`;
    return `<li>${head}: about ${t.distance_km} km, ~${t.hours} h by road${picked ? " (cab)" : ""}
      <span class="stay-est">(estimate, around ${money(t.cost_per_person)} per person)</span>
      <div class="stay-est">${escapeHtml(t.note)}</div></li>`;
  }).join("");
  return `<div class="stay-transfers"><b>Travel between your stays</b><ul>${rows}</ul></div>`;
}

/** Stays summary shown on the finished itinerary. */
export function buildStaysSummaryHtml(data) {
  const blocks = (data.stay_blocks || []).filter((b) => b.needs_hotel);
  if (!blocks.length) return "";
  let rowsPrevHotel = null;
  const rows = blocks.map((b) => {
    const h = b.hotel;
    const price = h && h.nightly_price ? ` · ₹${Math.round(h.nightly_price).toLocaleString("en-IN")} / night` : "";
    const link = h && h.booking_url ? ` <a href="${escapeHtml(h.booking_url)}" target="_blank" rel="noopener noreferrer">Book ↗</a>` : "";
    const prev = rowsPrevHotel;
    const hop = h && prev ? hotelHop(prev, h) : null;
    const hopLine = h && prev && !(hop && hop.km < 3)
      ? `<div class="hotel-hop">🔁 Changing hotel from ${escapeHtml(prev.name)}: ${hop ? `about ${hop.km} km, roughly ${hop.minutes} min by cab (estimate)` : "distance not available"}</div>`
      : "";
    if (h) rowsPrevHotel = h;
    return `<li><b>${escapeHtml(b.area)}</b> · ${b.nights} night(s)${b.check_in ? ` · ${escapeHtml(b.check_in)} → ${escapeHtml(b.check_out)}` : ""}<br>
      ${h ? `🏨 ${escapeHtml(h.name)}${price}${link}` : `<span class="stay-est">No hotel chosen for this stay</span>`}${hopLine}</li>`;
  }).join("");
  return `<div class="stays-summary"><h3>Where you will stay</h3><ul>${rows}</ul>${buildTransfersHtml(data.transfers)}</div>`;
}


// ---------------------------------------------------------------- hotel step: finished and upcoming stays
const stayTitle = (block) => {
  const nights = `${block.nights} night${block.nights === 1 ? "" : "s"}`;
  const dates = block.check_in ? `${escapeHtml(block.check_in)} → ${escapeHtml(block.check_out)}` : `Days ${block.start_day}–${block.end_day}`;
  return { head: `Stay ${block.index + 1}: ${escapeHtml(block.area)}`, meta: `${nights} · ${dates}` };
};

/** A finished stay shrinks to one card showing only the hotel that was chosen. */
export function buildStayDoneHtml(block, choice, inboundLine = "") {
  const t = stayTitle(block);
  const body = choice
    ? `<div class="stay-done-hotel"><b>🏨 ${escapeHtml(choice.name)}</b>
         <span>${choice.rating ? `★ ${escapeHtml(choice.rating)}` : "Unrated"}${choice.nightly_price ? ` · ₹${Math.round(choice.nightly_price).toLocaleString("en-IN")} / night` : ""}</span>
         ${choice.address ? `<span class="stay-est">${escapeHtml(choice.address)}</span>` : ""}</div>`
    : `<div class="stay-done-hotel"><span class="stay-est">No hotel for this stay</span></div>`;
  return `
    <section class="stay-block stay-done" data-index="${block.index}">
      <div class="stay-done-main">
        <div><div class="stay-done-title">✓ ${t.head}</div><div class="stay-meta">${t.meta}</div>${inboundLine ? `<div class="stay-inbound">${inboundLine}</div>` : ""}</div>
        ${body}
      </div>
      <button type="button" class="btn btn-secondary btn-sm stay-change">${choice ? "Change" : "Choose a hotel"}</button>
    </section>`;
}

/** A stay that comes later: visible, but not open yet. */
export function buildStayUpcomingHtml(block) {
  const t = stayTitle(block);
  return `
    <section class="stay-block stay-upcoming" data-index="${block.index}">
      <div class="stay-done-main">
        <div><div class="stay-done-title">${t.head}</div><div class="stay-meta">${t.meta} · choose after the stay above</div></div>
      </div>
      <button type="button" class="btn btn-secondary btn-sm stay-change">Choose now</button>
    </section>`;
}

// ---------------------------------------------------------------- Batch B: day cards, hotel hops, trip at a glance
export const DAY_COLORS = ["#0F766E", "#EA580C", "#2563EB", "#9333EA", "#DB2777", "#CA8A04", "#16A34A"];
export const dayColor = (n) => DAY_COLORS[(Math.max(1, Number(n) || 1) - 1) % DAY_COLORS.length];

/** Straight-line distance x 1.3 as road distance, about 28 km/h plus 8 minutes: same rule as the server. */
export function hotelHop(a, b) {
  if (!a || !b || a.latitude == null || a.longitude == null || b.latitude == null || b.longitude == null) return null;
  const rad = (d) => (d * Math.PI) / 180;
  const dLat = rad(b.latitude - a.latitude);
  const dLon = rad(b.longitude - a.longitude);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.latitude)) * Math.cos(rad(b.latitude)) * Math.sin(dLon / 2) ** 2;
  const km = 2 * 6371 * Math.asin(Math.sqrt(h)) * 1.3;
  return { km: Math.round(km * 10) / 10, minutes: Math.max(10, Math.round((km / 28) * 60 + 8)) };
}

/** Clear "you are changing hotel" strip between two chosen hotels. */
export function buildHotelConnectorHtml(from, to) {
  const hop = hotelHop(from, to);
  const dist = hop ? `about <b>${hop.km} km</b> apart · roughly ${hop.minutes} min by cab <span class="stay-est">(estimate)</span>` : `<span class="stay-est">distance not available</span>`;
  return `<div class="hotel-connector" role="note"><span aria-hidden="true">🔁</span>
    <div><b>Changing hotel:</b> ${escapeHtml(from.name)} → ${escapeHtml(to.name)}<br>${dist}</div></div>`;
}

const NOTE_ICONS = { arrival: "🛬", hotel_change: "🔁", departure: "🧳" };

/** End of the day: "after your last stop, go back to the hotel" with a map link and an approximate time. */
export function buildReturnToHotelHtml(rt) {
  if (!rt || !rt.hotel_name) return "";
  const d = rt.directions || {};
  const chips = [
    rt.leave_at ? `<span class="badge badge-primary">🕘 Head back around ${escapeHtml(rt.leave_at)}</span>` : "",
    d.distance_km != null ? `<span class="badge badge-secondary">📏 ~${escapeHtml(d.distance_km)} km</span>` : "",
    d.walk_minutes != null ? `<span class="badge badge-secondary">🚶 ~${escapeHtml(d.walk_minutes)} min walk</span>` : "",
    d.drive_minutes != null ? `<span class="badge badge-secondary">🚗 ~${escapeHtml(d.drive_minutes)} min by car/auto</span>` : "",
    rt.arrive_at ? `<span class="badge badge-secondary">🏨 At the hotel around ${escapeHtml(rt.arrive_at)}</span>` : "",
  ].filter(Boolean).join(" ");
  const link = d.maps_url
    ? `<a href="${escapeHtml(d.maps_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm stop-directions-link">🗺️ Open map: ${escapeHtml(rt.from_name || "last stop")} → ${escapeHtml(rt.hotel_name)} ↗</a>`
    : "";
  return `
    <section class="day-return" aria-label="Back to the hotel">
      <div class="day-return-title">🏨 Back to your hotel</div>
      <p class="segment-description">${escapeHtml(rt.text || "")}</p>
      ${rt.hotel_address ? `<div class="stop-address">📮 ${escapeHtml(rt.hotel_address)}</div>` : ""}
      <div class="stop-directions-chips">${chips}</div>
      ${link}
      <div class="stop-directions-note">Distance and time are estimates; open the map for exact directions.</div>
    </section>`;
}

/** Flight details after a flight was chosen between two places (times and distance, no cab prices). */
export function buildFlightDetailHtml(choice, transfer) {
  if (!choice) return "";
  const o = choice.option || choice;
  const when = clock(o.departure_time) ? `${clock(o.departure_time)} → ${clock(o.arrival_time)}` : "";
  const dur = o.duration_formatted ? ` · ${escapeHtml(o.duration_formatted)} in the air` : "";
  const km = transfer && (transfer.air_km || transfer.distance_km)
    ? ` · about ${escapeHtml(transfer.air_km || transfer.distance_km)} km${transfer.air_km ? " by air" : ""}` : "";
  const route = o.origin || o.destination ? `${escapeHtml(o.origin || "")} → ${escapeHtml(o.destination || "")}` : "";
  return `<div class="flight-detail">${buildTransferSummaryLine(choice)}${route ? `<br><small>${route}</small>` : ""}${when || dur || km ? `<br><small>${escapeHtml(when)}${dur}${km}</small>` : ""}</div>`;
}

/** Arrival / hotel change / departure cards for one day. `types` picks which kinds to show. */
export function buildDayNotesHtml(notes, types) {
  return (notes || []).filter((n) => !types || types.includes(n.type)).map((n) => `
    <div class="day-note day-note-${escapeHtml(n.type)}">
      <div class="day-note-title"><span aria-hidden="true">${escapeHtml(n.icon || NOTE_ICONS[n.type] || "ℹ️")}</span> ${escapeHtml(n.title)}</div>
      <ul>${(n.lines || []).map((l) => `<li>${escapeHtml(l)}</li>`).join("")}</ul>
    </div>`).join("");
}

/** Up to `max` place names a day is about, for the highlight chips. */
export function dayHighlights(day, max = 4) {
  const names = [];
  for (const seg of [day.morning, day.afternoon, day.evening]) {
    for (const p of (seg && seg.places) || []) if (p && p.name && !names.includes(p.name)) names.push(p.name);
  }
  return names.slice(0, max);
}

/** The picture at the very top: route, stays, key numbers and the theme of every day. */
export function buildTripGlanceHtml(data) {
  const ob = data.selected_outbound_transport;
  const ib = data.selected_return_transport;
  const icon = (leg) => (!leg ? "➡️" : String(leg.mode).toLowerCase() === "train" ? "🚆" : "✈️");
  const blocks = (data.stay_blocks || []).filter((b) => b.needs_hotel);
  const hops = new Map((data.transfers || []).map((t) => [t.to_stay, t]));
  const stays = blocks.length
    ? blocks.map((b, i) => {
        const hop = hops.get(b.index);
        const modeIcon = hop && hop.choice ? ({ flight: "✈️", train: "🚆", other: "🚌", cab: "🚕" }[hop.choice.mode] || "🚕") : "🚕";
        const link = i > 0 ? `<div class="glance-link small">${modeIcon}<small>${hop ? "~" + hop.distance_km + " km" : ""}</small></div>` : "";
        const hotel = b.hotel ? `<small class="glance-hotel">🏨 ${escapeHtml(b.hotel.name)}</small>` : "";
        return `${link}<div class="glance-node stay"><span class="glance-pin">📍</span><b>${escapeHtml(b.area)}</b>
          <small>${b.nights} night${b.nights === 1 ? "" : "s"}</small>${hotel}</div>`;
      }).join("")
    : `<div class="glance-node stay"><span class="glance-pin">📍</span><b>${escapeHtml(data.destination || "Your trip")}</b></div>`;
  const places = (data.days || []).reduce((n, d) => n + dayHighlights(d, 99).length, 0);
  const nights = Math.max(0, (data.duration_days || 1) - 1);
  const hotels = (data.selected_hotels || []).length;
  const pills = [
    `🗓️ ${data.duration_days} day${data.duration_days === 1 ? "" : "s"}`,
    `🌙 ${nights} night${nights === 1 ? "" : "s"}`,
    places ? `📍 ${places} places` : "",
    hotels ? `🏨 ${hotels} hotel${hotels === 1 ? "" : "s"}` : "",
    data.estimated_budget_total ? `💰 ${escapeHtml(data.estimated_budget_total)}` : ""
  ].filter(Boolean).map((p) => `<span class="glance-pill">${p}</span>`).join("");
  const dayChips = (data.days || []).map((d) =>
    `<span class="glance-day" style="--day-color:${dayColor(d.day_number)}"><b>Day ${escapeHtml(d.day_number)}</b> ${escapeHtml(d.theme)}</span>`).join("");
  return `
    <div class="trip-glance">
      <div class="glance-title">Your trip at a glance</div>
      <div class="glance-route">
        <div class="glance-node"><span class="glance-pin">🏠</span><b>${escapeHtml(data.source || "Home")}</b><small>Start</small></div>
        <div class="glance-link">${icon(ob)}</div>
        ${stays}
        <div class="glance-link">${icon(ib)}</div>
        <div class="glance-node"><span class="glance-pin">🏠</span><b>${escapeHtml(data.source || "Home")}</b><small>Back home</small></div>
      </div>
      <div class="glance-pills">${pills}</div>
      <div class="glance-days">${dayChips}</div>
    </div>`;
}

// ---------------------------------------------------------------- other places to book a flight
/**
 * Links to well-known flight sites with the route and date already filled in, so a traveller can
 * always continue booking even when the provider's own booking link fails. Returns [] when the route
 * or date is not known (nothing is guessed).
 */
export function buildFlightSiteLinks(searchParams) {
  const p = searchParams || {};
  const dep = String(p.departure_id || "").trim().toUpperCase();
  const arr = String(p.arrival_id || "").trim().toUpperCase();
  const date = String(p.outbound_date || "").trim();
  const adults = Math.max(1, parseInt(p.adults, 10) || 1);
  if (!/^[A-Z]{3}$/.test(dep) || !/^[A-Z]{3}$/.test(arr) || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return [];
  const yymmdd = date.slice(2, 4) + date.slice(5, 7) + date.slice(8, 10);
  return [
    { name: "Google Flights", url: `https://www.google.com/travel/flights?q=${encodeURIComponent(`Flights to ${arr} from ${dep} on ${date} one way`)}&curr=INR` },
    { name: "Skyscanner", url: `https://www.skyscanner.co.in/transport/flights/${dep.toLowerCase()}/${arr.toLowerCase()}/${yymmdd}/?adultsv2=${adults}&cabinclass=economy&currency=INR` },
    { name: "Kayak", url: `https://www.kayak.co.in/flights/${dep}-${arr}/${date}/${adults}adults` }
  ];
}

export function buildFlightSiteLinksHtml(searchParams, title = "Or book on a flight website") {
  const links = buildFlightSiteLinks(searchParams);
  if (!links.length) return "";
  const p = searchParams;
  return `
    <div class="flight-sites">
      <div class="flight-sites-title">${escapeHtml(title)}</div>
      <div class="flight-sites-row">
        ${links.map((l) => `<a class="btn btn-secondary btn-sm" href="${escapeHtml(l.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(l.name)} ↗</a>`).join("")}
      </div>
      <div class="flight-sites-note">${escapeHtml(p.departure_id)} → ${escapeHtml(p.arrival_id)} on ${escapeHtml(p.outbound_date)} is filled in for you.
        Prices there can differ from the one shown here, and you pick the flight again on the site.</div>
    </div>`;
}


// ---------------------------------------------------------------- Batch C: scope follows the number of days
/** How many places to stay in suits a trip this long (same rule as the server). */
export function recommendedAreas(kind, days) {
  const d = Math.max(1, Math.floor(Number(days) || 1));
  if (kind === "country") return Math.max(1, Math.min(5, Math.floor(d / 3)));
  if (kind === "state") return Math.max(1, Math.min(5, Math.floor(d / 2)));
  return Math.max(1, Math.min(3, Math.floor(d / 3)));
}

export function scopeAdviceText(kind, name, days, nSelected = 0) {
  const rec = recommendedAreas(kind, days);
  let text;
  if (kind === "country" || kind === "state") {
    const big = kind === "country" ? "a whole country" : "a whole state";
    text = `${name} is ${big}. With ${days} day(s), about ${rec} place(s) to stay in works best, so less time is spent travelling between them.`;
  } else {
    text = `With ${days} day(s) in ${name}, you can stay in the city only${rec > 1 ? ` or add up to ${rec - 1} nearby place(s)` : ""}.`;
  }
  if (nSelected > rec) text += ` You picked ${nSelected}; that is possible but will mean more travelling.`;
  return text;
}

/** One-line "about" text shown under a place. */
export function placeAboutHtml(p) {
  const about = p && p.about ? `<p class="stop-about">${escapeHtml(p.about)}</p>` : "";
  const todo = p && p.what_to_do ? `<p class="stop-todo"><b>What to do:</b> ${escapeHtml(p.what_to_do)}</p>` : "";
  return about + todo;
}

// ---------------------------------------------------------------- Batch D: travel between stays
export const TRANSFER_TABS = [
  { id: "flight", label: "✈️ Flights" },
  { id: "train", label: "🚆 Trains" },
  { id: "other", label: "🚌 Bus & other" },
  { id: "cab", label: "🚕 Cab" }
];

const rupees = (v) => `₹${Math.round(v).toLocaleString("en-IN")}`;
const shortPlace = (t) => { const s = String(t || ""); return s.includes("(") && s.endsWith(")") ? s.slice(s.indexOf("(") + 1, -1) : s; };
const clock = (t) => { const m = String(t || "").match(/(\d{1,2}:\d{2})/); return m ? m[1] : ""; };

/** Links to search buses, ferries and other ways. We do not have prices for these, so they are plainly external links. */
export function otherTravelLinks(from, to) {
  const f = encodeURIComponent(from);
  const t = encodeURIComponent(to);
  return [
    { name: "Rome2Rio (trains, buses, ferries, flights)", url: `https://www.rome2rio.com/s/${f}/${t}` },
    { name: "Google Maps public transport", url: `https://www.google.com/maps/dir/?api=1&origin=${f}&destination=${t}&travelmode=transit` }
  ];
}

/** The chooser shown for a long move between two stays: tabs on top, the panel below. */
export function buildTransferChooserHtml(block, transfer, tab) {
  const date = transfer.date ? ` on ${escapeHtml(transfer.date)}` : "";
  const tabs = TRANSFER_TABS.map((t) => `<button type="button" class="transfer-tab${t.id === tab ? " active" : ""}" data-tab="${t.id}" role="tab" aria-selected="${t.id === tab}">${t.label}</button>`).join("");
  return `
    <section class="stay-block transfer-chooser" data-index="${block.index}">
      <div class="transfer-head">
        <h3>How will you get from ${escapeHtml(transfer.from_area)} to ${escapeHtml(transfer.to_area)}?</h3>
        <div class="stay-meta">About ${transfer.distance_km} km${date}. Pick one, then you will choose your hotel in ${escapeHtml(transfer.to_area)}.</div>
      </div>
      <div class="transfer-tabs" role="tablist">${tabs}</div>
      <div class="transfer-panel" data-panel></div>
    </section>`;
}

function optionCard(o, kind) {
  const isFlight = kind === "flight";
  const price = o.price
    ? `<div class="transfer-price">${rupees(o.price)}<small> per person · live quote</small></div>`
    : `<div class="transfer-price muted">${isFlight ? "Price not available" : "Fare not provided"}<small> per person</small></div>`;
  const stops = o.stops === 0 ? "Direct" : (o.stops ? `${o.stops} stop${o.stops === 1 ? "" : "s"}` : "");
  return `
    <article class="transfer-option" data-id="${escapeHtml(o.id)}">
      <div class="transfer-option-main">
        <div><b>${escapeHtml(String(o.operator || "").replace("Indian Railways (", "").replace(/\)$/, ""))}</b> <span class="stay-est">${escapeHtml(o.number || "")}</span></div>
        <div class="transfer-times">${escapeHtml(clock(o.departure_time))} → ${escapeHtml(clock(o.arrival_time))} <span class="stay-est">· ${escapeHtml(o.duration_formatted || "")}${stops ? " · " + stops : ""}</span></div>
        <div class="stay-est">${escapeHtml(shortPlace(o.origin))} → ${escapeHtml(shortPlace(o.destination))}</div>
      </div>
      <div class="transfer-option-side">
        ${price}
        <div class="transfer-option-actions">
          <button type="button" class="btn btn-primary btn-sm transfer-select" data-id="${escapeHtml(o.id)}" data-kind="${kind}">Select</button>
          ${isFlight ? `<button type="button" class="btn btn-secondary btn-sm transfer-book" data-id="${escapeHtml(o.id)}">Book ↗</button>`
            : `<a class="btn btn-secondary btn-sm" href="https://www.irctc.co.in/nget/train-search" target="_blank" rel="noopener noreferrer">IRCTC ↗</a>`}
        </div>
      </div>
    </article>`;
}

/** Content of one tab. data = the leg search result (or null while loading); state = {loading, error}. */
export function buildTransferPanelHtml(tab, data, transfer, state = {}) {
  if (tab === "cab") {
    return `<div class="transfer-cab">
      <p><b>Cab or taxi</b>: about ${transfer.distance_km} km, roughly ${transfer.hours} hours on the road.</p>
      <p>Estimated cost about ${rupees(transfer.cost_per_person)} per person <span class="stay-est">(a rough per-km estimate, check real prices)</span>.</p>
      <p class="stay-est">${escapeHtml(transfer.note || "")}</p>
      <button type="button" class="btn btn-primary transfer-select" data-kind="cab">Use a cab for this journey</button></div>`;
  }
  if (tab === "other") {
    const links = otherTravelLinks(transfer.from_area, transfer.to_area).map((l) =>
      `<a class="btn btn-secondary btn-sm" href="${escapeHtml(l.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(l.name)} ↗</a>`).join(" ");
    return `<div class="transfer-other">
      <p>Buses, ferries and other options are not priced here. These sites open with both places filled in:</p>
      <div class="flight-sites-row">${links}</div>
      <p class="stay-est">We have not checked timetables or prices on these sites. When you know how you will travel, come back and press the button below.</p>
      <button type="button" class="btn btn-primary transfer-select" data-kind="other">I will arrange this myself (bus, ferry or other)</button></div>`;
  }
  if (state.loading) return `<div class="empty-state"><p>Searching ${tab === "flight" ? "flights" : "trains"} for ${escapeHtml(transfer.from_area)} → ${escapeHtml(transfer.to_area)}…</p></div>`;
  if (state.error) return `<div class="empty-state"><p>Could not load options right now.</p><p class="stay-est">You can still use a cab, or the Bus & other tab.</p></div>`;
  if (!transfer.date) return `<div class="empty-state"><p>Add travel dates to see ${tab === "flight" ? "flights" : "trains"} for this journey.</p></div>`;
  const list = (data && (tab === "flight" ? data.flights : data.trains)) || [];
  if (!list.length) {
    const why = tab === "flight" ? (data && data.airport_notice) : (data && data.rail_notice);
    return `<div class="empty-state"><p>No ${tab === "flight" ? "flights" : "trains"} found for this date.</p>${why ? `<p class="stay-est">${escapeHtml(why)}</p>` : ""}
      <p class="stay-est">Try the Bus & other tab, or a cab.</p></div>`;
  }
  const note = tab === "train" ? `<div class="stay-est transfer-note">Train fares are not provided by our data source. Use the IRCTC link to see fares and seats.</div>` : "";
  return note + list.map((o) => optionCard(o, tab)).join("");
}

/** One line describing a chosen journey (used on finished stays and the final page). */
export function buildTransferSummaryLine(choice) {
  if (!choice) return "";
  if (choice.mode === "cab") return "🚕 By cab";
  if (choice.mode === "other") return "🚌 Bus, ferry or other (you arrange it)";
  const o = choice.option || choice;
  const icon = choice.mode === "train" ? "🚆" : "✈️";
  const name = String(o.operator || "").replace("Indian Railways (", "").replace(/\)$/, "");
  const when = clock(o.departure_time) ? ` · ${clock(o.departure_time)} → ${clock(o.arrival_time)}` : "";
  const price = o.price ? ` · ${rupees(o.price)} per person` : (choice.mode === "train" ? " · fare not provided" : "");
  return `${icon} ${escapeHtml(name)} ${escapeHtml(o.number || "")}${when}${price}`.trim();
}

// ---------------------------------------------------------------- Batch D: hotels ranked by what matters
export function haversineKm(a, b) {
  const rad = (d) => (d * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}

const hasXY = (h) => h && h.latitude != null && h.longitude != null;

/**
 * Ranks hotels for one stay. The best match is close to where you will spend your days, fairly priced, well
 * rated, and (when you arrive by plane or train) not far from where you arrive.
 *   centroid: {lat, lon} of the stay's places     anchor: {lat, lon, label} of the airport or station, or null
 * Returns [{hotel, score (0-100), spotsKm, anchorKm, why: [..]}] best first. Missing data is skipped, never guessed.
 */
export function scoreHotels(hotels, { centroid = null, anchor = null } = {}) {
  const rows = (hotels || []).map((h) => ({
    hotel: h,
    spotsKm: centroid && hasXY(h) ? haversineKm(centroid, { lat: h.latitude, lon: h.longitude }) : null,
    anchorKm: anchor && hasXY(h) ? haversineKm(anchor, { lat: h.latitude, lon: h.longitude }) : null,
    price: h.nightly_price > 0 ? h.nightly_price : null
  }));
  const lowerIsBetter = (key) => {
    const vals = rows.map((r) => r[key]).filter((v) => v != null);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    return (v) => (v == null ? null : (hi <= lo ? 1 : 1 - (v - lo) / (hi - lo)));
  };
  const nSpots = lowerIsBetter("spotsKm"), nPrice = lowerIsBetter("price"), nAnchor = lowerIsBetter("anchorKm");
  const weights = { spots: 0.40, price: 0.25, rating: 0.25, anchor: anchor ? 0.10 : 0 };
  // A measure only counts when at least one hotel has it. A hotel that is missing it is NOT rewarded for that:
  // it gets a below-average mark, so missing information never lifts a hotel above the rest.
  const anyOf = (get) => rows.some((r) => get(r) != null);
  const active = {
    spots: anyOf((r) => r.spotsKm), price: anyOf((r) => r.price),
    rating: anyOf((r) => r.hotel.rating || null), anchor: anyOf((r) => r.anchorKm)
  };
  const MISSING = 0.3;
  const scored = rows.map((r) => {
    const parts = [
      [active.spots ? weights.spots : 0, nSpots(r.spotsKm) ?? MISSING],
      [active.price ? weights.price : 0, nPrice(r.price) ?? MISSING],
      [active.rating ? weights.rating : 0, (r.hotel.rating ? Math.min(1, r.hotel.rating / 5) : null) ?? MISSING],
      [active.anchor ? weights.anchor : 0, nAnchor(r.anchorKm) ?? MISSING]
    ].filter(([w]) => w > 0);
    const total = parts.reduce((s, [w]) => s + w, 0);
    const score = total ? Math.round((parts.reduce((s, [w, v]) => s + w * v, 0) / total) * 100) : 0;
    const why = [];
    if (r.spotsKm != null) why.push(`📍 ${r.spotsKm < 1 ? "under 1" : r.spotsKm.toFixed(1)} km from where you will spend your days`);
    if (r.anchorKm != null && anchor) why.push(`${anchor.label && /station/i.test(anchor.label) ? "🚉" : "🛬"} ${r.anchorKm.toFixed(1)} km from ${anchor.label || "where you arrive"}`);
    return { hotel: r.hotel, score, spotsKm: r.spotsKm, anchorKm: r.anchorKm, why };
  });
  // short badges for the strongest points
  const prices = rows.map((r) => r.price).filter((v) => v != null).sort((a, b) => a - b);
  scored.forEach((s) => {
    const p = s.hotel.nightly_price;
    if (p > 0 && prices.length > 2 && p <= prices[Math.floor(prices.length / 3)]) s.why.push("💰 Among the cheaper options");
    if (s.hotel.rating >= 4.5) s.why.push("⭐ Highly rated");
  });
  return scored.sort((a, b) => b.score - a.score);
}

export function buildMatchChipsHtml(info) {
  if (!info) return "";
  return `<div class="hotel-why"><span class="hotel-match">${info.score}% match</span>${info.why.map((w) => `<span>${escapeHtml(w)}</span>`).join("")}</div>`;
}
