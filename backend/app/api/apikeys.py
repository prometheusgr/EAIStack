"""API endpoints for API Key management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from uuid import uuid4

from app.core.auth import get_current_user
from app.db.models import APIKey
from app.api.schemas import APIKeyCreate, APIKeyUpdate, APIKeyResponse
from app.core.security import mask_secret

router = APIRouter(prefix="/api/apikeys", tags=["apikeys"])


def get_db():
    """Get database session (overridable in tests)."""
    from app.core.config import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _to_response(key: APIKey) -> APIKeyResponse:
    """Convert APIKey model to response DTO."""
    return APIKeyResponse(
        id=key.id,
        user_id=key.user_id,
        name=key.name,
        provider=key.provider,
        secret_value_masked=mask_secret(key.secret_value),
        created_at=key.created_at,
        updated_at=key.updated_at,
        revoked_at=key.revoked_at,
    )


@router.post("", status_code=201, response_model=APIKeyResponse)
async def create_apikey(
    payload: APIKeyCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new API key for the current user."""
    key = APIKey(
        id=str(uuid4()),
        user_id=user["user_id"],
        name=payload.name,
        provider=payload.provider,
        secret_value=payload.secret_value,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return _to_response(key)


@router.get("", response_model=list[APIKeyResponse])
async def list_apikeys(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all active API keys for the current user."""
    keys = db.query(APIKey).filter(
        APIKey.user_id == user["user_id"],
        APIKey.revoked_at.is_(None),
    ).all()
    return [_to_response(key) for key in keys]


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_apikey(
    key_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific API key (masked secret)."""
    key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == user["user_id"],
    ).first()

    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    return _to_response(key)


@router.put("/{key_id}", response_model=APIKeyResponse)
async def update_apikey(
    key_id: str,
    payload: APIKeyUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an API key (name only; secret is immutable)."""
    key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == user["user_id"],
    ).first()

    if not key:
        raise HTTPException(status_code=404, detail="API key not found")

    if key.revoked_at is not None:
        raise HTTPException(status_code=410, detail="API key has been revoked")

    key.name = payload.name
    key.provider = payload.provider
    key.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(key)
    return _to_response(key)


@router.delete("/{key_id}", response_model=APIKeyResponse)
async def revoke_apikey(
    key_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke (soft-delete) an API key."""
    key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == user["user_id"],
    ).first()

    if not key:
        raise HTTPException(status_code=404, detail="API key not found")

    key.revoked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(key)
    return _to_response(key)
