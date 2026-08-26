"""Tests for the versioned prompt library.

Covers the library's own render/version behavior. chat_agent's use of
CHAT_AGENT_SYSTEM_PROMPT is covered by tests/unit/test_chat_agent.py.
"""

import pytest
from langchain_core.messages import SystemMessage

from app.prompts.chat_prompts import CHAT_AGENT_SYSTEM_PROMPT
from app.prompts.prompt_template import PromptTemplate


@pytest.mark.unit
def test_prompt_template_render_returns_system_message():
    """Rendering a template produces a LangChain SystemMessage, matching
    what chat_agent.py passes directly to the LLM.
    """
    template = PromptTemplate(name="test_prompt", version=1, template="You are a test assistant.")

    rendered = template.render()

    assert isinstance(rendered, SystemMessage)
    assert rendered.content == "You are a test assistant."


@pytest.mark.unit
def test_prompt_template_render_is_stable_across_calls():
    """Rendering the same template twice produces equal content -- a
    prompt template has no hidden per-call state (e.g. a timestamp).
    """
    template = PromptTemplate(name="test_prompt", version=1, template="Fixed content.")

    assert template.render().content == template.render().content


@pytest.mark.unit
def test_chat_agent_system_prompt_is_versioned():
    """The chat agent's system prompt is a named, versioned template, not
    an inline string -- the concrete gap this ticket closes.
    """
    assert CHAT_AGENT_SYSTEM_PROMPT.name == "chat_agent_system"
    assert CHAT_AGENT_SYSTEM_PROMPT.version == 1


@pytest.mark.unit
def test_chat_agent_system_prompt_still_instructs_direct_tool_result_use():
    """Regression guard for the specific llama.cpp behavior chat_agent.py's
    original inline comment documented: without this instruction, some
    local models describe a tool call's JSON instead of answering from its
    result. Moving the string into the prompt library must not lose it.
    """
    rendered = CHAT_AGENT_SYSTEM_PROMPT.render()

    assert "tool" in rendered.content.lower()
    assert "directly" in rendered.content.lower()
