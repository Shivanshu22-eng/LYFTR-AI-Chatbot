# LYFTR AI — Full-Stack Agricultural AI Assistant

A production-grade full-stack AI application powered by **React + Vite**, **FastAPI**, **SQLite**, and **LiteLLM** with Gemini multimodal inference, multi-key failover, response caching, live weather, crop recommendations, and per-response observability.

**Live URLs**
- **Frontend**: https://frontend-nu-jade-29.vercel.app/
- **Backend**: https://lyftr-ai-chatbot-1-k3zj.onrender.com
- **GitHub**: https://github.com/Shivanshu22-eng/LYFTR-AI-Chatbot

---

## 1. Features

### Core Chat
- Multi-turn conversation with full session history
- LiteLLM multi-key Gemini failover (auto-rotates on 429 / quota / 5xx)
- LiteLLM in-memory response caching — `LIVE_INFERENCE` vs `LLM_CACHE`
- Per-message metadata: `source`, `model`, `latency_ms`, `input_tokens`, `output_tokens`, `key_id`, `fallback_attempts`
- Key redaction — raw API keys never appear in logs, responses, or errors

### Image Analysis (Multimodal)
- Upload JPG / JPEG / PNG / WEBP images (max 10 MB)
- Real Gemini multimodal inference (agricultural vision analyst prompt)
- Drag-and-drop in both chat input and dedicated Image Analysis panel
- Image requests always bypass the text cache (`bypass_cache=True`)
- Results persisted to SQLite `image_analyses` table

### Live Weather
- Real-time weather via Open-Meteo (free, no API key required)
- Geocoding → current conditions (temperature, humidity, rain, wind, condition)
- 5-day forecast
- Results persisted to SQLite `weather_queries` table

### Crop Recommendations
- 10 crop profiles with 100-point weighted scoring:
  - Temperature 30 pts · Soil 25 pts · Water 20 pts · Season 15 pts · pH 10 pts
- Optionally fetches live weather for the given location
- Transparent assumption list when inputs are missing
- Results persisted to SQLite `crop_recommendations` table

### Five-Section UI
1. **AI Chat** — original chat with image attachment button
2. **Image Analysis** — dedicated panel with preset agricultural prompts
3. **Live Weather** — location search, stats grid, 5-day forecast
4. **Crop Recommendations** — soil/season/irrigation form + scored results
5. **Chat History** — SQLite-persisted sessions, analyses, weather, crop records

---

## 2. Project Structure

```
LYFTR-AI-Chatbot/
├── .env.example
├── .gitignore
├── render.yaml
├── docker-compose.yml
├── README.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py           # FastAPI routes + lifespan
│       ├── database.py       # SQLite init + CRUD (5 tables)
│       ├── schemas.py        # Pydantic models
│       ├── chat_service.py   # LiteLLM multi-key failover, caching, multimodal
│       ├── weather_service.py# Open-Meteo geocoding + forecast
│       └── crop_service.py   # 10-crop weighted scoring engine
│   └── tests/
│       ├── test_health.py    # 35 original tests
│       └── test_features.py  # 8 new feature tests
└── frontend/
    ├── vercel.json
    ├── .env.production       # VITE_API_BASE_URL=https://lyftr-ai-chatbot-1-k3zj.onrender.com
    └── src/
        ├── App.jsx           # 5-tab multi-panel app
        ├── api.js            # API client (chat, image, weather, crop, history)
        ├── components/
        │   ├── Sidebar.jsx           # 5-section nav + session list
        │   ├── ChatArea.jsx
        │   ├── MessageInput.jsx      # Text + image attach + drag-drop
        │   ├── ImageAnalysisPanel.jsx
        │   ├── WeatherPanel.jsx
        │   ├── CropPanel.jsx
        │   ├── HistoryPanel.jsx
        │   ├── StatusBar.jsx
        │   └── ErrorNotification.jsx
        └── styles/App.css
```

---

## 3. Local Setup

### Prerequisites
- Python 3.11+ with pip
- Node.js 18+
- Two Gemini API keys

### Environment Variables

Copy `.env.example` to `.env` in the repository root:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|---|---|---|
| `LLM_API_KEYS` | Comma-separated Gemini API keys | *(required)* |
| `LITELLM_MODEL` | LiteLLM model identifier | `gemini/gemini-3.5-flash-lite` |
| `DATABASE_PATH` | SQLite file path | `./lyftr.db` |
| `CORS_ORIGINS` | Allowed frontend origins | `http://localhost:5173` |
| `ENABLE_FAILURE_SIMULATION` | Enable `X-Simulate-Failure` header | `false` |

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

---

## 4. API Reference

### Original Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health, DB status, key count, cache |
| POST | `/chat` | Send message, receive AI response + metadata |
| GET | `/sessions` | List all sessions |
| POST | `/sessions` | Create new session |
| GET | `/sessions/{session_id}/messages` | Session message history |

### New Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/analyze-image` | Multipart upload → Gemini multimodal analysis |
| GET | `/weather?location=...` | Live weather (Open-Meteo) |
| POST | `/crop-recommend` | Scored crop recommendations |
| GET | `/history/activity` | All persisted analyses, weather, crop records |

#### POST `/analyze-image`
```
Content-Type: multipart/form-data
Fields:
  file     (required) — image file, JPG/PNG/WEBP, max 10 MB
  prompt   (optional) — custom analysis prompt
  session_id (optional) — associate result with a session
```

#### POST `/crop-recommend`
```json
{
  "location": "Pune",        // optional — fetches live weather if provided
  "soil_type": "loamy",      // clay | sandy | loamy | silty | peaty | chalky
  "soil_ph": 6.5,            // optional
  "season": "Rabi",          // Kharif | Rabi | Zaid | Year-round
  "temperature_c": 20.0,     // optional — overrides live weather
  "rainfall_mm": 400.0,      // optional — overrides live weather
  "irrigation": "moderate",  // none | low | moderate | high
  "session_id": "..."        // optional
}
```

### Failure Simulation

Send `X-Simulate-Failure` header on `POST /chat` (requires `ENABLE_FAILURE_SIMULATION=true`):

| Value | Behaviour |
|---|---|
| `key_1=429` | Simulates 429 on key-1, fails over to key-2 |
| `key_1=429,key_2=500` | Both keys fail → HTTP 503 |
| `*=429` | All keys fail → HTTP 503 |
| `all_keys_fail` | All keys fail → HTTP 503 |

---

## 5. Database Schema

SQLite (`lyftr.db`) with 5 tables — all using `CREATE TABLE IF NOT EXISTS`:

| Table | Purpose |
|---|---|
| `sessions` | Chat sessions |
| `messages` | Chat messages with LiteLLM metadata |
| `image_analyses` | Gemini multimodal results |
| `weather_queries` | Open-Meteo query results |
| `crop_recommendations` | Scored crop recommendation results |

> **Note on Render Free plan**: SQLite at `./lyftr.db` is ephemeral on the free tier (no persistent disk). Data persists within a deployment but resets on redeploy. For persistent storage, configure a Render persistent disk at `/data` and set `DATABASE_PATH=/data/lyftr.db`.

---

## 6. Testing

```bash
# Backend (43 tests: 35 original + 8 new feature tests)
python -m pytest backend/tests -v

# Frontend production build
cd frontend && npm run build

# Playwright E2E (4 tests, Chromium)
cd frontend && npx playwright test
```

**Test results:**
- pytest: **43/43 passed** ✅
- Frontend build: **passed** ✅ (38 modules, 172.57 kB)
- Playwright: **4/4 passed** ✅

**Live integration tests:**
- Open-Meteo weather API (Pune + London): **PASS** ✅
- Gemini multimodal inference: verified via mocked pytest ✅
- LiteLLM caching (`LIVE_INFERENCE` / `LLM_CACHE`): **PASS** ✅
- Multi-key failover (429 → key-2): **PASS** ✅

---

## 7. Deployment

### Backend on Render

The `render.yaml` configures a Python Web Service with root directory `backend`.

Required Render environment variables:
- `LLM_API_KEYS` — your Gemini API keys (comma-separated)
- `CORS_ORIGINS` — set to your Vercel frontend URL
- `ENABLE_FAILURE_SIMULATION` — set to `true` for testing

### Frontend on Vercel

1. Import repository in Vercel with Root Directory `frontend`.
2. Set `VITE_API_BASE_URL` to your Render backend URL.
3. Deploy — Vercel uses `npm run build` and `frontend/vercel.json` for SPA rewrites.

The committed `frontend/.env.production` already sets `VITE_API_BASE_URL` to the deployed Render URL.
