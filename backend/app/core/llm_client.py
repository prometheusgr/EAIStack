"""LLM client and fake implementation for testing."""

from typing import Any, List, Optional, Sequence, Type, Union

import httpx
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.tls import get_ssl_context
from app.services.system_settings_service import resolve_llm_config


class FakeChatModel(BaseChatModel):
    """Fake chat model for unit testing. Returns canned or scripted responses.

    Mirrors the AIMessage-returning interface of ChatOpenAI (the real
    provider) so agent code can treat both identically. By default it
    returns a single plain-text response with no tool calls. Tests that
    need to script a tool-call turn followed by a follow-up answer can
    pass `responses`, a queue of AIMessages consumed one per invocation
    (the last one repeats once the queue is exhausted).
    """

    response: str = "This is a fake response from the mocked LLM."
    responses: Optional[List[AIMessage]] = None
    call_count: int = 0

    # A separate queue from `responses`: with_structured_output() callers
    # (app.workflows.primitives's reviewer node) never go through
    # _generate()/invoke() at all -- the real ChatOpenAI.with_structured_output
    # returns a distinct Runnable that parses a JSON-schema-constrained
    # completion into a pydantic instance, so this fake needs its own
    # scripted queue of already-constructed pydantic instances, consumed by
    # its own counter, rather than reusing the AIMessage queue above.
    structured_responses: Optional[List[BaseModel]] = None
    structured_call_count: int = 0

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FakeChatModel":
        """Accept tool bindings without altering scripted/canned behavior."""
        return self

    def with_structured_output(
        self, schema: Union[dict, Type[BaseModel]], *, include_raw: bool = False, **kwargs: Any
    ) -> Runnable[Any, BaseModel]:
        """Return the next scripted pydantic instance from structured_responses
        (the last one repeats once exhausted, matching `responses`' own
        repeat-last-on-exhaustion behavior) on every invocation, ignoring the
        input messages -- a test scripts what the reviewer should decide, not
        what it should read.

        Tests that never set structured_responses get a clear error rather
        than a silent None: a review-loop test that forgets to script the
        reviewer's verdict is a test-authoring bug, not a runtime condition
        this fake should paper over.
        """

        def _next_response(_input: Any) -> BaseModel:
            if not self.structured_responses:
                raise ValueError(
                    "FakeChatModel.with_structured_output() called with no "
                    "structured_responses scripted"
                )
            index = min(self.structured_call_count, len(self.structured_responses) - 1)
            result = self.structured_responses[index]
            self.structured_call_count += 1
            return result

        return RunnableLambda(_next_response)

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Return the next scripted AIMessage, or the canned plain-text response."""
        if self.responses:
            index = min(self.call_count, len(self.responses) - 1)
            message = self.responses[index]
        else:
            message = AIMessage(content=self.response)

        self.call_count += 1
        return ChatResult(generations=[ChatGeneration(message=message)])


def get_llm_client(db: Session):
    """
    Factory returning the appropriate LLM client based on the resolved config.

    Config is resolved fresh on every call via resolve_llm_config(db) — a
    DB-stored admin override (if any) wins over the env-var default, with no
    caching, so a change made through the settings screen takes effect on
    the next call without a backend restart.

    Returns:
        Either FakeChatModel for testing, or ChatOpenAI for real inference.
    """
    config = resolve_llm_config(db)

    if config.provider == "fake":
        return FakeChatModel()
    elif config.provider in ("llama-cpp", "openai-compatible"):
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        # ChatOpenAI takes no verify= of its own, so the internal CA bundle
        # (Phase 5, Decision 2) has to arrive as preconfigured httpx clients,
        # which langchain-openai hands straight to the OpenAI SDK. Both the
        # sync and async kwargs are set: chat inference runs on the async
        # path, but leaving the sync one unconfigured would silently skip the
        # bundle for any synchronous invocation.
        #
        # get_ssl_context() (not the raw path) because this factory runs on
        # every chat request and builds two clients each time — reusing the
        # cached, already-parsed trust store avoids re-reading the CA bundle
        # PEM file from disk on every single chat turn.
        verify = get_ssl_context()

        return ChatOpenAI(
            base_url=config.url,
            api_key=SecretStr(config.api_key or "not-needed"),
            model=config.model,
            temperature=0.7,
            timeout=config.timeout,
            http_client=httpx.Client(verify=verify),
            http_async_client=httpx.AsyncClient(verify=verify),
        )
    else:
        raise ValueError(f"Unknown llm_provider: {config.provider}")
