"""Agent-related API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.base import CheckpointTuple
from sqlalchemy.orm import Session

from app.agents.chat_agent import create_chat_agent
from app.agents.checkpointer import SqlAlchemyCheckpointSaver
from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    ThreadHistoryResponse,
    ThreadListResponse,
    ThreadMessage,
    ThreadSummary,
)
from app.core.auth import get_current_user
from app.db.database import get_db
from app.repositories import ThreadRepository

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

    A client-supplied thread_id that doesn't belong to the caller is never
    trusted: ThreadRepository.get_or_create_owned silently mints a fresh
    thread instead, so a request always succeeds but never resumes or
    reveals another user's conversation.
    """
    thread = ThreadRepository(db).get_or_create_owned(request.thread_id, user["user_id"])

    agent = create_chat_agent(db=db, user_id=user["user_id"])
    state = {
        "messages": [HumanMessage(content=request.message)],
        "thread_id": thread.id,
        "user_id": user["user_id"],
    }

    result = agent.invoke(state, config={"configurable": {"thread_id": thread.id}})
    db.commit()
    final_message = result["messages"][-1]

    return ChatResponse(response=final_message.content, thread_id=result["thread_id"])


@router.get("/threads")
async def list_threads(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ThreadListResponse:
    """List the authenticated user's conversation threads, most recent first."""
    threads = ThreadRepository(db).list_for_user(user["user_id"])
    return ThreadListResponse(
        threads=[
            ThreadSummary(id=t.id, created_at=t.created_at, updated_at=t.updated_at)
            for t in threads
        ]
    )


@router.get("/threads/{thread_id}")
async def get_thread_history(
    thread_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ThreadHistoryResponse:
    """Fetch one thread's message history.

    Returns 404 both when the thread doesn't exist and when it belongs to
    a different user - never 403, so a caller can't distinguish "not
    yours" from "doesn't exist" and probe for valid thread_ids.
    """
    thread = ThreadRepository(db).get_by_id_for_user(thread_id, user["user_id"])
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    checkpoint_tuple = SqlAlchemyCheckpointSaver(db).get_tuple(
        {"configurable": {"thread_id": thread.id}}
    )
    messages = _render_messages(checkpoint_tuple)

    return ThreadHistoryResponse(id=thread.id, messages=messages)


def _render_messages(checkpoint_tuple: CheckpointTuple | None) -> list[ThreadMessage]:
    """Map a checkpoint's stored LangChain messages to user/agent turns.

    Mirrors what ChatWindow already renders: only human and AI messages
    are shown, tool-call/tool-result messages are internal detail.
    """
    if checkpoint_tuple is None:
        return []

    stored_messages = checkpoint_tuple.checkpoint["channel_values"].get("messages", [])
    rendered: list[ThreadMessage] = []
    for message in stored_messages:
        if isinstance(message, HumanMessage):
            rendered.append(ThreadMessage(role="user", text=str(message.content)))
        elif isinstance(message, AIMessage) and message.content:
            rendered.append(ThreadMessage(role="agent", text=str(message.content)))
    return rendered
