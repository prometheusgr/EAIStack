"""Unit tests for app.core.tracing.configure_tracing - TDD discipline.

Covers the two behaviors that changed when tracing_enabled moved onto the
DB-override pattern and configure_tracing's call site moved into a FastAPI
lifespan hook (see app.main): the enabled/disabled decision is now driven
by an explicit `enabled` argument (the caller's already-resolved value,
DB-override merged over env default) rather than reading
settings.tracing_enabled directly, and a second call in the same process
must be a safe no-op rather than double-registering OTel instrumentation -
lifespan hooks are not guaranteed to run exactly once per process in every
ASGI server/test harness, so configure_tracing must defend itself.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.core.tracing import configure_tracing, is_tracing_configured


@pytest.fixture(autouse=True)
def _reset_tracing_configured_guard():
    """configure_tracing's idempotency guard is module-level state, so it
    must be reset between tests - otherwise a prior test's call would make
    every later test see it as "already configured" (or vice versa).
    """
    import app.core.tracing as tracing_module

    tracing_module._configured = False
    yield
    tracing_module._configured = False


@pytest.mark.unit
def test_configure_tracing_is_a_noop_when_disabled():
    """enabled=False must not import/construct anything from
    openinference/phoenix - the whole point of gating tracing off by
    default so unit tests never build a real OTel exporter.
    """
    with patch("phoenix.otel.register") as mock_register:
        configure_tracing(settings, enabled=False)

    mock_register.assert_not_called()


@pytest.mark.unit
def test_configure_tracing_registers_instrumentation_when_enabled():
    """enabled=True registers OTel + LangChain instrumentation exactly
    once.
    """
    mock_tracer_provider = MagicMock()
    with (
        patch("phoenix.otel.register", return_value=mock_tracer_provider) as mock_register,
        patch(
            "openinference.instrumentation.langchain.LangChainInstrumentor"
        ) as mock_instrumentor_cls,
    ):
        configure_tracing(settings, enabled=True)

    mock_register.assert_called_once()
    mock_instrumentor_cls.return_value.instrument.assert_called_once_with(
        tracer_provider=mock_tracer_provider
    )


@pytest.mark.unit
def test_configure_tracing_second_call_is_a_noop():
    """Calling configure_tracing twice in the same process (e.g. a second
    lifespan startup, or a test harness that constructs the app more than
    once) must not re-register - double instrumentation would either raise
    or silently duplicate every span.
    """
    with (
        patch("phoenix.otel.register", return_value=MagicMock()) as mock_register,
        patch(
            "openinference.instrumentation.langchain.LangChainInstrumentor"
        ) as mock_instrumentor_cls,
    ):
        configure_tracing(settings, enabled=True)
        configure_tracing(settings, enabled=True)

    mock_register.assert_called_once()
    mock_instrumentor_cls.return_value.instrument.assert_called_once()


@pytest.mark.unit
def test_is_tracing_configured_false_before_configure_tracing_runs():
    """Reflects that this process has not actually instrumented tracing
    yet, independent of whether an admin's DB override says it should be
    enabled - see resolve_tracing_config, the DB-desired counterpart this
    process-actual accessor is meant to be compared against.
    """
    assert is_tracing_configured() is False


@pytest.mark.unit
def test_is_tracing_configured_true_after_successful_configure_tracing():
    with (
        patch("phoenix.otel.register", return_value=MagicMock()),
        patch("openinference.instrumentation.langchain.LangChainInstrumentor"),
    ):
        configure_tracing(settings, enabled=True)

    assert is_tracing_configured() is True


@pytest.mark.unit
def test_is_tracing_configured_stays_false_when_configure_tracing_is_a_noop():
    """enabled=False leaves the process un-instrumented - the common
    default case, and the scenario issue #48's dashboard exists to surface
    when it diverges from an admin's DB-desired tracing_enabled=True.
    """
    configure_tracing(settings, enabled=False)

    assert is_tracing_configured() is False
