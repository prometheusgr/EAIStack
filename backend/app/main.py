"""FastAPI application entry point."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, auth
from app.core.auth import get_current_user
from app.core.config import settings

app = FastAPI(
    title="EAIStack Backend",
    description="Enterprise AI Stack - FastAPI Backend",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router)
app.include_router(auth.router)


@app.get("/health")
async def health_check():
    """Health check endpoint (public)."""
    return {"status": "ok"}


@app.get("/auth/me")
async def get_user_info(user: dict = Depends(get_current_user)):
    """Get authenticated user info."""
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "email": user["email"],
        "name": user["name"],
    }


@app.get("/debug/token")
async def debug_token(user: dict = Depends(get_current_user)):
    """Debug endpoint - shows full token payload."""
    return {
        "message": "Token validation successful",
        "user": user,
        "keycloak_url": settings.keycloak_url,
        "keycloak_realm": settings.keycloak_realm,
        "keycloak_client_id": settings.keycloak_client_id,
    }
