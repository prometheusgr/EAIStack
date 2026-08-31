"""Unit tests for app.core.config.Settings - TDD discipline.

Covers the blank-env-var boolean crash: pydantic-settings' default bool
parsing rejects an empty string outright (`ValidationError: bool_parsing`),
so any bool-typed field left blank in the environment (e.g. an unset
`TRACING_ENABLED=` line in a .env file, or a K8s ConfigMap that renders an
empty string rather than omitting the key) crashes Settings() construction
at import time - the whole process fails to start instead of falling back
to the field's default.
"""

import pytest

from app.core.config import Settings


@pytest.mark.unit
def test_blank_bool_env_var_falls_back_to_default(monkeypatch):
    """A blank string for a bool field must not crash Settings() - it
    should be treated the same as the env var being unset, i.e. fall back
    to the field's default.
    """
    monkeypatch.setenv("TRACING_ENABLED", "")

    result = Settings()

    assert result.tracing_enabled is False  # the field's declared default


@pytest.mark.unit
def test_blank_bool_env_var_on_a_true_default_field_falls_back_to_default(monkeypatch):
    """Same fallback behaviour for a bool field whose default is True, so
    the fix isn't accidentally coupled to False being the fallback value.
    """
    monkeypatch.setenv("GUARDRAILS_INPUT_ENABLED", "")

    result = Settings()

    assert result.guardrails_input_enabled is True  # the field's declared default


@pytest.mark.unit
def test_non_blank_bool_env_var_still_parses_normally(monkeypatch):
    """The blank-string normalization must not swallow real values - a
    genuine "true"/"false" env var still parses as before.
    """
    monkeypatch.setenv("TRACING_ENABLED", "true")

    result = Settings()

    assert result.tracing_enabled is True


@pytest.mark.unit
def test_blank_string_env_var_on_a_non_bool_field_is_unaffected(monkeypatch):
    """The normalization is bool-field-scoped: a blank string for a
    str-typed field must still come through as an empty string, not be
    coerced to that field's default (an empty LLM API key is a real,
    meaningful value - "no key" - not "unset").
    """
    monkeypatch.setenv("LLM_API_KEY", "")

    result = Settings()

    assert result.llm_api_key == ""
