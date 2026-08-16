"""Unit tests for API Keys CRUD - TDD discipline."""

import pytest
from uuid import uuid4
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.mark.unit
def test_apikey_model_basic_creation(db_session):
    """Test: APIKey model can be created with basic fields."""
    from app.db.models import APIKey

    key = APIKey(
        id=str(uuid4()),
        user_id="user-123",
        name="Test Key",
        provider="openai",
        secret_value="sk-proj-secret",
    )
    db_session.add(key)
    db_session.commit()

    retrieved = db_session.query(APIKey).filter_by(user_id="user-123").first()
    assert retrieved is not None
    assert retrieved.name == "Test Key"
    assert retrieved.provider == "openai"


@pytest.mark.unit
def test_apikey_model_user_isolation(db_session):
    """Test: APIKeys are isolated per user."""
    from app.db.models import APIKey

    key1 = APIKey(
        id=str(uuid4()),
        user_id="user-a",
        name="Key A",
        provider="openai",
        secret_value="secret-a",
    )
    key2 = APIKey(
        id=str(uuid4()),
        user_id="user-b",
        name="Key B",
        provider="anthropic",
        secret_value="secret-b",
    )
    db_session.add_all([key1, key2])
    db_session.commit()

    user_a_keys = db_session.query(APIKey).filter_by(user_id="user-a").all()
    user_b_keys = db_session.query(APIKey).filter_by(user_id="user-b").all()

    assert len(user_a_keys) == 1
    assert len(user_b_keys) == 1
    assert user_a_keys[0].name == "Key A"
    assert user_b_keys[0].name == "Key B"


@pytest.mark.unit
def test_apikey_model_revoked_at_excludes_revoked(db_session):
    """Test: Revoked APIKeys (revoked_at not None) are excluded from active list."""
    from app.db.models import APIKey

    key1 = APIKey(
        id=str(uuid4()),
        user_id="user-a",
        name="Active Key",
        provider="openai",
        secret_value="secret-1",
        revoked_at=None,
    )
    key2 = APIKey(
        id=str(uuid4()),
        user_id="user-a",
        name="Revoked Key",
        provider="openai",
        secret_value="secret-2",
        revoked_at=datetime.utcnow(),
    )
    db_session.add_all([key1, key2])
    db_session.commit()

    active_keys = db_session.query(APIKey).filter_by(user_id="user-a", revoked_at=None).all()

    assert len(active_keys) == 1
    assert active_keys[0].name == "Active Key"


@pytest.mark.unit
def test_mask_secret_helper_masks_from_end(db_session):
    """Test: mask_secret helper masks from the end, keeps prefix."""
    from app.core.security import mask_secret

    secret = "sk-proj-1234567890abcdefghijklmnop"
    masked = mask_secret(secret)

    assert masked.startswith("sk-")
    assert "1234567890" not in masked
    assert masked.endswith("...")
    assert len(masked) < len(secret)


@pytest.mark.unit
def test_mask_secret_helper_short_secret(db_session):
    """Test: mask_secret handles short secrets gracefully."""
    from app.core.security import mask_secret

    secret = "short"
    masked = mask_secret(secret)

    assert "short" not in masked
    assert masked.startswith("s")
    assert masked.endswith("...")


@pytest.mark.unit
def test_apikey_schema_excludes_secret_value_on_response(db_session):
    """Test: APIKey response schema never includes full secret_value."""
    from app.api.schemas import APIKeyResponse

    schema = APIKeyResponse(
        id="key-123",
        user_id="user-a",
        name="My Key",
        provider="openai",
        secret_value_masked="sk-proj-***...***",
        created_at=datetime.utcnow(),
        revoked_at=None,
    )

    data = schema.model_dump()
    assert "secret_value" not in data
    assert data["secret_value_masked"] == "sk-proj-***...***"


@pytest.mark.unit
def test_apikey_request_schema_requires_fields(db_session):
    """Test: APIKey request schema enforces required fields."""
    from app.api.schemas import APIKeyCreate
    from pydantic import ValidationError

    # Missing required fields should fail
    with pytest.raises(ValidationError):
        APIKeyCreate(name="Test", provider="openai")  # Missing secret_value

    with pytest.raises(ValidationError):
        APIKeyCreate(name="Test", secret_value="secret")  # Missing provider

    with pytest.raises(ValidationError):
        APIKeyCreate(provider="openai", secret_value="secret")  # Missing name

    # Valid creation should succeed
    valid = APIKeyCreate(
        name="Test",
        provider="openai",
        secret_value="sk-proj-secret"
    )
    assert valid.name == "Test"
