"""Agent-related API endpoints."""

import uuid
from functools import lru_cache

from fastapi import APIRouter, Depends

from app.agents.chat_agent import create_chat_agent
from app.api.schemas import ChatRequest, ChatResponse
from app.core.auth import get_current_user

router = APIRouter(prefix="/api/agents", tags=["agents"])


@lru_cache
def get_chat_agent():
    """Provide the compiled chat agent, built on first request.

    Cached so the LangGraph graph (and any real LLM client it binds) is
    constructed lazily rather than at module import time, and can be
    overridden in tests via app.dependency_overrides.
    """
    return create_chat_agent()


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user: dict = Depends(get_current_user),
    agent=Depends(get_chat_agent),
) -> ChatResponse:
    """Chat with the agent.

    Requires authentication via Keycloak bearer token.
    Streaming is deferred to a future phase.
    """
    thread_id = request.thread_id or str(uuid.uuid4())

    state = {
        "user_message": request.message,
        "thread_id": thread_id,
        "tool_result": None,
        "response": None,
    }

    result = agent.invoke(state)

    return ChatResponse(response=result["response"], thread_id=result["thread_id"])
