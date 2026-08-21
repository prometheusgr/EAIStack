"""LangGraph agent for chat interactions."""

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from sqlalchemy.orm import Session

from app.agents.tools import make_search_knowledge_base_tool
from app.core.llm_client import get_llm_client

MAX_TOOL_CALL_ROUNDS = 5

# Some local models (verified: Llama 3.1 8B Instruct via llama.cpp --jinja) will
# describe a tool call's JSON instead of answering from its result unless told
# explicitly to do otherwise. This is prepended per-invocation rather than
# stored in state, so it isn't duplicated across tool-call rounds.
SYSTEM_PROMPT = SystemMessage(
    content=(
        "You are a helpful assistant. Be brief and direct. When a tool returns results, use that "
        "information directly to answer the user's question in plain language. "
        "Do not describe the tool call itself."
    )
)


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


def create_chat_agent(db: Session, user_id: str):
    """Create and compile the chat agent graph for one request.

    Built per-request (not cached) because the search_knowledge_base tool is
    bound to this specific db session and user_id — the model can never
    supply its own user_id, which keeps knowledge-base search scoped to the
    authenticated user.
    """
    search_tool = make_search_knowledge_base_tool(user_id=user_id, db=db)
    tools = [search_tool]
    llm = get_llm_client(db).bind_tools(tools)

    def call_agent(state: ChatState) -> ChatState:
        response = llm.invoke([SYSTEM_PROMPT, *state["messages"]])
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

    return graph.compile()
