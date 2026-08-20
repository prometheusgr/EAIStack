"""Database initialization and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Database setup for SessionLocal
# Note: Tables are created only in tests (via conftest) or via alembic migrations
# in production. This avoids connection errors at import time if DB is not ready.
try:
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception:
    # If DB connection fails at import time, create an unbound SessionLocal so
    # import doesn't crash when no DB is reachable (e.g. running the test suite
    # without a live Postgres). Sessions created from it raise only if actually
    # used to run a query; production and tests both override get_db with a
    # real, bound session before any query executes.
    SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def get_db():
    """Get database session (overridable in tests)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
