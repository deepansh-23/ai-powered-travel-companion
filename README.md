## 🚀 Live Demo

**[🌐 Open AI-Powered Travel Companion](https://ai-powered-travel-companion.onrender.com)**

Try the deployed application to explore its AI-powered travel planning and other available features.

# Smart Local Guide — Full-Stack Web Application

An intelligent, full-stack AI-assisted local discovery platform, multi-day itinerary planner, work-friendly café locator, and 24/7 emergency medical care guide.

Built from scratch using **HTML5, Vanilla CSS3, Vanilla JavaScript (ES6+), and Python FastAPI**.

---

## 1. Project Overview

Smart Local Guide helps travelers, remote workers, and city explorers discover authentic places around them. It features an interactive map synchronized in real time with place cards, detailed day-by-day itinerary planning, neighborhood analytical guides, work-friendly study cafés with verified amenities, and emergency healthcare listings.

The application operates in a **mock-first architecture**, allowing all pages, interactive maps, category filters, and routing calculations to be run without requiring external paid API keys.

---

## 2. Key Features

1. **Interactive Map & Place Cards (Places Near You, Quiet Work Cafés, 24/7 Medical Care)**:
   - Full-width MapLibre GL JS vector basemap (light CARTO Positron and dark CARTO Dark Matter styles).
   - Distinct coral star marker for the search center / user location ("You are here" vs "Search centre").
   - Result markers styled dynamically using CSS variables across all 5 themes.
   - Dynamic category / amenity / service-type filter chips with real-time counts.
   - Selecting a card or marker highlights the place, dims other markers, draws a route, and opens a walking/driving route summary panel.
   - Straight-line dashed route fallback when routing is unavailable or approximate.
2. **Itinerary Planner**:
   - Multi-day trip generation (1–7 days) customized by pace, budget, and travel interests.
   - Day-by-day timeline: morning, lunch stop, afternoon, dinner stop, evening, and transport notes.
   - Export to PDF and text-to-speech audio overview placeholders.
3. **Area Guide (Neighborhood Summarizer)**:
   - 12 analytical sections: character, dining, cafés, shopping, medical, ATMs, landmarks, parks, public transit, advantages, limitations, and lifestyle suitability.
   - Quick facts dashboard covering walkability score and transit connectivity.
4. **Quiet Work Cafés**:
   - Laptop-friendly study cafés filtered by verified amenities (Wi-Fi, charging outlets, quiet zones, good seating, AC, long working hours).
5. **24/7 Medical Care**:
   - Serious healthcare UI with prominent emergency service disclaimers.
   - Service-type filters: 24/7 hospitals, Emergency departments (A&E), Urgent treatment centers, Late-night pharmacies, and Clinics.
   - Verified 24/7 badges displayed only when confirmed by data sources.
6. **Search & Planning History**:
   - Filterable archive of generated itineraries, place discoveries, and area guides with modal view, PDF generation, and deletion.
7. **5 Selectable Themes**:
   - Warm Aesthetic (Default: Deep Teal `#0F766E`, Sand `#F4E7D3`, Coral `#E76F51`)
   - Rose Gold
   - Sage Green
   - Classic Light
   - Dedicated Dark Theme (with automatic dark basemap switching)

---

## 3. Architecture & Folder Structure

```
Local_guide_project/
│
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI application & router registry
│   │   ├── config.py                # Centralized settings & environment variables
│   │   ├── models/                  # Pydantic data schemas
│   │   │   ├── route.py
│   │   │   ├── places.py
│   │   │   ├── cafes.py
│   │   │   ├── medical.py
│   │   │   ├── itinerary.py
│   │   │   ├── area.py
│   │   │   └── history.py
│   │   ├── routes/                  # API endpoints
│   │   │   ├── health.py
│   │   │   ├── route.py
│   │   │   ├── places.py
│   │   │   ├── cafes.py
│   │   │   ├── medical.py
│   │   │   ├── itinerary.py
│   │   │   ├── area.py
│   │   │   ├── history.py
│   │   │   └── export.py
│   │   ├── services/                # Business logic & external service adapters
│   │   │   ├── routing_service.py
│   │   │   ├── geocoding_service.py
│   │   │   ├── places_service.py
│   │   │   ├── ai_service.py
│   │   │   ├── search_service.py
│   │   │   ├── pdf_service.py
│   │   │   └── tts_service.py
│   │   └── utils/                   # Authoritative validation and geo helpers
│   │       ├── validation.py
│   │       ├── geo.py
│   │       └── helpers.py
│   ├── tests/                       # Pytest test suite
│   │   ├── test_validation.py
│   │   ├── test_geo.py
│   │   └── test_routes.py
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── index.html                   # Home / Landing page
│   ├── pages/
│   │   ├── itinerary.html           # Itinerary Planner
│   │   ├── places.html              # Places Near You
│   │   ├── area.html                # Area Guide
│   │   ├── cafes.html               # Quiet Work Cafés
│   │   ├── medical.html             # 24/7 Medical Care
│   │   └── history.html             # Search & Planning History
│   ├── css/
│   │   ├── variables.css            # Tokens, 5 color themes, typography
│   │   ├── style.css                # Base reset, layout, forms, buttons
│   │   ├── components.css           # Navbar, cards anatomy, filter chips, modal, toast
│   │   ├── map.css                  # MapLibre styling, custom SVG markers, popup
│   │   ├── pages.css                # Page-specific views and timelines
│   │   └── responsive.css           # Desktop 3-col, tablet 2-col, mobile 1-col
│   └── js/
│       ├── config.js                # Public map styles & defaults (no secrets)
│       ├── state.js                 # Shared reactive app state
│       ├── api.js                   # API client with abort controllers
│       ├── app.js                   # Global initializer
│       ├── utils/
│       │   ├── geo.js               # Distance formatting & bounds calculation
│       │   └── formatters.js        # HTML escaping & text utilities
│       ├── components/
│       │   ├── navbar.js
│       │   ├── cards.js             # Card anatomy (Section 50.2)
│       │   ├── filter-chips.js      # Synced category chips with counts
│       │   ├── map.js               # Reusable MapLibre component
│       │   ├── nearby-explorer.js   # Shared controller for Places/Cafés/Medical
│       │   ├── modal.js
│       │   ├── toast.js
│       │   ├── loader.js
│       │   └── history.js
│       └── pages/
│           ├── places.js
│           ├── cafes.js
│           ├── medical.js
│           ├── itinerary.js
│           ├── area.js
│           └── history.js
│
├── data/
│   └── mock/
│       ├── locations.json           # Geocoding database of city centers
│       ├── places.json              # 27 validated places (testing all edge cases)
│       ├── cafes.json               # 16 work-friendly cafés with amenity tags
│       ├── medical.json             # 14 medical facilities with 24/7 verification
│       ├── itinerary.json           # Multi-day itinerary templates
│       └── area.json                # 12-section neighborhood analytical profiles
│
├── .env.example
├── .gitignore
├── pytest.ini
├── README.md
└── run.py                           # Single-command full-stack server
```

---

## 4. How Map, Routing, and Geolocation Work

### The Map
- **Engine**: MapLibre GL JS (loaded via pinned CDN v3.6.2, zero API key required).
- **Basemap Tiles**: Keyless vector basemaps built on OpenStreetMap data provided by CARTO:
  - Light themes use `CARTO Positron`.
  - Dark theme uses `CARTO Dark Matter`.
- **Markers**: Created dynamically with SVG elements using CSS custom properties:
  - Search center / User location is rendered as an accent coral pin with a star (`You are here` or `Search centre`).
  - Result places are rendered as small primary teal dots with white borders.
  - Places without coordinates are presented as cards with `"Map N/A"` and no marker (coordinates are never guessed).
  - Selecting a place dims all other markers to 35% opacity while maintaining clickability.

### Routing (`POST /api/route`)
- **Backend-Mediated**: The browser never calls a routing provider directly.
- **Provider**: Calls a keyless, OSRM-compatible public routing service (`https://router.project-osrm.org`) through the FastAPI backend with walking (`profile="foot"`) and driving profiles.
- **Performance & Safety**:
  - Request validation restricts routes to 50 km maximum distance.
  - In-memory cache stores calculated routes by origin/destination/mode.
  - 5-second timeout on network requests.
- **Graceful Straight-Line Fallback**: If the public routing service is unavailable, unreachable, or times out, the backend automatically returns a straight line GeoJSON LineString calculated from the Haversine formula, flagged as `is_approximate: true` with `duration_s: null`. The frontend renders this as a dashed line with a clear fallback summary label (`"Approximate straight-line distance"`).

### Geolocation & Geocoding
- **Priority**:
  1. **"Use my location" button**: Requests browser geolocation with explicit user permission and visual prompt. Coordinates are sent to the backend and labelled `"You are here"`.
  2. **Typed location**: Looked up in `data/mock/locations.json`. Matches city or district names and is labelled `"Search centre"`.
  3. **Permission denied or invalid query**: Returns a friendly notification and falls back to manual entry without breaking the page.
- **Privacy**: Precise user coordinates are never logged; coordinate logging rounds values to 2 decimal places (~1.1 km).

---

## 5. Critical Data Validation Rules

All validation rules are enforced in the **backend**, not merely visually hidden in the browser:

1. **Place Name Validation**: Reject empty, whitespace-only, and placeholder names (`"Unnamed Place"`, `"N/A"`, `"test"`, `"null"`).
2. **Deduplication**: Places with identical normalized names and addresses/coordinates are stripped.
3. **Website URL Validation**:
   - Only absolute `http://` and `https://` URLs are accepted.
   - Bare domains starting with `www.` are normalized to `https://`.
   - Dangerous schemes (`javascript:`, `data:`, `file:`) and placeholder hosts (`localhost`, `example.com`) are rejected and returned as `null`.
   - When `website` is `null`, the frontend hides the link completely.
4. **Rating Validation**:
   - Ratings must be between `0.0` and `5.0` AND must have an accompanying `rating_source`.
   - Missing ratings are returned as `null` (never defaulted to 0); frontend displays `"Rating unavailable"`.
5. **Distance Calculation**:
   - `distance_m` is computed directly by the backend using the Haversine formula from validated coordinates.
6. **24/7 Verification**:
   - The `"24/7"` badge is displayed on medical cards only when `is_24_7 === true` in validated data.
7. **Description Grounding**:
   - 2–3 sentences grounded strictly in verified structured data, labelled with `description_source`.

---

## 6. Installation & Quick Start

### Prerequisites
- Python 3.10+
- Modern web browser (Chrome, Edge, Firefox, Safari)

### 1. Clone & Set Up Environment
```bash
git clone <repo-url>
cd Local_guide_project

# Optional: Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt
```

### 2. Configure Environment (Optional)
The application starts out of the box in mock mode without any `.env` file.
To customize settings:
```bash
cp .env.example .env
```

### 3. Run Application
Run the root single-command runner:
```bash
python run.py
```

The application is now live:
- **Web Application**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **API Documentation (Swagger UI)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **API Health Check**: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

---

## 7. Running Backend Tests

Run the Pytest suite covering place validation, URL sanitization, rating rules, coordinate validation, haversine calculations, and API routes:

```bash
python -m pytest backend/tests -v
```

All 12 unit and integration tests will execute and validate the core logic.

---

## 8. API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Service health status check |
| `POST` | `/api/places/search` | Search places near a center or typed location |
| `POST` | `/api/cafes/search` | Search work-friendly cafés with amenity filters |
| `POST` | `/api/medical/search` | Search emergency healthcare facilities & pharmacies |
| `POST` | `/api/route` | Calculate walking or driving route with OSRM and fallback |
| `POST` | `/api/itinerary/generate` | Generate multi-day personalized travel itinerary |
| `POST` | `/api/area/summarize` | Summarize neighborhood character in 12 analytical sections |
| `GET` | `/api/history` | List saved searches and itineraries (filter by category) |
| `POST` | `/api/history` | Save a new search or planning history record |
| `DELETE` | `/api/history/{id}` | Delete a saved history record |
| `POST` | `/api/export/pdf` | Generate PDF export payload |
| `POST` | `/api/export/audio` | Synthesize text-to-speech audio overview |

---

## 9. Future Integration Points (Planned Phases)

The codebase is structured with isolated service adapters ready for live provider integration in later phases:
- **Places / Search Provider** (`backend/app/services/places_service.py`): Ready for Geoapify, Google Places, or OpenStreetMap Overpass API.
- **AI Planning Provider** (`backend/app/services/ai_service.py`): Ready for Google Gemini (`gemini-1.5-flash`), OpenAI, or Groq models.
- **Web Search Provider** (`backend/app/services/search_service.py`): Ready for DuckDuckGo, Brave Search, or Serper API.
- **Geocoding Provider** (`backend/app/services/geocoding_service.py`): Ready for Nominatim or Photon geocoders.
- **PDF & Audio Services** (`backend/app/services/pdf_service.py`, `tts_service.py`): Ready for ReportLab / WeasyPrint and gTTS / ElevenLabs.
- **Persistent Database**: In-memory history and cache can be migrated to SQLite / PostgreSQL without altering route handlers.

---

## 10. License & Attribution

- Built as part of the Smart Local Guide project.
- Basemap tiles: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors and [CARTO](https://carto.com/).
- Routing: Open Source Routing Machine (OSRM).
