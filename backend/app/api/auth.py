"""Authentication endpoints - handles OAuth2 code exchange."""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.client_ip import resolve_client_ip
from app.core.config import settings
from app.core.tls import httpx_verify
from app.db.database import get_db
from app.db.models import utc_now
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services import check_auth_rate_limit, purge_user_conversations, resolve_retention_config
from app.services.rate_limit_config_service import resolve_rate_limit_config
from app.services.rate_limiter_service import rate_limit_exceeded_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class TokenExchangeRequest(BaseModel):
    """OAuth2 token request - authorization code or refresh token grant."""

    code: str | None = None
    redirect_uri: str | None = None
    grant_type: str = "authorization_code"
    refresh_token: str | None = None


class LogoutResponse(BaseModel):
    """Response body for POST /api/auth/logout."""

    purged_conversations: int


class TokenResponse(BaseModel):
    """OAuth2 token response."""

    access_token: str
    token_type: str
    refresh_token: str | None = None
    id_token: str | None = None
    expires_in: int | None = None


@router.post("/token", response_model=TokenResponse)
async def exchange_token(
    request: TokenExchangeRequest,
    http_request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse | JSONResponse:
    """
    OAuth2 token endpoint - supports authorization code and refresh token grants.

    Authorization code flow:
    1. Frontend redirects to Keycloak login
    2. User logs in to Keycloak
    3. Keycloak redirects back with ?code=...
    4. Frontend sends code to this endpoint
    5. This endpoint exchanges code with Keycloak server-to-server
    6. Returns access token to frontend

    Refresh token flow:
    1. Frontend has a stored refresh_token
    2. Frontend sends refresh_token to this endpoint
    3. This endpoint exchanges it with Keycloak server-to-server
    4. Returns new access token to frontend

    Rate limiting (issue #25) runs before any of the above, keyed by client
    IP rather than user_id -- this endpoint is how a caller *gets* a JWT in
    the first place, so no validated identity exists yet to key on.
    app.core.client_ip.resolve_client_ip resolves the real client IP: by
    default (rate_limit_trusted_proxy_count=0) it's the raw transport peer
    IP, falling back to a single shared "unknown" bucket if even that is
    missing (possible under some ASGI test transports). Behind a reverse
    proxy/ingress (this repo's own Helm deployment target, Phase 5), the
    transport peer IP is the proxy's own address for every caller -- set
    rate_limit_trusted_proxy_count to the number of trusted hops so the
    real client IP is read from X-Forwarded-For instead; see
    docs/SECURITY.md's Rate Limiting section. Trip is a 429 with a
    Retry-After header, same shape as the chat endpoint's; also
    deliberately not audit-logged, for the same reason (see
    app.services.rate_limiter_service and docs/SECURITY.md).
    """
    client_ip = resolve_client_ip(
        peer_ip=http_request.client.host if http_request.client else None,
        forwarded_for_header=http_request.headers.get("X-Forwarded-For"),
        trusted_proxy_count=settings.rate_limit_trusted_proxy_count,
    )
    db_settings = SystemSettingsRepository(db).get()
    rate_limit_config = resolve_rate_limit_config(db, db_settings)
    rate_limit_result = check_auth_rate_limit(
        db, client_ip=client_ip, now=utc_now(), config=rate_limit_config
    )
    if not rate_limit_result.allowed:
        return rate_limit_exceeded_response(
            rate_limit_result, message="Too many requests. Please wait before trying again."
        )

    try:
        token_endpoint = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/token"

        if request.grant_type == "authorization_code":
            if not request.code or not request.redirect_uri:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="code and redirect_uri required for authorization_code grant",
                )
            logger.info("Exchanging authorization code for token")
            token_data = {
                "grant_type": "authorization_code",
                "code": request.code,
                "client_id": settings.keycloak_web_client_id,
                "redirect_uri": request.redirect_uri,
            }
        elif request.grant_type == "refresh_token":
            if not request.refresh_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="refresh_token required for refresh_token grant",
                )
            logger.info("Refreshing access token")
            token_data = {
                "grant_type": "refresh_token",
                "refresh_token": request.refresh_token,
                "client_id": settings.keycloak_web_client_id,
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported grant_type: {request.grant_type}",
            )

        async with httpx.AsyncClient(verify=httpx_verify()) as client:
            response = await client.post(token_endpoint, data=token_data, timeout=10.0)

            if response.status_code != 200:
                error_detail = response.text
                logger.error("Keycloak returned %d: %s", response.status_code, error_detail)
                try:
                    error_data = response.json()
                    error_detail = error_data.get(
                        "error_description",
                        error_data.get("error", error_detail),
                    )
                except Exception:
                    pass

                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token request failed",
                )

            token_response = response.json()
            logger.info("Token request successful")

            return TokenResponse(
                access_token=token_response.get("access_token"),
                token_type=token_response.get("token_type", "Bearer"),
                refresh_token=token_response.get("refresh_token"),
                id_token=token_response.get("id_token"),
                expires_in=token_response.get("expires_in"),
            )

    except httpx.RequestError as e:
        logger.error("Keycloak unreachable: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Keycloak unavailable",
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error: %s: %s", type(e).__name__, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token request failed",
        ) from e


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LogoutResponse:
    """Log out, optionally purging the caller's conversation history.

    Implements SECURITY.md's Option 1 (logout-triggered cleanup): when
    cleanup_on_logout is on, this deletes the caller's conversation threads
    and checkpoint state. When it's off, the session simply ends and history
    survives until the TTL sweep collects it.

    The user_id purged always comes from the validated token, never from
    request input, so this endpoint is structurally incapable of deleting
    another user's conversations. Audit records are never touched - the
    purge path does not query them.
    """
    if not resolve_retention_config(db).cleanup_on_logout:
        return LogoutResponse(purged_conversations=0)

    purged = purge_user_conversations(db, user_id=user["user_id"])
    db.commit()

    logger.info("Logout cleanup: purged %d conversation thread(s)", purged)
    return LogoutResponse(purged_conversations=purged)
