<div align="center">

# 🧭 AI Powered Travel Companion

### ✨ Explore Your City with Intelligence and Ease ✨

Plan a whole trip in one place: flights, trains, hotels, and a day-by-day plan with real places and map links.

**[🌐 Open the live app](https://ai-powered-travel-companion.onrender.com)**

</div>

---

## 🌟 What is this?

A website that helps you plan a trip from your front door to your hotel and back. You type where you start and where you want to go. The app finds flights and trains, suggests hotels, and writes a day-by-day plan for you. It also helps you find places, quiet cafés and 24/7 medical help near you.

You don't need to be a techie to use it. 😊

---

## 🎯 What can you do with it?

| | Feature | In simple words |
|---|---|---|
| 🗺️ | **Trip Planner** | Pick cities and dates, choose transport and a hotel, get a full itinerary and download it as a PDF |
| 🌍 | **City, state or country** | Type a place and the planner asks a few questions (where you land, which cities to visit) so big trips stay realistic |
| ✈️ | **Getting between cities** | For long moves, pick a flight, train, cab or other option first (flights with live prices, trains with times), then choose your hotel |
| 🏨 | **A hotel for each stay** | Long trips use several hotels, each near the places of those days, so you travel less |
| 🗺️ | **Trip picture & map** | Your route, stays and every place on one map, with each day in its own colour |
| 🧳 | **Arrival and departure notes** | Short, clear notes for landing, hotel changes and heading home, with cab time estimates |
| 📱 | **Quick Version** | A short, easy-to-read version of your plan with map links, made for use while travelling |
| ✈️ | **Flights with nearby dates** | See the cheapest day around your date: 🟢 cheap, 🟠 medium, 🔴 expensive |
| 🚆 | **Trains** | Pick your classes (SL, 3AC, 2AC, 1AC) and your exact railway stations |
| 🤖 | **Train advice** | The app compares trains by time and comfort and tells you which looks best |
| 📍 | **Places Near You** | Find interesting places on an interactive map |
| ☕ | **Quiet Work Cafés** | Cafés with Wi-Fi, plugs and a calm atmosphere |
| 🏥 | **24/7 Medical Care** | Hospitals, emergency rooms and late-night pharmacies |
| 🏙️ | **Area Guide** | A friendly summary of any neighbourhood |
| 📜 | **History** | Your past trips and guides, saved to your account |
| ⭐ | **Reviews** | Rate the app and read what others think |
| 🎨 | **5 themes** | Warm, Rose Gold, Sage Green, Classic Light and Dark |

---

---

## 👤 Log in or use it as a guest

- 🔐 **Log in** (free account): everything works, and your history, saved sessions and reviews are kept.
- 🚶 **Continue as guest**: places, cafés, medical search and the Area Guide work. Nothing is saved, and the Itinerary Planner, reviews and history need a login. Log in any time and the results you just made are saved for you.

Logged-in users can **delete their account** any time (menu next to your name → *Delete account*). This removes the login, history and saved sessions.

> The site owner can temporarily switch off new sign-ups, guest mode or new reviews, or put the site into maintenance mode, from the Admin Dashboard (see below).

---

## 🚆 About train fares and seats (please read)

The train data comes from **RailRadar**. It tells us the trains, timings, stations and which classes each train has. It does **not** give ticket prices or seat availability (Available / RAC / Waiting list).

So the app is honest about it:

- ✅ It shows which of your chosen classes each train really has.
- ❌ It never makes up a fare or a seat status. If the data isn't there, it says **"Not provided"**.
- 🔗 It gives you a link to IRCTC to check live fares and seats.
- 🧩 The code is ready to plug in another data source later that does supply fares.

---

---

## 🧠 How the planner thinks

- 🏨 **Fewer hotel changes.** One hotel for the whole stay in a place. A new hotel is only suggested when you move to another city, or when two or more days are spent far (about 20 km or more) from the first hotel. Hotels less than 3 km apart never trigger a "changing hotel" step.
- 🛬 **Arrival day is planned too.** After you land, the plan allows time to leave the airport, reach the hotel and rest for 1 to 1.5 hours. Then it adds a few nearby places and dinner for the rest of the evening. The same logic applies on days when you move between cities by flight or train.
- ✈️ **Flights between cities show flight details.** Once you pick a flight or train between two places, you see its times, duration and distance. Cab and road price estimates are shown only before you choose, or if you choose a cab.
- 🏨 **Every day ends with the way back.** After the last stop, a step shows the hotel, an approximate time to head back, the distance and a map link from that last stop.
- 🗺️ **Each day as a route.** A small horizontal flowchart shows the order of the day. "See on map" draws the numbered stops joined by a highlighted path.
- 🔀 **Use other services while one is running.** While an itinerary is being generated, links to other pages open in a new tab so the running work is not lost. The server also no longer freezes during slow AI calls.

---

## 🛡️ Admin Dashboard

A private control centre at **`/admin/`** for the site owner. It is built into the same app (no extra server) and uses the same PostgreSQL database.

| Section | What it does |
|---|---|
| 📊 **Overview** | Total users, admins, active/inactive accounts, itineraries and sign-ups in the last 7 days |
| 📈 **Analytics** | Daily, weekly and monthly active users, new vs returning users, guests vs registered users, most-used features (Itinerary Planner, Area Guide, cafés, medical, places), date-range filters and trend charts |
| 💸 **AI & API Usage** | AI requests by model and feature, successes, failures and response times, external API usage (SerpApi, Geoapify, RailRadar, OSRM, reCAPTCHA) with quota bars, estimated AI spend, and alerts for limits, failure spikes and unusually high traffic |
| 👥 **Users** | Search and filter by role or status, sort by newest or last activity, see registration date and last activity, suspend or reactivate, promote or demote admins, reset a password (temporary password shown once), delete accounts, and review account deletion requests (with safety guards: you can't remove yourself or the last admin) |
| 🗺️ **Itineraries** | Search, filter by type, and view any saved record (itinerary, places, cafés, medical, area guide) in a readable layout, with raw data one click away. Delete saved items |
| 📈 **API Monitoring** | Request counts, error rate, response times, slowest endpoints and recent failures (last 15 minutes or 24 hours) |
| 💚 **System Health** | App uptime, PostgreSQL connectivity and latency, and whether each external service is configured |
| ⚙️ **Settings** | Maintenance mode, new registrations, guest mode, new reviews, and a public announcement banner |
| 💬 **Feedback & Diagnostics** | Search, filter and page through real reviews; mark them reviewed or resolved; add private notes; see recent sanitized errors |

### How it is protected

- **Admin only, checked on the server.** Every admin API needs a logged-in admin. The page itself shows nothing without them.
- **Step-up password.** Admin actions need a fresh password check. It lasts 30 minutes and renews while you keep using the dashboard.
- **CAPTCHA-protected admin login** with generic error messages (no account guessing) and rate limits.
- **CSRF guard** on every change (same-origin check).
- **No secrets in the UI.** API keys, database credentials and tokens can't be viewed or edited from the dashboard.
- **Privacy.** In the Feedback view, emails, phone numbers and token-like text are masked. Diagnostics keep no request bodies, cookies or tokens, and show only partly hidden IP addresses.
- **Bounded logging.** Monitoring and diagnostics live in memory only (last 10,000 requests and 300 errors) and reset when the server restarts.
- **Disruptive settings need confirmation.** Turning on maintenance mode, or turning off registration, guest mode or reviews, asks you to confirm, and the server enforces that too.

### Analytics and privacy

Analytics use anonymous counters: a day, a user id (or a random guest id), a feature name and a count. No search text, locations, IP addresses or personal data are stored, and rows older than a year are removed. Counting starts the day this update goes live, so earlier days show no activity. Registrations are read from account records and cover every day. Days are counted in UTC.

### AI & API usage monitor

Every call to the Gemini model and to the external APIs is counted with its model or endpoint, feature, result, response time and token counts. Prompts, answers, API keys, user ids and IP addresses are never stored, and error text is scrubbed of anything that looks like a key. Rows older than a year are removed.

- **Spend is an estimate.** It uses editable list prices per model (USD per 1 million tokens). Models without a price get no estimate, and a free tier may cost nothing.
- **Limits are alerts, not blocks.** Set your plan sizes (AI requests per day, spend per month, SerpApi searches per month, Geoapify and RailRadar requests per day, calls per hour). The page warns at 80% and flags 100%. Visitors are never blocked.
- **Other alerts:** unusually high traffic compared with the last two weeks, a service failing often today, and provider rate or quota refusals (HTTP 429).
- **SerpApi quota:** the "Check SerpApi searches left" button reads your remaining searches from SerpApi's free account endpoint.
- Recent failures are kept in memory only and reset when the server restarts.

### Account controls

- **Reset password:** gives the user a random temporary password, shown once to the admin, and signs them out everywhere. It is not available for your own account or for other admins.
- **Deletion requests:** users choose *Request account deletion* in their account menu. Nothing is deleted until an admin approves. Admins can also dismiss a request. Users can still use *Delete account now* (needs their password) or *Change password* from the same menu.

### Settings explained

| Setting | Effect |
|---|---|
| Maintenance mode | Visitors see a maintenance banner and the public API returns 503. Admins, login and the dashboard keep working. |
| Allow new registrations | Off = nobody can create a new account. Existing users can still log in. |
| Allow guest mode | Off = visitors must log in. |
| Allow new reviews | Off = no new reviews. Existing reviews stay visible. |
| Announcement banner | Shows plain text (up to 300 characters) at the top of every page. |

### Setting up your first admin

```bash
# 1. Create a normal account on the website first, then:
python backend/scripts/migrate_add_is_admin.py     # adds the is_admin column (safe to repeat)
python backend/scripts/promote_admin.py <username> # makes that account an admin

# 2. Add the Settings and Feedback tables/columns (safe to repeat, deletes nothing)
python backend/scripts/migrate_admin_features.py
```

Then open **/admin/** and sign in with the admin login.

> ⚠️ These scripts use the database in your `.env`. If that is your live Aiven database, they change live data. Run the migration **before** deploying a new version that uses the new columns.

---

## 🚀 How to run it on your computer

You need **Python 3.10 or newer** and a web browser.

```bash
# 1. Get the code
git clone <your-repo-url>
cd ai-powered-travel-companion

# 2. (Optional) make a clean Python environment
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac / Linux

# 3. Install what the app needs
pip install -r backend/requirements.txt

# 4. Start it
python run.py
```

Then open **http://127.0.0.1:8000/** 🎉

- 🛡️ Admin Dashboard: http://127.0.0.1:8000/admin/
- 📖 API pages (for developers): http://127.0.0.1:8000/docs
- 💚 Health check: http://127.0.0.1:8000/api/health

### 🔑 Keys (optional)

Without keys the app runs in **demo mode** with sample data. For real results, copy `.env.example` to `.env` and add your keys:

| Key | What it is used for |
|---|---|
| `GEOAPIFY_API_KEY` | Places, cafés, medical search and maps |
| `GEMINI_API_KEY` | The AI that writes itineraries, area guides and train advice |
| `SERPAPI_API_KEY` | Real flight and hotel prices |
| `SERP_API_KEY2` | Optional backup SerpApi key. Used automatically when the first key is out of searches or rejected |
| `RAILRADAR_API_KEY` | Trains, stations and classes |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSL_CA` | PostgreSQL (Aiven) for accounts, history, reviews and settings |
| `RECAPTCHA_SITE_KEY`, `RECAPTCHA_SECRET_KEY` | The "I'm not a robot" check (also used on admin login) |
| `AUTH_SECRET` | Secret for signing guest and admin step-up cookies. **Set a fixed value in production** (otherwise a key derived from the database password is used). |

Set `MOCK_MODE=false` to switch to real data.

> 🔒 **Keep your `.env` file private.** It is already in `.gitignore`. Never upload it to GitHub or share it in a zip. If a key ever leaks, create a new one.

---

## ☁️ Deployment (Render)

The app runs as one Render web service that serves both the API and the website.

1. Put your keys in Render's **Environment** settings (never in the code).
2. Run `python backend/scripts/migrate_admin_features.py` against the database **before** deploying a version that needs new columns.
3. Deploy, then check `/api/health` and the **System Health** page in the dashboard.

Render restarts clear the in-memory monitoring and diagnostics, which is expected.

---

## 🧪 Run the tests

```bash
python -m pytest backend/tests -v
```

Tests use a throw-away SQLite database and mock data. They never touch your real database or call paid APIs.

A small check for the page-building code (needs Node.js):

```bash
node frontend/tests/itinerary-extras.test.mjs
```

---

## 🗂️ What's inside

```
ai-powered-travel-companion/
├── backend/               🐍 The server (Python + FastAPI)
│   ├── app/
│   │   ├── routes/        Web addresses the pages talk to (login, trips, trains, settings...)
│   │   ├── services/      The "workers": flights, trains, hotels, AI, PDF, site-settings guard...
│   │   ├── models/        The shape of the data
│   │   └── utils/         Small helpers
│   ├── admin/             🛡️ Admin Dashboard backend (routes, permissions, monitoring, service)
│   ├── scripts/           One-off database scripts (admin promotion, migrations)
│   └── tests/             Automated tests
├── frontend/              🎨 The website (HTML, CSS, JavaScript)
│   ├── pages/             One page per feature
│   ├── js/                What happens when you click
│   ├── css/               How it looks (themes included)
│   └── admin/             🛡️ Admin Dashboard pages, scripts and styles (kept separate)
├── data/mock/             Sample data for demo mode
├── run.py                 ▶️ Starts everything
└── .env.example           🔑 Template for your keys
```

---

## 🧰 Built with

🐍 Python + FastAPI · 🌐 HTML, CSS and plain JavaScript · 🗺️ MapLibre maps · 🤖 Google Gemini · ✈️ SerpApi (flights & hotels) · 🚆 RailRadar · 📍 Geoapify · 🐘 PostgreSQL (Aiven) · ☁️ Render · 📄 ReportLab (PDFs)

---

## 💡 Good to know

- 💸 Prices from flight and hotel providers are live quotes, not booking guarantees. They can change.
- 🕒 Always check opening hours before you go.
- 🚑 In an emergency, call your local emergency number. This app is a helper, not a replacement.

---

## 📄 License

Made as a full-stack portfolio project. Feel free to learn from it. ❤️
