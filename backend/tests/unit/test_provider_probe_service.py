"""Unit tests for app.services.provider_probe_service.probe_provider.

TDD discipline: these specify the user-visible signal the Settings screen's
"Test connection" button relies on -- a probe result the admin can read
(connected + model list, or a plain-English reason it failed) without ever
raising out to a 500.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.provider_probe_service import probe_provider


def _mock_async_client(mock_response=None, raise_error: Exception | None = None):
    """Patch app.services.provider_probe_service.httpx.AsyncClient, mirroring
    test_auth_api_rate_limit.py's _mock_keycloak_success shape.
    """
    mock_client_instance = AsyncMock()
    if raise_error is not None:
        mock_client_instance.get = AsyncMock(side_effect=raise_error)
    else:
        mock_client_instance.get = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)
    return patch(
        "app.services.provider_probe_service.httpx.AsyncClient",
        return_value=mock_client_instance,
    )


def _response(status_code: int, json_body):
    response = MagicMock()
    response.status_code = status_code
    response.json = MagicMock(return_value=json_body)
    return response


@pytest.mark.unit
async def test_probe_provider_returns_model_ids_on_success():
    response = _response(200, {"data": [{"id": "llama-3-8b"}, {"id": "nomic-embed"}]})

    with _mock_async_client(mock_response=response):
        result = await probe_provider(url="http://localhost:8000/v1", api_key=None, timeout=5.0)

    assert result.ok is True
    assert result.models == ["llama-3-8b", "nomic-embed"]
    assert result.error is None


@pytest.mark.unit
async def test_probe_provider_reports_connection_refused_without_raising():
    with _mock_async_client(raise_error=httpx.ConnectError("Connection refused")):
        result = await probe_provider(url="http://localhost:9999/v1", api_key=None, timeout=5.0)

    assert result.ok is False
    assert result.models == []
    assert result.error is not None
    assert "Connection refused" in result.error or "connect" in result.error.lower()


@pytest.mark.unit
async def test_probe_provider_reports_timeout_without_raising():
    with _mock_async_client(raise_error=httpx.TimeoutException("timed out")):
        result = await probe_provider(url="http://localhost:8000/v1", api_key=None, timeout=1.0)

    assert result.ok is False
    assert result.models == []
    assert result.error is not None


@pytest.mark.unit
async def test_probe_provider_reports_non_2xx_status():
    response = _response(404, {"error": "not found"})

    with _mock_async_client(mock_response=response):
        result = await probe_provider(url="http://localhost:8000/v1", api_key=None, timeout=5.0)

    assert result.ok is False
    assert result.models == []
    assert "404" in result.error


@pytest.mark.unit
async def test_probe_provider_reports_malformed_body_without_raising():
    response = _response(200, {"unexpected": "shape"})

    with _mock_async_client(mock_response=response):
        result = await probe_provider(url="http://localhost:8000/v1", api_key=None, timeout=5.0)

    assert result.ok is False
    assert result.models == []
    assert result.error is not None


@pytest.mark.unit
async def test_probe_provider_sends_no_auth_header_when_api_key_is_none():
    response = _response(200, {"data": []})

    with _mock_async_client(mock_response=response) as mock_ctor:
        await probe_provider(url="http://localhost:8000/v1", api_key=None, timeout=5.0)

    mock_client_instance = mock_ctor.return_value
    call_kwargs = mock_client_instance.get.call_args.kwargs
    headers = call_kwargs.get("headers") or {}
    assert "Authorization" not in headers


@pytest.mark.unit
async def test_probe_provider_sends_bearer_header_when_api_key_set():
    response = _response(200, {"data": []})

    with _mock_async_client(mock_response=response) as mock_ctor:
        await probe_provider(url="http://localhost:8000/v1", api_key="secret-key", timeout=5.0)

    mock_client_instance = mock_ctor.return_value
    call_kwargs = mock_client_instance.get.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer secret-key"


@pytest.mark.unit
async def test_probe_provider_strips_trailing_slash_before_appending_models():
    response = _response(200, {"data": []})

    with _mock_async_client(mock_response=response) as mock_ctor:
        await probe_provider(url="http://localhost:8000/v1/", api_key=None, timeout=5.0)

    mock_client_instance = mock_ctor.return_value
    requested_url = mock_client_instance.get.call_args.args[0]
    assert requested_url == "http://localhost:8000/v1/models"
