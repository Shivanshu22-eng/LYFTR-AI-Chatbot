"""
LYFTR AI Chatbot - Pydantic Schemas
Request/response models for the API.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional


class ChatRequest(BaseModel):
    """Request body for the POST /chat endpoint."""
    session_id: str = Field(..., min_length=1, max_length=128, description="Session ID (1-128 chars)")
    message: str = Field(..., description="User message content (1-4000 chars after trimming)")
    system_prompt: Optional[str] = Field(None, max_length=4000, description="Optional custom system prompt")
    model: Optional[str] = Field(None, description="LiteLLM model identifier override")

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
    """Metadata about an AI response."""
    resolution_source: Literal["LIVE_INFERENCE", "LLM_CACHE"]
    model: Optional[str] = None
    latency_ms: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    key_id: Optional[str] = None
    fallback_attempts: Optional[int] = None


class ChatMessage(BaseModel):
    """A single chat message."""
    id: str
    session_id: str
    role: str
    content: str
    meta: Optional[MessageMeta] = None
    created_at: str


class ChatResponse(BaseModel):
    """Response from the POST /chat endpoint."""
    session_id: str
    reply: str
    metadata: MessageMeta


class SessionOut(BaseModel):
    """Public session representation."""
    id: str
    title: str
    created_at: str
    updated_at: str


class HealthResponse(BaseModel):
    """Response for the GET /health endpoint."""
    status: str
    keys_configured: int
    cache_enabled: bool
    version: Optional[str] = None
    database: Optional[str] = None


class CropRecommendRequest(BaseModel):
    """Request body for the POST /crop-recommend endpoint."""
    session_id: Optional[str] = Field(None, max_length=128)
    location: Optional[str] = Field(None, max_length=150)
    soil_type: Optional[str] = Field(None, max_length=64)
    soil_ph: Optional[float] = Field(None, ge=0.0, le=14.0)
    season: Optional[str] = Field(None, max_length=32)
    temperature_c: Optional[float] = Field(None, ge=-40.0, le=60.0)
    rainfall_mm: Optional[float] = Field(None, ge=0.0, le=5000.0)
    irrigation: Optional[str] = Field(None, max_length=32)
