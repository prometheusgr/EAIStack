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

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.utils import to_base64url_uint

from app.auth import TokenVerificationError, verify_bearer_token


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
