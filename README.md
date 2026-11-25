# LYFTR AI Chatbot

A full-stack AI chatbot application powered by **React + Vite**, **FastAPI**, **SQLite**, and **LiteLLM** with multi-key Gemini failover, built-in response caching, and per-response observability.

---

## 1. Overview & Architecture

- **Frontend**: React 18 + Vite SPA with a dark navy and white UI, session sidebar, typing indicator, error toast notifications, live backend health indicator, and per-message metadata badges (`source`, `model`, `latency_ms`, `input_tokens`, `output_tokens`, `key_id`, `fallback_attempts`).
- **Backend**: Python + FastAPI REST API with Pydantic request validation, SQLite persistence (`sessions` and `messages` tables), and LiteLLM integration.
- **Resilience & Caching**:
  - Rotates across multiple API keys configured via `LLM_API_KEYS`.
  - Automatically fails over on `429`, quota/rate-limit, and `5xx` errors while redacting raw keys from all logs and responses.
  - Enables LiteLLM local in-memory caching and reports `LIVE_INFERENCE` vs `LLM_CACHE`.
  - Supports `X-Simulate-Failure` header testing while bypassing cache.

---

## 2. Project Structure

```
LYFTR-AI-Chatbot/
├── .env.example
├── .gitignore
├── Makefile
├── README.md
├── docker-compose.yml
├── render.yaml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI app, routes, lifespan
│   │   ├── database.py      # SQLite auto-init & CRUD
│   │   ├── schemas.py       # Pydantic models & validation
│   │   └── chat_service.py  # LiteLLM multi-key failover & caching
│   └── tests/
│       └── test_health.py   # Automated pytest suite
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── vercel.json
    ├── package.json
    ├── vite.config.js
    ├── index.html
    ├── public/
    │   └── lyftr-icon.svg
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── api.js
        ├── components/
        │   ├── Sidebar.jsx
        │   ├── ChatArea.jsx
        │   ├── MessageInput.jsx
        │   ├── StatusBar.jsx
        │   └── ErrorNotification.jsx
        └── styles/
            ├── index.css
            └── App.css
```

---

## 3. Local Setup & Development

### Environment Variables

Copy `.env.example` to `.env` in the repository root and configure your keys:

```bash
cp .env.example .env
```

Key variables:
- `LLM_API_KEYS`: Comma-separated list of Gemini/OpenAI API keys (e.g. `key1,key2`) for automatic failover.
- `LITELLM_MODEL`: Model identifier (default `gemini/gemini-3.5-flash-lite`).
- `DATABASE_PATH`: Path to the SQLite database file (default `./lyftr.db`).
- `CORS_ORIGINS`: Comma-separated allowed frontend origins.

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows (or source venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

---

## 4. Docker & Makefile Usage

Ensure `.env` exists in the project root, then run:

```bash
make up      # Build and start backend + frontend containers
make down    # Stop and remove containers (preserves SQLite volume)
make logs    # Tail container logs
```

- **SQLite Persistence**: `docker-compose.yml` mounts a named Docker volume `lyftr_sqlite_data` at `/data` (`DATABASE_PATH=/data/lyftr.db`) so chat history persists across container restarts.
- **Ports**: Frontend on `http://localhost:3000`, Backend on `http://localhost:8000`.

---

## 5. API Reference & Testing

### Endpoints

| Method | Path                              | Description                          |
| ------ | --------------------------------- | ------------------------------------ |
| GET    | `/health`                         | Health, DB, key count, cache status  |
| POST   | `/chat`                           | Send message and receive AI response |
| GET    | `/sessions`                       | List all chat sessions               |
| POST   | `/sessions`                       | Create a new chat session            |
| GET    | `/sessions/{session_id}/messages` | Retrieve session message history     |

### Failure Simulation Header

Send `X-Simulate-Failure` on `POST /chat` to test failover without hitting cache:
- `429`, `rate_limit`, `quota`, `500`, `502`, `503`, `5xx`: Simulates a failure on the first key and fails over to the next key.
- `all_keys_fail`: Exhausts all keys and returns HTTP `502`.

### Running Tests & Production Build

```bash
# Backend automated tests
cd backend
pytest -v

# Frontend production build
cd frontend
npm run build
```

---

## 6. Deployment (Vercel & Render)

### Backend on Render (`render.yaml`)
1. Connect your repository to Render using `render.yaml` (Blueprint) or create a Python Web Service with root directory `backend`.
2. Set `LLM_API_KEYS` in Render's environment variables and update `CORS_ORIGINS` to your Vercel URL.
3. Render mounts the persistent disk at `/data` for SQLite and checks `/health`.

### Frontend on Vercel (`frontend/vercel.json`)
1. Import the repository in Vercel with Root Directory set to `frontend`.
2. Set environment variable `VITE_API_BASE_URL` to your deployed Render backend URL (e.g. `https://lyftr-ai-chatbot-backend.onrender.com`).
3. Deploy — Vercel uses `npm run build` and outputs `dist` with SPA rewrites configured in `frontend/vercel.json`.
