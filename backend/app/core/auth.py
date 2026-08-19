"""Authentication and authorization middleware."""

import logging
import time
import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

from app.core.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer()

_jwks_cache: dict | None = None
_jwks_cache_expiry: float = 0.0
_JWKS_CACHE_TTL: int = 600  # 10 minutes


async def get_keycloak_public_key() -> dict:
    """Fetch Keycloak realm's public key with TTL caching."""
    global _jwks_cache, _jwks_cache_expiry

    current_time = time.monotonic()

    if _jwks_cache is not None and current_time < _jwks_cache_expiry:
        logger.debug("Using cached JWKS")
        return _jwks_cache

    jwks_url = (
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
    )
    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_url)
        response.raise_for_status()
        jwks = response.json()

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


async def extract_user_from_payload(payload: dict) -> dict:
    """Extract current user from verified token payload."""
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
    }


async def get_current_user(payload: dict = Depends(verify_token)) -> dict:
    """Extract current user from verified token payload (dependency-injected)."""
    return await extract_user_from_payload(payload)
