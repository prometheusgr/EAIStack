"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, apikeys, auth, embeddings, knowledge_base
from app.api import settings as settings_api
from app.core.auth import get_current_user
from app.core.config import settings
from app.core.tracing import configure_tracing
from app.db.database import SessionLocal
from app.services.tracing_config_service import resolve_tracing_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Resolve DB-backed config that must be settled before the app starts
    serving, then hand control to the running app.

    tracing_enabled is the one field in SystemSettings that can't be
    resolved per-request the way llm_provider/guardrail config are (see
    app.services.tracing_config_service's module docstring - there is no
    supported way to re-instrument a running process's OTel tracer
    provider), so it is resolved exactly once, here, at startup. A short-
    lived session is enough: this is a single read, not something that
    needs to stay open for the app's lifetime.
    """
    db = SessionLocal()
    try:
        tracing_config = resolve_tracing_config(db)
    finally:
        db.close()

    configure_tracing(settings, enabled=tracing_config.enabled)

    yield


app = FastAPI(
    title="EAIStack Backend",
    description="Enterprise AI Stack - FastAPI Backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Schema is managed by Alembic migrations
# Run migrations with: alembic upgrade head
# To generate new migrations after model changes: alembic revision --autogenerate -m "description"

app.include_router(agents.router)
app.include_router(auth.router)
app.include_router(apikeys.router)
app.include_router(embeddings.router)
app.include_router(knowledge_base.router)
app.include_router(settings_api.router)


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
