"""Input guardrail: rejects user messages before they reach the LLM.

Trip behavior is reject, chosen over sanitize or flag-only: a message that
trips a length or prompt-injection check is refused outright with a 4xx
response (see app.api.agents.chat), and never forwarded to the model in
modified form. Silently rewriting a user's message (sanitize) risks
answering a different question than the one they asked without their
knowledge; flag-only (allow through, just log) still lets an injection
attempt reach the model. Reject is the only one of the three that is both
safe and legible to the caller.

Deterministic, pure logic -- no LLM call, no I/O, no DB access -- so it is
fully unit testable per AGENTS.md's TDD standard with no mocking required
at all. All admin-configurable overrides (max_input_length,
enabled_pattern_ids, custom_phrases) are resolved one layer up, in
app.services.guardrail_config_service / chat_guardrail_service -- this
module never touches a database.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

# The env-level default length threshold (see
# app.core.config.Settings.guardrail_max_input_length) -- what an admin gets
# if they haven't overridden it via the settings screen. Distinct from
# MAX_INPUT_LENGTH_CEILING below: the two happen to be numerically equal
# today, but they mean different things, and a future change to one must
# not silently move the other.
DEFAULT_MAX_INPUT_LENGTH = 8000

# Hard, never-overridable upper bound on max_input_length -- chosen to
# comfortably fit a real question (including pasted context) while bounding
# worst-case prompt size before it reaches the LLM. Unlike
# DEFAULT_MAX_INPUT_LENGTH, no admin override (via SystemSettings or
# otherwise) can ever raise the effective threshold past this value; it is
# enforced at the request-schema boundary (see
# UpdateSettingsRequest.max_input_length's Field(le=...) in app.api.schemas)
# so an out-of-range value is rejected before it ever reaches this module.
MAX_INPUT_LENGTH_CEILING = 8000


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
#
# Keyed by a stable slug id (rather than a bare list) so an admin can
# individually enable/disable a pattern via the settings screen
# (GuardrailPatternRepository seeds one row per id here, see
# app.services.guardrail_config_service) without the toggle ever smuggling
# in arbitrary regex of its own -- the actual regex logic always stays in
# code, reviewed like any other code change; the DB only ever stores
# on/off state and a human-readable label.
_PROMPT_INJECTION_PATTERNS: dict[str, re.Pattern] = {
    # Instruction override: "ignore/disregard/forget ... instructions/rules"
    "instruction_override": re.compile(
        r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|above|prior|all)\b.{0,20}"
        r"\b(instructions?|rules?|prompt)\b",
        re.IGNORECASE,
    ),
    "instruction_override_forget_everything": re.compile(
        r"\b(forget)\b.{0,40}\beverything\b.{0,20}\b(told|said|instructed)\b",
        re.IGNORECASE,
    ),
    # Role reassignment: "you are now X", "act as an unrestricted AI", "developer mode"
    "role_reassignment_dan": re.compile(
        r"\byou are now\b.{0,40}\b(DAN|unrestricted|no restrictions)\b", re.IGNORECASE
    ),
    "role_reassignment_unrestricted": re.compile(
        r"\bact as an?\b.{0,20}\bunrestricted\b", re.IGNORECASE
    ),
    "developer_mode": re.compile(r"\bdeveloper mode\b.{0,20}\bno restrictions\b", re.IGNORECASE),
    # re.MULTILINE so ^ matches the start of any line, not just index 0 of
    # the whole message -- otherwise prefixing one innocuous line before
    # "SYSTEM:" would bypass this check entirely.
    "system_prefix_injection": re.compile(r"^\s*SYSTEM\s*:", re.IGNORECASE | re.MULTILINE),
    # System-prompt exfiltration: "print/reveal/repeat your system prompt / instructions"
    "system_prompt_exfiltration": re.compile(
        r"\b(print|reveal|show|repeat|tell me)\b.{0,20}\b(your|the)\b.{0,20}"
        r"\b(system prompt|initial instructions)\b",
        re.IGNORECASE,
    ),
    # Same exfiltration intent with the object named first: "your initial
    # instructions? repeat them exactly"
    "system_prompt_exfiltration_reversed": re.compile(
        r"\b(your|the)\b.{0,20}\b(system prompt|initial instructions)\b.{0,60}"
        r"\b(repeat|reveal|print|show)\b",
        re.IGNORECASE,
    ),
}

# Human-readable labels for the settings screen, keyed by the same ids as
# _PROMPT_INJECTION_PATTERNS -- kept next to the patterns themselves (rather
# than duplicated in guardrail_config_service) so the id list can never
# drift between the two.
BUILT_IN_PATTERN_LABELS: dict[str, str] = {
    "instruction_override": "Instruction override (ignore/disregard previous instructions)",
    "instruction_override_forget_everything": "Instruction override (forget everything you were told)",
    "role_reassignment_dan": "Role reassignment (DAN / unrestricted persona)",
    "role_reassignment_unrestricted": "Role reassignment (act as an unrestricted AI)",
    "developer_mode": "Developer mode / no-restrictions claim",
    "system_prefix_injection": "SYSTEM: prefix injection",
    "system_prompt_exfiltration": "System prompt exfiltration (reveal/print/repeat)",
    "system_prompt_exfiltration_reversed": "System prompt exfiltration (object-first phrasing)",
}


def _is_prompt_injection(
    message: str, enabled_pattern_ids: frozenset[str], custom_phrases: Sequence[str]
) -> bool:
    """True if message matches any enabled built-in pattern or any custom
    phrase.

    custom_phrases are matched as case-insensitive, literal substrings --
    never compiled as regex. This is a hard constraint (ReDoS risk of
    admin-supplied regex, an explicit scope decision, not an oversight): a
    phrase containing regex metacharacters like "." or "*" must only ever
    match that exact literal text.
    """
    if any(
        pattern.search(message)
        for pattern_id, pattern in _PROMPT_INJECTION_PATTERNS.items()
        if pattern_id in enabled_pattern_ids
    ):
        return True

    lowered_message = message.lower()
    return any(phrase.lower() in lowered_message for phrase in custom_phrases)


# One entry per reason code in check_input, kept next to it so a new
# rejection reason and its user-facing wording are always introduced
# together -- see InputGuardrailResult.message.
_REJECTION_MESSAGES = {
    "input_empty": "That message couldn't be sent. Please enter a question.",
    "input_too_long": "That message is too long. Please shorten it and try again.",
    "prompt_injection_suspected": "That message couldn't be sent. Please rephrase your question.",
}


def check_input(
    message: str,
    *,
    max_input_length: int = DEFAULT_MAX_INPUT_LENGTH,
    enabled_pattern_ids: frozenset[str] | None = None,
    custom_phrases: Sequence[str] = (),
) -> InputGuardrailResult:
    """Check a user message against the input guardrails.

    Checks run in a fixed order -- empty, then length, then prompt
    injection -- and stop at the first violation, so a rejection always
    reports one unambiguous reason rather than every check that happened
    to also fail.

    max_input_length, enabled_pattern_ids, and custom_phrases are the
    admin-configurable overrides from issue #16 (resolved from DB/env
    config one layer up, in app.services.guardrail_config_service):

    - max_input_length overrides the length-rejection threshold. Defaults
      to DEFAULT_MAX_INPUT_LENGTH so every existing caller that doesn't
      pass it keeps today's behavior unchanged.
    - enabled_pattern_ids=None (the default) means "every built-in pattern
      is enabled" -- again so an existing call site/test that doesn't care
      about per-pattern toggling keeps working. A caller that resolves real
      admin config always passes an explicit frozenset, including an empty
      one to mean "every built-in pattern disabled".
    - custom_phrases are additional admin-supplied literal phrases (see
      _is_prompt_injection) checked alongside the built-in patterns. A
      match produces the same "prompt_injection_suspected" reason code as a
      built-in pattern match -- there is no separate reason code for a
      custom-phrase hit.
    """
    if not message.strip():
        reason = "input_empty"
        return InputGuardrailResult(
            verdict=GuardrailVerdict.REJECTED, reason=reason, message=_REJECTION_MESSAGES[reason]
        )

    if len(message) > max_input_length:
        reason = "input_too_long"
        return InputGuardrailResult(
            verdict=GuardrailVerdict.REJECTED, reason=reason, message=_REJECTION_MESSAGES[reason]
        )

    resolved_pattern_ids = (
        frozenset(_PROMPT_INJECTION_PATTERNS.keys())
        if enabled_pattern_ids is None
        else enabled_pattern_ids
    )
    if _is_prompt_injection(message, resolved_pattern_ids, custom_phrases):
        reason = "prompt_injection_suspected"
        return InputGuardrailResult(
            verdict=GuardrailVerdict.REJECTED, reason=reason, message=_REJECTION_MESSAGES[reason]
        )

    return InputGuardrailResult(verdict=GuardrailVerdict.ALLOWED, reason=None, message=None)
