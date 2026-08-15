"""LLM client and fake implementation for testing."""

from typing import Any, List, Optional

from langchain_core.language_model import LLM
from langchain_core.callbacks import CallbackManagerForLLMRun
from pydantic import BaseModel


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

    def _generate(
        self,
        messages: List[Any],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Any:
        """Generate method required by LangChain."""
        self.call_count += 1
        from langchain_core.outputs import ChatGeneration, LLMResult
        from langchain_core.messages import AIMessage

        return LLMResult(
            generations=[
                [ChatGeneration(message=AIMessage(content=self.response))]
            ]
        )


def get_llm_client():
    """
    Factory function to get the LLM client.

    In production, returns a real client pointing to llama-server.
    In tests, this is replaced by mock_llm fixture.
    """
    from app.core.config import settings

    # TODO: Return ChatOpenAI client pointing to llama-server in production
    # For now, return a placeholder
    return FakeChatModel()
