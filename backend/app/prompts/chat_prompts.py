"""Prompt templates for the chat agent (app.agents.chat_agent).

Replaces the module-level SystemMessage constant chat_agent.py previously
defined inline. Each agent gets its own prompts module (see
docs/AGENT_LIBRARY.md); a second agent adds chat_prompts.py's sibling, not
more content here.
"""

from app.prompts.prompt_template import PromptTemplate

# Some local models (verified: Llama 3.1 8B Instruct via llama.cpp --jinja)
# will describe a tool call's JSON instead of answering from its result
# unless told explicitly to do otherwise. Rendered fresh per-invocation by
# chat_agent.call_agent rather than stored in graph state, so it is never
# duplicated across tool-call rounds.
CHAT_AGENT_SYSTEM_PROMPT = PromptTemplate(
    name="chat_agent_system",
    version=1,
    template=(
        "You are a helpful assistant. Be brief and direct. When a tool returns results, use that "
        "information directly to answer the user's question in plain language. "
        "Do not describe the tool call itself."
    ),
)
