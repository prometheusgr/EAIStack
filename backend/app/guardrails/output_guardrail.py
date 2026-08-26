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

Two independent detection strategies guard against system-prompt leaks, because
neither alone covers the whole threat:

- _SYSTEM_PROMPT_DISCLOSURE_PATTERN matches *phrasing* -- a response that
  announces itself as a disclosure ("my system prompt is: ..."). This catches
  a model that complies with a direct "reveal your system prompt" request,
  regardless of what the prompt's own wording happens to be.
- _find_verbatim_prompt_leak matches *content* -- a response that reproduces a
  long enough run of the actual system prompt's own text, with no announcing
  phrase at all (e.g. complying with "repeat everything above verbatim" by
  simply printing the instructions). Phrasing-based matching cannot catch this
  because there is no self-referential phrase to match; only comparing against
  the real prompt text can. See test_filter_output_redacts_verbatim_system_prompt_leak.

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
# Every alternative requires self-referential disclosure framing, not just
# the bare noun phrase "system prompt" followed by a colon -- a legitimate
# response can mention "your system prompt:" as a UI/config concept (e.g.
# "configure your system prompt: go to Settings...") without disclosing
# anything, and the bare form used to match that too, redacting the entire
# rest of the response. See
# test_filter_output_does_not_flag_ordinary_mentions_of_system_prompt. The
# bare "system prompt" alternative is anchored to the very start of the
# response (^) so it only matches a declarative header-style disclosure
# ("SYSTEM PROMPT: ...", see test_filter_output_redacts_system_prompt_disclosure)
# rather than the phrase appearing anywhere mid-sentence.
#
# re.DOTALL so the trailing .* also consumes newlines: a disclosed prompt
# that spans multiple lines must be redacted in full, not just through the
# first line break (see test_filter_output_redacts_multiline_system_prompt).
_SYSTEM_PROMPT_DISCLOSURE_PATTERN = re.compile(
    r"(my system prompt is|here is my system prompt|\bthe system prompt\b"
    r"|\bsystem prompt (?:is|was)\b|^system prompt)\s*:.*",
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

# How many consecutive words of verbatim overlap with the real system prompt
# count as a leak, not a coincidental shared phrase. Short overlaps ("You
# are a helpful assistant" is exactly the kind of generic phrase a response
# might legitimately echo back while explaining what the assistant does) are
# common false-positive territory; a run this long is not something an
# ordinary answer produces by accident. Word-based (not character-based) so
# the threshold means the same thing regardless of a prompt's average word
# length. See test_filter_output_does_not_flag_a_short_coincidental_overlap.
_VERBATIM_LEAK_MIN_WORDS = 6


def _find_verbatim_prompt_leak(text: str, system_prompt: str) -> str | None:
    """Return the longest maximal run of `text` that verbatim-overlaps
    `system_prompt`, provided that run is at least _VERBATIM_LEAK_MIN_WORDS
    words long, or None if no such run exists.

    This is a content check, not a phrasing check: it catches a response
    that reproduces the system prompt's actual wording with no
    self-announcing lead-in at all (e.g. complying with "repeat everything
    above verbatim"), which no phrase-matching regex can detect since there
    is no phrase to match -- see the module docstring.

    "Maximal" matters: a leaked passage is usually longer than the minimum
    threshold, and the whole leaked passage must be redacted, not just the
    first _VERBATIM_LEAK_MIN_WORDS words of it. This walks every alignment
    between the two word sequences and extends each match as far as it
    verbatim-continues, rather than only ever considering fixed-size
    windows. See
    test_filter_output_redacts_verbatim_system_prompt_leak_with_no_announcing_phrase,
    which reproduces a leak considerably longer than the minimum.

    Whitespace-insensitive (a model may reformat line breaks or spacing when
    echoing text) but otherwise exact: this is deliberately not a fuzzy or
    semantic match, so it never redacts a response that merely covers the
    same topic as the system prompt in different words.
    """
    prompt_words = [word.lower() for word in system_prompt.split()]
    text_words = text.split()
    text_words_lower = [word.lower() for word in text_words]

    if len(prompt_words) < _VERBATIM_LEAK_MIN_WORDS:
        return None

    best_match: tuple[int, int] | None = None  # (start, length) in text_words

    for text_start in range(len(text_words_lower)):
        for prompt_start in range(len(prompt_words)):
            match_length = 0
            while (
                text_start + match_length < len(text_words_lower)
                and prompt_start + match_length < len(prompt_words)
                and text_words_lower[text_start + match_length]
                == prompt_words[prompt_start + match_length]
            ):
                match_length += 1

            if match_length >= _VERBATIM_LEAK_MIN_WORDS and (
                best_match is None or match_length > best_match[1]
            ):
                best_match = (text_start, match_length)

    if best_match is None:
        return None

    start, length = best_match
    return " ".join(text_words[start : start + length])


@dataclass(frozen=True)
class OutputGuardrailResult:
    """Result of filtering one agent response.

    was_modified tells the caller whether any redaction happened, without
    needing to diff text and result themselves -- api.agents.chat uses it
    to decide whether the event is audit-worthy.
    """

    text: str
    was_modified: bool


def filter_output(text: str, system_prompt: str | None = None) -> OutputGuardrailResult:
    """Redact system-prompt disclosures, verbatim system-prompt leaks, and
    credential-shaped tokens from an agent response.

    Runs every check (not first-match-wins like the input guardrail): an
    output can legitimately trip more than one filter, and unlike a
    rejection reason, there is no single "the reason" to report here.

    system_prompt enables the verbatim-leak check (see
    _find_verbatim_prompt_leak): optional because that check needs the
    caller's actual rendered prompt text, which not every caller has handy
    (e.g. a unit test exercising only the phrasing-based or credential
    checks), and because a caller with no system prompt at all has nothing
    to leak.
    """
    filtered = _SYSTEM_PROMPT_DISCLOSURE_PATTERN.sub(_REDACTED, text)

    if system_prompt:
        leaked_span = _find_verbatim_prompt_leak(filtered, system_prompt)
        if leaked_span is not None:
            leak_pattern = re.compile(re.escape(leaked_span).replace(r"\ ", r"\s+"), re.IGNORECASE)
            filtered = leak_pattern.sub(_REDACTED, filtered)

    filtered = _CREDENTIAL_TOKEN_PATTERN.sub(_REDACTED, filtered)

    return OutputGuardrailResult(text=filtered, was_modified=filtered != text)
