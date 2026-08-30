"""Guardrail enforcement for the chat agent: check, filter, and audit-log.

Wraps app.guardrails.input_guardrail and app.guardrails.output_guardrail --
themselves deterministic, pure logic with no LLM call or I/O -- with the
audit-log write each one's trip behavior requires. Pulled out of
app.api.agents.chat because the same "run a guardrail, audit-log it if it
trips" shape appears twice in that endpoint (once for input rejection, once
for output redaction), and because docs/AGENT_LIBRARY.md already documents
that a second agent's endpoint must run this same input/output guardrail
sequence -- a second production caller, not just a duplicated shape within
one function.

Every function here takes `now` explicitly rather than reading the clock
(see AGENTS.md's time injection pattern) and flushes but never commits --
the caller (the endpoint) owns the transaction, same contract as every
repository and other service in this codebase. This also means a
guardrail's audit-log write can share a single commit with whatever else
the caller is already about to commit (e.g. the redaction audit entry lands
in the same commit as the thread's touch()), rather than forcing an extra
round-trip.
"""

from datetime import datetime

from langchain_core.messages import BaseMessage
from sqlalchemy.orm import Session

from app.guardrails.input_guardrail import GuardrailVerdict, InputGuardrailResult, check_input
from app.guardrails.output_guardrail import OutputGuardrailResult, filter_output
from app.repositories import AuditLogRepository
from app.services.guardrail_config_service import GuardrailConfig, resolve_guardrail_config


def check_input_guardrail(
    db: Session,
    *,
    message: str,
    actor_user_id: str,
    now: datetime,
    config: GuardrailConfig | None = None,
) -> InputGuardrailResult:
    """Run the input guardrail and audit-log a rejection.

    The input guardrail's trip behavior is reject, not sanitize or
    flag-only: a message that trips a length or prompt-injection check is
    refused outright, and never forwarded to the model in modified form.
    Silently rewriting a user's message (sanitize) risks answering a
    different question than the one they asked without their knowledge;
    flag-only (allow through, just log) still lets an injection attempt
    reach the model. Reject is the only one of the three that is both safe
    and legible to the caller (see app.guardrails.input_guardrail for the
    full rationale).

    Config (max_input_length, which built-in patterns are enabled, custom
    phrases, and the on/off switch itself) is resolved fresh from
    SystemSettings/GuardrailPatternRepository -- see
    app.services.guardrail_config_service -- so an admin's change via the
    settings screen takes effect on the very next chat request. If the
    input guardrail is switched off entirely, the check never runs at all:
    the message is allowed and nothing is audit-logged, exactly as if it
    had passed the check normally (an allowed message is never an
    audit-worthy event).

    config: the caller's already-resolved GuardrailConfig, if it has one.
    A single chat request calls both this function and
    filter_agent_response, and each independent resolve_guardrail_config()
    call was previously paying for its own SystemSettings SELECT plus a
    GuardrailPattern seed-check and list -- doubling guardrail-config DB
    work per request for a value that cannot change mid-request. Pass the
    same resolved config to both calls (see app.api.agents.chat) to avoid
    that; omitted only by callers (e.g. unit tests) that don't have one
    handy, in which case this function resolves its own, same as before.

    A rejection is a compliance-relevant event and is recorded in the
    append-only audit trail, attributed to the caller who sent the
    message. An allowed message is not audit-logged -- only violations are
    compliance-relevant, not every chat turn.
    """
    if config is None:
        config = resolve_guardrail_config(db)
    if not config.input_enabled:
        return InputGuardrailResult(verdict=GuardrailVerdict.ALLOWED, reason=None, message=None)

    result = check_input(
        message,
        max_input_length=config.max_input_length,
        enabled_pattern_ids=config.enabled_pattern_ids,
        custom_phrases=config.custom_phrases,
    )
    if result.verdict == GuardrailVerdict.REJECTED:
        AuditLogRepository(db).record(
            actor_user_id=actor_user_id,
            action="guardrail.input_rejected",
            field_name="message",
            old_value=None,
            new_value=result.reason,
            now=now,
        )
    return result


def filter_agent_response(
    db: Session,
    *,
    final_message: BaseMessage,
    system_prompt: str,
    actor_user_id: str,
    thread_id: str,
    now: datetime,
    config: GuardrailConfig | None = None,
) -> OutputGuardrailResult:
    """Run the output guardrail on the agent's final message and audit-log
    a redaction.

    final_message.text extracts plain text from the message's content,
    which LangChain types as str | list[str | dict] -- some providers
    return a list of content blocks (e.g. multi-part or provider-annotated
    responses) instead of a bare string. A plain str() on a list would
    produce Python's repr syntax (e.g. "[{'type': 'text', ...}]"), which
    both defeats the output guardrail's text-based regexes and shows
    garbled output to the user.

    system_prompt is the caller's actual rendered system prompt (e.g.
    CHAT_AGENT_SYSTEM_PROMPT.render().content for the chat agent) --
    threaded through so the output guardrail's verbatim-leak check can
    compare the response against the real prompt text, not just look for a
    self-announcing disclosure phrase. A second agent with its own prompt
    passes its own rendered text here; nothing in this service is
    chat-agent-specific.

    The output guardrail's trip behavior is sanitize (redact-in-place), not
    reject: unlike the input guardrail, there is no cheap way to "ask
    again" once the LLM has already produced a full response, and the
    response is usually otherwise useful even when one span within it is a
    system-prompt echo or a credential-shaped string (see
    app.guardrails.output_guardrail for the full rationale).

    Config resolution and the config parameter follow the same shape as
    check_input_guardrail -- see that function's docstring for why passing
    an already-resolved config matters (avoiding a second, redundant
    resolution within the same chat request). If the output guardrail is
    switched off entirely, filter_output is never called: the response is
    returned unmodified and nothing is audit-logged, exactly as if it had
    passed the filter with no redactions needed.

    A redaction is a compliance-relevant event, just like an input
    rejection, and is recorded in the append-only audit trail -- keyed by
    thread_id, never by the redacted response text itself, since that text
    is exactly what must not be written into an indefinitely-retained
    audit record. An unmodified response is not audit-logged.
    """
    if config is None:
        config = resolve_guardrail_config(db)
    if not config.output_enabled:
        return OutputGuardrailResult(text=final_message.text, was_modified=False)

    result = filter_output(final_message.text, system_prompt=system_prompt)
    if result.was_modified:
        AuditLogRepository(db).record(
            actor_user_id=actor_user_id,
            action="guardrail.output_redacted",
            field_name="response",
            old_value=None,
            new_value=thread_id,
            now=now,
        )
    return result
