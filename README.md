# LYFTR AI — Full-Stack AI & Agricultural Assistant

A production-grade full-stack AI application powered by **React + Vite**, **FastAPI**, **SQLite**, **LiteLLM** (Gemini), **Open-Meteo**, and **Pollinations.ai** (`flux`) with JWT authentication, role-based access control, administrator dashboard, content moderation, and per-response observability.

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

### AI Image Generation Studio
- Natural-language image generation powered by **Pollinations.ai** (`flux` model)
- **10 Artistic Styles**: Photorealistic, Cinematic, Anime, Digital Art, 3D Rendering, Illustration, Watercolor, Fantasy, Architecture, Product Photography
- **5 Aspect Ratios**: `1:1`, `16:9`, `9:16`, `4:3`, `3:2`
- **1–4 Variations** per request, image previews, direct downloads, and regeneration
- Per-user generation history stored in SQLite (`image_generations`) without storing binary image blobs

### Authentication & Role-Based Access Control (RBAC)
- User registration (`POST /auth/register`) and login (`POST /auth/login`) with **PBKDF2-HMAC-SHA256** password hashing (260,000 iterations) and **HS256 JWT** tokens
- Three roles: `user`, `authorized_creator`, `admin`
- Public registration always assigns `user` role; initial admin is bootstrapped strictly via `ADMIN_EMAIL` and `ADMIN_PASSWORD` environment variables
- Users cannot escalate or change their own roles; admins cannot demote themselves

### Administrator Dashboard & Content Moderation
- Global image-generation enable/disable switch (`PATCH /admin/settings/image-generation`)
- User management: promote/demote roles, suspend/activate accounts, set per-user daily generation limits (`0` = blocked), and configure allowed content categories (`safe`, `adult`, `violent`, `disturbing`)
- Backend-enforced content moderation:
  - Always blocks severe/exploitative content for all roles (including admins)
  - Blocks explicit/adult terms for regular `user` accounts while allowing administrator-approved categories for `authorized_creator`
  - Provider-level `safe=true` parameter always enforced
- Audit log (`GET /admin/audit-logs`) tracking all permission and settings changes

### Image Analysis (Multimodal)
- Upload JPG / JPEG / PNG / WEBP images (max 5 MB)
- Real Gemini multimodal inference (agricultural vision analyst prompt)
- Drag-and-drop in both chat input and dedicated Image Analysis panel
- Image requests always bypass the text cache (`bypass_cache=True`)

### Live Weather & Crop Recommendations
- Real-time weather + 5-day forecast via **Open-Meteo** (free, no API key required)
- 10 crop profiles with 100-point weighted scoring (Temperature 30 pts, Soil 25 pts, Water 20 pts, Season 15 pts, pH 10 pts) and transparent assumptions

### Seven-Section UI
1. **AI Chat** — multi-turn chat with image attachment button
2. **Image Analysis** — dedicated multimodal vision panel
3. **Image Studio** — prompt, style, ratio, variations, gallery, downloads, history (authenticated)
4. **Live Weather** — location search, stats grid, 5-day forecast
5. **Crop Guide** — soil/season/irrigation form + scored results
6. **History** — SQLite-persisted sessions, analyses, weather, crop records
7. **Admin** — user permissions, global settings, all generations, audit logs (administrators only)

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
│       ├── main.py            # FastAPI routes, auth dependencies, lifespan
│       ├── auth_service.py    # PBKDF2 password hashing & HS256 JWT tokens
│       ├── image_service.py   # Pollinations.ai Flux generation & content moderation
│       ├── database.py        # SQLite init + CRUD (9 tables)
│       ├── schemas.py         # Pydantic models & validation
│       ├── chat_service.py    # LiteLLM multi-key failover, caching, multimodal
│       ├── weather_service.py # Open-Meteo geocoding + forecast
│       └── crop_service.py    # 10-crop weighted scoring engine
│   └── tests/
│       ├── test_health.py     # 35 original chat/health/failover tests
│       ├── test_features.py   # 8 weather/crop/analysis tests
│       └── test_image_gen.py  # 42 auth/image-gen/admin/moderation tests
└── frontend/
    ├── vercel.json
    ├── .env.production        # VITE_API_BASE_URL=https://lyftr-ai-chatbot-1-k3zj.onrender.com
    └── src/
        ├── App.jsx            # 7-tab multi-panel app + auth state
        ├── api.js             # API client (auth, chat, image gen, admin, weather, crop)
        ├── components/
        │   ├── AuthModal.jsx
        │   ├── ImageGenerationPanel.jsx
        │   ├── AdminPanel.jsx
        │   ├── Sidebar.jsx
        │   ├── ChatArea.jsx
        │   ├── MessageInput.jsx
        │   ├── ImageAnalysisPanel.jsx
        │   ├── WeatherPanel.jsx
        │   ├── CropPanel.jsx
        │   ├── HistoryPanel.jsx
        │   ├── StatusBar.jsx
        │   └── ErrorNotification.jsx
        └── styles/App.css
```

---

## 3. Local Setup & Administrator Configuration

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
| `JWT_SECRET_KEY` | Secret key for HS256 JWT signing | *(required in prod)* |
| `ADMIN_EMAIL` | Initial administrator email (bootstrapped on startup) | *(optional)* |
| `ADMIN_PASSWORD` | Initial administrator password (bootstrapped on startup) | *(optional)* |
| `ENABLE_FAILURE_SIMULATION` | Enable `X-Simulate-Failure` header | `false` |

### Administrator Bootstrap
1. Set `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and `JWT_SECRET_KEY` in your `.env` (or Render dashboard).
2. Start the backend — `_bootstrap_admin()` automatically creates (or upgrades) the administrator account in SQLite on startup.
3. Public `POST /auth/register` always creates a standard `user` account and cannot create an admin.

### Running Locally

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

---

## 4. API Reference

### Authentication & User Profile
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | Public | Register a new `user` account, returns JWT |
| POST | `/auth/login` | Public | Login with email/password, returns JWT |
| GET | `/auth/me` | Bearer | Get current user profile & permissions |

### Image Generation
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/images/generate` | Bearer | Generate 1–4 images (checks global switch, daily limit, content policy) |
| GET | `/images/history` | Bearer | Get current user's generation history |
| GET | `/images/{image_id}` | Bearer | Get specific generation record (owner or admin only) |

### Administrator (Admin Role Required)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/admin/users` | Admin | List all users and their permissions |
| PATCH | `/admin/users/{user_id}/permissions` | Admin | Update role, active status, daily limit, allowed categories |
| PATCH | `/admin/settings/image-generation` | Admin | Toggle global image generation or default daily limit |
| GET | `/admin/settings` | Admin | View all global settings |
| GET | `/admin/audit-logs` | Admin | View permission/setting change audit log |
| GET | `/admin/image-generations` | Admin | View all users' image generation history |

### Chat, Analysis, Weather & Crops
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health, DB status, key count, cache |
| POST | `/chat` | Send message, receive AI response + metadata |
| GET / POST | `/sessions` | List or create chat sessions |
| GET | `/sessions/{session_id}/messages` | Session message history |
| POST | `/analyze-image` | Multipart upload → Gemini multimodal analysis |
| GET | `/weather?location=...` | Live weather (Open-Meteo) |
| POST | `/crop-recommend` | Scored crop recommendations |
| GET | `/history/activity` | Persisted analyses, weather, crop records |

---

## 5. Database Schema

SQLite (`lyftr.db`) with 9 tables initialized idempotently via `CREATE TABLE IF NOT EXISTS`:

| Table | Purpose |
|---|---|
| `sessions` | Chat sessions |
| `messages` | Chat messages with LiteLLM metadata |
| `image_analyses` | Gemini multimodal analysis results |
| `weather_queries` | Open-Meteo query results |
| `crop_recommendations` | Scored crop recommendation results |
| `users` | User accounts, password hashes, roles, active status, daily limits, allowed categories |
| `image_generations` | Image generation requests, metadata, CDN URLs, status |
| `app_settings` | Global settings (`image_generation_enabled`, default limits) |
| `audit_logs` | Administrator permission and setting change audit trail |

---

## 6. Testing

```bash
# Backend (85 tests: 35 chat/health + 8 weather/crop/analysis + 42 auth/image-gen/admin)
python -m pytest backend/tests -v

# Frontend production build
cd frontend && npm run build

# Playwright E2E (4 tests, Chromium)
cd frontend && npx playwright test
```

---

## 7. Deployment

### Backend on Render (`render.yaml`)
- Root Directory: `backend`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Required Render env vars: `LLM_API_KEYS`, `CORS_ORIGINS`, `JWT_SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`

### Frontend on Vercel (`frontend/vercel.json`)
- Root Directory: `frontend`
- `frontend/.env.production` sets `VITE_API_BASE_URL=https://lyftr-ai-chatbot-1-k3zj.onrender.com`
