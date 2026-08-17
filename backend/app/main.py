"""FastAPI application entry point."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, auth, apikeys
from app.core.auth import get_current_user
from app.core.config import settings
from sqlalchemy.orm import sessionmaker
from app.db.models import Base
from sqlalchemy import create_engine

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

# Database setup for SessionLocal
# Note: Tables are created only in tests (via conftest) or via alembic migrations
# in production. This avoids connection errors at import time if DB is not ready.
try:
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception:
    # If DB connection fails at import time, create a dummy SessionLocal
    # Tests will override this via dependency injection
    from sqlalchemy import create_mock_engine

    def dump(sql, *multiparams, **params):
        pass

    mock_engine = create_mock_engine(lambda: None, dump)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=mock_engine)

app.include_router(agents.router)
app.include_router(auth.router)
app.include_router(apikeys.router)


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
