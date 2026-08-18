"""FastAPI application entry point."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, auth, apikeys, embeddings, knowledge_base
from app.core.auth import get_current_user
from app.core.config import settings
from app.db.database import SessionLocal, engine
from app.db.models import Base

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

# Create tables at startup (development only; production uses alembic migrations)
with engine.begin() as conn:
    conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
Base.metadata.create_all(bind=engine)

app.include_router(agents.router)
app.include_router(auth.router)
app.include_router(apikeys.router)
app.include_router(embeddings.router)
app.include_router(knowledge_base.router)


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
