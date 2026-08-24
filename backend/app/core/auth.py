"""Authentication and authorization middleware."""

import logging
import time
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

from app.core.config import settings
from app.core.tls import httpx_verify

logger = logging.getLogger(__name__)
security = HTTPBearer()

_jwks_cache: dict[Any, Any] | None = None
_jwks_cache_expiry: float = 0.0
_JWKS_CACHE_TTL: int = 600  # 10 minutes


async def get_keycloak_public_key() -> dict[Any, Any]:
    """Fetch Keycloak realm's public key with TTL caching."""
    global _jwks_cache, _jwks_cache_expiry

    current_time = time.monotonic()

    if _jwks_cache is not None and current_time < _jwks_cache_expiry:
        logger.debug("Using cached JWKS")
        return _jwks_cache

    jwks_url = (
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
    )
    async with httpx.AsyncClient(verify=httpx_verify()) as client:
        response = await client.get(jwks_url)
        response.raise_for_status()
        jwks: dict[Any, Any] = response.json()

    _jwks_cache = jwks
    _jwks_cache_expiry = current_time + _JWKS_CACHE_TTL
    logger.debug("Cached JWKS, expires in %ds", _JWKS_CACHE_TTL)
    return jwks


async def verify_token(credentials=Depends(security)) -> dict:
    """Verify JWT token from Keycloak."""
    token = credentials.credentials
    logger.debug("Verifying token, first 20 chars: %s...", token[:20])

    try:
        logger.debug("Fetching Keycloak public key from %s", settings.keycloak_url)
        jwks = await get_keycloak_public_key()
        logger.debug("Got %d keys from Keycloak", len(jwks.get("keys", [])))

        unverified_header = jwt.get_unverified_header(token)
        if not isinstance(unverified_header, dict):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token header is invalid",
            )

        kid = unverified_header.get("kid")
        logger.debug("Token kid: %s", kid)

        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing key ID (kid)",
            )

        key = None
        for k in jwks.get("keys", []):
            if k.get("kid") == kid:
                key = jwt.PyJWK(k)
                break

        if not key:
            logger.debug("Key not found in cache, refreshing...")
            global _jwks_cache, _jwks_cache_expiry
            _jwks_cache = None
            _jwks_cache_expiry = 0.0
            jwks = await get_keycloak_public_key()
            for k in jwks.get("keys", []):
                if k.get("kid") == kid:
                    key = jwt.PyJWK(k)
                    break

        if not key:
            logger.error("Key not found for kid: %s", kid)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Key not found",
            )

        valid_audiences = [settings.keycloak_client_id, settings.keycloak_web_client_id]
        logger.debug("Decoding token with audiences: %s", valid_audiences)

        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=valid_audiences,
                options={"verify_aud": True},
            )
        except jwt.InvalidAudienceError:
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
            logger.warning(
                "Token audience: %s, valid audiences: %s",
                payload.get("aud"),
                valid_audiences,
            )
            raise

        logger.info(
            "Token verified for user: %s, audience: %s",
            payload.get("preferred_username"),
            payload.get("aud"),
        )
        return payload

    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except jwt.InvalidAudienceError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid audience: {str(e)}",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )
    except Exception as e:
        logger.error("Unexpected token verification error: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed",
        ) from e


async def extract_user_from_payload(payload: dict, access_token: str | None = None) -> dict:
    """Extract current user from verified token payload.

    access_token carries the raw JWT string (not the decoded payload) so
    callers that need to forward the caller's own credentials to another
    service — e.g. the doc-search MCP server, which independently verifies it
    against Keycloak's JWKS rather than trusting a bare user_id — can do so
    without re-encoding a token from the decoded payload.
    """
    user_id = payload.get("sub")
    username = payload.get("preferred_username")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
        )

    return {
        "user_id": user_id,
        "username": username,
        "email": payload.get("email"),
        "name": payload.get("name"),
        "token": payload,
        "access_token": access_token,
    }


async def get_current_user(
    payload: dict = Depends(verify_token),
    credentials=Depends(security),
) -> dict:
    """Extract current user from verified token payload (dependency-injected).

    Takes its own Depends(security) (the same HTTPBearer instance verify_token
    uses) purely to recover the raw token string — verify_token only returns
    the decoded payload, never the string it decoded, and changing that return
    shape would break every existing caller that treats its result as the
    payload dict directly.
    """
    return await extract_user_from_payload(payload, access_token=credentials.credentials)


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require the admin Keycloak realm role (dependency-injected).

    Reads roles from the token's realm_access.roles claim, the standard
    location Keycloak places realm roles in a JWT. Raises 403 if the
    admin role is absent, whether because the user lacks it or the token
    has no realm_access claim at all.
    """
    roles = user["token"].get("realm_access", {}).get("roles", [])
    if "admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
