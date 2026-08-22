"""Independent JWT/JWKS verification for the doc-search MCP server.

This server is reached over the network by the backend (and, in principle,
any other future caller), so it never trusts a bare user_id handed to it —
every call must carry a Keycloak access token, which is verified here against
Keycloak's own JWKS. This mirrors backend/app/core/auth.py's verify_token,
trimmed to just "verify signature + audience + expiry, return sub": doc-search
has no admin-role concept and no FastAPI request/response handling, so those
parts of the backend's version don't apply here.
"""

import logging
import time
from typing import Any

import httpx
import jwt

from app.config import settings

logger = logging.getLogger(__name__)

_jwks_cache: dict[Any, Any] | None = None
_jwks_cache_expiry: float = 0.0
_JWKS_CACHE_TTL: int = 600  # 10 minutes

# Tracks the monotonic time of the *last* JWKS fetch attempt, regardless of
# whether it was a normal TTL-driven refresh or a forced refetch triggered by
# an unrecognized kid (see verify_bearer_token below). A forced refetch is
# only allowed to actually hit the network if this much time has passed
# since the previous attempt. Without this, a token carrying a bogus/unknown
# kid on every request would force a full JWKS refetch from Keycloak on
# every single request, bypassing _JWKS_CACHE_TTL entirely and turning an
# unauthenticated endpoint into a DoS amplifier against Keycloak (a shared
# piece of infrastructure the whole stack depends on). Deliberately much
# shorter than _JWKS_CACHE_TTL: legitimate key rotation should still be
# picked up promptly, this only caps the *rate* of forced refetches.
_jwks_last_refetch_attempt: float = 0.0
_JWKS_REFETCH_COOLDOWN_SECONDS: int = 30

_http_client: httpx.AsyncClient | None = None


class TokenVerificationError(Exception):
    """Raised when a bearer token fails signature, audience, or expiry checks."""


def _get_http_client() -> httpx.AsyncClient:
    """Return a process-wide httpx.AsyncClient, created on first use.

    A fresh AsyncClient per request means a fresh TCP+TLS connection every
    time (no keep-alive reuse) — cheap when JWKS fetches are rare (once per
    _JWKS_CACHE_TTL), but this is also the resource the cooldown above is
    protecting: reusing one pooled client keeps even a burst of
    cooldown-limited forced refetches cheap. Mirrors app/db.py's
    module-level SessionLocal/engine: a lazily-created, process-lifetime
    singleton rather than an explicit startup/shutdown lifespan hook, since
    this service has no existing lifespan wiring to hook into.
    """
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient()
    return _http_client


async def get_keycloak_jwks() -> dict[Any, Any]:
    """Fetch Keycloak realm's JWKS with TTL caching."""
    global _jwks_cache, _jwks_cache_expiry, _jwks_last_refetch_attempt

    current_time = time.monotonic()
    if _jwks_cache is not None and current_time < _jwks_cache_expiry:
        return _jwks_cache

    jwks_url = (
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
    )
    client = _get_http_client()
    response = await client.get(jwks_url, timeout=10.0)
    response.raise_for_status()
    jwks: dict[Any, Any] = response.json()

    _jwks_cache = jwks
    _jwks_cache_expiry = current_time + _JWKS_CACHE_TTL
    _jwks_last_refetch_attempt = current_time
    return jwks


async def verify_bearer_token(token: str) -> str:
    """Verify a Keycloak-issued access token and return its subject (user_id).

    Raises TokenVerificationError for any failure: expired token, wrong
    audience, unknown or mismatched signing key, or a malformed token. Never
    returns a user_id unless the signature has actually been checked against
    a Keycloak-published key — a valid `kid` match alone is not sufficient.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as e:
        raise TokenVerificationError(f"Malformed token: {e}") from e

    kid = unverified_header.get("kid")
    if not kid:
        raise TokenVerificationError("Token missing key ID (kid)")

    jwks = await get_keycloak_jwks()
    key = _find_key_for_kid(jwks, kid)

    if key is None and _cooldown_has_elapsed():
        global _jwks_cache, _jwks_cache_expiry
        _jwks_cache = None
        _jwks_cache_expiry = 0.0
        jwks = await get_keycloak_jwks()
        key = _find_key_for_kid(jwks, kid)

    if key is None:
        raise TokenVerificationError(f"No matching signing key for kid: {kid}")

    valid_audiences = [settings.keycloak_client_id, settings.keycloak_web_client_id]
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=valid_audiences,
            options={"verify_aud": True},
        )
    except jwt.ExpiredSignatureError as e:
        raise TokenVerificationError("Token expired") from e
    except jwt.InvalidAudienceError as e:
        raise TokenVerificationError(f"Invalid audience: {e}") from e
    except jwt.InvalidTokenError as e:
        raise TokenVerificationError(f"Invalid token: {e}") from e

    user_id = payload.get("sub")
    if not user_id:
        raise TokenVerificationError("Token missing subject claim")

    return str(user_id)


def _cooldown_has_elapsed() -> bool:
    """Whether enough time has passed since the last JWKS fetch attempt to
    allow another forced refetch on a cache miss. See
    _JWKS_REFETCH_COOLDOWN_SECONDS for why this exists.
    """
    return time.monotonic() - _jwks_last_refetch_attempt >= _JWKS_REFETCH_COOLDOWN_SECONDS


def _find_key_for_kid(jwks: dict[Any, Any], kid: str) -> jwt.PyJWK | None:
    """Return the PyJWK matching kid, or None if not present in this JWKS."""
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            return jwt.PyJWK(k)
    return None
