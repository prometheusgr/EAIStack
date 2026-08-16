"""LLM client and fake implementation for testing."""

from typing import Any, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import LLM

from app.core.config import settings


class FakeChatModel(LLM):
    """Fake LLM for unit testing. Returns canned responses."""

    response: str = "This is a fake response from the mocked LLM."
    call_count: int = 0

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Return the canned response."""
        self.call_count += 1
        return self.response


def get_llm_client():
    """
    Factory returning the appropriate LLM client based on config.

    Returns:
        Either FakeChatModel for testing, or ChatOpenAI for real inference.
    """
    if settings.llm_provider == "fake":
        return FakeChatModel()
    elif settings.llm_provider in ("llama-cpp", "openai-compatible"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            base_url=settings.llm_url,
            api_key=settings.llm_api_key or "not-needed",
            model=settings.llm_model,
            temperature=0.7,
            timeout=settings.llm_timeout,
        )
    else:
        raise ValueError(f"Unknown llm_provider: {settings.llm_provider}")
