"""LangGraph agent for chat interactions."""

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from sqlalchemy.orm import Session

from app.agents.checkpointer import SqlAlchemyCheckpointSaver
from app.core.llm_client import get_llm_client
from app.mcp_client import make_search_knowledge_base_tool
from app.prompts.chat_prompts import CHAT_AGENT_SYSTEM_PROMPT

MAX_TOOL_CALL_ROUNDS = 5


class ChatState(TypedDict):
    """State for the chat agent."""

    messages: Annotated[list[AnyMessage], add_messages]
    thread_id: str
    user_id: str


def _last_ai_message_has_tool_calls(state: ChatState) -> bool:
    last_message = state["messages"][-1]
    return isinstance(last_message, AIMessage) and bool(last_message.tool_calls)


def _count_tool_call_rounds(state: ChatState) -> int:
    return sum(
        1 for message in state["messages"] if isinstance(message, AIMessage) and message.tool_calls
    )


def create_chat_agent(db: Session, token: str, mcp_url: str):
    """Create and compile the chat agent graph for one request.

    Built per-request (not cached) because the search_knowledge_base tool is
    bound to this specific caller's forwarded access token — the model can
    never supply its own credentials, which keeps knowledge-base search
    scoped to the authenticated user. token is the caller's own,
    already-validated Keycloak access token (see app.core.auth.get_current_user),
    forwarded to the doc-search MCP server so it can independently verify
    identity rather than trusting a bare user_id from this service (see
    app.mcp_client.doc_search_client). The checkpointer is built the same
    way and for the same reason: it's bound to this db session, and thread
    ownership must already have been verified by the caller (see
    ThreadRepository) before a thread_id ever reaches it.
    """
    search_tool = make_search_knowledge_base_tool(token=token, mcp_url=mcp_url)
    tools = [search_tool]
    llm = get_llm_client(db).bind_tools(tools)

    def call_agent(state: ChatState) -> ChatState:
        response = llm.invoke([CHAT_AGENT_SYSTEM_PROMPT.render(), *state["messages"]])
        return {**state, "messages": [response]}

    def route_after_agent(state: ChatState) -> str:
        if not _last_ai_message_has_tool_calls(state):
            return END
        if _count_tool_call_rounds(state) >= MAX_TOOL_CALL_ROUNDS:
            return END
        return "call_tool"

    graph = StateGraph(ChatState)
    graph.add_node("call_agent", call_agent)
    graph.add_node("call_tool", ToolNode(tools))

    graph.set_entry_point("call_agent")
    graph.add_conditional_edges(
        "call_agent",
        route_after_agent,
        {"call_tool": "call_tool", END: END},
    )
    graph.add_edge("call_tool", "call_agent")

    return graph.compile(checkpointer=SqlAlchemyCheckpointSaver(db))
