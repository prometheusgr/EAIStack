"""LLM observability: OpenTelemetry tracing for the chat agent (issue #4).

Traces are sent to a self-hosted Arize Phoenix instance (see docker-compose's
`phoenix` service) via OTLP. Instrumentation is registered once, at process
start, not resolved per-request like the LLM/embedding provider config -
there is no supported way to swap a LangChainInstrumentor's tracer provider
on a running process, so this is a one-time setup call rather than a
per-call resolution.
"""

from app.core.config import Settings


def configure_tracing(settings: Settings) -> None:
    """Register OTel tracing and LangChain auto-instrumentation, if enabled.

    A no-op when settings.tracing_enabled is False - the default, and what
    every unit test process runs with. This must only ever be called once,
    explicitly, from app.main's startup path; it must never run as a
    side effect of importing app.agents.chat_agent or app.core.llm_client,
    so hermetic tests using FakeChatModel never construct a real OTel
    exporter or make a network call.

    When disabled, OpenTelemetry's global tracer provider is left as its
    default no-op implementation, so any instrumentation elsewhere in the
    dependency tree that calls trace.get_tracer() incurs no overhead and
    sends nothing.
    """
    if not settings.tracing_enabled:
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
