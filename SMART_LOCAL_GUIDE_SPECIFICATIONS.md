# Smart Local Guide — From-Scratch Web Application Specification

## 1. Project Overview

**Project name:** Smart Local Guide

**Goal:** Rebuild the existing Streamlit-based Smart Local Guide as a proper full-stack web application from scratch, starting with a clean raw frontend and backend structure. The first milestone is a polished, functional-looking web application with all major pages, components, responsive UI, and clear API boundaries. Real AI/search/API integrations should be added after the raw project is stable.

**Primary use case:** Help a user discover places, understand an area, build an itinerary, find work-friendly cafés, and locate medical services using AI-assisted local information.

**Important development approach:**
1. Create the complete project structure from scratch.
2. Build the frontend using HTML/CSS/JavaScript rather than Streamlit.
3. Build the backend as a clean API layer.
4. Initially use mock/sample data where necessary so the complete UI can be tested without API keys.
5. After the raw project works, integrate real search/place/AI APIs one by one.
6. Keep integrations modular so changing an AI provider or place-search provider does not require rewriting the UI.

---

# 2. Existing Feature Set to Preserve

The new application should retain the conceptual feature set of the current project:

1. **Itinerary Planner**
2. **Places Near You**
3. **Area Summarizer**
4. **Quiet Work Cafés**
5. **24/7 Medical Care**
6. Search/source-aware results
7. Separate history for the different features
8. PDF export
9. Audio/TTS support
10. Responsive modern interface
11. Theme support
12. Safe handling of API keys through environment variables

The current Streamlit implementation uses AI generation, DuckDuckGo web search, PDF generation, gTTS, and session-based history. These are implementation details of the old version, not requirements that the new architecture must copy exactly.

---

# 3. Recommended Technology Stack

## Frontend

Use:

- HTML5
- CSS3
- Vanilla JavaScript (ES6+)
- Fetch API
- CSS Grid and Flexbox
- Google Fonts or another lightweight web font
- SVG icons or an icon library if needed
- MapLibre GL JS (loaded from a CDN, no API key) for the interactive map used on Places, Cafés and Medical (see Section 50)

Do NOT use Streamlit.

Do not introduce React/Vue/Angular unless explicitly requested later. The goal of this version is to keep the architecture understandable and easy to explain.

## Backend

Recommended:

- Python
- FastAPI
- Uvicorn
- Pydantic models
- Modular service architecture

The backend should expose REST-style JSON APIs.

## Future integrations

Keep adapters/interfaces ready for:

- AI provider
- Places/search provider
- Geocoding
- Maps
- PDF generation
- Text-to-speech
- Persistent database

Do not hard-code one provider throughout the project.

---

# 4. Project Architecture

Create a structure similar to:

smart-local-guide/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models/
│   │   │   ├── itinerary.py
│   │   │   ├── places.py
│   │   │   ├── area.py
│   │   │   ├── cafes.py
│   │   │   ├── medical.py
│   │   │   └── history.py
│   │   ├── routes/
│   │   │   ├── itinerary.py
│   │   │   ├── places.py
│   │   │   ├── area.py
│   │   │   ├── cafes.py
│   │   │   ├── medical.py
│   │   │   ├── history.py
│   │   │   └── health.py
│   │   ├── services/
│   │   │   ├── ai_service.py
│   │   │   ├── places_service.py
│   │   │   ├── search_service.py
│   │   │   ├── geocoding_service.py
│   │   │   ├── pdf_service.py
│   │   │   └── tts_service.py
│   │   └── utils/
│   │       ├── validation.py
│   │       └── helpers.py
│   │
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── index.html
│   ├── pages/
│   │   ├── itinerary.html
│   │   ├── places.html
│   │   ├── area.html
│   │   ├── cafes.html
│   │   ├── medical.html
│   │   └── history.html
│   ├── css/
│   │   ├── style.css
│   │   ├── variables.css
│   │   ├── components.css
│   │   ├── pages.css
│   │   └── responsive.css
│   ├── js/
│   │   ├── app.js
│   │   ├── api.js
│   │   ├── state.js
│   │   ├── ui.js
│   │   ├── components/
│   │   │   ├── navbar.js
│   │   │   ├── sidebar.js
│   │   │   ├── modal.js
│   │   │   ├── toast.js
│   │   │   ├── loader.js
│   │   │   ├── cards.js
│   │   │   └── history.js
│   │   └── pages/
│   │       ├── itinerary.js
│   │       ├── places.js
│   │       ├── area.js
│   │       ├── cafes.js
│   │       └── medical.js
│   └── assets/
│       ├── images/
│       └── icons/
│
├── data/
│   └── mock/
│       ├── places.json
│       ├── itinerary.json
│       ├── area.json
│       ├── cafes.json
│       └── medical.json
│
├── .gitignore
├── README.md
└── run.py

The exact structure may be adjusted if Antigravity has a cleaner equivalent, but separation between frontend, backend, services, routes, and static assets must be maintained.

## Additional files required for the map and card experience (Section 50)

Add these to the structure above:

- `backend/app/models/route.py`
- `backend/app/routes/route.py`
- `backend/app/services/routing_service.py`
- `backend/app/utils/geo.py` (haversine distance, coordinate validation)
- `frontend/js/config.js` (public, non-secret settings only, such as the map style URLs and default zoom)
- `frontend/js/components/map.js` (reusable MapLibre component)
- `frontend/js/components/filter-chips.js` (category / amenity / service-type chips with counts)
- `frontend/js/components/nearby-explorer.js` (shared controller that keeps cards, markers, filters and selection in sync for Places, Cafés and Medical)
- `frontend/js/utils/geo.js` (distance formatting and map bounds helpers only; distances themselves are calculated by the backend)
- `frontend/css/map.css`
- `data/mock/locations.json` (mock geocoding: known location names with centre coordinates)
- backend tests folder `backend/tests/` (see Section 43)

---

# 5. Global UI/UX Direction

The application should look like a modern travel/local-discovery product rather than an academic demo.

## Visual personality

Desired feeling:

- modern
- premium but approachable
- clean
- calm
- travel-oriented
- intelligent
- practical
- trustworthy
- visually rich without becoming cluttered

Avoid:

- generic Bootstrap-looking pages
- excessive gradients
- excessive glassmorphism
- huge empty areas
- tiny text
- overly rounded cartoon-style cards
- excessive animations
- visually noisy dashboards

## 5.1 Primary Color Palette

Use a warm travel-inspired palette as the default visual identity.

### Primary — Deep Teal

```text
Primary:        #0F766E
Primary Hover:  #0B5F59
Primary Light:  #CCFBF1
```

Use for:

- primary buttons
- active navigation
- selected filters
- links
- important interactive elements
- primary icons

### Secondary — Warm Sand

```text
Secondary:      #F4E7D3
Secondary Dark: #E8D2B3
```

Use for:

- subtle backgrounds
- feature highlights
- travel-themed sections
- secondary visual accents

### Accent — Coral

```text
Accent:         #E76F51
Accent Hover:   #D85D42
Accent Light:   #FDE3DC
```

Use sparingly for:

- important calls to action
- selected/highlighted information
- special badges
- visual emphasis

Do not use the accent color for every button.

### Background

```text
Background:     #FAF9F6
Surface:        #FFFFFF
Surface Soft:   #F5F7F6
```

The overall application should feel light and spacious.

### Text

```text
Text Primary:   #1F2937
Text Secondary: #4B5563
Text Muted:     #6B7280
Text Inverse:   #FFFFFF
```

Use `Text Primary` for headings and important information.

Use `Text Secondary` for normal descriptions.

Use `Text Muted` for metadata and less-important information.

### Borders

```text
Border:         #E5E7EB
Border Strong:  #D1D5DB
```

Keep borders subtle.

### Status Colors

```text
Success:        #15803D
Success Light:  #DCFCE7

Warning:        #D97706
Warning Light:  #FEF3C7

Danger:         #DC2626
Danger Light:   #FEE2E2

Info:           #2563EB
Info Light:     #DBEAFE
```

Use status colors only for actual status information. Do not use them purely as decoration.

---

## 5.2 Dark Theme Palette

The dark theme should not simply invert every color.

Use:

```text
Dark Background:       #111827
Dark Surface:          #1F2937
Dark Surface Soft:     #273449
Dark Border:           #374151

Dark Text Primary:     #F9FAFB
Dark Text Secondary:   #D1D5DB
Dark Text Muted:       #9CA3AF

Dark Primary:          #2DD4BF
Dark Primary Hover:    #14B8A6

Dark Accent:           #FB8B6B
```

Maintain readable contrast.

Avoid pure black backgrounds.

---

## 5.3 Theme Variations

Provide these selectable themes:

### Warm Aesthetic
Primary:
`#0F766E`

Accent:
`#E76F51`

Background:
`#FAF9F6`

### Rose Gold
Primary:
`#9F5F68`

Accent:
`#D89A9E`

Background:
`#FFF9F8`

### Sage Green
Primary:
`#587A63`

Accent:
`#A3B18A`

Background:
`#F7F8F3`

### Classic Light
Primary:
`#2563EB`

Accent:
`#F59E0B`

Background:
`#F8FAFC`

### Dark Theme
Use the dedicated dark palette defined above.

All themes must use the same component structure. Only CSS variables should change.

---

## 5.4 CSS Design Tokens

Create CSS variables instead of hard-coding colors throughout the project.

Example:

```css
:root {
  --color-primary: #0F766E;
  --color-primary-hover: #0B5F59;
  --color-primary-light: #CCFBF1;

  --color-secondary: #F4E7D3;

  --color-accent: #E76F51;
  --color-accent-hover: #D85D42;

  --color-background: #FAF9F6;
  --color-surface: #FFFFFF;
  --color-surface-soft: #F5F7F6;

  --color-text-primary: #1F2937;
  --color-text-secondary: #4B5563;
  --color-text-muted: #6B7280;
  --color-text-inverse: #FFFFFF;

  --color-border: #E5E7EB;
  --color-border-strong: #D1D5DB;

  --color-success: #15803D;
  --color-warning: #D97706;
  --color-danger: #DC2626;
  --color-info: #2563EB;

  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 18px;
  --radius-xl: 24px;

  --shadow-sm: 0 2px 8px rgba(15, 23, 42, 0.06);
  --shadow-md: 0 8px 24px rgba(15, 23, 42, 0.08);
  --shadow-lg: 0 16px 40px rgba(15, 23, 42, 0.12);
}
```

Do not use shadows everywhere. Use them to establish hierarchy.

---

## 5.5 Typography

Use a modern, highly readable font.

Recommended:

- Inter
- Manrope
- DM Sans

Suggested hierarchy:

```text
Hero heading:     48–64px desktop
Page heading:     32–42px
Section heading:   24–30px
Card heading:      17–20px
Body:              15–17px
Metadata:          13–14px
```

On mobile, reduce heading sizes responsively.

Use appropriate line-height, especially for AI-generated text.

---

## 5.6 Spacing System

Use a consistent spacing scale based around:

```text
4px
8px
12px
16px
24px
32px
48px
64px
80px
```

Do not use arbitrary spacing values throughout the application.

---

## 5.7 Buttons

### Primary button

- Deep Teal background
- White text
- subtle hover transition
- medium radius
- clear focus state

### Secondary button

- white/surface background
- teal text
- subtle border

### Accent button

Use Coral only for actions that need special visual emphasis.

Do not make every CTA coral.

Buttons should have:

- hover
- active
- disabled
- focus states

---

## 5.8 Cards

Cards should use:

- white/surface background
- subtle border
- small-to-medium shadow
- 12–18px radius
- consistent internal padding

Use larger cards for major feature sections and smaller cards for search results.

Avoid excessive card nesting.

---

## 5.9 Icons

Use one consistent icon style throughout the application.

Recommended:

- Lucide Icons
- Font Awesome
- inline SVG icons

Avoid mixing multiple visual icon styles.

Icons should support the text rather than replace it.

---

## 5.10 Forms

Inputs should have:

- visible labels
- white/surface background
- subtle border
- 10–12px radius
- clear focus ring using the primary color
- readable placeholder text

Focus example:

```text
border: #0F766E
box-shadow: 0 0 0 3px #CCFBF1
```

Do not use placeholder text as the only field label.

---

## 5.11 UI Hierarchy

Use color intentionally:

- Primary teal = main interaction
- Coral = limited emphasis
- Sand = warm supporting background
- Neutral colors = most of the interface
- Status colors = actual status only

The majority of the screen should remain neutral so that important actions stand out.

---

## 5.12 Responsive UI

Desktop:

- spacious layout
- multi-column cards
- two-column forms where appropriate

Tablet:

- reduced grid columns
- comfortable spacing

Mobile:

- single-column layout
- stacked cards
- full-width important buttons
- hamburger navigation
- touch-friendly controls

Avoid horizontal scrolling.

---

## 5.13 Motion

Use subtle transitions:

- 150–250ms
- ease-out/ease-in-out

Use animations for:

- hover
- page entry
- loading
- modal transitions
- skeletons

Respect:

```css
@media (prefers-reduced-motion: reduce)
```

Do not use distracting continuous animations.

---

# 6. Main Navigation

Desktop navigation should contain:

- Logo: Smart Local Guide
- Home
- Itinerary
- Places
- Area Guide
- Work Cafés
- Medical Care
- History

Include:

- theme toggle
- mobile menu button
- optional location indicator
- primary CTA such as "Plan a Trip"

The navbar should remain visually consistent throughout the application.

---

# 7. Landing / Home Page

Create an attractive homepage.

## Hero section

Headline:

"Explore smarter. Travel better."

Supporting text should explain that Smart Local Guide helps users discover places, plan itineraries, understand neighborhoods, find work-friendly cafés, and locate medical services.

Primary CTA:

"Plan Your Trip"

Secondary CTA:

"Explore Places"

## Visual

Use a travel/local discovery visual such as:

- city map
- destination photograph
- map pins
- subtle geographic pattern

Do not depend on external images during the raw build. Use a local placeholder or CSS/SVG illustration.

## Feature cards

Show five main feature cards:

1. AI Itinerary Planner
2. Places Near You
3. Area Guide
4. Quiet Work Cafés
5. 24/7 Medical Care

Each card should have:

- icon
- title
- short description
- action

## How it works

Three or four steps:

1. Tell us what you need
2. Search and understand the area
3. Get an organized recommendation
4. Save/export your result

## Trust section

Explain:

- source-aware results
- no unnecessary invented facts
- clear uncertainty
- practical recommendations

---

# 8. Itinerary Planner

## Purpose

Allow users to create a personalized multi-day itinerary.

## Form fields

Include:

- City / destination
- Neighborhood or area (optional)
- Number of days
- Budget
- Search radius
- Interests
- Food preference
- Cuisine preferences
- Bakery/café preferences
- Group type
- Travel pace
- Transportation
- Additional preferences

## Interests

Support options such as:

- History
- Art & museums
- Parks & nature
- Beaches
- Adventure
- Shopping
- Food
- Cafés
- Nightlife
- Music
- Movies & entertainment
- Photography
- Architecture
- Religious places
- Family
- Amusement parks
- Scenic locations
- Wellness
- Sports
- Bookstores/libraries
- Theatre
- Work-friendly
- Hidden gems

## UI

Use:

- structured form sections
- chips or multi-select controls
- budget slider/input
- day selector
- clear Generate button

Do not make the form feel like a long government form.

Use collapsible "More preferences" for secondary options.

## Result

Display:

- trip overview
- total estimated budget
- day-by-day sections
- morning
- afternoon
- evening
- recommended places
- food stops
- transportation notes
- approximate spending
- source links

Each place should appear as a card.

## Important accuracy rule

The interface must distinguish:

- verified/source information
- AI-generated planning suggestions
- approximate information

Do not present uncertain information as an exact fact.

---

# 9. Places Near You

## Purpose

Discover useful places around a location.

## Input

- location/search area
- category selection
- number of results per category

## Categories

- Restaurants
- Cafés
- Bakeries
- Hotels
- Tourist spots
- Shopping
- Hospitals
- Pharmacies
- ATMs
- Cultural landmarks
- Parks/nature
- Entertainment
- Bookstores
- Hidden gems
- Museums
- Public transport
- Events

## Result design

Results are shown as a **responsive grid of rich place cards together with an interactive map** that plots every result. The full layout, card anatomy, map behaviour, category filtering and route highlighting are defined in **Section 50** and are mandatory for this page.

Each card must support:

- place name
- category (with icon)
- distance from the current location / search centre (calculated by the backend, shown only when available)
- rating with review count when supplied by a real source, otherwise the muted text "Rating unavailable"
- description of 2–3 lines
- address/location when verified
- website ("Visit Website →") only when the URL passed backend validation
- phone number only when supplied by the source
- source
- selection behaviour: clicking a card highlights the place and its route on the map

Above the cards, show the interactive map with a highlighted current-location / search-centre marker and one marker for each visible result. Category chips (with a Radius selector) filter the cards and the map markers together.

## Critical requirement

Do NOT display unnamed or low-information places as normal recommendations.

A place should have a meaningful name before being shown as a recommendation.

If a source has no usable name:

- filter it out, or
- place it into an internal debug/logging state rather than showing it to the user.

Do not invent names.

This requirement should be enforced in backend validation, not only through frontend filtering.

---

# 10. Area Guide / Area Summarizer

## Purpose

Give a practical overview of a neighborhood or area.

## Input

- area
- radius

## Result sections

1. Overall character
2. Food
3. Cafés
4. Shopping
5. Hospitals/pharmacies
6. ATMs
7. Attractions
8. Parks
9. Public transport
10. Advantages
11. Limitations
12. Who the area may suit

## UI

Use a dashboard-style layout with:

- summary hero
- category cards
- map area placeholder
- useful-place cards
- quick facts

Avoid presenting unsupported exact distances/hours.

If actual geographic data becomes available later, show verified distances.

---

# 11. Quiet Work Cafés

## Purpose

Help users find cafés suitable for studying or working.

## Filters

- Wi-Fi
- Charging
- Quiet environment
- Good seating
- AC
- Outdoor seating
- Good coffee
- Desserts
- Long working hours
- Budget-friendly

## Cards

Each café card should show:

- name
- rating when supplied by a real source, otherwise "Rating unavailable"
- description of 2–3 lines
- supported amenities
- location and distance (distance only when calculated)
- source
- website (only when validated) and phone (only when supplied)

The Quiet Work Cafés page must also show the **same interactive map and card-to-map behaviour as Places Near You** (Section 50): all results as markers, the current location / search centre highlighted, amenity filters that add or remove both cards and markers, and route highlighting when a card is clicked.

Only display an amenity when supported by data/source.

Do not invent Wi-Fi, charging, opening hours, or other amenities.

---

# 12. 24/7 Medical Care

## Purpose

Help users find medical services, especially urgent or late-night options.

## Service types

- 24/7 hospitals
- Emergency departments
- Urgent care
- Late-night pharmacies
- Clinics
- Diagnostic centers

## Medical UI requirements

This page should have a more serious visual tone.

Use:

- clear red/danger status indicators only where appropriate
- emergency information box
- service type labels
- source information
- location information
- 24/7 status only when verified

Do not invent:

- phone numbers
- opening hours
- 24/7 status
- emergency services

Include a visible reminder that emergency situations should be handled through local emergency services rather than relying solely on the application.

## Medical cards and map

The 24/7 Medical Care page must also show the **same interactive map and card-to-map behaviour as Places Near You** (Section 50):

- all results as markers, with the current location / search centre highlighted
- service-type filters that add or remove both cards and markers
- clicking a card (or marker) highlights that facility and draws the route to it, with walking/driving options
- a "24/7" badge (icon plus text) only when the 24/7 status is verified by data
- phone numbers only when supplied by the source
- the emergency reminder above stays visible near the map and results

Use the same serious visual tone as the rest of this page. Do not use red for map markers just for decoration.

---

# 13. History

## Purpose

Allow users to review previous generated results.

Categories:

- Itinerary
- Places
- Area
- Cafés
- Medical

## History card

Each entry should include:

- feature type
- title
- date/time
- short preview
- View
- Export PDF
- Audio where supported
- Delete

For the initial raw build, history can use local/session storage or mock data.

Later it can be moved to SQLite/PostgreSQL.

---

# 14. Result Cards

Create a reusable result-card component.

Possible elements:

- image/placeholder
- category badge
- place name
- description
- location
- distance
- rating only if supplied by a real source (otherwise the muted text "Rating unavailable", see Section 50.2)
- phone number only if supplied by a real source
- source
- website
- map button
- save button

Do not display fake ratings.

Do not display fake reviews.

Do not display fake prices.

If data is unavailable, hide the field rather than showing invented information. The one exception is the rating on Places, Cafés and Medical cards, which shows the muted text "Rating unavailable" so cards stay aligned and the user knows it is missing, not zero.

---

# 15. Search and Source UX

Every externally sourced recommendation should be traceable to a source.

Use a small "Source" area in cards.

Example:

Source: Web result

Website: View source

Later this can be replaced with:

Source: Geoapify / Google Places / OpenStreetMap / official website

Do not make source URLs visually dominant.

---

# 16. Loading States

Every API action needs a proper loading state.

Examples:

- skeleton cards
- animated spinner
- "Finding places..."
- "Building your itinerary..."
- "Analyzing the area..."

Do not freeze the page.

Disable duplicate submissions while an operation is running.

---

# 17. Empty States

Create reusable empty states.

Examples:

"No places found"

"No history yet"

"Enter a destination to start planning"

"Try a larger search area"

Each empty state should explain the next action.

---

# 18. Error Handling

Errors should be human-readable.

Never expose raw Python stack traces to the user.

Example:

Instead of:

`500 Internal Server Error`

show:

"We couldn't complete this search right now. Please try again."

For developers, keep detailed errors in backend logs.

---

# 19. Responsive Design

The application must work on:

- desktop
- laptop
- tablet
- mobile

Desktop:

- sidebar or full navbar
- multi-column cards
- two-column forms where appropriate

Tablet:

- reduced columns

Mobile:

- single column
- hamburger navigation
- full-width forms
- cards stacked
- sticky/floating primary action only if useful

Avoid horizontal scrolling.

---

# 20. Accessibility

Follow basic WCAG-friendly practices:

- semantic HTML
- labels for inputs
- keyboard navigation
- visible focus states
- sufficient contrast
- alt text for images
- buttons should have understandable labels
- do not rely only on color to communicate status

---

# 21. Themes

Implement a theme system using CSS variables.

Initial themes:

1. Warm Aesthetic
2. Rose Gold
3. Sage Green
4. Classic Light
5. Dark

The theme selector should modify CSS variables rather than duplicating styles.

Store selected theme locally.

---

# 22. Animations

Use subtle animations only.

Recommended:

- card hover
- page fade-in
- button feedback
- modal transition
- skeleton shimmer

Avoid:

- excessive bouncing
- constant movement
- distracting background animation

Respect reduced-motion preferences.

---

# 23. Backend API Design

Create clean endpoints.

## Health

GET `/api/health`

Response:

```json
{
  "status": "ok",
  "service": "smart-local-guide"
}
```

## Itinerary

POST `/api/itinerary/generate`

Input includes destination, days, budget, interests, food preferences, pace, transport, radius, etc.

## Places

POST `/api/places/search`

Input:

- location (text) **or** coordinates from the browser ("Use my location")
- categories
- result count
- radius

Response: the envelope defined in Section 50.7 (centre, radius, counts per category, and places with distance, rating, website and phone only when validated).

## Area

POST `/api/area/summarize`

Input:

- area
- radius

## Cafés

POST `/api/cafes/search`

Input:

- location (text) or coordinates
- amenities
- radius

Response: the same envelope as places, plus supported amenities for each café.

## Medical

POST `/api/medical/search`

Input:

- location (text) or coordinates
- service types
- radius

Response: the same envelope as places, plus service type, verified 24/7 status and phone where supplied.

## Route

POST `/api/route`

Input:

- origin (latitude, longitude)
- destination (latitude, longitude)
- mode (`walking` or `driving`)

Response: route geometry (GeoJSON LineString), distance, duration, mode, provider and an `is_approximate` flag. If no real route can be obtained, return a straight-line fallback clearly flagged as approximate (see Section 50.7).

## History

GET `/api/history`

POST `/api/history`

DELETE `/api/history/{id}`

## Export

POST `/api/export/pdf`

## Audio

POST `/api/export/audio`

These are proposed contracts. They can be refined during implementation, but frontend and backend must communicate through stable JSON schemas.

---

# 24. Service Layer

Keep provider-specific logic out of route files.

Example:

Route:
`POST /api/places/search`

should call:

`places_service.search_places(...)`

rather than directly calling an external API.

Similarly:

`ai_service.generate(...)`

`search_service.search(...)`

`geocoding_service.geocode(...)`

`pdf_service.create_pdf(...)`

`tts_service.create_audio(...)`

This will make future provider changes easy.

---

# 25. AI Service

Create a provider-independent interface.

Example conceptual interface:

```python
class AIService:
    async def generate(self, prompt: str, context: dict) -> str:
        ...
```

The application should be able to switch AI providers by changing configuration rather than rewriting every feature.

Potential future providers:

- Google Gemini
- Groq
- OpenAI-compatible providers
- Ollama Cloud
- another provider later

Do not hard-code provider calls into page logic.

---

# 26. Places/Search Service

Create a provider-independent place/search interface.

Possible future providers:

- Geoapify
- Google Places
- OpenStreetMap
- Mapbox
- another search provider

The service should normalize results into a common format.

Example:

```json
{
  "id": "stable-unique-id",
  "name": "Example Place",
  "category": "cafe",
  "description": "Two to three sentences built only from supplied data",
  "description_source": "provider",
  "address": "Verified address if available",
  "latitude": 0,
  "longitude": 0,
  "distance_m": 0,
  "rating": null,
  "rating_count": null,
  "rating_source": null,
  "website": "https://example.com",
  "phone": null,
  "source": "provider"
}
```

Distances are expressed in metres (`distance_m`) so short distances can be shown as "119 m". See Section 50.7 for the full response envelope.

All optional fields should be nullable.

---

# 27. Place Validation

Implement backend validation.

Rules:

1. Place name is required.
2. Empty/placeholder/meaningless names are rejected.
3. Duplicate places should be removed.
4. URLs should be validated where possible.
5. Unsupported data should not be fabricated.
6. Ratings/reviews should only appear when supplied by a source.
7. Distance should only appear when calculated from coordinates.
8. Opening hours should only appear when supplied by a reliable source.
9. Websites must be absolute http/https URLs that pass validation (and the optional reachability check); otherwise the website is returned as `null`. See Section 50.7.
10. A rating must be between 0 and 5 and must have a rating source; otherwise rating fields are `null`. A missing rating is never turned into 0.
11. Coordinates must be valid (latitude -90 to 90, longitude -180 to 180). Only places with valid coordinates may appear on the map, and coordinates are never guessed.
12. Descriptions must be 2–3 sentences, grounded in supplied data, and labelled with a `description_source`.
13. Phone numbers are shown only when supplied by a source.

This is especially important because the current project can receive unnamed search results.

---

# 28. Geolocation

The raw build should support manual location entry **and** a "Use my location" button (browser geolocation with explicit user permission) on Places, Cafés and Medical, because the map highlights the current location. See Section 50.6.

Possible flow:

1. User clicks "Use my location"
2. Browser asks permission
3. Coordinates are received
4. Backend reverse-geocodes coordinates
5. Nearby search uses coordinates

Never silently collect location.

Clearly communicate why location permission is requested.

---

# 29. Maps

An interactive map is **part of the first build** for Places Near You, Quiet Work Cafés and 24/7 Medical Care. The complete requirements (library, basemap, markers, current-location highlight, category sync, route highlighting, fallbacks, accessibility) are in **Section 50**.

Summary:

- Use MapLibre GL JS with a keyless OpenStreetMap-based basemap. No API key is required for the first version.
- Build one reusable map component and use it on all three pages.
- Map markers must come from verified/validated coordinates only.
- The Area Guide keeps its map placeholder for now.
- The map provider must be replaceable later (Leaflet, Mapbox, Google Maps or another provider) through `frontend/js/config.js` and the map component, without changing page logic.

---

# 30. PDF Export

PDF export should be handled server-side.

The generated PDF should contain:

- application name
- result title
- generated date
- user inputs
- result content
- source information

Use a Unicode-capable font.

Avoid the old Helvetica Unicode problem.

---

# 31. Audio / Text-to-Speech

Keep TTS separate from the UI.

The UI should simply request:

`POST /api/export/audio`

The backend returns an audio file or URL.

The frontend should provide:

- Play
- Pause
- Stop
- Download if appropriate

TTS provider can be changed later.

---

# 32. Security

Never put API keys inside:

- HTML
- CSS
- JavaScript
- GitHub repository
- client-side requests

Keys belong in `.env`.

Use `.env.example` containing placeholders.

Example:

```env
AI_API_KEY=
PLACES_API_KEY=
SEARCH_API_KEY=
```

The backend communicates with external services.

The browser should never receive private API keys.

Add `.env` to `.gitignore`.

---

# 33. Configuration

Centralize configuration.

Example:

```python
class Settings:
    AI_API_KEY: str
    AI_MODEL: str
    PLACES_API_KEY: str | None
    SEARCH_API_KEY: str | None
```

Do not scatter environment-variable access across many files.

---

# 34. Mock Data Requirement

Before connecting real APIs, the project must work using mock data.

Create realistic mock JSON for:

- places
- itinerary
- area summary
- cafés
- medical results

The frontend must be testable without API keys.

For the map and card experience the mock data must also:

- include valid latitude/longitude for every place, consistent with the mock search centre, so the backend can calculate real haversine distances
- include at least one fully populated mock location with a good spread of results (for example 25 or more places across at least five categories, plus enough cafés and medical facilities to demonstrate the map and filters)
- include a mix of entries with and without rating, website and phone, so both the "Rating unavailable" state and the hidden-field states are visible
- include at least one place with no coordinates (card shown, no marker) and one with an invalid website (link hidden), to prove the validation
- use `"source": "sample-data"`, and the API must return `"data_mode": "mock"` so the UI shows the sample-data banner
- provide `data/mock/locations.json` for mock geocoding (several known locations with centre coordinates)

Include enough data to demonstrate:

- multiple categories
- cards
- filters
- empty states
- loading
- errors
- history

---

# 35. Data Flow

## Itinerary

Frontend form
→ API request
→ backend validation
→ search/place service
→ AI service
→ normalized result
→ frontend result cards
→ optional history
→ PDF/audio

## Places

Location + categories
→ backend
→ search/place provider
→ normalize
→ validate
→ remove unnamed/duplicates
→ validate coordinates, websites, ratings
→ calculate distances from the centre
→ return JSON
→ frontend cards + map markers
→ on selection: route request → highlighted route on map

## Area

Area + radius
→ geocoding/search
→ category searches
→ normalize
→ AI summary
→ frontend dashboard

## Cafés

Location + amenities
→ search/place provider
→ normalize
→ verify amenities
→ validate coordinates, websites, ratings
→ calculate distances from the centre
→ frontend cards + map markers + route on selection

## Medical

Location + service type
→ search
→ normalize
→ verify emergency/24-7 claims
→ validate coordinates, websites, phone numbers
→ calculate distances from the centre
→ frontend cards + map markers + route on selection + safety notice

---

# 36. UI Components to Build

Reusable components:

- Navbar
- Sidebar
- Footer
- Hero
- Button
- Input
- Select
- Multi-select
- Checkbox
- Radio
- Slider
- Search bar
- Feature card
- Place card
- Result card
- Category badge
- Filter panel
- Modal
- Toast
- Alert
- Loading spinner
- Skeleton
- Empty state
- Error state
- History item
- Source badge
- Map placeholder (Area Guide)
- Interactive map (MapLibre) with markers, legend and controls
- Category / amenity / service-type filter chips with counts
- Radius selector
- Route summary panel (walking/driving toggle, directions link)
- "Use my location" button
- Audio player
- PDF export button
- Theme selector

---

# 37. Form UX

Forms must:

- use labels
- have sensible defaults
- validate required inputs
- show inline validation
- preserve entered values when possible
- prevent accidental duplicate submissions
- clearly identify required fields
- use helpful placeholder examples

Example:

Destination:
`e.g. Delhi, Mumbai, Jaipur`

Do not use placeholder text as the only label.

---

# 38. Dashboard / Result UX

Results should not look like raw JSON.

Use:

- headings
- cards
- badges
- sections
- icons
- source links
- expandable details

Long AI responses should be structured into readable sections.

Do not dump a large paragraph onto the screen.

---

# 39. History UX

History should feel like a real product feature.

Provide:

- search/filter history
- feature filter
- date
- preview
- open
- delete
- export

Initially use browser/local storage or in-memory backend state.

Later move to a database.

---

# 40. Database Plan

Do not make a database mandatory for the raw prototype.

Prepare architecture for:

SQLite initially.

Potential tables:

- users
- history
- saved_places
- searches
- generated_itineraries

Later PostgreSQL can replace SQLite.

---

# 41. Performance

Use:

- async FastAPI endpoints where appropriate
- loading states
- minimal frontend dependencies
- lazy loading for images
- caching for repeated search requests where appropriate
- normalized response structures

Do not block the UI unnecessarily.

---

# 42. Logging

Backend should log:

- API requests
- external provider failures
- validation failures
- provider response errors

Do not log:

- API keys
- sensitive user data unnecessarily

---

# 43. Testing Requirements

Create basic tests for:

- health endpoint
- input validation
- unnamed-place filtering
- duplicate removal
- API response schema
- empty search results
- history creation/deletion
- website validation (invalid, placeholder and non-http URLs return null)
- rating validation (out of range or missing source returns null)
- coordinate validation and haversine distance calculation
- route endpoint, including the straight-line fallback flagged as approximate
- places without coordinates still returned without a marker or distance

Frontend should be manually tested at:

- desktop
- tablet
- mobile

Manual map checks: marker sync with filters, current-location highlight, card-to-route selection, deselecting, theme switch (including dark basemap), and behaviour when map tiles or routing are unavailable.

---

# 44. README Requirements

README should explain:

1. Project overview
2. Features
3. Architecture
4. Folder structure
5. Technologies
6. Installation
7. Environment variables
8. Running backend
9. Running frontend
10. API endpoints
11. Mock-data mode
12. Future integrations
13. Security
14. Deployment
15. Author/project information

Do not claim an API integration is implemented if it is only planned.

---

# 45. Development Phases

## Phase 1 — Raw project

Build:

- folder structure
- FastAPI backend
- HTML pages
- CSS system
- JavaScript structure
- navigation
- responsive layout
- mock data
- reusable components

No real API dependency.

## Phase 2 — Functional frontend

Implement:

- forms
- filters
- result cards
- loading states
- errors
- history
- theme switching
- mock API integration
- interactive map with synchronised result cards on Places, Cafés and Medical (Section 50)
- current-location highlight, category filters synced with markers, and route highlight on card click

## Phase 3 — Backend integration

Connect:

- FastAPI routes
- validation
- service layer
- mock provider adapter

## Phase 4 — Real search/place API

Add a real provider.

Normalize all results.

Filter unnamed places.

Add coordinates and distances where available.

## Phase 5 — AI

Connect an AI provider through `ai_service.py`.

AI should receive structured context rather than arbitrary raw UI state.

## Phase 6 — Advanced maps/geolocation

The first-build map, markers, browser location, distances and route highlighting already exist (Section 50). Add:

- real geocoding and reverse geocoding
- a production routing provider
- marker clustering for dense results
- saved places on the map

## Phase 7 — Export

Add:

- PDF
- TTS/audio

## Phase 8 — Persistence

Add:

- SQLite
- history
- saved places

## Phase 9 — Production

Add:

- security checks
- error monitoring
- deployment
- environment configuration
- final README

---

# 46. First Milestone Definition

The first generated project is considered successful when:

- the application starts locally
- homepage works
- all five major features have pages
- navigation works
- responsive layout works
- theme selector works
- forms work
- mock results appear
- result cards work
- loading/error/empty states exist
- history UI exists
- Places, Cafés and Medical each show an interactive map above rich result cards
- the current location / search centre is highlighted on the map
- removing a category or filter removes its cards and markers
- clicking a card highlights the place and its route on the map
- websites shown on cards have passed validation
- backend health endpoint works
- frontend communicates with backend
- no API key is required to demonstrate the raw application
- no feature depends on Streamlit

The first milestone does NOT need real AI or real maps.

---

# 47. Important Product Rules

1. Never invent place names.
2. Never invent ratings.
3. Never invent addresses.
4. Never invent opening hours.
5. Never claim a place is 24/7 without supporting data.
6. Never expose API keys to the frontend.
7. Do not show unnamed places as normal recommendations.
8. Do not claim exact distances unless calculated.
9. Separate AI-generated suggestions from verified source information.
10. Keep provider-specific code inside services.
11. Keep the UI independent from AI/search provider choice.
12. Prefer graceful empty/error states over fabricated content.
13. Make the application explainable enough for a student portfolio/interview.
14. Never show a website link that has not passed backend validation.
15. Never draw a straight line as if it were a real route, and never show a route duration without a routing result.
16. Only place map markers at validated coordinates.
17. Keep cards, markers and filters driven by one shared state so they can never disagree.

---

# 48. Antigravity Implementation Guidance

Antigravity should first generate the complete raw project, not attempt to perfect every external integration immediately.

Prioritize:

1. Architecture
2. UI/UX
3. Responsive frontend
4. Reusable components
5. API contracts
6. Mock data
7. Backend skeleton
8. Integration points

Use clean code and meaningful filenames.

Avoid putting the entire application into one HTML or Python file.

Avoid inline CSS where possible.

Avoid inline JavaScript where possible.

Use modular files.

Keep comments where architectural decisions may not be obvious.

---

# 49. Final UI Direction

The final product should resemble a polished modern local-discovery/travel application.

Think:

- travel assistant
- local discovery platform
- AI planning tool
- neighborhood guide

The user should understand what to do within a few seconds of opening the homepage.

The application should feel like a real portfolio product rather than a classroom CRUD application.

---

# 50. Interactive Map & Place Cards (Places Near You, Quiet Work Cafés, 24/7 Medical Care)

This section is **authoritative** for the result cards and the interactive map on three pages: **Places Near You**, **Quiet Work Cafés** and **24/7 Medical Care**. Where it conflicts with an older statement elsewhere in this document (for example "do not require a map API" or "Phase 6 — Maps"), this section wins. Everything else in the specification stays as written.

The three pages must share **one implementation** (one map component, one card component, one filter-chip component, one explorer controller). Each page only supplies its own data, its own filters and small card differences described below. Do not build three separate map implementations.

The Area Guide keeps its map placeholder and is not part of this section.

## 50.1 Reference design (from user-supplied screenshots)

The screenshots supplied by the project owner are the visual reference. They are described here so this specification stands on its own.

**Map (top of results):**

- Full-width, rounded (`--radius-xl`) map card with a subtle border, about 340–420px tall on desktop and about 260–300px on mobile.
- Light, minimal, grey-toned basemap (CARTO Positron style built on OpenStreetMap data, rendered with MapLibre GL JS).
- Every result is a small round **dark-teal marker** with a white outline.
- The user's current location / search centre is a **larger, clearly different coral pin with a star**, so it can never be confused with a result marker.
- Attribution text is visible in the bottom-right corner.

**Results header:**

- Left: heading ("Nearby Places", "Quiet Work Cafés" or "24/7 Medical Care") followed by a muted count such as "46 places".
- Right: a **Radius** dropdown (for example 1 km, 2 km, 3 km, 5 km, 10 km; default 3 km).

**Filter chips (below the header):**

- A row of pill-shaped chips: **All** first (selected style = filled teal with white text), then one chip per category with a small icon.
- Unselected chips are white/surface with a subtle border.

**Cards (below the chips):**

- Responsive grid: 3 columns on desktop, 2 on tablet, 1 on mobile.
- White cards, soft shadow, rounded corners, on a warm off-white page background.

## 50.2 Card anatomy

Each card, top to bottom:

1. **Header row:** a category icon (SVG, same icon set as the rest of the app, not emoji) + **place name** (bold). The **distance** is right-aligned in muted text.
2. **Rating row:**
   - If a real rating is supplied by the data source: star icon + number, and the review count in muted text when supplied (for example `★ 4.5 (1,203)`).
   - If no rating is supplied: the muted text **"Rating unavailable"**. Never show `0`, never show a placeholder rating.
3. **Category / type label** (for example "Hotel", "Attraction", "Café", "Urgent care").
4. **Description: 2–3 lines** (roughly 150–260 characters). Clamp to 3 lines in CSS and offer a small "Read more" toggle when the text is longer. See 50.7 for how descriptions may be produced.
5. **Address** (only when supplied by the source).
6. A thin divider, then the **footer row**:
   - **"Visit Website →"** link, shown **only** if the website passed backend validation (50.7). If there is no valid website, do not render the link at all.
   - **Phone number** as a `tel:` link, shown **only** if supplied by the source.
   - No fabricated or placeholder contact details, ever.
7. A small muted **Source** line (for example "Source: Sample data", later "Source: Geoapify"). Keep it visually quiet, as defined in Section 15.

Page-specific additions:

- **Quiet Work Cafés:** show amenity badges under the category (Wi-Fi, Charging, Quiet, AC, and so on) **only** for amenities that the data explicitly supports.
- **24/7 Medical Care:** show a **service-type label** (Emergency department, Urgent care, Late-night pharmacy, and so on). Show a **"24/7" badge with an icon and the text "24/7"** only when the backend marks `is_24_7 = true` from supporting data. If not verified, show nothing about 24/7 (optionally a muted "Opening hours unavailable"). Status must never rely on colour alone.

Distance formatting:

- Under 1,000 m: whole metres (`119 m`). From 1,000 m: one decimal in km (`1.4 km`).
- The card distance is the **straight-line distance calculated by the backend** from the search centre or the user's location. Give it a tooltip/aria-label such as "Straight-line distance". Route distance is shown separately when a place is selected (50.5).
- If distance cannot be calculated, hide it.

Default sort: **nearest first**. If distances are unavailable, sort alphabetically.

Card states:

- Cards have **default**, **hover**, **focus-visible** (clear ring using the primary colour) and **selected** (see 50.5) states. Cards are never dimmed; only map markers are dimmed.
- The entire card acts as a selection target, but website and phone are separate links inside it. Use an accessible pattern that avoids nesting interactive elements (for example the place name is a real `<button>` whose hit area is stretched over the card, while links sit above it).

## 50.3 Map behaviour

**Library:** MapLibre GL JS loaded from a CDN with a pinned version. No API key is required.

**Basemap:**

- Light themes: a keyless vector basemap based on OpenStreetMap data (CARTO Positron style).
- Dark theme: the matching dark style (CARTO Dark Matter) so the map follows the selected theme.
- The basemap style URL lives in `frontend/js/config.js` (public settings only, never secrets), so the provider can be replaced later without touching component code.
- Attribution required by MapLibre, CARTO and OpenStreetMap must stay visible. Do not hide or remove it.

**Markers:**

- **Result markers:** round, primary-colour fill, white outline, about 14–16px, created from CSS variables so all five themes work. They must be keyboard-focusable buttons with an `aria-label` containing the place name.
- **Current-location marker:** larger, accent-colour (coral) pin with a star, white outline, always on top of result markers. Label it "You are here" when the location came from the browser, or "Search centre" when it came from a typed location. Never claim "You are here" for a typed location.
- Add a small **legend** (current location / result / selected).
- No continuous or pulsing animation. Respect `prefers-reduced-motion` (use instant view changes instead of animated fly-to).
- Optional but recommended: a very light dashed circle showing the selected search radius.

**Only real coordinates become markers.** A place without valid coordinates is still shown as a card, but with no marker and a small note "Location on map unavailable". Never guess coordinates.

**Initial view:** fit the map to the search centre plus all visible markers with padding. Provide zoom in/out controls and a "recentre" button.

## 50.4 Category filtering synchronised with the map

There is a single source of truth for what is visible: the set of **active categories** (Places), **active amenity filters** (Cafés) or **active service types** (Medical).

- Cards, markers, the results count and the chip counts are all derived from this one state.
- **Removing a category (deselecting its chip, or removing it in the category selector) immediately hides its cards and its markers.** Re-selecting it brings both back. No new network request is needed for chip toggling because the data is already loaded.
- **All** selects every category. Chips are multi-select. If the user deselects everything, show an empty state ("No categories selected. Choose a category or show all") with a "Show all" button.
- Each chip shows the number of loaded places in that category; the heading count reflects the currently visible number.
- After any filter change, refit the map to the visible markers **unless** a place is currently selected. If the selected place gets filtered out, clear the selection and remove its route.
- Changing the **radius** or the search location triggers a new backend request with loading states (50.8).
- For Cafés, amenity filters work the same way: a café is visible only if it has every selected amenity **as supported by data**.
- For Medical, the service-type chips (24/7 hospitals, Emergency departments, Urgent care, Late-night pharmacies, Clinics, Diagnostic centres) work the same way.

## 50.5 Selecting a place: highlight and route

Clicking a **card** or a **map marker** selects the place. Card and marker stay in sync in both directions (clicking a marker also highlights and scrolls to its card).

When a place is selected:

1. **Card:** shows the selected style (primary border, light primary background, and a "Selected" text/icon so it does not rely on colour only) and `aria-current="true"`.
2. **Marker:** the selected marker becomes larger, uses the accent colour, and shows a label/popup with name, category and distance. **All other markers are dimmed** (reduced opacity) but remain clickable.
3. **Route:** a route line is drawn from the current location / search centre to the place. Style: a wide white casing under a solid primary/accent line so it is clearly visible on the light basemap. The map fits both endpoints with padding.
4. **Route summary panel** (on the map or directly under it): shows the mode, distance and duration **only when returned by the routing service**, for example "Walking · 1.2 km · 15 min". Includes a **Walking / Driving** toggle (default: walking; remember the choice locally) and a **"Get directions"** external link that opens the destination in a maps app/website using coordinates (no API key). Include a close button.
5. **Deselect:** clicking the selected card again, clicking the close button, pressing `Esc`, or clicking empty map space clears the selection, the route and the dimming, and restores the previous map view.

Routing rules:

- The browser never calls a routing provider directly. It calls `POST /api/route` on the backend (Section 23 and 50.6).
- If the routing service is unavailable, times out or finds no route, draw a **dashed straight line** and label it clearly, for example "Route unavailable. Straight-line distance about 340 m." A straight line must never be presented as a real route, and a duration must never be shown without a routing result.
- Cancel any in-flight route request when the selection changes (AbortController) and ignore stale responses. Cache route results per origin/destination/mode.
- While a route is loading show a small spinner in the summary panel. Keep the previous view stable; do not blank the map.

Mobile behaviour: selecting a card scrolls the map into view (respecting reduced motion) and shows a "Back to list" button in the route summary panel.

## 50.6 Current location and search centre

Support three ways to get a centre, in this order of priority:

1. **"Use my location" button:** the browser asks for permission. Show a short explanation of why location is requested before or beside the button. Never request location silently or on page load. Coordinates go to the backend, which may reverse-geocode them later. Label: "You are here".
2. **Typed location** (for example "Manchester", "Connaught Place, Delhi"): the backend geocodes it to a centre. Label: "Search centre".
3. **Permission denied or unavailable:** show a friendly message and fall back to the typed location field. Never block the page.

Privacy:

- Do not store precise coordinates in history or local storage by default. Store the location label only.
- Do not log precise user coordinates unnecessarily (Section 42). Round them in logs.

In mock mode, geocoding is handled by `data/mock/locations.json` (a small list of known location names with centre coordinates). If a typed location is not found, return a friendly "We couldn't find that location. Try a nearby landmark or a larger area" error; never guess coordinates.

## 50.7 Backend responsibilities for the new features

**Response envelope** for `POST /api/places/search`, `/api/cafes/search` and `/api/medical/search`:

```json
{
  "center": {
    "latitude": 0,
    "longitude": 0,
    "label": "Manchester, United Kingdom",
    "kind": "user_location"
  },
  "radius_km": 3,
  "total": 46,
  "counts_by_category": { "cafe": 12, "hotel": 9 },
  "data_mode": "mock",
  "places": [
    {
      "id": "stable-unique-id",
      "name": "Example Place",
      "category": "hotel",
      "description": "Two to three sentences.",
      "description_source": "provider",
      "address": "Verified address or null",
      "latitude": 0,
      "longitude": 0,
      "distance_m": 285,
      "rating": null,
      "rating_count": null,
      "rating_source": null,
      "website": null,
      "phone": null,
      "source": "sample-data"
    }
  ]
}
```

- `center.kind` is `user_location` or `search_area`.
- `data_mode` is `mock` or `live`. When `mock`, the frontend shows a visible, dismissible-per-session banner: "Showing sample data for demonstration. Names, ratings and contact details are illustrative."
- Café results add `amenities` (only supported ones). Medical results add `service_type`, `is_24_7` (`true` / `false` / `null`) and `phone`.

**Website validation (backend, not only frontend).** The user reported that websites sometimes do not work, so:

- Accept only absolute `http`/`https` URLs. Normalise obvious bare domains to `https://`. Reject anything else, including empty strings, `javascript:` URLs, `localhost`, `example.com`-style placeholders, and search-engine or redirect/tracking links.
- If a URL fails validation, return `website: null` (the frontend then hides the link). Do not substitute a guessed URL.
- Optional live check, controlled by `VERIFY_WEBSITES` in configuration: send a lightweight HEAD request (fall back to GET), timeout about 3 seconds, follow redirects, run with limited concurrency. Treat DNS failure, connection failure, 404/410 and 5xx as unreachable, so `website: null`. Treat 2xx, 3xx, 401, 403, 405 and 429 as reachable, because many valid sites block automated checks. Cache results (for example 24 hours) so repeated searches stay fast.
- Default: `VERIFY_WEBSITES=false` in mock mode, `true` when a real places provider is connected.
- Links open with `target="_blank"` and `rel="noopener noreferrer"`.

**Rating validation.** `rating` must be a number from 0 to 5 **and** must have a `rating_source`. Otherwise set `rating`, `rating_count` and `rating_source` to `null`. Never default a missing rating to 0 and never estimate one.

**Description rules.** Descriptions are 2–3 sentences and must be grounded in supplied data only.

- Preferred order: the provider's own description → a neutral sentence built from known fields (category, area/address, verified tags) → later, an AI-written summary produced from that same structured data.
- Set `description_source` to `provider`, `generated_template` or `ai`. The UI shows a small "AI summary" label when the source is `ai`, keeping AI text visibly separate from verified source information (Product Rule 9).
- Descriptions must not contain claims about ratings, prices, opening hours, amenities or 24/7 status unless those exact facts are present in the structured data.

**Distance.** Calculate `distance_m` in the backend with a haversine function in `utils/geo.py` from the centre to each place's validated coordinates. Never accept a distance supplied by a provider or by the frontend as truth without recomputing or verifying it.

**Coordinates.** Latitude must be between -90 and 90 and longitude between -180 and 180. Places with invalid or missing coordinates are kept (if otherwise valid) with `latitude` and `longitude` set to `null`, and no distance.

**Routing service.** Create `routing_service.py` behind a provider-independent interface, for example `get_route(origin, destination, mode) -> Route`.

- `POST /api/route` request: `origin {latitude, longitude}`, `destination {latitude, longitude}`, `mode` (`walking` or `driving`).
- Response: `geometry` (GeoJSON LineString), `distance_m`, `duration_s`, `mode`, `provider`, `is_approximate`.
- Provider order: (1) a keyless, OSRM-compatible public routing service configured in `.env` (`ROUTING_BASE_URL`), treated as best-effort with no uptime guarantee and to be replaced by a production provider later; (2) automatic fallback to a straight line with `is_approximate: true`, `duration_s: null` and `distance_m` from haversine. Verify the public service's current usage terms and available walking/driving profiles before relying on it.
- Timeout about 5 seconds, small in-memory cache, request validation (valid coordinates, sensible maximum origin/destination separation such as 50 km, otherwise a friendly 422 error).
- Log provider failures (Section 42) without exposing keys or precise user coordinates.

**Configuration additions** (centralised in `config.py`, placeholders in `.env.example`, no secrets): `MOCK_MODE`, `ROUTING_PROVIDER`, `ROUTING_BASE_URL`, `VERIFY_WEBSITES`.

## 50.8 States for the map and cards

- **Loading:** skeleton map block plus skeleton cards, with text such as "Finding places nearby…". Disable the search button while loading. Route loading is described in 50.5.
- **Map failed to load** (for example no internet or blocked tiles): replace the map with an error state ("The map couldn't load. Your results are still listed below.") and a Retry button. Cards, filters and text route info must keep working.
- **Empty:** "No places found. Try a larger radius or different categories."
- **Centre not found / permission denied / route unavailable:** friendly messages as described above. Never show raw errors or stack traces (Section 18).
- **No valid coordinates for any result:** show the cards and a map message "None of these results have map locations."

## 50.9 Responsive layout

- **Desktop:** map on top, then header, chips, and a 3-column card grid.
- **Tablet:** 2-column grid, slightly shorter map.
- **Mobile:** single column, map about 260–300px, touch targets at least 44px, radius dropdown and chips remain usable. The chip row may scroll horizontally **inside its own container**, but the page itself must never scroll horizontally.

## 50.10 Accessibility for the map and cards

- The cards list is a complete text alternative to the map. Every piece of information on the map is also available in the list.
- Markers are keyboard-focusable buttons; `Enter` or `Space` selects; `Esc` clears the selection.
- Announce route results through a polite live region (for example "Route to Premier Inn: walking, 1.2 kilometres, about 15 minutes").
- Selected, 24/7 and current-location states use icons or text as well as colour.
- Maintain the contrast rules for text on the primary and accent colours.

## 50.11 Theming

- Marker, route and selection colours come from CSS variables and are re-read when the theme changes, so all five themes work without extra code.
- Switching to the Dark theme switches the basemap style; switching back restores the light style. The current selection and route must survive a theme switch.

## 50.12 Security and future providers

- No API key may ever appear in frontend files. The keyless basemap and the backend-mediated routing service satisfy this for the first version.
- If a keyed map or tile provider is adopted later, use a domain-restricted public key or proxy the requests through the backend, and record the change in `frontend/js/config.js` and the README.
- Keep the map component independent of the data provider: it receives normalised places and a centre, nothing more.

## 50.13 Acceptance checklist for this feature

- Places Near You, Quiet Work Cafés and 24/7 Medical Care each show a map above a card grid, using one shared map component.
- Every result with valid coordinates appears as a marker; the current location / search centre is clearly highlighted with a different marker.
- Deselecting a category (or amenity / service type) removes its cards and markers immediately, and re-selecting restores them.
- Clicking a card or a marker highlights both, dims the other markers, draws the route (or a clearly labelled straight-line fallback) and shows the route summary.
- Cards show name, distance, rating or "Rating unavailable", category, a 2–3 line description, address, a validated website (only when valid) and a phone number (only when supplied), plus source.
- No card shows a fabricated rating, website, phone number, address, opening hours or 24/7 status.
- Invalid or unreachable websites never appear as links.
- Map and route failures degrade gracefully and never break the cards.
- Layout works on desktop, tablet and mobile with no horizontal page scrolling.
- The feature works with no API keys.
