"""
LYFTR AI Chatbot - FastAPI Application
Main entry point for the backend server.
"""

import os
import json
import logging
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, HTTPException, Header, Request, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware

from app.database import (
    init_db, create_session, get_session, get_sessions,
    get_messages, save_message, update_session_title,
    save_image_analysis, get_image_analyses,
    save_weather_query, get_weather_queries,
    save_crop_recommendation, get_crop_recommendations,
)
from app.schemas import (
    ChatRequest, ChatResponse, ChatMessage, MessageMeta,
    SessionOut, HealthResponse, CropRecommendRequest,
)
from app.chat_service import (
    get_ai_response, analyze_image_with_gemini,
    get_api_keys, ensure_cache, is_cache_enabled,
)
from app.weather_service import fetch_live_weather
from app.crop_service import recommend_crops

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


# ---- Multimodal Image Analysis ---------------------------------------------

ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/png": "image/png",
    "image/webp": "image/webp",
}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


@app.post("/analyze-image")
async def analyze_image(
    file: UploadFile = File(...),
    prompt: str = Form(""),
    session_id: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure"),
):
    """Analyze an uploaded JPG/JPEG/PNG/WEBP image with multimodal Gemini (bypasses text cache)."""
    filename = file.filename or "upload"
    ext = os.path.splitext(filename.lower())[1]
    content_type = (file.content_type or "").lower().split(";")[0].strip()

    if ext not in ALLOWED_IMAGE_EXTENSIONS and content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported image format. Please upload a JPG, JPEG, PNG, or WEBP file.",
        )

    mime_type = ALLOWED_IMAGE_MIME_TYPES.get(content_type)
    if not mime_type:
        mime_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }[ext]

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds maximum allowed size of {MAX_IMAGE_BYTES // (1024 * 1024)} MB.",
        )

    if session_id:
        if not get_session(session_id):
            raise HTTPException(status_code=404, detail="Session not found")

    sim_enabled = os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true"
    effective_sim = x_simulate_failure if sim_enabled else None

    try:
        ai = await analyze_image_with_gemini(
            image_bytes=image_bytes,
            mime_type=mime_type,
            prompt=prompt,
            model=model,
            simulate_failure=effective_sim,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    user_prompt = prompt.strip() or "Analyze attached image"
    saved_record = save_image_analysis(
        filename=filename,
        mime_type=mime_type,
        prompt=user_prompt,
        analysis=ai["content"],
        session_id=session_id,
        model=ai.get("model"),
        latency_ms=ai.get("latency_ms"),
        key_id=ai.get("key_id"),
    )

    if session_id:
        save_message(
            session_id=session_id,
            role="user",
            content=f"[Image: {filename}] {user_prompt}",
        )
        save_message(
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

    return {
        "id": saved_record["id"],
        "session_id": session_id,
        "filename": filename,
        "mime_type": mime_type,
        "analysis": ai["content"],
        "cache_bypassed": True,
        "metadata": {
            "resolution_source": ai.get("resolution_source"),
            "model": ai.get("model"),
            "latency_ms": ai.get("latency_ms"),
            "input_tokens": ai.get("input_tokens"),
            "output_tokens": ai.get("output_tokens"),
            "key_id": ai.get("key_id"),
            "fallback_attempts": ai.get("fallback_attempts"),
        },
    }


# ---- Live Weather ----------------------------------------------------------

@app.get("/weather")
async def get_weather(
    location: str = Query(..., min_length=1, max_length=150),
    session_id: Optional[str] = Query(None),
):
    """Fetch live weather and 5-day forecast from Open-Meteo and log the query."""
    if session_id and not get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        weather = await fetch_live_weather(location)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    cur = weather["current"]
    save_weather_query(
        location=location,
        resolved_name=weather["resolved_name"],
        latitude=weather["latitude"],
        longitude=weather["longitude"],
        temperature_c=cur.get("temperature_c"),
        humidity_pct=cur.get("humidity_pct"),
        rainfall_mm=cur.get("rainfall_mm"),
        wind_speed_kmh=cur.get("wind_speed_kmh"),
        condition=cur.get("condition", "Unknown"),
        source=weather["source"],
        fetched_at=weather["fetched_at"],
        session_id=session_id,
    )
    return weather


# ---- Crop Recommendation Engine -------------------------------------------

@app.post("/crop-recommend")
async def crop_recommend(req: CropRecommendRequest):
    """Recommend suitable crops using live weather (if location provided) and soil/season inputs."""
    if req.session_id and not get_session(req.session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    weather_used = None
    temp = req.temperature_c
    rain = req.rainfall_mm

    if req.location and req.location.strip() and (temp is None or rain is None):
        try:
            weather_used = await fetch_live_weather(req.location.strip())
            if temp is None:
                temp = weather_used["current"].get("temperature_c")
            if rain is None:
                # Use 5-day forecast precipitation sum or current rainfall when available
                fc_rain = sum(
                    d.get("precipitation_mm") or 0.0
                    for d in weather_used.get("forecast", [])
                )
                cur_rain = weather_used["current"].get("rainfall_mm") or 0.0
                rain = round(max(fc_rain, cur_rain), 1)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))

    result = recommend_crops(
        location=weather_used["resolved_name"] if weather_used else req.location,
        soil_type=req.soil_type,
        soil_ph=req.soil_ph,
        season=req.season,
        temperature_c=temp,
        rainfall_mm=rain,
        irrigation=req.irrigation,
    )
    result["weather_used"] = weather_used

    save_crop_recommendation(
        location=result["location"],
        soil_type=req.soil_type,
        soil_ph=req.soil_ph,
        season=req.season,
        temperature_c=result["inputs_used"]["temperature_c"],
        rainfall_mm=result["inputs_used"]["rainfall_mm"],
        irrigation=result["inputs_used"]["irrigation"],
        recommendations_json=json.dumps(result["recommendations"]),
        assumptions_json=json.dumps(result["assumptions"]),
        session_id=req.session_id,
    )
    return result


# ---- Activity History (SQLite Persistence Inspection) ---------------------

@app.get("/history/activity")
async def activity_history(
    session_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Return persisted image analyses, weather queries, and crop recommendations."""
    return {
        "image_analyses": get_image_analyses(session_id=session_id, limit=limit),
        "weather_queries": get_weather_queries(session_id=session_id, limit=limit),
        "crop_recommendations": get_crop_recommendations(session_id=session_id, limit=limit),
    }
