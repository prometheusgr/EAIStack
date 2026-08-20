"""LLM client and fake implementation for testing."""

from typing import Any, List, Optional, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from sqlalchemy.orm import Session

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

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FakeChatModel":
        """Accept tool bindings without altering scripted/canned behavior."""
        return self

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

        return ChatOpenAI(
            base_url=config.url,
            api_key=config.api_key or "not-needed",
            model=config.model,
            temperature=0.7,
            timeout=config.timeout,
        )
    else:
        raise ValueError(f"Unknown llm_provider: {config.provider}")
