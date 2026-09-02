"""Probes an OpenAI-compatible provider URL for reachability and served models.

Backs the Settings screen's "Test connection" action for the LLM and
embedding provider URL fields: both llama-cpp and openai-compatible
providers implement OpenAI's `GET /v1/models` endpoint, so one probe
against it both proves the URL is a working OpenAI-compatible server and
returns real model names for the admin to pick from, instead of typing one
in blind.

This is a diagnostic, not an internal call that should ever raise past its
own boundary: every failure mode (unreachable host, timeout, non-2xx,
unexpected body shape) is folded into ProviderProbeResult(ok=False, ...)
so the API layer can hand it straight to the frontend without needing to
distinguish "the probe failed" from "the probe function itself broke".
"""

from dataclasses import dataclass

import httpx

from app.core.tls import get_ssl_context


@dataclass(frozen=True)
class ProviderProbeResult:
    """Outcome of probing one provider URL's /models endpoint."""

    ok: bool
    models: list[str]
    error: str | None


async def probe_provider(url: str, api_key: str | None, timeout: float) -> ProviderProbeResult:
    """GET {url}/models (OpenAI-compatible) and return the served model ids.

    api_key is sent as a Bearer token only when truthy -- an unauthenticated
    local llama-server must not receive a bogus header that could make it
    reject the request, mirroring app.core.llm_client.get_llm_client's
    "not-needed" fallback for the real chat client.
    """
    models_url = f"{url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    try:
        async with httpx.AsyncClient(verify=get_ssl_context()) as client:
            response = await client.get(models_url, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        return ProviderProbeResult(ok=False, models=[], error=f"Could not reach {url}: {exc}")

    if response.status_code < 200 or response.status_code >= 300:
        return ProviderProbeResult(
            ok=False,
            models=[],
            error=f"{url} responded with HTTP {response.status_code}",
        )

    try:
        body = response.json()
        models = [entry["id"] for entry in body["data"]]
    except (ValueError, KeyError, TypeError):
        return ProviderProbeResult(
            ok=False,
            models=[],
            error=f"{url} did not return a recognizable OpenAI-compatible model list",
        )

    return ProviderProbeResult(ok=True, models=models, error=None)
