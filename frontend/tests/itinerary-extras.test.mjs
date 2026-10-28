import * as x from "../js/pages/itinerary-extras.js";
import assert from "node:assert";
// date strip
const resp={days:[
 {date:"2026-11-02",label:"Mon 02 Nov",cheapest_price:6500,tier:"high",flights_found:3,is_selected:false,is_cheapest:false},
 {date:"2026-11-03",label:"Tue 03 Nov",cheapest_price:4000,tier:"low",flights_found:4,is_selected:false,is_cheapest:true},
 {date:"2026-11-04",label:"Wed 04 Nov",cheapest_price:5200,tier:"medium",flights_found:2,is_selected:true,is_cheapest:false},
 {date:"2026-11-05",label:"Thu 05 Nov",cheapest_price:null,tier:"unknown",flights_found:0,is_selected:false,is_cheapest:false}],
 note:"Tip: flying on Tue 03 Nov is about ₹1,200 cheaper per person"};
const h=x.buildDateStripHtml(resp,(d)=>d==="2026-11-05");
assert(h.includes("tier-low")&&h.includes("tier-medium")&&h.includes("tier-high")&&h.includes("tier-unknown"));
assert(h.includes("₹4,000")&&h.includes("Cheapest")&&h.includes("Selected"));
assert((h.match(/disabled/g)||[]).length===2, "selected + out-of-range chip disabled");
assert(h.includes("💡"));
assert(x.buildDateStripHtml({days:[],notice:"x <b>"}).includes("x &lt;b&gt;"));
// fare & availability
const fa={classes:[{code:"3A",label:"AC 3 Tier (3AC)",offered:true,fare_per_person:null,availability_status:null,data_quality:"verified"},
 {code:"2A",label:"AC 2 Tier (2AC)",offered:true,fare_per_person:1850,availability_status:"RAC",availability_detail:"RAC 4"},
 {code:"1A",label:"AC First Class (1AC)",offered:false},{code:"SL",label:"Sleeper (SL)",offered:null}],notice:"Fares not provided by RailRadar",check_url:"https://www.irctc.co.in/nget/train-search"};
const f=x.buildFareAvailabilityHtml(fa);
assert(f.includes("Not provided")&&f.includes("₹1,850")&&f.includes("RAC")&&f.includes("Not available on this train")&&f.includes("irctc"));
assert(!f.includes("undefined")&&!f.includes("null"));
assert(x.buildFareAvailabilityHtml(null)==="" && x.buildFareAvailabilityHtml({classes:[]})==="");
// advice
const a=x.buildTrainAdviceHtml({headline:"Recommended: R (1)",summary:"Take <it>",source:"rule-based",picks:[{label:"Best overall",option_id:"t1",title:"R (1)",reasons:["Fast"]}],caveats:[]});
assert(a.includes("Rule-based")&&a.includes("data-option-id=\"t1\"")&&a.includes("Take &lt;it&gt;"));
// quick version
const day={day_number:1,theme:"Old city & food",estimated_day_cost:"₹2,500",
 morning:{title:"Heritage",time_window:"9-12",places:[{name:"Golden Temple",duration:"2h",admission:"Free",directions:{maps_url:"https://www.google.com/maps/dir/?api=1&origin=A&destination=B"}},{name:"Bagh",address:"Amritsar"}]},
 food_stop_lunch:{name:"Kesar",cuisine:"Punjabi",recommendation:"Kulcha"},afternoon:{title:"Wagah",time_window:"2-5",places:[]},
 food_stop_dinner:null,evening:null};
const rows=x.quickRows(day);
assert.deepEqual(rows.map(r=>[r.when,r.name,!!r.url]),[["Morning","Golden Temple",true],["Morning","Bagh",true],["Lunch","Kesar",true],["Afternoon","Wagah",false]]);
assert(rows[1].url.includes("query=Bagh%20Amritsar"));
const q=x.buildQuickVersionHtml({title:"T <x>",days:[day],selected_hotel:{name:"H"},selected_outbound_transport:{operator:"IndiGo",number:"6E1",departure_time:"a",arrival_time:"b",price:4200},estimated_budget_total:"₹21,000"});
assert(q.includes("T &lt;x&gt;")&&q.includes("Map ↗")&&q.includes("Golden Temple")&&q.includes("₹4,200")&&q.includes("Quick version"));
assert(x.stationOptionsHtml([{code:"NDLS",name:"New Delhi",city:"Delhi"}],"NDLS").includes("selected"));
console.log("itinerary-extras: all assertions passed");

// ---- Phase 1: budget + did-you-mean
const cb = { detail: { travelers: 2, days: 3, nights: 2, rooms: 1, live_total: 20000, estimate_total: 9000, grand_total: 29000, per_person_total: 14500,
  daily: { per_person_per_day: 2000, split: [{ label: "Food & drinks", per_person_per_day: 800 }] },
  lines: [{ key: "outbound", label: "Outbound travel", kind: "live", per_person: 5000, total: 10000, note: "5,000 per person x 2" },
          { key: "food", label: "Food & drinks", kind: "estimate", per_person: 2400, total: 4800, note: "x" }],
  missing: ["Hotel stay: no hotel selected, so it is not included in the total."] } };
const bs = x.buildBudgetSummaryHtml(cb), bb = x.buildBudgetBreakdownHtml(cb);
assert(bs.includes("₹29,000") && bs.includes("₹14,500"));
assert(bb.includes("Live quote") && bb.includes("Estimate") && bb.includes("no hotel selected") && bb.includes("per person"));
assert(x.buildBudgetSummaryHtml({}) === "" && x.buildBudgetBreakdownHtml(null) === "");
const dym = x.buildDidYouMeanHtml([{ typed: "Munchen", field: "itineraryDest", items: [{ label: "Munich, Bavaria, Germany", kind_label: "City" }] }, { typed: "Delhi", field: "itinerarySource", items: [] }]);
assert(dym.includes('data-field="itineraryDest"') && dym.includes("Munich, Bavaria, Germany") && !dym.includes("Delhi"));
assert(x.buildDidYouMeanHtml([{ typed: "a", field: "f", items: [] }]) === "");
console.log("phase 1 builders: all assertions passed");

// ---- Phase 2: scope panel, stays, summaries
const scope = { kind: "state", name: "Kerala", advice: "Kerala is a whole state.", recommended_areas: 3, needs_arrival: true,
  modes: [{ value: "inside", label: "Stay inside Kerala" }, { value: "neighbours", label: "Also explore neighbouring states" }],
  suggestions: [{ name: "Kochi", note: "Backwaters <gateway>" }, { name: "Munnar", note: "" }], suggestions_title: "Cities you would like to visit (optional)",
  neighbours: [{ name: "Tamil Nadu", note: "" }], neighbours_title: "Neighbouring states to add (optional)" };
let sp = x.buildScopePanelHtml(scope, { mode: "inside", selected: ["Kochi"], neighbourSelected: [], arrival: "" });
assert(sp.includes('id="scopeArrival"') && sp.includes("required") && sp.includes("Kochi") && sp.includes("Backwaters &lt;gateway&gt;"));
assert(sp.includes('value="Kochi" checked') && !sp.includes('value="Munnar" checked'));
assert(!sp.includes("Tamil Nadu"), "neighbours are hidden until that mode is chosen");
sp = x.buildScopePanelHtml(scope, { mode: "neighbours", selected: [], neighbourSelected: ["Tamil Nadu"], arrival: "Kochi" });
assert(sp.includes("Tamil Nadu") && sp.includes('value="Kochi"') && sp.includes('name="scopeMode" value="neighbours" checked'));
const city = { kind: "city", name: "Jaipur", advice: "x", recommended_areas: 2, needs_arrival: false, modes: [{ value: "only", label: "Only Jaipur" }, { value: "nearby", label: "Jaipur and nearby places" }],
  suggestions: [{ name: "Agra", note: "" }], suggestions_title: "Nearby" };
const onlyHtml = x.buildScopePanelHtml(city, { mode: "only", selected: [], neighbourSelected: [], arrival: "" });
assert(!onlyHtml.includes("scopeArrival") && !onlyHtml.includes("Agra"), "city-only shows no extra questions");
assert(x.buildScopePanelHtml(city, { mode: "nearby", selected: [] }).includes("Agra"));
assert(x.buildScopePanelHtml(null, {}) === "");
assert(x.scopeCountText(scope, 1).includes("one place") && x.scopeCountText(scope, 3).includes("good fit") && x.scopeCountText(scope, 5).includes("more than the 3"));

const block = { index: 1, area: "Agra", nights: 2, start_day: 4, end_day: 5, check_in: "2099-03-13", check_out: "2099-03-15", places: ["Taj Mahal", "Agra Fort"], needs_hotel: true };
const sb = x.buildStayBlockHtml(block, undefined);
assert(sb.includes("Stay 2: Agra") && sb.includes("2 nights") && sb.includes("Taj Mahal, Agra Fort") && sb.includes("stay-find") && sb.includes("stay-skip"));
assert(x.buildStayBlockHtml({ ...block, nights: 1 }, undefined).includes("1 night"));
assert(x.buildStayBlockHtml(block, { name: "Hotel <A>", nightly_price: 3200 }).includes("Hotel &lt;A&gt;"));
assert(x.buildStayBlockHtml(block, null).includes("No hotel for this stay"));

const transfers = [{ from_area: "Jaipur", to_area: "Agra", distance_km: 291, hours: 5.8, cost_per_person: 1018, note: "Road/rail estimate; check timetables." }];
assert(x.buildTransfersHtml(transfers).includes("291 km") && x.buildTransfersHtml(transfers).includes("estimate") && x.buildTransfersHtml([]) === "");
const done = { stay_blocks: [{ ...block, hotel: { name: "Taj View", nightly_price: 5000, booking_url: "https://example.com/b" } },
  { index: 2, area: "Delhi", nights: 1, needs_hotel: true, hotel: null }, { index: 3, area: "Delhi", nights: 0, needs_hotel: false }], transfers };
const sum = x.buildStaysSummaryHtml(done);
assert(sum.includes("Taj View") && sum.includes("₹5,000") && sum.includes("Book ↗") && sum.includes("No hotel chosen for this stay") && sum.includes("Travel between your stays"));
assert(x.buildStaysSummaryHtml({ stay_blocks: [{ needs_hotel: false }] }) === "");
const qv = x.buildQuickVersionHtml({ title: "T", days: [{ day_number: 2, area: "Agra", theme: "Taj", morning: { places: [{ name: "Taj Mahal" }] } }],
  selected_hotels: [{ name: "Taj View", area: "Agra" }, { name: "Delhi Inn", area: "Delhi" }] });
assert(qv.includes("Stay in Agra") && qv.includes("Delhi Inn") && qv.includes("Day 2 · Agra"));
console.log("phase 2 builders: all assertions passed");

// ---- Batch A: finished and upcoming stays shrink to a card
const doneBlock = { index: 0, area: "Jaipur", nights: 3, check_in: "2099-03-10", check_out: "2099-03-13", start_day: 1, end_day: 3 };
const doneHtml = x.buildStayDoneHtml(doneBlock, { name: "Hotel <Pink>", rating: 4.4, nightly_price: 3200, address: "MI Road" });
assert(doneHtml.includes("stay-done") && doneHtml.includes("Hotel &lt;Pink&gt;") && doneHtml.includes("₹3,200") && doneHtml.includes("MI Road") && doneHtml.includes("stay-change") && doneHtml.includes(">Change<"));
assert(!doneHtml.includes("stay-find") && !doneHtml.includes("Find hotels"), "a finished stay shows only the chosen hotel");
assert(x.buildStayDoneHtml(doneBlock, null).includes("No hotel for this stay") && x.buildStayDoneHtml(doneBlock, null).includes("Choose a hotel"));
const upHtml = x.buildStayUpcomingHtml({ ...doneBlock, index: 1, area: "Agra", nights: 1 });
assert(upHtml.includes("stay-upcoming") && upHtml.includes("Stay 2: Agra") && upHtml.includes("1 night") && upHtml.includes("choose after the stay above"));
console.log("batch A builders: all assertions passed");

// ---- Batch B: visuals, day notes, hotel hops
import { collectTripPoints } from "../js/components/trip-map.js";
const trip = { source: "Delhi", destination: "Rajasthan", duration_days: 4, estimated_budget_total: "₹82,800 total estimate",
  selected_outbound_transport: { mode: "flight" }, selected_return_transport: { mode: "train" },
  areas: ["Jaipur", "Udaipur"], selected_hotels: [{ name: "Pink Inn", area: "Jaipur", latitude: 26.92, longitude: 75.8 }, { name: "Lake View", area: "Udaipur", latitude: 24.58, longitude: 73.68 }],
  stay_blocks: [{ index: 0, area: "Jaipur", nights: 2, needs_hotel: true, hotel: { name: "Pink Inn" } }, { index: 1, area: "Udaipur", nights: 1, needs_hotel: true, hotel: { name: "Lake View" } }],
  transfers: [{ to_stay: 1, distance_km: 395 }],
  days: [{ day_number: 1, theme: "Pink city", area: "Jaipur", morning: { places: [{ name: "Hawa Mahal", latitude: 26.92, longitude: 75.82 }] }, afternoon: { places: [{ name: "City Palace", latitude: 26.93, longitude: 75.82 }] },
          food_stop_lunch: { name: "Laxmi Misthan", latitude: 26.92, longitude: 75.82 }, evening: { places: [] }, notes: [{ type: "arrival", title: "Getting there", icon: "✈️", lines: ["Today you fly <Delhi> → Jaipur."] }] },
         { day_number: 2, theme: "Forts", area: "Jaipur", morning: { places: [{ name: "Amber Fort" }] }, afternoon: { places: [] }, evening: { places: [] },
           notes: [{ type: "hotel_change", title: "Changing hotel today", lines: ["Check out of Pink Inn by 11:00."] }, { type: "departure", title: "Heading home", lines: ["Be at the airport by 16:30."] }] }] };
const g = x.buildTripGlanceHtml(trip);
assert(g.includes("Your trip at a glance") && g.includes("Delhi") && g.includes("Jaipur") && g.includes("Udaipur") && g.includes("Pink Inn") && g.includes("~395 km"));
assert(g.includes("✈️") && g.includes("🚆") && g.includes("4 days") && g.includes("3 nights") && g.includes("₹82,800") && g.includes("Day 1") && g.includes("Pink city"));
assert(g.includes("2 hotels") && g.includes("3 places"), "counts places across days");
assert(!x.buildTripGlanceHtml({ ...trip, stay_blocks: [], selected_hotels: [] }).includes("undefined"));
const topNotes = x.buildDayNotesHtml(trip.days[0].notes, ["arrival", "hotel_change"]);
assert(topNotes.includes("day-note-arrival") && topNotes.includes("Today you fly &lt;Delhi&gt;"));
assert(x.buildDayNotesHtml(trip.days[1].notes, ["arrival", "hotel_change"]).includes("Changing hotel today"));
assert(!x.buildDayNotesHtml(trip.days[1].notes, ["arrival", "hotel_change"]).includes("Heading home"));
assert(x.buildDayNotesHtml(trip.days[1].notes, ["departure"]).includes("Heading home"));
assert.deepEqual(x.dayHighlights(trip.days[0]), ["Hawa Mahal", "City Palace"]);
assert(x.dayColor(1) !== x.dayColor(2) && x.dayColor(8) === x.dayColor(1));
const hop = x.hotelHop({ latitude: 26.92, longitude: 75.8 }, { latitude: 24.58, longitude: 73.68 });
assert(hop.km > 300 && hop.minutes > 300 && x.hotelHop({}, { latitude: 1, longitude: 1 }) === null);
const conn = x.buildHotelConnectorHtml({ name: "Pink Inn", latitude: 26.92, longitude: 75.8 }, { name: "Lake <View>", latitude: 24.58, longitude: 73.68 });
assert(conn.includes("Changing hotel") && conn.includes("Pink Inn") && conn.includes("Lake &lt;View&gt;") && conn.includes("km</b> apart") && conn.includes("estimate"));
assert(x.buildHotelConnectorHtml({ name: "A" }, { name: "B" }).includes("distance not available"));
const stays2 = x.buildStaysSummaryHtml({ stay_blocks: [{ index: 0, area: "Jaipur", nights: 2, needs_hotel: true, hotel: { name: "Pink Inn", latitude: 26.92, longitude: 75.8 } },
  { index: 1, area: "Udaipur", nights: 1, needs_hotel: true, hotel: { name: "Lake View", latitude: 24.58, longitude: 73.68 } }], transfers: [] });
assert(stays2.includes("Changing hotel from Pink Inn") && stays2.includes("km, roughly"));
const pts = collectTripPoints(trip);
assert(pts.places.length === 3 && pts.places.filter((p) => p.food).length === 1 && pts.hotels.length === 2);
assert(pts.places.every((p) => p.lat != null && p.day >= 1), "places without coordinates are left off the map");
console.log("batch B builders: all assertions passed");

// ---- Alternative flight booking links
const flightParams = { departure_id: "DEL", arrival_id: "FCO", outbound_date: "2026-11-04", adults: 2, currency: "INR" };
const siteLinks = x.buildFlightSiteLinks(flightParams);
assert.deepEqual(siteLinks.map((s) => s.name), ["Google Flights", "Skyscanner", "Kayak"]);
assert(siteLinks[0].url.startsWith("https://www.google.com/travel/flights?q=") && decodeURIComponent(siteLinks[0].url).includes("Flights to FCO from DEL on 2026-11-04 one way"));
assert(siteLinks[1].url === "https://www.skyscanner.co.in/transport/flights/del/fco/261104/?adultsv2=2&cabinclass=economy&currency=INR");
assert(siteLinks[2].url === "https://www.kayak.co.in/flights/DEL-FCO/2026-11-04/2adults");
assert.deepEqual(x.buildFlightSiteLinks({}), [], "nothing is guessed without a route and date");
assert.deepEqual(x.buildFlightSiteLinks({ ...flightParams, departure_id: "DEL,BOM" }), []);
assert.deepEqual(x.buildFlightSiteLinks({ ...flightParams, outbound_date: "04/11/2026" }), []);
const siteHtml = x.buildFlightSiteLinksHtml(flightParams);
assert(siteHtml.includes("Or book on a flight website") && siteHtml.includes('rel="noopener noreferrer"') && siteHtml.includes("DEL → FCO on 2026-11-04") && siteHtml.includes("Prices there can differ"));
assert(x.buildFlightSiteLinksHtml(null) === "");
console.log("flight site links: all assertions passed");

// ---- Booking dialog heading can be set; default unchanged
assert(x.buildFlightSiteLinksHtml(flightParams, "Book on a flight website").includes("Book on a flight website"));
assert(!x.buildFlightSiteLinksHtml(flightParams, "Book on a flight website").includes("Or book on"));
console.log("booking dialog heading: ok");

// ---- Batch C: scope follows the trip length, place "about", scroll progress
import { computeProgress } from "../js/components/scroll-progress.js";
assert(x.recommendedAreas("country", 14) === 4 && x.recommendedAreas("country", 3) === 1 && x.recommendedAreas("country", 30) === 5);
assert(x.recommendedAreas("state", 3) === 1 && x.recommendedAreas("state", 8) === 4 && x.recommendedAreas("city", 9) === 3 && x.recommendedAreas("city", 2) === 1);
assert(x.scopeAdviceText("country", "Italy", 10, 5) === "Italy is a whole country. With 10 day(s), about 3 place(s) to stay in works best, so less time is spent travelling between them. You picked 5; that is possible but will mean more travelling.");
assert(x.scopeAdviceText("city", "Jaipur", 6).includes("add up to 1 nearby place(s)") && !x.scopeAdviceText("city", "Jaipur", 2).includes("nearby"));
// fewer days -> fewer suggested places, more days -> more (what changing the dates now does)
assert(x.recommendedAreas("country", 12) > x.recommendedAreas("country", 6));
const sc = { kind: "country", name: "Italy", advice: "a", recommended_areas: 2, needs_arrival: true, modes: [], source: "ai",
  suggestions: [{ name: "Rome" }, { name: "Florence" }, { name: "Venice" }, { name: "Milan" }], suggestions_title: "Where?" };
const panel = x.buildScopePanelHtml(sc, { mode: "", selected: [], neighbourSelected: [], arrival: "" }, { days: 6, refreshDays: 12 });
assert((panel.match(/fits your 6 days/g) || []).length === 2, "only the best-fitting suggestions are marked");
assert(panel.includes('id="scopeRefresh"') && panel.includes("Refresh suggestions for 12 days"));
assert(!x.buildScopePanelHtml(sc, { mode: "", selected: [] }, { days: 6 }).includes("scopeRefresh"));
assert(!x.buildScopePanelHtml({ ...sc, recommended_areas: 4 }, { mode: "", selected: [] }, { days: 6 }).includes("fits your"), "no marks when everything fits");
const about = x.placeAboutHtml({ about: "A pink <palace>.", what_to_do: "Look up." });
assert(about.includes("A pink &lt;palace&gt;.") && about.includes("What to do:") && x.placeAboutHtml({}) === "");
assert(computeProgress({ scrollY: 0, scrollHeight: 3000, viewportHeight: 1000 }) === 0);
assert(computeProgress({ scrollY: 1000, scrollHeight: 3000, viewportHeight: 1000 }) === 0.5);
assert(computeProgress({ scrollY: 5000, scrollHeight: 3000, viewportHeight: 1000 }) === 1);
assert(computeProgress({ scrollY: 50, scrollHeight: 800, viewportHeight: 1000 }) === 0, "a page that does not scroll shows no progress");
assert(computeProgress({ scrollY: -20, scrollHeight: 3000, viewportHeight: 1000 }) === 0);
console.log("batch C builders: all assertions passed");

// ---- Batch D: travel between stays, hotel best match
const tr = { from_area: "Jaipur", to_area: "Agra", distance_km: 291, hours: 5.8, cost_per_person: 1018, note: "Road/rail estimate.", date: "2099-03-12", needs_choice: true };
const blk = { index: 1, area: "Agra" };
const chooser = x.buildTransferChooserHtml(blk, tr, "train");
assert(chooser.includes("How will you get from Jaipur to Agra?") && chooser.includes("2099-03-12") && chooser.includes('data-tab="flight"') && chooser.includes('data-tab="train"') && chooser.includes('data-tab="other"') && chooser.includes('data-tab="cab"'));
assert(chooser.includes('transfer-tab active" data-tab="train"') && !chooser.includes('transfer-tab active" data-tab="flight"'));
const legData = { flights: [{ id: "f1", operator: "IndiGo", number: "6E 1", departure_time: "2099-03-12 09:00", arrival_time: "2099-03-12 10:05", duration_formatted: "1h 5m", stops: 0, price: 3500, origin: "JAI (Jaipur Airport)", destination: "AGR (Agra Airport)" }, { id: "f2", operator: "Air X", price: null, stops: 1 }],
  trains: [{ id: "t1", operator: "Indian Railways (Shatabdi)", number: "12001", departure_time: "2099-03-12 08:10", arrival_time: "2099-03-12 11:25", duration_formatted: "3h 15m", origin: "JP Station", destination: "AGC Station" }] };
const flightsPanel = x.buildTransferPanelHtml("flight", legData, tr, {});
assert(flightsPanel.includes("₹3,500") && flightsPanel.includes("per person") && flightsPanel.includes("09:00 → 10:05") && flightsPanel.includes("Direct") && flightsPanel.includes("Jaipur Airport → Agra Airport"));
assert(flightsPanel.includes("transfer-book") && flightsPanel.includes("Price not available") && flightsPanel.includes('data-kind="flight"'));
const trainsPanel = x.buildTransferPanelHtml("train", legData, tr, {});
assert(trainsPanel.includes("Shatabdi") && trainsPanel.includes("Fare not provided") && trainsPanel.includes("irctc.co.in") && trainsPanel.includes("not provided by our data source") && !trainsPanel.includes("transfer-book"));
assert(x.buildTransferPanelHtml("flight", null, tr, { loading: true }).includes("Searching flights"));
assert(x.buildTransferPanelHtml("train", null, tr, { error: true }).includes("Could not load options"));
assert(x.buildTransferPanelHtml("train", { trains: [], rail_notice: "Train search covers India only." }, tr, {}).includes("India only"));
assert(x.buildTransferPanelHtml("flight", legData, { ...tr, date: null }, {}).includes("Add travel dates"));
const cabPanel = x.buildTransferPanelHtml("cab", null, tr, {});
assert(cabPanel.includes("291 km") && cabPanel.includes("₹1,018") && cabPanel.includes("estimate") && cabPanel.includes('data-kind="cab"') && !cabPanel.includes("transfer-option"));
const otherPanel = x.buildTransferPanelHtml("other", null, tr, {});
assert(otherPanel.includes("rome2rio.com/s/Jaipur/Agra") && otherPanel.includes("travelmode=transit") && otherPanel.includes("not priced here") && otherPanel.includes('data-kind="other"'));
assert(x.otherTravelLinks("New Delhi", "Agra")[0].url === "https://www.rome2rio.com/s/New%20Delhi/Agra");
assert(x.buildTransferSummaryLine({ mode: "cab" }).includes("cab") && x.buildTransferSummaryLine({ mode: "other" }).includes("arrange"));
const sumF = x.buildTransferSummaryLine({ mode: "flight", option: legData.flights[0] });
assert(sumF.includes("✈️") && sumF.includes("6E 1") && sumF.includes("09:00 → 10:05") && sumF.includes("₹3,500 per person"));
assert(x.buildTransferSummaryLine({ mode: "train", option: legData.trains[0] }).includes("fare not provided") && x.buildTransferSummaryLine(null) === "");
assert(x.buildStayDoneHtml({ index: 1, area: "Agra", nights: 1, start_day: 3, end_day: 4 }, { name: "H" }, "✈️ IndiGo 6E 1").includes("✈️ IndiGo 6E 1"));
assert(x.buildStayBlockHtml({ index: 1, area: "Agra", nights: 1, start_day: 3, end_day: 4 }, undefined, "🚆 Shatabdi").includes("Change travel"));
assert(!x.buildStayBlockHtml({ index: 0, area: "Agra", nights: 1, start_day: 1, end_day: 2 }, undefined).includes("Change travel"));
assert(x.buildStayBlockHtml({ index: 0, area: "A", nights: 1, start_day: 1, end_day: 2 }, undefined).includes('value="best_match"'));
assert(x.buildTransfersHtml([{ ...tr, choice: { mode: "flight", operator: "IndiGo", number: "6E 1", departure_time: "2099-03-12 09:00", arrival_time: "2099-03-12 10:05", price: 3500 } }]).includes("IndiGo"));
assert(x.buildTransfersHtml([{ ...tr, choice: { mode: "cab" } }]).includes("(cab)"));
assert(x.buildTripGlanceHtml({ source: "Delhi", duration_days: 3, stay_blocks: [{ index: 0, area: "Jaipur", nights: 1, needs_hotel: true }, { index: 1, area: "Agra", nights: 1, needs_hotel: true }],
  transfers: [{ to_stay: 1, distance_km: 291, choice: { mode: "train" } }], days: [] }).includes("🚆<small>~291 km"));

// hotels: best match combines distance, price, rating and arrival closeness
const centre = { lat: 26.9, lon: 75.8 };
const hotels = [
  { id: "far-cheap", name: "Far & cheap", latitude: 27.3, longitude: 76.3, nightly_price: 1500, rating: 3.9 },
  { id: "near-pricey", name: "Near & pricey", latitude: 26.905, longitude: 75.805, nightly_price: 9000, rating: 4.6 },
  { id: "near-fair", name: "Near & fair", latitude: 26.91, longitude: 75.81, nightly_price: 3000, rating: 4.5 },
  { id: "no-coords", name: "No coords", nightly_price: 2500, rating: 4.0 }];
const ranked = x.scoreHotels(hotels, { centroid: centre });
assert(ranked[0].hotel.id === "near-fair", "close, fairly priced and well rated wins: " + ranked.map((r) => r.hotel.id));
assert(ranked.every((r) => r.score >= 0 && r.score <= 100) && ranked.length === 4);
assert(ranked.find((r) => r.hotel.id === "near-fair").why.some((w) => w.includes("km from where you will spend your days")));
assert(ranked.find((r) => r.hotel.id === "no-coords").spotsKm === null, "missing coordinates are skipped, not guessed");
assert(ranked.find((r) => r.hotel.id === "near-pricey").hotel.rating >= 4.5 && ranked.find((r) => r.hotel.id === "near-pricey").why.includes("⭐ Highly rated"));
const withAnchor = x.scoreHotels(hotels, { centroid: centre, anchor: { lat: 27.3, lon: 76.3, label: "Jaipur Airport" } });
assert(withAnchor.find((r) => r.hotel.id === "far-cheap").why.some((w) => w.includes("km from Jaipur Airport")));
assert(withAnchor.find((r) => r.hotel.id === "far-cheap").score > ranked.find((r) => r.hotel.id === "far-cheap").score, "being near the airport helps a hotel");
assert(withAnchor[0].why.some((w) => w.startsWith("🛬")) && x.scoreHotels(hotels, { centroid: centre, anchor: { lat: 1, lon: 1, label: "Agra Cantt Station" } })[0].why.some((w) => w.startsWith("🚉")));
assert.deepEqual(x.scoreHotels([], {}), []);
assert(x.buildMatchChipsHtml(ranked[0]).includes("% match") && x.buildMatchChipsHtml(null) === "");
assert(x.haversineKm({ lat: 26.92, lon: 75.8 }, { lat: 24.58, lon: 73.68 }) > 300);
console.log("batch D builders: all assertions passed");
assert(withAnchor.findIndex((r) => r.hotel.id === "no-coords") > withAnchor.findIndex((r) => r.hotel.id === "near-fair"), "missing data never lifts a hotel");
console.log("hotel ranking guard: ok");

// ---- Plan your area: a suggested start city and places to choose from
const italy = { kind: "country", name: "Italy", advice: "a", recommended_areas: 3, needs_arrival: true, modes: [], source: "static",
  default_arrival: "Rome", default_arrival_note: "capital",
  arrival_options: [{ name: "Rome", note: "capital" }, { name: "Florence", note: "Art" }, { name: "Venice", note: "Canals" }],
  suggestions: [{ name: "Florence", note: "Art" }, { name: "Venice", note: "Canals" }, { name: "Milan", note: "Fashion" }], suggestions_title: "Where?" };
const italyHtml = x.buildScopePanelHtml(italy, { mode: "", selected: [], neighbourSelected: [], arrival: "Rome" }, { days: 10 });
assert(italyHtml.includes('data-city="Rome"') && italyHtml.includes("★ Rome") && italyHtml.includes('data-city="Florence"') && italyHtml.includes('data-city="Venice"'));
assert(italyHtml.includes('scope-arrival-chip active" data-city="Rome"') && !italyHtml.includes('scope-arrival-chip active" data-city="Venice"'));
assert(italyHtml.includes('id="scopeArrival"') && italyHtml.includes('value="Rome"') && italyHtml.includes("We suggest Rome (capital)") && italyHtml.includes("Pick another start"));
assert(italyHtml.includes("Popular places from our built-in list") && italyHtml.includes('value="Milan"') && italyHtml.includes('class="scope-check"'));
const venice = x.buildScopePanelHtml(italy, { mode: "", selected: [], arrival: "venice" }, { days: 10 });
assert(venice.includes('scope-arrival-chip active" data-city="Venice"') && !venice.includes('scope-arrival-chip active" data-city="Rome"'), "choosing another start city highlights it");
const noDefault = x.buildScopePanelHtml({ ...italy, default_arrival: null, arrival_options: [], source: "basic", suggestions: [] }, { mode: "", selected: [], arrival: "" }, { days: 10 });
assert(noDefault.includes('id="scopeArrival"') && !noDefault.includes("scope-arrival-chip") && !noDefault.includes("We suggest"));
console.log("plan-your-area start city: all assertions passed");

// ---------------------------------------------------------------- day route, return to hotel, flight details
{
  const { buildDayStops, buildDayFlowHtml } = await import("../js/components/day-route.js");
  const { buildReturnToHotelHtml, buildTransfersHtml, buildFlightDetailHtml } = await import("../js/pages/itinerary-extras.js");
  const place = (name, lat, lon) => ({ name, latitude: lat, longitude: lon });
  const day = {
    day_number: 1,
    morning: { places: [place("Colosseum", 41.89, 12.49)] },
    food_stop_lunch: { name: "Trattoria", latitude: 41.9, longitude: 12.5 },
    afternoon: { places: [place("Forum", 41.892, 12.485)] },
    food_stop_dinner: { name: "Pizzeria", skipped: true },
    evening: { places: [place("Trevi", 41.9, 12.48)] },
    return_to_hotel: { hotel_name: "Hotel Hiberia" },
  };
  const stops = buildDayStops(day, { name: "Hotel Hiberia", latitude: 41.91, longitude: 12.5 });
  assert.deepEqual(stops.map((s) => s.name), ["Hotel Hiberia", "Colosseum", "Trattoria", "Forum", "Trevi", "Hotel Hiberia"]);
  assert.deepEqual(stops.map((s) => s.num), [0, 1, 2, 3, 4, 5]);           // visiting order, skipped dinner left out
  assert.ok(buildDayFlowHtml(stops).includes("dayflow") && buildDayFlowHtml(stops).includes("Trevi"));
  assert.equal(buildDayFlowHtml([stops[0]]), "");

  const rt = { hotel_name: "Hotel Hiberia", hotel_address: "Via X", from_name: "Trevi", text: "After Trevi, head back.", leave_at: "21:30",
    arrive_at: "21:45", directions: { distance_km: 2.1, walk_minutes: 28, drive_minutes: 12, maps_url: "https://maps.example/x?a=1&b=2" } };
  const rtHtml = buildReturnToHotelHtml(rt);
  assert.ok(rtHtml.includes("Back to your hotel") && rtHtml.includes("21:30") && rtHtml.includes("https://maps.example/x?a=1&amp;b=2"));
  assert.equal(buildReturnToHotelHtml(null), "");

  // after a flight is chosen: flight details (time, distance), never the cab / road price estimate
  const transfers = [{ from_area: "Rome", to_area: "Florence", to_stay: 1, distance_km: 360, air_km: 277, hours: 7.2, cost_per_person: 1260, note: "Road/rail estimate" }];
  const choice = { 1: { mode: "flight", option: { operator: "ITA", number: "AZ1", departure_time: "2099-03-12 09:00", arrival_time: "2099-03-12 10:05", duration_formatted: "1h 5m", price: 5200 } } };
  const chosen = buildTransfersHtml(transfers, choice);
  assert.ok(chosen.includes("09:00") && chosen.includes("10:05") && chosen.includes("277") && chosen.includes("ITA"));
  assert.ok(!chosen.includes("by road") && !chosen.includes("per person)") && !chosen.includes("1,260"));
  assert.ok(buildTransfersHtml(transfers).includes("by road"));             // nothing chosen yet: the road estimate is still shown
  assert.ok(buildFlightDetailHtml(null) === "");
  console.log("day route / return to hotel / flight details: all assertions passed");
}

// ---------------------------------------------------------------- nearby dates are offered, not fetched automatically
{
  const { buildDateStripPromptHtml } = await import("../js/pages/itinerary-extras.js");
  const html = buildDateStripPromptHtml();
  assert.ok(html.includes("date-strip-load") && html.includes("Compare prices for nearby dates") && html.includes("only when you ask"));
  console.log("nearby-date prompt: all assertions passed");
}

// ---------------------------------------------------------------- website links on places and restaurants
{
  const { siteLinkHtml } = await import("../js/pages/itinerary-extras.js");
  const ok = siteLinkHtml("https://example.org/a?x=1&y=2");
  assert.ok(ok.includes('href="https://example.org/a?x=1&amp;y=2"') && ok.includes('rel="noopener noreferrer"') && ok.includes("Website"));
  assert.equal(siteLinkHtml(""), "");
  assert.equal(siteLinkHtml(null), "");
  assert.equal(siteLinkHtml("javascript:alert(1)"), "");
  assert.equal(siteLinkHtml("www.nohttp.test"), "");
  console.log("website links: all assertions passed");
}
