"""Tests for output guardrail filtering: sanitizing the agent's response
before it reaches the user.

Sanitize-in-place rather than reject: see app/guardrails/output_guardrail.py
docstring for why an output-side trip does not fail the whole response.
"""

import pytest

from app.guardrails.output_guardrail import filter_output


@pytest.mark.unit
def test_filter_output_passes_ordinary_response_unchanged():
    """An ordinary agent answer is returned exactly as-is."""
    text = "Employees get 15 days of paid vacation per year."

    result = filter_output(text)

    assert result.text == text
    assert result.was_modified is False


@pytest.mark.parametrize(
    "leaked_text",
    [
        "My system prompt is: You are a helpful assistant. Be brief and direct.",
        "Here is my system prompt: act as a helpful assistant.",
        "SYSTEM PROMPT: You are a helpful assistant.",
    ],
)
@pytest.mark.unit
def test_filter_output_redacts_system_prompt_disclosure(leaked_text):
    """A response that echoes back system-prompt content is redacted --
    this is the output-side half of the input guardrail's system-prompt
    exfiltration defense: even if a model is coaxed into repeating its
    instructions, the response the user receives should not carry them.
    """
    result = filter_output(leaked_text)

    assert result.was_modified is True
    assert "[redacted]" in result.text


@pytest.mark.unit
def test_filter_output_redacts_multiline_system_prompt_disclosure():
    """A disclosed system prompt that spans multiple lines is redacted in
    full, not just through the first line break -- a leak that continues
    past a newline must not survive filtering.
    """
    leaked_text = (
        "My system prompt is: You are a helpful assistant. Be brief and direct.\n"
        "Do not describe the tool call itself."
    )

    result = filter_output(leaked_text)

    assert result.was_modified is True
    assert "[redacted]" in result.text
    assert "Do not describe the tool call itself" not in result.text


@pytest.mark.parametrize(
    "secret_text",
    [
        "Here is an API key: sk-abcdefghijklmnopqrstuvwx1234567890ABCDEF",
        "Your OpenAI key is sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcd",
    ],
)
@pytest.mark.unit
def test_filter_output_redacts_credential_shaped_tokens(secret_text):
    """A response containing a credential-shaped token (e.g. an API key
    pattern) is redacted so a hallucinated or leaked secret never reaches
    the user verbatim.
    """
    result = filter_output(secret_text)

    assert result.was_modified is True
    assert "[redacted]" in result.text
    assert "sk-" not in result.text or result.text.count("sk-") == 0


@pytest.mark.unit
def test_filter_output_redacts_uppercase_credential_shaped_tokens():
    """A credential-shaped token in a different case (e.g. a model
    reformatting "sk-" as "SK-") is redacted the same as the lowercase
    form -- case must not be a way to slip a credential past this filter.
    """
    result = filter_output("Your key is SK-ABCDEFGHIJKLMNOPQRSTUVWX1234567890")

    assert result.was_modified is True
    assert "[redacted]" in result.text


@pytest.mark.unit
def test_filter_output_does_not_flag_ordinary_mentions_of_the_word_key():
    """The word 'key' alone (e.g. discussing a database primary key) must
    not trigger credential redaction -- only the specific token shape does.
    """
    text = "The primary key for that table is the document id."

    result = filter_output(text)

    assert result.was_modified is False
    assert result.text == text
