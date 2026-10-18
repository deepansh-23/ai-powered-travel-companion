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
