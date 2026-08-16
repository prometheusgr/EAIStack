"""Tests for the LLM client and FakeChatModel."""

import pytest

from app.core.llm_client import FakeChatModel, get_llm_client


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
