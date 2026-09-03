"""LLM observability: OpenTelemetry tracing for the chat agent (issue #4).

Traces are sent to a self-hosted Arize Phoenix instance (see docker-compose's
`phoenix` service) via OTLP. Instrumentation is registered once per process,
not resolved per-request like the LLM/embedding provider config - there is
no supported way to swap a LangChainInstrumentor's tracer provider on a
running process, so this is a one-time setup call rather than a per-call
resolution.

Called from app.main's lifespan hook at startup, after resolving
tracing_enabled from the DB-override-over-env-default pattern (see
app.services.tracing_config_service.resolve_tracing_config) - the caller
passes the already-resolved boolean in, rather than this module reading
settings.tracing_enabled itself, so a DB override actually takes effect
(previously this field was env-only). Because that resolution happens once,
at startup, an admin's change via the settings screen requires a backend
restart to take effect - unlike llm_provider, which every call re-resolves.
"""

from app.core.config import Settings

# Module-level guard against double registration: a second call in the same
# process (e.g. a lifespan hook that somehow runs twice, or a test harness
# that constructs the app more than once) must be a safe no-op rather than
# re-registering OTel/LangChain instrumentation, which would either raise
# or silently duplicate every span.
_configured = False


def configure_tracing(settings: Settings, *, enabled: bool) -> None:
    """Register OTel tracing and LangChain auto-instrumentation, if enabled.

    A no-op when `enabled` is False - the default, and what every unit test
    process runs with, since FakeChatModel-based tests never resolve
    tracing_enabled to True. Idempotent: a second call in the same process
    is also a no-op, regardless of `enabled`, so callers don't need to
    track whether they've already called this themselves.

    When disabled, OpenTelemetry's global tracer provider is left as its
    default no-op implementation, so any instrumentation elsewhere in the
    dependency tree that calls trace.get_tracer() incurs no overhead and
    sends nothing.
    """
    global _configured
    if _configured or not enabled:
        return

    from openinference.instrumentation.langchain import LangChainInstrumentor
    from phoenix.otel import register

    # batch=True is required, not cosmetic: register()'s default
    # SimpleSpanProcessor exports each span synchronously and retries inline
    # on failure (confirmed by hand - a few seconds of retry delay per span
    # when Phoenix is unreachable). That delay would land inside every traced
    # chat request. BatchSpanProcessor exports on a background thread, so a
    # slow or down Phoenix instance can't add latency to - or block - a live
    # chat response.
    tracer_provider = register(
        endpoint=settings.tracing_otlp_endpoint,
        project_name="eaistack-chat-agent",
        batch=True,
        verbose=False,
    )
    LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
    _configured = True


def is_tracing_configured() -> bool:
    """Whether OTel tracing has actually been instrumented in this process.

    Distinct from resolve_tracing_config(db).enabled (the DB-desired state,
    re-read fresh on every call): this reflects whether configure_tracing
    has actually run and succeeded here, in this process, since it started.
    The two can diverge -- an admin's change via the settings screen only
    takes effect after the next backend restart (see configure_tracing's
    docstring) -- which is exactly the divergence issue #48's admin
    dashboard surfaces to an admin who might otherwise assume a settings
    change took effect immediately, the way every other config field does.
    """
    return _configured
