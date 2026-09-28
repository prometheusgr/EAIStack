"""Tests for the versioned prompt library (app.prompts.prompt_template).

Covers PromptTemplate's own render/version behavior in isolation. A
concrete workflow's prompt text (e.g. the built-in chat workflow's) now
lives inline in its YAML definition (backend/workflows/*.yaml, see
app.workflows.schema.AgentStepDef) rather than as a PromptTemplate
instance -- see tests/unit/test_chat_workflow.py and
tests/unit/test_workflow_loader.py for coverage of that content.
"""

import pytest
from langchain_core.messages import SystemMessage

from app.prompts.prompt_template import PromptTemplate


@pytest.mark.unit
def test_prompt_template_render_returns_system_message():
    """Rendering a template produces a LangChain SystemMessage."""
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
