"""Agent-related API endpoints."""

import uuid

from fastapi import APIRouter, Depends
from langchain_core.messages import HumanMessage
from sqlalchemy.orm import Session

from app.agents.chat_agent import create_chat_agent
from app.api.schemas import ChatRequest, ChatResponse
from app.core.auth import get_current_user
from app.db.database import get_db

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Chat with the agent.

    Requires authentication via Keycloak bearer token.
    Streaming is deferred to a future phase.
    """
    thread_id = request.thread_id or str(uuid.uuid4())

    agent = create_chat_agent(db=db, user_id=user["user_id"])
    state = {
        "messages": [HumanMessage(content=request.message)],
        "thread_id": thread_id,
        "user_id": user["user_id"],
    }

    result = agent.invoke(state)
    final_message = result["messages"][-1]

    return ChatResponse(response=final_message.content, thread_id=result["thread_id"])
