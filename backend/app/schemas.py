"""
LYFTR AI Chatbot - Pydantic Schemas
Request/response models for the API (original + new auth/image-gen/admin).
"""

from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import Literal, Optional, List
import json


# ===========================================================================
# Original schemas (preserved unchanged)
# ===========================================================================

class ChatRequest(BaseModel):
    """Request body for the POST /chat endpoint."""
    session_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., description="User message content (1-4000 chars after trimming)")
    system_prompt: Optional[str] = Field(None, max_length=4000)
    model: Optional[str] = Field(None)

    @field_validator("message")
    @classmethod
    def message_must_be_valid_length(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Message must not be empty or whitespace only")
        if len(trimmed) > 4000:
            raise ValueError("Message must not exceed 4000 characters after trimming")
        return trimmed

    @field_validator("session_id")
    @classmethod
    def session_id_must_be_valid_length(cls, v: str) -> str:
        if not v.strip() or len(v) > 128:
            raise ValueError("session_id must be between 1 and 128 characters")
        return v


class MessageMeta(BaseModel):
    resolution_source: Literal["LIVE_INFERENCE", "LLM_CACHE"]
    model: Optional[str] = None
    latency_ms: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    key_id: Optional[str] = None
    fallback_attempts: Optional[int] = None


class ChatMessage(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    meta: Optional[MessageMeta] = None
    created_at: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: MessageMeta


class SessionOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class HealthResponse(BaseModel):
    status: str
    keys_configured: int
    cache_enabled: bool
    version: Optional[str] = None
    database: Optional[str] = None


class CropRecommendRequest(BaseModel):
    session_id: Optional[str] = Field(None, max_length=128)
    location: Optional[str] = Field(None, max_length=150)
    soil_type: Optional[str] = Field(None, max_length=64)
    soil_ph: Optional[float] = Field(None, ge=0.0, le=14.0)
    season: Optional[str] = Field(None, max_length=32)
    temperature_c: Optional[float] = Field(None, ge=-40.0, le=60.0)
    rainfall_mm: Optional[float] = Field(None, ge=0.0, le=5000.0)
    irrigation: Optional[str] = Field(None, max_length=32)


# ===========================================================================
# Auth schemas
# ===========================================================================

class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    role: str


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    daily_gen_limit: int
    allowed_categories: List[str] = ["safe"]
    created_at: str
    updated_at: str


# ===========================================================================
# Image generation schemas
# ===========================================================================

VALID_STYLES = [
    "photorealistic", "cinematic", "anime", "digital_art", "3d_rendering",
    "illustration", "watercolor", "fantasy", "architecture", "product_photography",
]
VALID_RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:2"]


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    style: str = Field("photorealistic")
    aspect_ratio: str = Field("1:1")
    num_images: int = Field(1, ge=1, le=4)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Prompt must not be empty")
        return trimmed

    @field_validator("style")
    @classmethod
    def validate_style(cls, v: str) -> str:
        if v not in VALID_STYLES:
            return "photorealistic"
        return v

    @field_validator("aspect_ratio")
    @classmethod
    def validate_ratio(cls, v: str) -> str:
        if v not in VALID_RATIOS:
            return "1:1"
        return v


class ImageGenerationOut(BaseModel):
    id: str
    prompt: str
    style: str
    aspect_ratio: str
    num_images: int
    images: List[dict]
    provider: str
    model: str
    latency_ms: Optional[float] = None
    status: str
    error_message: Optional[str] = None
    created_at: str


# ===========================================================================
# Admin schemas
# ===========================================================================

class UpdateUserPermissionsRequest(BaseModel):
    role: Optional[Literal["user", "authorized_creator", "admin"]] = None
    is_active: Optional[bool] = None
    daily_gen_limit: Optional[int] = Field(None, ge=0, le=1000)
    allowed_categories: Optional[List[str]] = None

    @field_validator("allowed_categories")
    @classmethod
    def validate_categories(cls, v):
        if v is None:
            return v
        valid = {"safe", "adult", "violent", "disturbing"}
        invalid = set(v) - valid
        if invalid:
            raise ValueError(f"Invalid categories: {invalid}. Must be one of {valid}")
        return v


class UpdateImageSettingsRequest(BaseModel):
    image_generation_enabled: Optional[bool] = None
    image_generation_allowed_categories: Optional[List[str]] = None
    image_generation_default_daily_limit: Optional[int] = Field(None, ge=0, le=1000)
