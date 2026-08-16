"""Authentication and authorization middleware."""


import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

from app.core.config import settings

security = HTTPBearer()


async def get_keycloak_public_key() -> dict:
    """Fetch Keycloak realm's public key."""
    jwks_url = (
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
    )
    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_url)
        response.raise_for_status()
        return response.json()


async def verify_token(credentials=Depends(security)) -> dict:
    """Verify JWT token from Keycloak."""
    import logging
    logger = logging.getLogger(__name__)

    token = credentials.credentials
    logger.debug(f"Verifying token, first 20 chars: {token[:20]}...")

    try:
        import jwt

        logger.debug(f"Fetching Keycloak public key from {settings.keycloak_url}")
        jwks = await get_keycloak_public_key()
        logger.debug(f"Got {len(jwks.get('keys', []))} keys from Keycloak")

        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        logger.debug(f"Token kid: {kid}")

        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing key ID",
            )

        key = None
        for k in jwks.get("keys", []):
            if k.get("kid") == kid:
                key = jwt.algorithms.RSAAlgorithm.from_jwk(k)
                break

        if not key:
            logger.error(f"Key not found for kid: {kid}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Key not found",
            )

        logger.debug(f"Decoding token with audience: {[settings.keycloak_client_id, 'eaistack-web']}")
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=[settings.keycloak_client_id, "eaistack-web"],
                options={"verify_aud": True},
            )
        except jwt.InvalidAudienceError as aud_error:
            logger.warning(f"Audience validation failed: {aud_error}, trying without aud validation")
            # Fallback: decode without audience validation to see what's in the token
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
            logger.warning(f"Token audience: {payload.get('aud')}, valid audiences: {[settings.keycloak_client_id, 'eaistack-web']}")
            raise jwt.InvalidAudienceError(f"Token audience '{payload.get('aud')}' not in {[settings.keycloak_client_id, 'eaistack-web']}")

        logger.info(f"Token verified for user: {payload.get('preferred_username')}, audience: {payload.get('aud')}")
        return payload

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
        import logging
        logging.error(f"Token verification error: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(e)}",
        )


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
