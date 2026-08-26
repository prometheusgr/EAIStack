"""Input guardrail: rejects user messages before they reach the LLM.

Trip behavior is reject, chosen over sanitize or flag-only: a message that
trips a length or prompt-injection check is refused outright with a 4xx
response (see app.api.agents.chat), and never forwarded to the model in
modified form. Silently rewriting a user's message (sanitize) risks
answering a different question than the one they asked without their
knowledge; flag-only (allow through, just log) still lets an injection
attempt reach the model. Reject is the only one of the three that is both
safe and legible to the caller.

Deterministic, pure logic -- no LLM call, no I/O -- so it is fully unit
testable per AGENTS.md's TDD standard with no mocking required at all.
"""

import re
from dataclasses import dataclass
from enum import Enum

# Chosen to comfortably fit a real question (including pasted context) while
# bounding worst-case prompt size before it reaches the LLM. Not read from
# app.core.config.settings: this is a hard safety bound on a single message,
# not a per-deployment tunable like the retention windows are.
MAX_INPUT_LENGTH = 8000


class GuardrailVerdict(Enum):
    """Outcome of a guardrail check."""

    ALLOWED = "allowed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class InputGuardrailResult:
    """Result of checking one user message against the input guardrails.

    reason is a short, stable machine-readable code -- it is what gets
    written to AuditLog.field_name, so its exact spelling is part of the
    guardrail's contract with callers. message is the human-readable text
    for the same rejection, generated here (not duplicated as a separate
    lookup table in the frontend) so the two can never drift out of sync:
    a new reason code and its user-facing wording are always added in the
    same place, in the same commit.
    """

    verdict: GuardrailVerdict
    reason: str | None
    message: str | None


# Each pattern targets a specific, well-documented injection technique
# rather than a single trigger word, so an ordinary sentence that happens to
# contain a word like "ignore" or "instructions" does not false-positive
# (see test_check_input_allows_benign_messages_that_share_words_with_heuristics).
_PROMPT_INJECTION_PATTERNS = [
    # Instruction override: "ignore/disregard/forget ... instructions/rules"
    re.compile(
        r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|above|prior|all)\b.{0,20}"
        r"\b(instructions?|rules?|prompt)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(forget)\b.{0,40}\beverything\b.{0,20}\b(told|said|instructed)\b",
        re.IGNORECASE,
    ),
    # Role reassignment: "you are now X", "act as an unrestricted AI", "developer mode"
    re.compile(r"\byou are now\b.{0,40}\b(DAN|unrestricted|no restrictions)\b", re.IGNORECASE),
    re.compile(r"\bact as an?\b.{0,20}\bunrestricted\b", re.IGNORECASE),
    re.compile(r"\bdeveloper mode\b.{0,20}\bno restrictions\b", re.IGNORECASE),
    # re.MULTILINE so ^ matches the start of any line, not just index 0 of
    # the whole message -- otherwise prefixing one innocuous line before
    # "SYSTEM:" would bypass this check entirely.
    re.compile(r"^\s*SYSTEM\s*:", re.IGNORECASE | re.MULTILINE),
    # System-prompt exfiltration: "print/reveal/repeat your system prompt / instructions"
    re.compile(
        r"\b(print|reveal|show|repeat|tell me)\b.{0,20}\b(your|the)\b.{0,20}"
        r"\b(system prompt|initial instructions)\b",
        re.IGNORECASE,
    ),
    # Same exfiltration intent with the object named first: "your initial
    # instructions? repeat them exactly"
    re.compile(
        r"\b(your|the)\b.{0,20}\b(system prompt|initial instructions)\b.{0,60}"
        r"\b(repeat|reveal|print|show)\b",
        re.IGNORECASE,
    ),
]


def _is_prompt_injection(message: str) -> bool:
    return any(pattern.search(message) for pattern in _PROMPT_INJECTION_PATTERNS)


# One entry per reason code in check_input, kept next to it so a new
# rejection reason and its user-facing wording are always introduced
# together -- see InputGuardrailResult.message.
_REJECTION_MESSAGES = {
    "input_empty": "That message couldn't be sent. Please enter a question.",
    "input_too_long": "That message is too long. Please shorten it and try again.",
    "prompt_injection_suspected": "That message couldn't be sent. Please rephrase your question.",
}


def check_input(message: str) -> InputGuardrailResult:
    """Check a user message against the input guardrails.

    Checks run in a fixed order -- empty, then length, then prompt
    injection -- and stop at the first violation, so a rejection always
    reports one unambiguous reason rather than every check that happened
    to also fail.
    """
    if not message.strip():
        reason = "input_empty"
        return InputGuardrailResult(
            verdict=GuardrailVerdict.REJECTED, reason=reason, message=_REJECTION_MESSAGES[reason]
        )

    if len(message) > MAX_INPUT_LENGTH:
        reason = "input_too_long"
        return InputGuardrailResult(
            verdict=GuardrailVerdict.REJECTED, reason=reason, message=_REJECTION_MESSAGES[reason]
        )

    if _is_prompt_injection(message):
        reason = "prompt_injection_suspected"
        return InputGuardrailResult(
            verdict=GuardrailVerdict.REJECTED, reason=reason, message=_REJECTION_MESSAGES[reason]
        )

    return InputGuardrailResult(verdict=GuardrailVerdict.ALLOWED, reason=None, message=None)
