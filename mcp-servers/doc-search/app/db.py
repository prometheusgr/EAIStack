"""Database initialization and session management.

Mirrors backend/app/db/database.py's shape exactly: doc-search is a
separate deployable with its own connection to the same Postgres instance
(read access to knowledge_base/embeddings, read access to system_settings
for the admin-configurable embedding provider override).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

try:
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception:
    # If DB connection fails at import time, create an unbound SessionLocal so
    # import doesn't crash when no DB is reachable (e.g. running the test
    # suite without a live Postgres). Mirrors backend/app/db/database.py.
    SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def get_db():
    """Yield a database session, closed when the caller is done with it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
