"""Database initialization and session management."""

from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, create_mock_engine

from app.core.config import settings

# Database setup for SessionLocal
# Note: Tables are created only in tests (via conftest) or via alembic migrations
# in production. This avoids connection errors at import time if DB is not ready.
try:
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception:
    # If DB connection fails at import time, create a dummy SessionLocal
    # Tests will override this via dependency injection
    def dump(sql, *multiparams, **params):
        pass

    engine = create_mock_engine(lambda: None, dump)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Get database session (overridable in tests)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
