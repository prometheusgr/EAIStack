"""Tests for the LLM client and FakeChatModel."""

import pytest

from app.core.config import settings
from app.core.llm_client import FakeChatModel, get_llm_client


@pytest.fixture
def llm_provider(monkeypatch):
    """Set settings.llm_provider for the duration of a single test."""

    def _set(provider: str):
        monkeypatch.setattr(settings, "llm_provider", provider)

    return _set


@pytest.mark.unit
def test_fake_chat_model_import():
    """FakeChatModel should be importable without error."""
    assert FakeChatModel is not None


@pytest.mark.unit
def test_fake_chat_model_invoke_returns_canned_response():
    """FakeChatModel.invoke() should return the canned response string."""
    model = FakeChatModel(response="Test response")
    result = model.invoke("What is 2+2?")
    assert result == "Test response"


@pytest.mark.unit
def test_fake_chat_model_invoke_default_response():
    """FakeChatModel should have a default response."""
    model = FakeChatModel()
    result = model.invoke("Any prompt")
    assert result == "This is a fake response from the mocked LLM."


@pytest.mark.unit
def test_fake_chat_model_call_count_increments():
    """FakeChatModel.call_count should increment on each invoke."""
    model = FakeChatModel()
    assert model.call_count == 0

    model.invoke("First call")
    assert model.call_count == 1

    model.invoke("Second call")
    assert model.call_count == 2


@pytest.mark.unit
def test_get_llm_client_returns_fake_model():
    """get_llm_client() should return a FakeChatModel instance."""
    client = get_llm_client()
    assert isinstance(client, FakeChatModel)


@pytest.mark.unit
def test_get_llm_client_invocable():
    """get_llm_client() result should be invocable."""
    client = get_llm_client()
    result = client.invoke("Any prompt")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["llama-cpp", "openai-compatible"])
def test_get_llm_client_returns_real_client_for_openai_providers(llm_provider, provider):
    """Non-fake providers should build a ChatOpenAI client, not the fake model."""
    from langchain_openai import ChatOpenAI

    llm_provider(provider)

    client = get_llm_client()

    assert isinstance(client, ChatOpenAI)
    assert not isinstance(client, FakeChatModel)


@pytest.mark.unit
def test_get_llm_client_applies_configured_model_and_timeout(llm_provider, monkeypatch):
    """The configured model name and timeout should reach the real client."""
    llm_provider("llama-cpp")
    monkeypatch.setattr(settings, "llm_model", "mistral-7b-instruct")
    monkeypatch.setattr(settings, "llm_timeout", 90)

    client = get_llm_client()

    assert client.model_name == "mistral-7b-instruct"
    assert client.request_timeout == 90


@pytest.mark.unit
def test_get_llm_client_rejects_unknown_provider(llm_provider):
    """An unrecognized provider should fail loudly, naming the bad value."""
    llm_provider("not-a-real-provider")

    with pytest.raises(ValueError, match="not-a-real-provider"):
        get_llm_client()
