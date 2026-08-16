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
    token = credentials.credentials

    try:
        import jwt

        jwks = await get_keycloak_public_key()
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

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
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Key not found",
            )

        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.keycloak_client_id,
        )

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
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
