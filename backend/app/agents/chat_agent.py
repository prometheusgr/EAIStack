"""LangGraph agent for chat interactions."""

from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.core.llm_client import get_llm_client


class ChatState(TypedDict):
    """State for the chat agent."""

    user_message: str
    thread_id: str
    tool_result: Optional[str]
    response: Optional[str]


def call_agent(state: ChatState) -> ChatState:
    """Call the LLM with the user's message."""
    llm = get_llm_client()
    response = llm.invoke(state["user_message"])
    return {**state, "response": response}


def call_tool(state: ChatState) -> ChatState:
    """Call a mocked tool based on the LLM response."""
    # For now, a simple mocked tool that echoes information
    if "time" in state["response"].lower():
        tool_result = "The current time is 3:45 PM."
    elif "date" in state["response"].lower():
        tool_result = "Today is December 15, 2024."
    elif "weather" in state["response"].lower():
        tool_result = "The weather is sunny and 72°F."
    else:
        tool_result = f"Tool executed based on: {state['response'][:50]}"

    return {**state, "tool_result": tool_result}


def create_chat_agent():
    """Create and compile the chat agent graph."""
    graph = StateGraph(ChatState)

    # Add nodes
    graph.add_node("call_agent", call_agent)
    graph.add_node("call_tool", call_tool)

    # Add edges: entry -> call_agent -> call_tool -> END
    graph.set_entry_point("call_agent")
    graph.add_edge("call_agent", "call_tool")
    graph.add_edge("call_tool", END)

    return graph.compile()
