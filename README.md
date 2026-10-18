<div align="center">

# 🧭 AI Powered Travel Companion

### ✨ Explore Your City with Intelligence and Ease ✨

Plan a whole trip in one place: flights, trains, hotels, and a day-by-day plan with real places and map links.

**[🌐 Open the live app](https://ai-powered-travel-companion.onrender.com)**

</div>

---

## 🌟 What is this?

This is a website that helps you plan a trip from your front door to your hotel and back. You type where you start and where you want to go. The app finds flights and trains, suggests hotels, and writes a day-by-day plan for you. It also helps you find places, quiet cafés and 24/7 medical help near you.

You don't need to be a techie to use it. 😊

---

## 🎯 What can you do with it?

| | Feature | In simple words |
|---|---|---|
| 🗺️ | **Trip Planner** | Pick cities and dates, choose transport and a hotel, get a full itinerary and download it as a PDF |
| 🌍 | **City, state or country** | Type a place and the planner asks a few questions (where you land, which cities to visit) so big trips stay realistic |
| 🏨 | **A hotel for each stay** | Long trips use several hotels, each near the places of those days, so you travel less |
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

## 👤 Log in or use it as a guest

When you open the app, you choose:

- 🔐 **Log in** (free account): everything works, and your history, saved sessions and reviews are kept.
- 🚶 **Continue as guest**: you can plan trips and use places, cafés, medical search and the Area Guide. Nothing is saved, and you can't post reviews or keep a history.

Logged-in users can also **delete their account** any time (menu next to your name → *Delete account*). This removes your login, history and saved sessions.

---

## 🚆 About train fares and seats (please read)

The train data comes from **RailRadar**. It tells us the trains, timings, stations and which classes each train has. It does **not** give ticket prices or seat availability (Available / RAC / Waiting list).

So the app is honest about it:

- ✅ It shows which of your chosen classes each train really has.
- ❌ It never makes up a fare or a seat status. If the data isn't there, it says **"Not provided"**.
- 🔗 It gives you a link to IRCTC to check live fares and seats.
- 🧩 The code is ready to plug in another data source later that does supply fares.

---

## 🚀 How to run it on your computer

You need **Python 3.10 or newer** and a web browser.

```bash
# 1. Get the code
git clone <your-repo-url>
cd Local_guide_project

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

- 📖 API pages (for developers): http://127.0.0.1:8000/docs
- 💚 Health check: http://127.0.0.1:8000/api/health

### 🔑 Keys (optional)

Without any keys the app runs in **demo mode** with sample data, so you can look around safely. For real results, copy `.env.example` to `.env` and add your keys:

| Key | What it is used for |
|---|---|
| `GEOAPIFY_API_KEY` | Places, cafés, medical search and maps |
| `GEMINI_API_KEY` | The AI that writes itineraries, area guides and train advice |
| `SERPAPI_API_KEY` | Real flight and hotel prices |
| `RAILRADAR_API_KEY` | Trains, stations and classes |
| `DB_*` settings | The database for accounts and history |
| `RECAPTCHA_*` | Optional "I'm not a robot" check |
| `AUTH_SECRET` | Optional secret for guest sessions |

Then set `MOCK_MODE=false` to switch to real data.

> 🔒 **Keep your `.env` file private.** It is already in `.gitignore`. Never upload it to GitHub. If a key ever leaks, create a new one.

---

## 🧪 Run the tests

```bash
python -m pytest backend/tests -v
```

There is also a small check for the page-building code (needs Node.js):

```bash
node frontend/tests/itinerary-extras.test.mjs
```

---

## 🗂️ What's inside

```
Local_guide_project/
├── backend/            🐍 The server (Python + FastAPI)
│   └── app/
│       ├── routes/     Web addresses the pages talk to (login, trips, trains...)
│       ├── services/   The "workers": flights, trains, hotels, AI, PDF...
│       ├── models/     The shape of the data
│       └── utils/      Small helpers
├── frontend/           🎨 The website (HTML, CSS, JavaScript)
│   ├── pages/          One page per feature
│   ├── js/             What happens when you click
│   └── css/            How it looks (themes included)
├── run.py              ▶️ Starts everything
└── .env.example        🔑 Template for your keys
```

---

## 🧰 Built with

🐍 Python + FastAPI · 🌐 HTML, CSS and plain JavaScript · 🗺️ MapLibre maps · 🤖 Google Gemini · ✈️ SerpApi (flights & hotels) · 🚆 RailRadar · 📍 Geoapify · 🐘 PostgreSQL · 📄 ReportLab (PDFs)

---

## 💡 Good to know

- 💸 Prices from flight and hotel providers are live quotes, not booking guarantees. They can change.
- 🕒 Always check opening hours before you go.
- 🚑 In an emergency, call your local emergency number. This app is a helper, not a replacement.

---

## 📄 License

Made as a full-stack portfolio project. Feel free to learn from it. ❤️
