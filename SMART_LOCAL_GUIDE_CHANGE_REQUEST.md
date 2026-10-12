# Smart Local Guide — Change Request & Technical Specification

## 1. Objective

Transform the existing Smart Local Guide into a complete, portfolio-quality **door-to-door trip planner**:

**Source → Destination → Outbound Transport → Local Trip → Return Transport → Final Itinerary → External Booking → PDF/History**

The existing application must be modified in place. Do not create a parallel application or rewrite working features unnecessarily.

---

## 2. Mandatory Architecture Rule

Before editing:

1. Inspect the existing project structure.
2. Identify the current frontend/backend architecture, routes, services, state management, history, maps, PDF generation, environment handling, and styling.
3. Read the relevant existing files before modifying them.
4. Reuse existing components/services where practical.
5. Do not assume filenames, endpoints, or state mechanisms.
6. Do not build a second application.
7. Preserve all existing working functionality and themes.
8. Use current official provider documentation for provider-specific API/authentication details.
9. Keep secrets server-side.
10. Test every changed feature and regression-test existing services.

---

## 3. New End-to-End Trip Flow

Implement:

```text
Itinerary Planner
  ↓
Source
  ↓
Destination
  ↓
Departure + Return Dates / Trip Duration
  ↓
Number of Travellers
  ↓
Travel Preference
  ↓
Transport Search
  ↓
Flights + Trains
  ↓
Compare
  ↓
Select Outbound
  ↓
Select Return
  ↓
Hotel Search + Price Comparison (optional, can be skipped)
  ↓
Local Trip Preferences
  ↓
Real Local Places
  ↓
Time-Aware Itinerary
  ↓
View / PDF / History / External Booking
```

Outbound and return are independent. Mixed transport must work, e.g. outbound flight + return train.

---

## 4. Initial Itinerary Inputs

Collect:

- Source/start location
- Destination
- Departure date
- Return date or trip duration
- Number of travellers

Travel preference:

- Cheapest
- Fastest
- Best Overall
- Prefer Flight
- Prefer Train
- No Preference

Preference affects recommendation ranking but must not hide valid alternatives.

---

## 5. Source/Destination Grounding

This is critical.

The application must:

- Keep source and destination separate.
- Validate both before searching.
- Use source/destination for transport searches.
- Use destination for local place searches.
- Clear/reinitialize destination-specific results when destination changes.
- Never use stale data from another city.
- Clearly display the selected source and destination.
- Never silently fall back to unrelated mock/cached results in live mode.

A previous issue where an Amritsar trip returned Manchester/Deansgate/John Rylands data must not recur.

---

## 6. Flight Integration — SerpApi (Google Flights)

Use **SerpApi's Google Flights engine** (`engine=google_flights`) as the flight provider. This replaces Amadeus; do not add any Amadeus code, credentials or dependencies.

Keep credentials server-side.

Logical configuration:

```env
SERPAPI_API_KEY=
```

Adapt names to the existing configuration system if necessary. The same key is also used for hotel search (Section 7A).

Use current official SerpApi documentation (Google Flights API) for exact parameters, response fields and error formats. Do not invent parameter names or response fields.

Flight search should use:

- Origin (airport code / city resolved to airport(s))
- Destination (airport code / city resolved to airport(s))
- Date
- Travellers
- Currency
- Travel class, stops filter and sort order where supported

Search rules:

- Outbound and return are selected independently, so search them as **two separate one-way searches** (outbound date, then return date with source/destination swapped) instead of a single round-trip search. This keeps prices per leg consistent and supports mixed flight/train journeys.
- Resolve city names to IATA airport codes before searching. If a city has several airports, search them and show which airport each option uses. If no airport serves the city, say so clearly and rely on trains instead; never guess a code.
- Merge the provider's "best" and "other" flight lists into one normalized list and remove duplicates.
- Cache identical searches (same origin, destination, date, travellers, currency) for a short period to conserve SerpApi credits.
- If the provider returns a booking token or booking options for a selected flight, use it to retrieve provider-supplied booking links. Do not construct booking URLs yourself.

Display provider-supplied facts where available:

- Airline
- Flight number
- Departure airport/time
- Arrival airport/time
- Duration
- Stops / layover airports and layover duration
- Price/currency
- Cabin/class
- Provider-supplied price insights (for example, whether the price is low/typical/high for the route), if returned

Gemini must never invent these facts.

---

## 7. Railway Integration — RailRadar

Use **RailRadar** as the initial railway provider.

Logical configuration:

```env
RAILRADAR_API_KEY=
```

Use current official RailRadar documentation for exact authentication/endpoints.

Support where available:

- Source station/city
- Destination station/city
- Journey date
- Train number/name
- Departure
- Arrival
- Duration
- Fare
- Class
- Other relevant train information

Create a provider abstraction so RailRadar can be replaced later.

---

## 7A. Hotel Search & Price Comparison — SerpApi (Google Hotels)

Use **SerpApi's Google Hotels engine** (`engine=google_hotels`) as the provider for hotel search, price comparison and cheapest-option discovery. Use the same `SERPAPI_API_KEY` as flights.

Use current official SerpApi documentation (Google Hotels API) for exact parameters, response fields and the property-details request. Do not invent parameter names or response fields.

Inputs:

- Destination (the validated destination from Section 5)
- Check-in date = arrival date of the selected outbound transport
- Check-out date = departure date of the selected return transport
- Number of travellers (and rooms, if supported by the existing UI)
- Currency

Filters and sorting (use provider-supported parameters where available):

- Sort: Lowest price, Highest rating, Most reviewed, Relevance
- Price range (min/max)
- Minimum rating
- Hotel class (stars)
- Amenities
- Free cancellation

Display provider-supplied facts where available:

- Hotel name
- Photos
- Star class and guest rating / review count
- Nightly rate and total stay price, with currency
- Taxes/fees information if the provider returns it
- Amenities, location/GPS coordinates and nearby places
- Booking-site price comparison for a hotel (the sites offering it and each site's price) from the provider's property-details response
- Free cancellation flag where provided

Rules:

- Price comparison: for the selected hotel, show the lowest price and the booking site offering it, and list other sites' prices where the provider returns them. Mark the cheapest option clearly.
- Backend code computes "Cheapest", "Best Rated" and "Best Value" labels (for example, a price/rating balance) and shows the reason. Gemini must not decide this.
- Use the provider-supplied booking links only (property page or booking-site links returned by SerpApi). Never construct or guess hotel booking URLs. Clearly indicate the user is leaving the app. No in-app booking or payment.
- Provider prices are live quotes, not guarantees; label them with the search date and the note that prices can change.
- Hotel coordinates from SerpApi may be shown on the existing map component, using the same marker/card selection behaviour as other services.
- Cache identical searches for a short period to conserve SerpApi credits. Fetch the extra property-details request only when the user opens or selects a hotel, not for every result.
- Hotel selection is optional. If the user skips it, or no hotel is returned, continue to the local itinerary and clearly label the accommodation cost as "not selected".
- If SerpApi fails or the key is missing, show a clear error. Optionally, offer Geoapify `accommodation.hotel` results as an unpriced fallback, clearly labeled "No price data available". Never fabricate prices, ratings or availability.
- The hotel search must be tied to the current destination. When the destination changes, clear hotel results (same stale-data rule as Section 5).

---

## 8. Transport Service Architecture

Keep transport providers behind a backend service layer conceptually like:

```text
SerpApiClient            (shared HTTP client, key handling, caching, error mapping)
FlightService            (SerpApi Google Flights)
RailService              (RailRadar)
HotelService             (SerpApi Google Hotels)
TransportSearchService
TransportRecommendationService
HotelRecommendationService
```

The exact implementation must follow the existing architecture.

Frontend must not directly contain provider credentials or provider-specific secrets.

---

## 9. Transport Comparison

Show a dedicated transport-selection page.

Separate:

### Outbound
- Flights
- Trains

### Return
- Flights
- Trains

For each option show, where available:

- Price
- Duration
- Departure
- Arrival
- Stops
- Airline/train
- Airport/station
- Recommendation label

The user must select an actual outbound and actual return option before continuing.

---

## 10. Recommendation Logic

Do not ask Gemini to determine objective cheapest/fastest results.

Backend logic should rank using:

- Price
- Duration
- Stops
- Departure/arrival convenience
- User preference

Conceptually:

- Cheapest → heavily weight price
- Fastest → heavily weight duration
- Prefer Flight → preference bonus for flight
- Prefer Train → preference bonus for train
- Best Overall → balanced price/duration/stops/convenience
- No Preference → neutral balanced score

Always show the reason for a recommendation.

---

## 11. Booking

Do **not** implement ticket booking/payment inside Smart Local Guide.

After selection, provide legitimate external links:

- Book Flight
- Book Train
- Book Hotel (provider-supplied hotel/booking-site links from Section 7A)

Rules:

- Never invent URLs.
- Prefer provider-supplied/authorized deep links.
- Otherwise use a legitimate provider search page.
- Clearly indicate the user is leaving the app.
- Do not collect payment information.

---

## 12. Local Itinerary Preferences

After transport selection, continue the existing local preferences.

Preserve existing:

- Budget
- Travellers
- Travel pace
- Local transportation
- Interests
- Food/cuisine
- Café/bakery preferences
- Other existing itinerary settings

Retain interest categories including:

- Beaches
- Adventure
- Desserts
- Nightlife
- Entertainment
- Photography
- Religious
- Family
- Amusement
- Wellness
- Bookstores
- Libraries
- Theatre

---

## 13. Food Preference

Prioritize:

1. Authentic/local/regional food of the destination
2. User-selected cuisine preferences
3. Other suitable options

---

## 14. Geoapify + Gemini

Continue using Geoapify for real local places and Gemini for itinerary reasoning.

Use:

```text
Destination
  ↓
Geoapify real places
  ↓
Backend validation/filtering
  ↓
Gemini
  ↓
Time-aware itinerary
```

Gemini must not invent locations.

---

## 15. Time-Aware Final Itinerary

The final itinerary must use actual selected transport times.

Account for:

- Departure/arrival times
- Journey duration
- Airport/station
- Pre-departure buffer
- Transfer to/from hotel (use the selected hotel's actual location and its check-in/check-out times when a hotel is selected)
- Check-in/check-out
- Local travel time
- Activity duration
- Meal timing
- Return-day departure constraints

Never schedule activities before realistic arrival.

Return day should leave enough time for:

```text
Checkout
→ final activity/meal if practical
→ travel to station/airport
→ pre-departure buffer
→ actual return transport
```

---

## 16. Final Itinerary Content

Combine:

### Journey
- Source/destination
- Outbound transport
- Return transport
- Actual times
- Airports/stations
- Duration
- Transport cost

### Local trip
- Day-by-day schedule
- Activities
- Real places
- Food
- Local transport
- Timings

### Cost summary
Where available:

- Outbound transport
- Return transport
- Accommodation: provider price for the selected hotel (Section 7A) if one was selected; otherwise labeled "not selected"
- Food
- Local transport
- Activities
- Total
- Per-person estimate

Clearly label actual provider prices versus estimates.

---

## 17. Map Selection

For Places Near You and other map services:

When a marker/place is selected:

- Make the selected marker clearly larger/different.
- Use an appropriate selected icon/ring/glow/animation.
- Highlight the matching card.
- Keep all other markers fully visible and usable.
- Do not blur/hide/fade all other markers.
- Optionally pan/center slightly.
- Selecting another marker removes the previous selected state.

---

## 18. Google Maps Directions

Add **Get Directions** to:

- Places Near You
- Quiet Work Cafés
- 24/7 Medical Care

Use actual coordinates/address for the selected destination.

Do not open only the generic Google Maps homepage.

---

## 19. Session Persistence

Current generated results must survive navigation within the active session.

Example:

```text
Generate itinerary
→ Places Near You
→ Generate places
→ Return to itinerary
→ itinerary still visible
```

Same requirement for Area Guide, Quiet Cafés, Medical Care, and Places.

Do not use the same mechanism for temporary session state and permanent History.

---

## 20. Generate New

Every service/result section needs a **Generate New** control.

Behavior:

- Existing current result remains viewable until the user starts a new generation.
- Generate New resets only that service's active input/result state.
- New generation is allowed.
- Previous results remain in persistent History.

---

## 21. History

History must persist across refresh, close, and reopen.

Use structured types such as:

```text
itinerary
places
area_guide
quiet_cafes
medical_care
```

For itineraries retain enough information to reconstruct:

- Source
- Destination
- Dates
- Travellers
- Travel preference
- Outbound selection
- Return selection
- Local preferences
- Generated itinerary
- Cost information
- Relevant transport/place facts
- Timestamp

---

## 22. History → View

History View must reconstruct the original service UI/state, not display raw JSON.

For itinerary history restore:

- Source/destination
- Dates
- Transport selections
- Itinerary
- Places/maps where applicable
- Costs
- PDF capability

For Places history restore:

- Search parameters
- Map
- Markers
- Cards
- Selected place if stored
- Directions/details

Implement service-specific restoration logic using the existing architecture.

---

## 23. PDF Fix

Inspect the existing PDF implementation and fix the current hanging/download issue.

Required flow:

```text
Generate PDF
→ Generating
→ Backend returns actual PDF binary
→ Frontend receives Blob/binary
→ Browser download
→ User receives .pdf
```

On failure:

- Show useful error
- Provide retry

Do not leave the UI stuck on "Generating PDF."

---

## 24. Reviews / Feedback

Add a Reviews section with:

- 1–5 star rating
- Short paragraph/comment

Persist reviews in backend/database.

They must survive refresh and browser reopen.

Do not rely only on localStorage.

Logical API:

```text
POST /api/feedback
GET /api/feedback
```

Adapt to existing backend conventions.

Suggested fields:

```text
id
rating
comment
created_at
service_used (optional)
approved (optional)
```

No login/signup is required unless the existing project already uses authentication.

---

## 25. CAPTCHA

Add CAPTCHA at initial site access for anti-bot/security protection.

Use a current Google reCAPTCHA configuration and follow its current official documentation.

Architecture:

```text
Browser
→ CAPTCHA
→ backend verification
→ application session
```

Requirements:

- Server-side verification
- Secret never exposed in frontend
- Do not require repeated CAPTCHA during normal navigation
- Protect review submission as appropriate
- Handle failed verification clearly

Logical environment placeholders:

```env
RECAPTCHA_SITE_KEY=
RECAPTCHA_SECRET_KEY=
```

Adapt to the chosen current provider/configuration.

---

## 26. Navigation Redesign

Reduce the crowded top navigation.

Main navigation:

- Home
- Itinerary Planner
- Other Services
- History / PDF
- Reviews

Other Services:

- Places Near You
- Area Guide / Area Summarize
- Quiet Work Cafés
- 24/7 Medical Care

Use a dropdown/expandable menu or equivalent clean design.

---

## 27. Homepage Hierarchy

Make the homepage clearly prioritize:

### Main
Itinerary Planner

### Other Services
- Places Near You
- Area Guide
- Quiet Work Cafés
- 24/7 Medical Care

### History / PDF

### Reviews

Preserve existing themes:

- Warm Aesthetic
- Rose Gold
- Sage Green
- Classic Light

---

## 28. State Separation

Separate:

### Temporary session state
- Current itinerary
- Current place search
- Current area guide
- Current café result
- Current medical result
- Current transport search/selection

### Persistent History
- Previous itineraries
- Previous service results
- Timestamps
- Reconstructable state

The exact storage mechanism must be chosen after inspecting the current architecture.

---

## 29. Environment / Security

Keep all secrets server-side.

Logical `.env` variables:

```env
GEMINI_API_KEY=
GEOAPIFY_API_KEY=

SERPAPI_API_KEY=

RAILRADAR_API_KEY=

RECAPTCHA_SITE_KEY=
RECAPTCHA_SECRET_KEY=
```

Ensure:

- `.env` is Git-ignored.
- `.env.example` has placeholders only.
- No secrets in frontend code.
- No secrets in logs.
- No credentials committed to Git.

---

## 30. Error Handling

Handle clearly:

- API unavailable
- Invalid credentials
- Rate limit
- No flights
- No trains
- No hotels
- SerpApi unavailable / invalid key / quota exhausted
- No places
- Invalid source/destination
- Gemini failure
- Geoapify failure
- PDF failure
- CAPTCHA failure

Never silently substitute unrelated-city data.

If mock mode exists, clearly label mock data and prevent accidental live/mock mixing.

---

## 31. Normalized Transport Model

Create/reuse a normalized internal model conceptually:

```text
TransportOption
- id
- mode
- provider
- operator
- number
- origin
- destination
- departure_time
- arrival_time
- duration_minutes
- stops
- price
- currency
- cabin_or_class
- booking_url
- raw_provider_data
```

Flights use `provider = serpapi_google_flights`; trains use `provider = railradar`.

Similarly create/reuse a normalized hotel model:

```text
HotelOption
- id
- provider (serpapi_google_hotels)
- name
- address / area
- latitude, longitude
- star_class
- rating, review_count
- nightly_price, total_price, currency
- check_in_date, check_out_date
- free_cancellation
- amenities
- images
- price_sources  (booking site, price, link)
- booking_url    (provider-supplied only)
- recommendation_labels
- raw_provider_data
```

Adapt to existing architecture.

---

## 32. Implementation Phases

### Phase 1 — Architecture audit
Inspect project, routes, services, state, history, maps, PDF, environment, styling.

### Phase 2 — Transport backend
SerpApi Google Flights, RailRadar, SerpApi Google Hotels, normalized models, comparison/recommendation, caching, errors.

### Phase 3 — New trip flow
Source, destination, dates, travellers, preference, transport page, selections.

### Phase 4 — Local itinerary
Selected transport + local preferences + Geoapify + Gemini + time-aware scheduling.

### Phase 5 — State/history
Session state, persistent History, Generate New, restoration.

### Phase 6 — Existing service improvements
Map selection, Google Maps directions, navigation redesign.

### Phase 7 — PDF/reviews
PDF download and persistent feedback.

### Phase 8 — CAPTCHA/security
Server-verified CAPTCHA and anti-spam.

### Phase 9 — Testing
Automated tests, full-flow manual scenarios and regression testing as defined in Section 33A, with evidence recorded.

---

## 33. Acceptance Criteria

The work is complete only when:

1. Source/destination can be entered.
2. Dates/duration and traveller count work.
3. Travel preference works.
4. Real flight data from SerpApi (Google Flights) can be searched.
5. Real RailRadar train data can be searched.
6. Flights/trains can be compared.
7. Cheapest/Fastest/Best Overall/Prefer Flight/Prefer Train/No Preference recommendations work.
8. Outbound and return can be selected independently.
9. Mixed flight/train trips work.
10. External booking links work without in-app payment.
11. Selected transport appears in the final itinerary.
12. Final itinerary is time-aware.
13. Local results are destination-grounded.
14. Local food is prioritized.
15. Existing local services remain functional.
16. Current results survive navigation within the session.
17. History survives refresh/close/reopen.
18. Generate New works per service.
19. History restores original service state.
20. Selected map marker/card is highlighted while other markers remain usable.
21. Directions use the actual destination.
22. PDF downloads correctly.
23. Reviews persist.
24. CAPTCHA is server-verified.
25. Secrets remain server-side.
26. No unrelated city data appears.
27. Existing visual themes/responsive behavior remain functional.
28. Real hotel data from SerpApi (Google Hotels) can be searched for the selected destination and dates.
29. Hotels can be sorted/filtered (lowest price, rating, stars, free cancellation) and prices compared across booking sites.
30. Selected hotel appears in the final itinerary, cost summary and PDF, with provider prices clearly labeled.
31. Hotel booking links are provider-supplied only; no hotel booking or payment happens in-app.
32. Hotel results never show data for a previous destination.
33. Automated tests from Section 33A are added and passing, the manual scenarios were run, and the final report contains the pass/fail evidence table.

---

## 33A. Test Plan & Verification

Testing is part of the deliverable. Do not report a feature as working unless it was actually run and the observed result was recorded.

### A. Automated tests (extend the existing pytest suite)

Add tests under the existing `backend/tests/` folder, following current naming and fixtures. Do not call live SerpApi/RailRadar from automated tests; use saved sample responses (fixtures) and mocked HTTP so tests are repeatable and do not use paid credits.

1. **Flight parsing:** a saved SerpApi Google Flights response is normalized into `TransportOption` objects with correct airline, flight number, times, airports, duration, stops, price and currency; "best" and "other" lists are merged without duplicates.
2. **Hotel parsing:** a saved SerpApi Google Hotels response is normalized into `HotelOption` objects with correct name, coordinates, rating, nightly/total price and provider-supplied links; property-details response is parsed into booking-site price comparison.
3. **Transport recommendation scoring** with fixed fixtures (for example, one cheap-slow option, one expensive-fast option, one balanced option):
   - Cheapest picks the lowest price.
   - Fastest picks the shortest duration.
   - Prefer Flight / Prefer Train favour that mode when scores are otherwise close.
   - Best Overall and No Preference pick the balanced option.
   - Every recommendation includes a non-empty reason.
4. **Hotel labels/sorting:** Cheapest, Best Rated and Best Value labels and the sort orders are computed correctly on fixed fixtures.
5. **Validation:** invalid, empty, identical source/destination, past dates, return before departure, and traveller counts outside the allowed range are rejected with clear errors.
6. **Error mapping:** simulated missing key, invalid key, rate limit/quota exhausted, timeout, empty results and malformed provider response each produce a clear, distinct error and never fall back to unrelated data.
7. **Grounding:** changing the destination clears destination-specific results; a response for one destination is never returned for another.
8. **Booking links:** `booking_url` values come only from provider data; when absent they are `null`/hidden, never constructed.
9. **CAPTCHA:** requests with a missing/invalid token are rejected server-side; a valid token passes (verification call mocked).
10. **Regression:** the existing test suite still passes unchanged.

### B. Manual / end-to-end scenarios (run the real app)

Run the app with real keys and record what was actually observed.

| # | Scenario | Expected result |
|---|---|---|
| 1 | Full journey: Delhi → Amritsar, outbound flight, return train, one hotel, local itinerary | Every step completes; the itinerary uses the selected transport's real times, hotel and destination places; PDF and History work |
| 2 | Destination switch: finish the scenario above, then plan Mumbai → Goa without refreshing | No Amritsar places, transport or hotels appear anywhere |
| 3 | Back-to-back same-source trips to two different destinations | Each result set matches only its own destination |
| 4 | Flight-only search | Flights listed with airline, number, times, duration, stops, price |
| 5 | Train-only search on an Indian rail route | Trains listed with provider data; clear message if the provider has no data |
| 6 | Mixed trip: outbound flight + return train, then outbound train + return flight | Both selections stored independently; both appear in the itinerary and cost summary |
| 7 | All six travel preferences on the same search | Recommendation changes appropriately and always shows a reason |
| 8 | Hotel search with sort Lowest price, then Highest rating | Order changes correctly; cheapest hotel is labeled; prices match provider data |
| 9 | Open one hotel's details | Booking-site price comparison appears; outbound link is the provider-supplied one |
| 10 | Skip hotel selection | Itinerary completes; accommodation shows "not selected" |
| 11 | City with no commercial airport (choose one and verify) | Clear message; trains remain available; no invented airport code |
| 12 | Unknown/misspelled destination (for example, "Xyzzyville") | Clear validation error; nothing from a previous trip is shown |
| 13 | Same source and destination; return date before departure | Rejected with clear messages |
| 14 | Remove/invalidate `SERPAPI_API_KEY`, then search | Clear configuration/credentials error; no fake data |
| 15 | Navigate away from a result and come back | Active session result is still there |
| 16 | Refresh and reopen the browser | History persists; opening a History item restores the original service UI/state |
| 17 | Generate New on each service | Only that service resets; other services and History are untouched |
| 18 | Click map markers and cards (places, cafés, medical, hotels) | Selected marker/card is highlighted; other markers remain clickable |
| 19 | Directions | Google Maps opens with the actual selected destination |
| 20 | PDF download after a full trip | File downloads, opens, and includes transport, hotel and itinerary with provider prices labeled |
| 21 | Submit and reload reviews | Review persists after restart |
| 22 | CAPTCHA: valid and invalid submission | Invalid is rejected by the server; valid passes |
| 23 | Existing services: Places, Cafés, Medical, Area Guide | Still work as before |
| 24 | All 5 themes; desktop, tablet and mobile widths | No layout breakage |

### C. Evidence required in the final report

Include a table with one row per automated test group and per manual scenario above: status (Pass / Fail / Not run), what was actually observed, and any fix made. Scenarios that could not be run (for example, no RailRadar access) must be listed as "Not run" with the reason; do not mark them as passed. Include the pytest summary line (passed/failed counts). Fix failures and re-run instead of only reporting them.

---

## 34. Final Implementation Instruction

**Inspect first. Implement second.**

This specification describes desired behavior; it is not permission to rewrite the project from scratch.

Use the existing architecture and naming where practical. Do not invent nonexistent files/endpoints. Do not create a parallel app. Do not remove working features unnecessarily. Do not fabricate transport/place information.

After implementation, run the app and test the complete user journey and regression checklist.
