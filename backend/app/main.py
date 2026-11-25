"""
LYFTR AI - FastAPI Application (v3.0)
Full-featured backend: chat, image analysis, weather, crops,
image generation, authentication, and admin management.
"""

import os
import json
import logging
from contextlib import asynccontextmanager
from typing import Optional
from functools import wraps

from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, HTTPException, Header, Request, UploadFile, File, Form, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.database import (
    init_db, create_session, get_session, get_sessions,
    get_messages, save_message, update_session_title,
    save_image_analysis, get_image_analyses,
    save_weather_query, get_weather_queries,
    save_crop_recommendation, get_crop_recommendations,
    # Auth
    create_user, get_user_by_email, get_user_by_id, get_all_users,
    update_user_permissions, count_user_generations_today,
    # Image generation
    save_image_generation, get_user_image_generations,
    get_all_image_generations, get_image_generation,
    # Settings
    get_setting, set_setting, get_all_settings,
    # Audit
    save_audit_log, get_audit_logs,
)
from app.schemas import (
    ChatRequest, ChatResponse, ChatMessage, MessageMeta,
    SessionOut, HealthResponse, CropRecommendRequest,
    RegisterRequest, LoginRequest, TokenResponse, UserOut,
    ImageGenerateRequest, ImageGenerationOut,
    UpdateUserPermissionsRequest, UpdateImageSettingsRequest,
)
from app.chat_service import (
    get_ai_response, analyze_image_with_gemini,
    get_api_keys, ensure_cache, is_cache_enabled,
)
from app.weather_service import fetch_live_weather
from app.crop_service import recommend_crops
from app.auth_service import (
    create_access_token, decode_access_token,
    hash_password, verify_password,
)
from app.image_service import generate_images

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv(find_dotenv(usecwd=False))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
APP_VERSION = "3.0.0"

# ---------------------------------------------------------------------------
# Admin bootstrap helper
# ---------------------------------------------------------------------------

def _bootstrap_admin():
    """Create the initial admin user from environment variables if not exists."""
    admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
    if not admin_email or not admin_password:
        logger.info("ADMIN_EMAIL/ADMIN_PASSWORD not set — skipping admin bootstrap.")
        return
    existing = get_user_by_email(admin_email)
    if existing:
        # Ensure the bootstrapped admin has admin role
        if existing.get("role") != "admin":
            update_user_permissions(existing["id"], role="admin")
            logger.info("Upgraded existing user %s to admin.", admin_email)
        return
    pw_hash = hash_password(admin_password)
    user = create_user(email=admin_email, password_hash=pw_hash, role="admin")
    logger.info("Admin user bootstrapped: %s", admin_email)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database…")
    init_db()
    ensure_cache()
    _bootstrap_admin()
    logger.info("Database ready. API keys configured: %d", len(get_api_keys()))
    yield
    logger.info("Shutting down.")


# ---------------------------------------------------------------------------
# App & middleware
# ---------------------------------------------------------------------------

app = FastAPI(title="LYFTR AI API", version=APP_VERSION, lifespan=lifespan)

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
# Auth helpers / dependencies
# ---------------------------------------------------------------------------

security = HTTPBearer(auto_error=False)


def get_current_user_optional(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict | None:
    """Return the current user dict if a valid token is provided, else None."""
    if not credentials:
        return None
    payload = decode_access_token(credentials.credentials)
    if not payload:
        return None
    user = get_user_by_id(payload.get("sub", ""))
    if not user or not user.get("is_active"):
        return None
    return user


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Require a valid JWT token; raise 401 if missing or invalid."""
    user = get_current_user_optional(credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required. Please log in.")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require admin role; raise 403 otherwise."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user


def require_image_permission(user: dict = Depends(get_current_user)) -> dict:
    """Require that image generation is enabled globally and user has permission."""
    global_enabled = get_setting("image_generation_enabled", "true").lower() == "true"
    if not global_enabled:
        raise HTTPException(
            status_code=403,
            detail="Image generation is currently disabled by the administrator.",
        )
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="Your account is suspended.")
    return user


# ---------------------------------------------------------------------------
# Routes — Health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="ok",
        version=APP_VERSION,
        database="sqlite",
        keys_configured=len(get_api_keys()),
        cache_enabled=is_cache_enabled(),
    )


# ---------------------------------------------------------------------------
# Routes — Auth
# ---------------------------------------------------------------------------

@app.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest):
    """Register a new user (always gets 'user' role)."""
    existing = get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    pw_hash = hash_password(req.password)
    user = create_user(email=req.email, password_hash=pw_hash, role="user")
    token = create_access_token({"sub": user["id"], "email": user["email"], "role": user["role"]})
    return TokenResponse(
        access_token=token, user_id=user["id"],
        email=user["email"], role=user["role"],
    )


@app.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """Login with email/password, returns JWT."""
    user = get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="Your account has been suspended.")
    token = create_access_token({"sub": user["id"], "email": user["email"], "role": user["role"]})
    return TokenResponse(
        access_token=token, user_id=user["id"],
        email=user["email"], role=user["role"],
    )


@app.get("/auth/me", response_model=UserOut)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user profile."""
    import json as _json
    cats = current_user.get("allowed_categories", '["safe"]')
    if isinstance(cats, str):
        cats = _json.loads(cats)
    return UserOut(
        id=current_user["id"],
        email=current_user["email"],
        role=current_user["role"],
        is_active=bool(current_user.get("is_active", True)),
        daily_gen_limit=current_user.get("daily_gen_limit", 10),
        allowed_categories=cats,
        created_at=current_user["created_at"],
        updated_at=current_user["updated_at"],
    )


# ---------------------------------------------------------------------------
# Routes — Sessions (original, unchanged)
# ---------------------------------------------------------------------------

@app.get("/sessions", response_model=list[SessionOut])
async def list_sessions():
    return get_sessions()


@app.post("/sessions", response_model=SessionOut, status_code=201)
async def new_session():
    return create_session()


@app.get("/sessions/{session_id}/messages", response_model=list[ChatMessage])
async def session_messages(session_id: str):
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
        result.append(ChatMessage(
            id=m["id"], session_id=m["session_id"], role=m["role"],
            content=m["content"], meta=meta, created_at=m["created_at"],
        ))
    return result


# ---------------------------------------------------------------------------
# Routes — Chat (original, unchanged)
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure"),
):
    if req.session_id:
        session = get_session(req.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        session_id = req.session_id
        history = get_messages(session_id)
    else:
        session_id = None
        history = []

    system_content = (
        req.system_prompt.strip()
        if req.system_prompt and req.system_prompt.strip()
        else "You are LYFTR AI, a helpful, accurate, and concise assistant."
    )
    llm_messages = [{"role": "system", "content": system_content}]
    for m in history:
        if m["role"] in ("user", "assistant"):
            llm_messages.append({"role": m["role"], "content": m["content"]})
    llm_messages.append({"role": "user", "content": req.message})

    sim_enabled = os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true"
    effective_sim = x_simulate_failure if sim_enabled else None

    try:
        ai = await get_ai_response(llm_messages, model=req.model, simulate_failure=effective_sim)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not session_id:
        session = create_session(title=req.message[:50])
        session_id = session["id"]

    save_message(session_id=session_id, role="user", content=req.message)
    save_message(
        session_id=session_id, role="assistant", content=ai["content"],
        model=ai.get("model"), resolution_source=ai.get("resolution_source"),
        latency_ms=ai.get("latency_ms"), input_tokens=ai.get("input_tokens"),
        output_tokens=ai.get("output_tokens"), key_id=ai.get("key_id"),
        fallback_attempts=ai.get("fallback_attempts"),
    )

    if len(history) == 0:
        update_session_title(session_id, req.message[:50])

    return ChatResponse(
        session_id=session_id,
        reply=ai["content"],
        metadata=MessageMeta(
            resolution_source=ai.get("resolution_source"),
            model=ai.get("model"), latency_ms=ai.get("latency_ms"),
            input_tokens=ai.get("input_tokens"), output_tokens=ai.get("output_tokens"),
            key_id=ai.get("key_id"), fallback_attempts=ai.get("fallback_attempts"),
        ),
    )


# ---------------------------------------------------------------------------
# Routes — Multimodal Image Analysis (original, unchanged)
# ---------------------------------------------------------------------------

ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg": "image/jpeg", "image/jpg": "image/jpeg",
    "image/png": "image/png", "image/webp": "image/webp",
}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


@app.post("/analyze-image")
async def analyze_image(
    file: UploadFile = File(...),
    prompt: str = Form(""),
    session_id: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure"),
):
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
        mime_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                     ".png": "image/png", ".webp": "image/webp"}[ext]

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds maximum allowed size of {MAX_IMAGE_BYTES // (1024 * 1024)} MB.",
        )

    if session_id and not get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    sim_enabled = os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true"
    effective_sim = x_simulate_failure if sim_enabled else None

    try:
        ai = await analyze_image_with_gemini(
            image_bytes=image_bytes, mime_type=mime_type,
            prompt=prompt, model=model, simulate_failure=effective_sim,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    user_prompt = prompt.strip() or "Analyze attached image"
    saved_record = save_image_analysis(
        filename=filename, mime_type=mime_type, prompt=user_prompt,
        analysis=ai["content"], session_id=session_id,
        model=ai.get("model"), latency_ms=ai.get("latency_ms"), key_id=ai.get("key_id"),
    )

    if session_id:
        save_message(session_id=session_id, role="user",
                     content=f"[Image: {filename}] {user_prompt}")
        save_message(
            session_id=session_id, role="assistant", content=ai["content"],
            model=ai.get("model"), resolution_source=ai.get("resolution_source"),
            latency_ms=ai.get("latency_ms"), input_tokens=ai.get("input_tokens"),
            output_tokens=ai.get("output_tokens"), key_id=ai.get("key_id"),
            fallback_attempts=ai.get("fallback_attempts"),
        )

    return {
        "id": saved_record["id"], "session_id": session_id,
        "filename": filename, "mime_type": mime_type,
        "analysis": ai["content"], "cache_bypassed": True,
        "metadata": {
            "resolution_source": ai.get("resolution_source"),
            "model": ai.get("model"), "latency_ms": ai.get("latency_ms"),
            "input_tokens": ai.get("input_tokens"), "output_tokens": ai.get("output_tokens"),
            "key_id": ai.get("key_id"), "fallback_attempts": ai.get("fallback_attempts"),
        },
    }


# ---------------------------------------------------------------------------
# Routes — Weather & Crops (original, unchanged)
# ---------------------------------------------------------------------------

@app.get("/weather")
async def get_weather(
    location: str = Query(..., min_length=1, max_length=150),
    session_id: Optional[str] = Query(None),
):
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
        location=location, resolved_name=weather["resolved_name"],
        latitude=weather["latitude"], longitude=weather["longitude"],
        temperature_c=cur.get("temperature_c"), humidity_pct=cur.get("humidity_pct"),
        rainfall_mm=cur.get("rainfall_mm"), wind_speed_kmh=cur.get("wind_speed_kmh"),
        condition=cur.get("condition", "Unknown"), source=weather["source"],
        fetched_at=weather["fetched_at"], session_id=session_id,
    )
    return weather


@app.post("/crop-recommend")
async def crop_recommend(req: CropRecommendRequest):
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
                fc_rain = sum(d.get("precipitation_mm") or 0.0 for d in weather_used.get("forecast", []))
                cur_rain = weather_used["current"].get("rainfall_mm") or 0.0
                rain = round(max(fc_rain, cur_rain), 1)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))

    result = recommend_crops(
        location=weather_used["resolved_name"] if weather_used else req.location,
        soil_type=req.soil_type, soil_ph=req.soil_ph, season=req.season,
        temperature_c=temp, rainfall_mm=rain, irrigation=req.irrigation,
    )
    result["weather_used"] = weather_used

    save_crop_recommendation(
        location=result["location"], soil_type=req.soil_type, soil_ph=req.soil_ph,
        season=req.season, temperature_c=result["inputs_used"]["temperature_c"],
        rainfall_mm=result["inputs_used"]["rainfall_mm"],
        irrigation=result["inputs_used"]["irrigation"],
        recommendations_json=json.dumps(result["recommendations"]),
        assumptions_json=json.dumps(result["assumptions"]),
        session_id=req.session_id,
    )
    return result


@app.get("/history/activity")
async def activity_history(
    session_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    return {
        "image_analyses": get_image_analyses(session_id=session_id, limit=limit),
        "weather_queries": get_weather_queries(session_id=session_id, limit=limit),
        "crop_recommendations": get_crop_recommendations(session_id=session_id, limit=limit),
    }


# ---------------------------------------------------------------------------
# Routes — Image Generation
# ---------------------------------------------------------------------------

@app.post("/images/generate")
async def generate_image_endpoint(
    req: ImageGenerateRequest,
    current_user: dict = Depends(require_image_permission),
):
    """Generate AI images. Requires authentication and image generation permission."""
    import json as _json

    # Check daily limit (0 means image generation is blocked for this user)
    user_limit = current_user.get("daily_gen_limit", 10)
    if user_limit is not None and user_limit >= 0:
        today_count = count_user_generations_today(current_user["id"])
        if today_count >= user_limit:
            raise HTTPException(
                status_code=429,
                detail=f"Daily generation limit reached ({user_limit} per day). Try again tomorrow.",
            )

    # Get user's allowed categories
    allowed_cats_raw = current_user.get("allowed_categories", '["safe"]')
    if isinstance(allowed_cats_raw, str):
        try:
            allowed_cats = _json.loads(allowed_cats_raw)
        except Exception:
            allowed_cats = ["safe"]
    else:
        allowed_cats = allowed_cats_raw or ["safe"]

    # Generate
    status = "success"
    error_message = None
    result = None

    try:
        result = await generate_images(
            prompt=req.prompt,
            style=req.style,
            aspect_ratio=req.aspect_ratio,
            num_images=req.num_images,
            user_role=current_user.get("role", "user"),
            allowed_categories=allowed_cats,
        )
    except PermissionError as e:
        status = "blocked"
        error_message = str(e)
        # Still record blocked attempts
        saved = save_image_generation(
            user_id=current_user["id"], prompt=req.prompt, style=req.style,
            aspect_ratio=req.aspect_ratio, num_images=req.num_images,
            images_json="[]", provider="pollinations.ai", model="flux",
            latency_ms=None, status=status, error_message=error_message,
        )
        raise HTTPException(status_code=403, detail=error_message)
    except (ValueError, RuntimeError) as e:
        status = "failed"
        error_message = str(e)
        saved = save_image_generation(
            user_id=current_user["id"], prompt=req.prompt, style=req.style,
            aspect_ratio=req.aspect_ratio, num_images=req.num_images,
            images_json="[]", provider="pollinations.ai", model="flux",
            latency_ms=None, status=status, error_message=error_message,
        )
        raise HTTPException(status_code=503 if "timed out" in error_message.lower() else 400,
                            detail=error_message)

    # Save successful generation
    images = result.get("images", [])
    latency = max((img.get("latency_ms", 0) for img in images), default=None)
    provider = images[0].get("provider", "pollinations.ai") if images else "pollinations.ai"
    model = images[0].get("model", "flux") if images else "flux"

    saved = save_image_generation(
        user_id=current_user["id"], prompt=req.prompt, style=req.style,
        aspect_ratio=req.aspect_ratio, num_images=req.num_images,
        images_json=_json.dumps(images), provider=provider, model=model,
        latency_ms=latency, status=status, error_message=None,
    )

    return {
        "id": saved["id"],
        "prompt": req.prompt,
        "style": req.style,
        "aspect_ratio": req.aspect_ratio,
        "num_images": req.num_images,
        "images": images,
        "provider": provider,
        "model": model,
        "latency_ms": latency,
        "status": status,
        "created_at": saved["created_at"],
        "total_generated": result.get("total_generated", len(images)),
        "total_requested": result.get("total_requested", req.num_images),
        "errors": result.get("errors", []),
    }


@app.get("/images/history")
async def image_history(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """Get image generation history for the current user."""
    import json as _json
    records = get_user_image_generations(current_user["id"], limit=limit, offset=offset)
    for r in records:
        if isinstance(r.get("images_json"), str):
            try:
                r["images"] = _json.loads(r["images_json"])
            except Exception:
                r["images"] = []
        del r["images_json"]
    return records


@app.get("/images/{image_id}")
async def get_image(
    image_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a specific image generation record."""
    import json as _json
    record = get_image_generation(image_id)
    if not record:
        raise HTTPException(status_code=404, detail="Image generation record not found.")
    # Users can only see their own; admins can see all
    if record["user_id"] != current_user["id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied.")
    if isinstance(record.get("images_json"), str):
        try:
            record["images"] = _json.loads(record["images_json"])
        except Exception:
            record["images"] = []
    return record


# ---------------------------------------------------------------------------
# Routes — Admin
# ---------------------------------------------------------------------------

@app.get("/admin/users")
async def admin_list_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(require_admin),
):
    """List all users (admin only)."""
    import json as _json
    users = get_all_users(limit=limit, offset=offset)
    for u in users:
        cats = u.get("allowed_categories", '["safe"]')
        if isinstance(cats, str):
            try:
                u["allowed_categories"] = _json.loads(cats)
            except Exception:
                u["allowed_categories"] = ["safe"]
    return users


@app.patch("/admin/users/{user_id}/permissions")
async def admin_update_user(
    user_id: str,
    req: UpdateUserPermissionsRequest,
    admin: dict = Depends(require_admin),
):
    """Update user role, status, or generation limits (admin only)."""
    # Prevent admin from demoting themselves
    if user_id == admin["id"] and req.role and req.role != "admin":
        raise HTTPException(status_code=400, detail="Administrators cannot demote themselves.")

    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    updated = update_user_permissions(
        user_id=user_id,
        role=req.role,
        is_active=req.is_active,
        daily_gen_limit=req.daily_gen_limit,
        allowed_categories=req.allowed_categories,
    )

    # Audit log
    changes = []
    if req.role is not None:
        changes.append(f"role: {target['role']} → {req.role}")
    if req.is_active is not None:
        changes.append(f"is_active: {bool(target.get('is_active'))} → {req.is_active}")
    if req.daily_gen_limit is not None:
        changes.append(f"daily_gen_limit: {target.get('daily_gen_limit')} → {req.daily_gen_limit}")
    if req.allowed_categories is not None:
        changes.append(f"allowed_categories: {req.allowed_categories}")

    save_audit_log(
        admin_id=admin["id"],
        action="update_user_permissions",
        target_user_id=user_id,
        details=f"Changed: {'; '.join(changes)}",
    )

    import json as _json
    if updated:
        cats = updated.get("allowed_categories", '["safe"]')
        if isinstance(cats, str):
            try:
                updated["allowed_categories"] = _json.loads(cats)
            except Exception:
                updated["allowed_categories"] = ["safe"]
    return updated


@app.patch("/admin/settings/image-generation")
async def admin_update_image_settings(
    req: UpdateImageSettingsRequest,
    admin: dict = Depends(require_admin),
):
    """Update global image generation settings (admin only)."""
    changes = []
    if req.image_generation_enabled is not None:
        value = "true" if req.image_generation_enabled else "false"
        set_setting("image_generation_enabled", value, updated_by=admin["id"])
        changes.append(f"image_generation_enabled={value}")

    if req.image_generation_allowed_categories is not None:
        import json as _json
        value = _json.dumps(req.image_generation_allowed_categories)
        set_setting("image_generation_allowed_categories", value, updated_by=admin["id"])
        changes.append(f"allowed_categories={value}")

    if req.image_generation_default_daily_limit is not None:
        value = str(req.image_generation_default_daily_limit)
        set_setting("image_generation_default_daily_limit", value, updated_by=admin["id"])
        changes.append(f"default_daily_limit={value}")

    save_audit_log(
        admin_id=admin["id"],
        action="update_image_settings",
        details=f"Changed: {'; '.join(changes)}",
    )

    return get_all_settings()


@app.get("/admin/settings")
async def admin_get_settings(admin: dict = Depends(require_admin)):
    """Get all application settings (admin only)."""
    return get_all_settings()


@app.get("/admin/audit-logs")
async def admin_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(require_admin),
):
    """Get admin audit logs (admin only)."""
    return get_audit_logs(limit=limit, offset=offset)


@app.get("/admin/image-generations")
async def admin_all_generations(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(require_admin),
):
    """Get all image generations across all users (admin only)."""
    import json as _json
    records = get_all_image_generations(limit=limit, offset=offset)
    for r in records:
        if isinstance(r.get("images_json"), str):
            try:
                r["images"] = _json.loads(r["images_json"])
            except Exception:
                r["images"] = []
    return records
