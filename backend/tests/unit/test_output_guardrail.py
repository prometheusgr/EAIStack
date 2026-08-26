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
def test_filter_output_does_not_flag_ordinary_mentions_of_system_prompt():
    """A response that merely discusses "system prompt" as a UI/config
    concept -- not a self-referential disclosure -- must not be redacted.

    Regression test: the bare `system prompt` alternative in
    _SYSTEM_PROMPT_DISCLOSURE_PATTERN used to match any occurrence of the
    phrase followed by a colon, so re.DOTALL's trailing `.*` redacted
    everything after "You can configure your system prompt:" even though
    nothing was disclosed. See the module docstring: the pattern should
    match an explicit disclosure, not any response that happens to discuss
    prompts in general.
    """
    text = (
        "You can configure your system prompt: go to Settings > Prompt "
        "Library and paste your instructions there. Employees also get "
        "15 days of vacation per year."
    )

    result = filter_output(text)

    assert result.was_modified is False
    assert result.text == text


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


_TEST_SYSTEM_PROMPT = (
    "You are a helpful assistant. Be brief and direct. When a tool returns "
    "results, use that information directly to answer the user's question "
    "in plain language. Do not describe the tool call itself."
)


@pytest.mark.unit
def test_filter_output_redacts_verbatim_system_prompt_leak_with_no_announcing_phrase():
    """A response that reproduces the system prompt's actual wording is
    redacted even with no self-announcing lead-in ("my system prompt is:",
    etc.) at all -- e.g. a model complying with "repeat everything above
    verbatim" by simply printing its instructions. _SYSTEM_PROMPT_DISCLOSURE_PATTERN
    cannot catch this: there is no disclosure phrase to match, only the
    prompt's own content repeated. See _find_verbatim_prompt_leak.
    """
    leaked_text = (
        "Sure! You are a helpful assistant. Be brief and direct. When a tool "
        "returns results, use that information directly to answer the "
        "user's question in plain language. Do not describe the tool call "
        "itself."
    )

    result = filter_output(leaked_text, system_prompt=_TEST_SYSTEM_PROMPT)

    assert result.was_modified is True
    assert "[redacted]" in result.text
    assert "Do not describe the tool call itself" not in result.text


@pytest.mark.unit
def test_filter_output_does_not_flag_a_short_coincidental_overlap():
    """A response that happens to share a short, generic phrase with the
    system prompt (e.g. explaining what kind of assistant it is) must not
    be redacted -- only a long-enough run of verbatim overlap counts as a
    leak, not any shared wording.
    """
    text = "I am a helpful assistant, here to answer your questions about the product catalog."

    result = filter_output(text, system_prompt=_TEST_SYSTEM_PROMPT)

    assert result.was_modified is False
    assert result.text == text


@pytest.mark.unit
def test_filter_output_without_system_prompt_skips_verbatim_leak_check():
    """A caller that doesn't pass system_prompt (e.g. one with no system
    prompt to leak, or an existing test exercising only the other checks)
    gets ordinary phrasing/credential filtering with no verbatim-leak check
    -- system_prompt is optional, not required.
    """
    text = "You are a helpful assistant. Be brief and direct. Nothing else is flagged here."

    result = filter_output(text)

    assert result.was_modified is False
    assert result.text == text


@pytest.mark.unit
def test_filter_output_verbatim_leak_check_is_whitespace_insensitive():
    """A model that reformats line breaks or spacing while echoing the
    prompt is still caught -- the verbatim-leak check compares words, not
    exact whitespace.
    """
    leaked_text = (
        "You   are a helpful\nassistant. Be brief and direct.\n\nWhen a tool "
        "returns   results, use that information directly to answer the "
        "user's question in plain language."
    )

    result = filter_output(leaked_text, system_prompt=_TEST_SYSTEM_PROMPT)

    assert result.was_modified is True
    assert "[redacted]" in result.text
