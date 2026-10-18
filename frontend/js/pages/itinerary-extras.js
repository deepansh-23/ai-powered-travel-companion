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
const chipList = (items, checkedSet, cls) => (items || []).map((it) => `
  <label class="scope-chip" title="${escapeHtml(it.note || "")}">
    <input type="checkbox" class="${cls}" value="${escapeHtml(it.name)}"${checkedSet.has(it.name) ? " checked" : ""}>
    <span><b>${escapeHtml(it.name)}</b>${it.note ? `<small>${escapeHtml(it.note)}</small>` : ""}</span>
  </label>`).join("");

/** The "Plan your area" questions. state = { mode, selected: [], neighbourSelected: [], arrival } */
export function buildScopePanelHtml(scope, state) {
  if (!scope) return "";
  const selected = new Set(state.selected || []);
  const nSelected = new Set(state.neighbourSelected || []);
  const isBig = scope.kind === "state" || scope.kind === "country";
  const modes = (scope.modes || []).map((m) => `
    <label class="scope-mode"><input type="radio" name="scopeMode" value="${escapeHtml(m.value)}"${state.mode === m.value ? " checked" : ""}> ${escapeHtml(m.label)}</label>`).join("");
  const showSuggestions = scope.kind === "country" || scope.kind === "state" || state.mode === "nearby";
  const showNeighbours = scope.kind === "state" && state.mode === "neighbours";
  const arrival = isBig ? `
    <div class="scope-block">
      <label class="form-label" for="scopeArrival">Where will you land / start? <span class="scope-req">required</span></label>
      <input type="text" id="scopeArrival" class="form-input" value="${escapeHtml(state.arrival || "")}" placeholder="A city with an airport or station, e.g. ${escapeHtml(((scope.suggestions || [])[0] || {}).name || "a city")}">
      <div class="scope-hint">Flights and trains are searched to this city, and your trip starts here.</div>
    </div>` : "";
  const sugg = showSuggestions && (scope.suggestions || []).length ? `
    <div class="scope-block">
      <div class="form-label">${escapeHtml(scope.suggestions_title)}</div>
      <div class="scope-chips">${chipList(scope.suggestions, selected, "scope-check")}</div>
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
export function buildStayBlockHtml(block, choice) {
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
          ${picked}
        </div>
        <div class="stay-actions">
          <select class="form-select stay-sort" aria-label="Sort hotels">
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

export function buildTransfersHtml(transfers) {
  if (!transfers || !transfers.length) return "";
  const rows = transfers.map((t) => `
    <li><b>${escapeHtml(t.from_area)} → ${escapeHtml(t.to_area)}</b>: about ${t.distance_km} km, ~${t.hours} h
      <span class="stay-est">(estimate, around ${money(t.cost_per_person)} per person)</span>
      <div class="stay-est">${escapeHtml(t.note)}</div></li>`).join("");
  return `<div class="stay-transfers"><b>Travel between your stays</b><ul>${rows}</ul></div>`;
}

/** Stays summary shown on the finished itinerary. */
export function buildStaysSummaryHtml(data) {
  const blocks = (data.stay_blocks || []).filter((b) => b.needs_hotel);
  if (!blocks.length) return "";
  const rows = blocks.map((b) => {
    const h = b.hotel;
    const price = h && h.nightly_price ? ` · ₹${Math.round(h.nightly_price).toLocaleString("en-IN")} / night` : "";
    const link = h && h.booking_url ? ` <a href="${escapeHtml(h.booking_url)}" target="_blank" rel="noopener noreferrer">Book ↗</a>` : "";
    return `<li><b>${escapeHtml(b.area)}</b> · ${b.nights} night(s)${b.check_in ? ` · ${escapeHtml(b.check_in)} → ${escapeHtml(b.check_out)}` : ""}<br>
      ${h ? `🏨 ${escapeHtml(h.name)}${price}${link}` : `<span class="stay-est">No hotel chosen for this stay</span>`}</li>`;
  }).join("");
  return `<div class="stays-summary"><h3>Where you will stay</h3><ul>${rows}</ul>${buildTransfersHtml(data.transfers)}</div>`;
}
