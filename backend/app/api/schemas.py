"""API request/response schemas."""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    """Response body for chat endpoint."""

    response: str
    thread_id: str
