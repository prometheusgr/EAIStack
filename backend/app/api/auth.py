"""Authentication endpoints - handles OAuth2 code exchange."""

import logging
import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class TokenExchangeRequest(BaseModel):
    """OAuth2 authorization code exchange request."""

    code: str
    redirect_uri: str


class TokenResponse(BaseModel):
    """OAuth2 token response."""

    access_token: str
    token_type: str
    refresh_token: str | None = None
    expires_in: int | None = None


@router.post("/token", response_model=TokenResponse)
async def exchange_code_for_token(request: TokenExchangeRequest):
    """
    Exchange authorization code for access token.

    This endpoint implements the OAuth2 authorization code exchange flow.
    Frontend gets a code from Keycloak, sends it here, and receives an access token.

    Flow:
    1. Frontend redirects to Keycloak login
    2. User logs in to Keycloak
    3. Keycloak redirects back with ?code=...
    4. Frontend sends code to this endpoint
    5. This endpoint exchanges code with Keycloak server-to-server
    6. Returns access token to frontend
    7. Frontend stores token and uses it for API calls
    """
    try:
        logger.info(f"[Auth] Exchanging code for token")
        logger.debug(f"[Auth] Code: {request.code[:20] if request.code else 'none'}...")

        # Exchange code with Keycloak server
        token_endpoint = (
            f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/token"
        )
        logger.debug(f"[Auth] Token endpoint: {token_endpoint}")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": request.code,
                    "client_id": "eaistack-web",  # Public client
                    "redirect_uri": request.redirect_uri,
                },
                timeout=10.0,
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"[Auth] Keycloak returned {response.status_code}: {error_detail}")
                try:
                    error_data = response.json()
                    error_detail = error_data.get(
                        "error_description",
                        error_data.get("error", error_detail)
                    )
                except Exception:
                    pass

                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Code exchange failed: {error_detail}",
                )

            token_data = response.json()
            logger.info("[Auth] Token exchange successful")

            return TokenResponse(
                access_token=token_data.get("access_token"),
                token_type=token_data.get("token_type", "Bearer"),
                refresh_token=token_data.get("refresh_token"),
                expires_in=token_data.get("expires_in"),
            )

    except httpx.RequestError as e:
        logger.error(f"[Auth] Keycloak unreachable: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Keycloak unavailable: {str(e)}",
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Auth] Unexpected error: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token exchange error: {str(e)}",
        ) from e
