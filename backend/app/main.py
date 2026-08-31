"""FastAPI application entry point."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, apikeys, auth, embeddings, knowledge_base
from app.api import settings as settings_api
from app.core.auth import get_current_user
from app.core.config import settings
from app.core.tracing import configure_tracing

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

# No-op unless TRACING_ENABLED is set (see app.core.tracing) - registers
# OpenTelemetry/LangChain instrumentation once, at import time of this
# module, so every chat agent run is traced to Phoenix if enabled.
configure_tracing(settings)

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
