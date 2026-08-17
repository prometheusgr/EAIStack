"""API request/response schemas."""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    """Response body for chat endpoint."""

    response: str
    thread_id: str


class APIKeyCreate(BaseModel):
    """Request body for creating an API key."""

    name: str = Field(..., min_length=1, max_length=255)
    provider: str = Field(..., description="API provider (openai, anthropic, huggingface, custom)")
    secret_value: str = Field(..., min_length=1, description="The secret API key")


class APIKeyUpdate(BaseModel):
    """Request body for updating an API key (name/provider only, secret is immutable)."""

    name: str = Field(..., min_length=1, max_length=255)
    provider: str = Field(..., description="API provider (openai, anthropic, huggingface, custom)")


class APIKeyResponse(BaseModel):
    """Response body for API key (never includes full secret)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    provider: str
    secret_value_masked: str = Field(..., description="Masked version of the secret")
    created_at: datetime
    updated_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
