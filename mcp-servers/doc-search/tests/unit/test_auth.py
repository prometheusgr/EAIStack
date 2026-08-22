"""Tests for independent JWT/JWKS verification in the doc-search MCP server.

This server never trusts a bare user_id handed to it by the backend: every
call must carry a Keycloak access token, which this module verifies against
Keycloak's JWKS itself (same category of check as backend/app/core/auth.py's
verify_token, trimmed to just "verify signature + audience, return sub").

Tests generate a real RSA keypair and a real signed JWT (mirrors
backend/tests/unit/test_auth_audience.py) so no live Keycloak is needed —
only the JWKS HTTP fetch is mocked.
"""

import time
from unittest.mock import AsyncMock, patch

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.utils import to_base64url_uint

import app.auth as auth_module
from app.auth import TokenVerificationError, verify_bearer_token


def _install_fake_jwks_endpoint(monkeypatch, jwks_by_call: list[dict]) -> list[int]:
    """Patch httpx.AsyncClient.get so calls to the JWKS endpoint are served
    from jwks_by_call (one dict per call, last one repeats once exhausted)
    without any real HTTP request. Returns a list whose length grows by one
    per actual call, so tests can assert exactly how many fetches happened.

    This patches at the httpx level (not app.auth.get_keycloak_jwks like the
    other tests in this file) because the cache-busting/cooldown behavior
    under test lives inside get_keycloak_jwks itself.
    """
    call_count: list[int] = []

    async def fake_get(self, url, *args, **kwargs):
        index = min(len(call_count), len(jwks_by_call) - 1)
        call_count.append(1)
        request = httpx.Request("GET", url)
        return httpx.Response(200, json=jwks_by_call[index], request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    return call_count


@pytest.fixture(autouse=True)
def _reset_jwks_cache_state():
    """Every test in this file starts with a clean module-level cache so
    fetch-count assertions aren't polluted by state left over from a
    previous test.
    """
    auth_module._jwks_cache = None
    auth_module._jwks_cache_expiry = 0.0
    auth_module._jwks_last_refetch_attempt = 0.0
    yield
    auth_module._jwks_cache = None
    auth_module._jwks_cache_expiry = 0.0
    auth_module._jwks_last_refetch_attempt = 0.0


def _make_signed_token(claims: dict, kid: str = "test-key") -> tuple[str, dict]:
    """Return (token, jwks) for a freshly generated RSA keypair."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})

    public_numbers = public_key.public_numbers()
    jwks = {
        "keys": [
            {
                "kid": kid,
                "kty": "RSA",
                "use": "sig",
                "n": to_base64url_uint(public_numbers.n).decode("utf-8"),
                "e": to_base64url_uint(public_numbers.e).decode("utf-8"),
            }
        ]
    }
    return token, jwks


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_bearer_token_returns_sub_for_valid_web_client_token():
    """A token signed for the eaistack-web audience is accepted; sub is returned."""
    token, jwks = _make_signed_token(
        {
            "sub": "user-123",
            "aud": "eaistack-web",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
    )

    with patch("app.auth.get_keycloak_jwks", new=AsyncMock(return_value=jwks)):
        user_id = await verify_bearer_token(token)

    assert user_id == "user-123"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_bearer_token_returns_sub_for_valid_api_client_token():
    """A token signed for the eaistack-api audience (service-to-service) is accepted."""
    token, jwks = _make_signed_token(
        {
            "sub": "service-account",
            "aud": "eaistack-api",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
    )

    with patch("app.auth.get_keycloak_jwks", new=AsyncMock(return_value=jwks)):
        user_id = await verify_bearer_token(token)

    assert user_id == "service-account"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_bearer_token_rejects_expired_token():
    """An expired token must not resolve to a user_id."""
    token, jwks = _make_signed_token(
        {
            "sub": "user-123",
            "aud": "eaistack-web",
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
        }
    )

    with patch("app.auth.get_keycloak_jwks", new=AsyncMock(return_value=jwks)):
        with pytest.raises(TokenVerificationError):
            await verify_bearer_token(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_bearer_token_rejects_wrong_audience():
    """A token minted for an unrelated client must be rejected."""
    token, jwks = _make_signed_token(
        {
            "sub": "user-123",
            "aud": "some-other-app",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
    )

    with patch("app.auth.get_keycloak_jwks", new=AsyncMock(return_value=jwks)):
        with pytest.raises(TokenVerificationError):
            await verify_bearer_token(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_bearer_token_rejects_account_only_audience():
    """The default Keycloak 'account' audience alone must not be treated as
    proof of eaistack-web/eaistack-api authorization (mirrors the backend's
    same guard in test_auth_audience.py).
    """
    token, jwks = _make_signed_token(
        {
            "sub": "user-123",
            "aud": "account",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
    )

    with patch("app.auth.get_keycloak_jwks", new=AsyncMock(return_value=jwks)):
        with pytest.raises(TokenVerificationError):
            await verify_bearer_token(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_bearer_token_rejects_token_with_unknown_kid():
    """A token whose kid isn't present in the fetched JWKS must be rejected,
    not crash with a KeyError.
    """
    token, jwks = _make_signed_token(
        {
            "sub": "user-123",
            "aud": "eaistack-web",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        kid="key-that-is-not-in-jwks",
    )
    jwks["keys"][0]["kid"] = "a-different-key"

    with patch("app.auth.get_keycloak_jwks", new=AsyncMock(return_value=jwks)):
        with pytest.raises(TokenVerificationError):
            await verify_bearer_token(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_bearer_token_rejects_token_signed_by_wrong_key():
    """A token signed by a key that isn't Keycloak's must be rejected even if
    the kid happens to match (signature verification, not just key lookup).
    """
    token, _real_jwks = _make_signed_token(
        {
            "sub": "user-123",
            "aud": "eaistack-web",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        kid="shared-kid",
    )
    # A JWKS from an unrelated keypair, but claiming the same kid.
    _unrelated_token, attacker_jwks = _make_signed_token(
        {"sub": "irrelevant", "aud": "eaistack-web"}, kid="shared-kid"
    )

    with patch("app.auth.get_keycloak_jwks", new=AsyncMock(return_value=attacker_jwks)):
        with pytest.raises(TokenVerificationError):
            await verify_bearer_token(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_bearer_token_rejects_malformed_token():
    """A string that isn't a JWT at all must raise, not crash."""
    with pytest.raises(TokenVerificationError):
        await verify_bearer_token("not-a-jwt")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unknown_kid_does_not_refetch_jwks_within_cooldown(monkeypatch):
    """Two requests bearing different bogus/unknown kids, submitted back to
    back, must only trigger ONE real JWKS fetch (the initial cache
    population) rather than a fresh Keycloak round-trip per request.

    Without a cooldown, verify_bearer_token's cache-miss handling
    unconditionally clears _jwks_cache and refetches on every unrecognized
    kid — turning a bogus/unknown kid into a free way to force full-rate
    JWKS refetches against Keycloak on every single request, bypassing the
    600s TTL entirely. This is the cache-busting DoS this test guards
    against.
    """
    _token, jwks = _make_signed_token(
        {
            "sub": "user-123",
            "aud": "eaistack-web",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        kid="the-real-key",
    )
    call_count = _install_fake_jwks_endpoint(monkeypatch, [jwks])

    bogus_token_1, _ = _make_signed_token(
        {"sub": "attacker", "aud": "eaistack-web"}, kid="bogus-kid-1"
    )
    bogus_token_2, _ = _make_signed_token(
        {"sub": "attacker", "aud": "eaistack-web"}, kid="bogus-kid-2"
    )

    with pytest.raises(TokenVerificationError):
        await verify_bearer_token(bogus_token_1)
    with pytest.raises(TokenVerificationError):
        await verify_bearer_token(bogus_token_2)

    assert len(call_count) == 1, (
        "expected exactly one JWKS fetch (initial population); the second "
        "unknown kid should have been rejected using the cooldown-protected "
        "cache instead of triggering another HTTP call"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_legitimate_key_rotation_refetches_after_cooldown_elapses(monkeypatch):
    """A genuinely rotated signing key must still be picked up once the
    cooldown window has passed — the cooldown must not permanently pin the
    cache past a real Keycloak key rotation.
    """
    old_token, old_jwks = _make_signed_token(
        {
            "sub": "user-old",
            "aud": "eaistack-web",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        kid="old-key",
    )
    new_token, new_jwks = _make_signed_token(
        {
            "sub": "user-new",
            "aud": "eaistack-web",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        kid="new-key",
    )
    call_count = _install_fake_jwks_endpoint(monkeypatch, [old_jwks, new_jwks])

    # Populate the cache with the old JWKS.
    user_id = await verify_bearer_token(old_token)
    assert user_id == "user-old"
    assert len(call_count) == 1

    # Simulate the cooldown having fully elapsed since the last refetch
    # attempt, as if real time had passed (e.g. Keycloak rotated its key
    # between requests, well outside the DoS-mitigation cooldown window).
    auth_module._jwks_last_refetch_attempt -= auth_module._JWKS_REFETCH_COOLDOWN_SECONDS + 1

    # The new key's kid isn't in the cached (old) JWKS, so this must trigger
    # a real refetch — and, this time, succeed.
    user_id = await verify_bearer_token(new_token)

    assert user_id == "user-new"
    assert len(call_count) == 2, "expected a second fetch once the cooldown had elapsed"
