"""
LYFTR AI Chatbot - FastAPI Application
Main entry point for the backend server.
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware

from app.database import (
    init_db, create_session, get_session, get_sessions,
    get_messages, save_message, update_session_title,
)
from app.schemas import (
    ChatRequest, ChatResponse, ChatMessage, MessageMeta,
    SessionOut, HealthResponse,
)
from app.chat_service import get_ai_response, get_api_keys, ensure_cache, is_cache_enabled

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv(find_dotenv(usecwd=False))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

APP_VERSION = "0.2.0"

# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup."""
    logger.info("Initializing database…")
    init_db()
    ensure_cache()
    logger.info("Database ready. API keys configured: %d", len(get_api_keys()))
    yield
    logger.info("Shutting down.")


# ---------------------------------------------------------------------------
# App & middleware
# ---------------------------------------------------------------------------

app = FastAPI(
    title="LYFTR AI Chatbot API",
    version=APP_VERSION,
    lifespan=lifespan,
)

CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        version=APP_VERSION,
        database="sqlite",
        keys_configured=len(get_api_keys()),
        cache_enabled=is_cache_enabled(),
    )


# ---- Sessions -------------------------------------------------------------

@app.get("/sessions", response_model=list[SessionOut])
async def list_sessions():
    """List all chat sessions."""
    return get_sessions()


@app.post("/sessions", response_model=SessionOut, status_code=201)
async def new_session():
    """Create a new chat session."""
    return create_session()


# ---- Messages --------------------------------------------------------------

@app.get("/sessions/{session_id}/messages", response_model=list[ChatMessage])
async def session_messages(session_id: str):
    """Retrieve all messages for a given session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    raw = get_messages(session_id)
    result = []
    for m in raw:
        meta = None
        if m["role"] == "assistant":
            meta = MessageMeta(
                resolution_source=m.get("resolution_source"),
                model=m.get("model"),
                latency_ms=m.get("latency_ms"),
                input_tokens=m.get("input_tokens"),
                output_tokens=m.get("output_tokens"),
                key_id=m.get("key_id"),
                fallback_attempts=m.get("fallback_attempts"),
            )
        result.append(
            ChatMessage(
                id=m["id"],
                session_id=m["session_id"],
                role=m["role"],
                content=m["content"],
                meta=meta,
                created_at=m["created_at"],
            )
        )
    return result


# ---- Chat ------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure"),
):
    """Send a message and receive an AI response."""
    # Resolve existing session (404 if unknown) or defer creation until AI succeeds
    if req.session_id:
        session = get_session(req.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        session_id = req.session_id
        history = get_messages(session_id)
    else:
        session_id = None
        history = []

    # Build conversation history in memory before persisting
    system_content = (
        req.system_prompt.strip()
        if req.system_prompt and req.system_prompt.strip()
        else "You are LYFTR AI, a helpful, accurate, and concise assistant."
    )
    llm_messages = [
        {"role": "system", "content": system_content},
    ]
    for m in history:
        if m["role"] in ("user", "assistant"):
            llm_messages.append({"role": m["role"], "content": m["content"]})
    llm_messages.append({"role": "user", "content": req.message})

    # Only accept X-Simulate-Failure when ENABLE_FAILURE_SIMULATION=true
    sim_enabled = os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true"
    effective_sim = x_simulate_failure if sim_enabled else None

    # Get AI response (with optional simulated failure) — do not persist if this fails
    try:
        ai = await get_ai_response(
            llm_messages,
            model=req.model,
            simulate_failure=effective_sim,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Persist session (if new), user message, and assistant message only after success
    if not session_id:
        session = create_session(title=req.message[:50])
        session_id = session["id"]

    save_message(session_id=session_id, role="user", content=req.message)

    saved = save_message(
        session_id=session_id,
        role="assistant",
        content=ai["content"],
        model=ai.get("model"),
        resolution_source=ai.get("resolution_source"),
        latency_ms=ai.get("latency_ms"),
        input_tokens=ai.get("input_tokens"),
        output_tokens=ai.get("output_tokens"),
        key_id=ai.get("key_id"),
        fallback_attempts=ai.get("fallback_attempts"),
    )

    # Auto-title on first exchange
    if len(history) == 0:
        update_session_title(session_id, req.message[:50])

    return ChatResponse(
        session_id=session_id,
        reply=ai["content"],
        metadata=MessageMeta(
            resolution_source=ai.get("resolution_source"),
            model=ai.get("model"),
            latency_ms=ai.get("latency_ms"),
            input_tokens=ai.get("input_tokens"),
            output_tokens=ai.get("output_tokens"),
            key_id=ai.get("key_id"),
            fallback_attempts=ai.get("fallback_attempts"),
        ),
    )
