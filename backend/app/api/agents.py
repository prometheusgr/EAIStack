"""Agent-related API endpoints."""

import uuid

from fastapi import APIRouter, Depends

from app.agents.chat_agent import create_chat_agent
from app.api.schemas import ChatRequest, ChatResponse
from app.core.auth import get_current_user

router = APIRouter(prefix="/api/agents", tags=["agents"])

_agent = create_chat_agent()


@router.post("/chat")
async def chat(request: ChatRequest, user: dict = Depends(get_current_user)) -> ChatResponse:
    """Chat with the agent.

    Requires authentication via Keycloak bearer token.
    """
    thread_id = request.thread_id or str(uuid.uuid4())

    state = {
        "user_message": request.message,
        "thread_id": thread_id,
        "tool_result": None,
        "response": None,
    }

    result = _agent.invoke(state)

    return ChatResponse(response=result["response"], thread_id=result["thread_id"])
