"""API endpoints for API Key management."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import APIKeyCreate, APIKeyResponse, APIKeyUpdate
from app.core.auth import get_current_user
from app.core.security import mask_secret
from app.db.database import get_db
from app.repositories import APIKeyRepository

router = APIRouter(prefix="/api/apikeys", tags=["apikeys"])


def _to_response(key) -> APIKeyResponse:
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
    repo = APIKeyRepository(db)
    key = repo.create(
        user_id=user["user_id"],
        name=payload.name,
        provider=payload.provider,
        secret_value=payload.secret_value,
    )
    return _to_response(key)


@router.get("", response_model=list[APIKeyResponse])
async def list_apikeys(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all active API keys for the current user."""
    repo = APIKeyRepository(db)
    keys = repo.get_by_user(user["user_id"])
    return [_to_response(key) for key in keys]


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_apikey(
    key_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific API key (masked secret)."""
    repo = APIKeyRepository(db)
    key = repo.get_by_id(key_id, user["user_id"])

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
    repo = APIKeyRepository(db)
    key = repo.get_by_id(key_id, user["user_id"])

    if not key:
        raise HTTPException(status_code=404, detail="API key not found")

    if key.revoked_at is not None:
        raise HTTPException(status_code=410, detail="API key has been revoked")

    repo.update(key_id, payload.name, payload.provider)
    db.refresh(key)
    return _to_response(key)


@router.delete("/{key_id}", response_model=APIKeyResponse)
async def revoke_apikey(
    key_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke (soft-delete) an API key."""
    repo = APIKeyRepository(db)
    key = repo.get_by_id(key_id, user["user_id"])

    if not key:
        raise HTTPException(status_code=404, detail="API key not found")

    repo.revoke(key_id)
    db.refresh(key)
    return _to_response(key)
