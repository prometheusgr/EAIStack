"""Output guardrail: filters the agent's response before it reaches the user.

Trip behavior is sanitize (redact-in-place), not reject: unlike the input
guardrail, there is no cheap way to "ask again" once the LLM has already
produced a full response, and the response is usually otherwise useful even
when one span within it is a system-prompt echo or a credential-shaped
string. Rejecting the entire response over one flagged span would throw away
a real, already-paid-for answer. The redacted spans are still recorded (see
OutputGuardrailResult.was_modified, used by api.agents.chat to decide
whether to audit-log the event) even though the response itself is not
blocked.

PII detection is explicitly out of scope for this pass -- see the PR
description for why (it interacts with the audit log's own retention
policy and needed a decision on which PII categories to scope in, which
this ticket left as future work rather than deciding under time pressure).

Deterministic, pure logic -- no LLM call -- so it is fully unit testable.
"""

import re
from dataclasses import dataclass

_REDACTED = "[redacted]"

# Matches an explicit disclosure of the system prompt, not any response that
# happens to discuss prompts in general -- see
# test_filter_output_redacts_system_prompt_disclosure. The system prompt's
# own wording ("You are a helpful assistant...") is not matched separately;
# catching the disclosure phrase is what generalizes to a differently-worded
# system prompt introduced later without editing this pattern.
#
# re.DOTALL so the trailing .* also consumes newlines: a disclosed prompt
# that spans multiple lines must be redacted in full, not just through the
# first line break (see test_filter_output_redacts_multiline_system_prompt).
_SYSTEM_PROMPT_DISCLOSURE_PATTERN = re.compile(
    r"(my system prompt is|here is my system prompt|system prompt)\s*:.*",
    re.IGNORECASE | re.DOTALL,
)

# Matches the shape of common API-key formats (e.g. OpenAI-style sk-...)
# rather than the word "key", which appears constantly in ordinary text
# (e.g. "primary key") -- see
# test_filter_output_does_not_flag_ordinary_mentions_of_the_word_key.
# re.IGNORECASE so an upper-cased or mixed-case token (e.g. a model
# reformatting "sk-" as "SK-") is still caught, consistent with every other
# pattern in this codebase's guardrails.
_CREDENTIAL_TOKEN_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b", re.IGNORECASE)


@dataclass(frozen=True)
class OutputGuardrailResult:
    """Result of filtering one agent response.

    was_modified tells the caller whether any redaction happened, without
    needing to diff text and result themselves -- api.agents.chat uses it
    to decide whether the event is audit-worthy.
    """

    text: str
    was_modified: bool


def filter_output(text: str) -> OutputGuardrailResult:
    """Redact system-prompt disclosures and credential-shaped tokens from an
    agent response.

    Runs both checks (not first-match-wins like the input guardrail): an
    output can legitimately trip more than one filter, and unlike a
    rejection reason, there is no single "the reason" to report here.
    """
    filtered = _SYSTEM_PROMPT_DISCLOSURE_PATTERN.sub(_REDACTED, text)
    filtered = _CREDENTIAL_TOKEN_PATTERN.sub(_REDACTED, filtered)

    return OutputGuardrailResult(text=filtered, was_modified=filtered != text)
