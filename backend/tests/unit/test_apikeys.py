"""Unit tests for API Keys CRUD - TDD discipline."""

from datetime import datetime
from uuid import uuid4

import pytest

from app.core.auth import get_current_user
from app.db.models import APIKey, ProviderEnum
from app.main import app


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
    from pydantic import ValidationError

    from app.api.schemas import APIKeyCreate

    # Missing required fields should fail
    with pytest.raises(ValidationError):
        APIKeyCreate(name="Test", provider="openai")  # Missing secret_value

    with pytest.raises(ValidationError):
        APIKeyCreate(name="Test", secret_value="secret")  # Missing provider

    with pytest.raises(ValidationError):
        APIKeyCreate(provider="openai", secret_value="secret")  # Missing name

    # Valid creation should succeed
    valid = APIKeyCreate(name="Test", provider="openai", secret_value="sk-proj-secret")
    assert valid.name == "Test"


# === ENDPOINT TESTS ===
# (client fixture provided by conftest.py)


@pytest.mark.unit
def test_create_apikey_success(client, db_session):
    """Test creating an API key with name, provider, secret — expect 201, response has masked secret."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        create_request = {
            "name": "OpenAI Key",
            "provider": "openai",
            "secret_value": "sk-1234567890abcdef",
        }

        response = client.post(
            "/api/apikeys",
            json=create_request,
        )

        # Expect 201 Created
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "OpenAI Key"
        assert data["provider"] == "openai"
        assert data["user_id"] == "test-user-123"
        # Secret should be masked
        assert data.get("secret_value_masked") is not None
        # Verify it was stored in DB
        stored_key = db_session.query(APIKey).filter_by(user_id="test-user-123").first()
        assert stored_key is not None
        assert stored_key.name == "OpenAI Key"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_list_apikeys_returns_user_keys(client, db_session):
    """Test: list as user A returns only A's keys."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        # Create some test keys for the user
        key1 = APIKey(
            id=str(uuid4()),
            user_id="test-user-123",
            name="Key 1",
            provider=ProviderEnum.openai,
            secret_value="secret-1",
        )
        key2 = APIKey(
            id=str(uuid4()),
            user_id="test-user-123",
            name="Key 2",
            provider=ProviderEnum.anthropic,
            secret_value="secret-2",
        )
        db_session.add_all([key1, key2])
        db_session.commit()

        response = client.get("/api/apikeys")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = {key["name"] for key in data}
        assert names == {"Key 1", "Key 2"}
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_get_apikey_detail_masked_secret(client, db_session):
    """Test: GET APIKey detail — expect secret masked/truncated, never full value."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        key = APIKey(
            id=str(uuid4()),
            user_id="test-user-123",
            name="Test Key",
            provider=ProviderEnum.openai,
            secret_value="sk-verylongsecretvalue1234567890",
        )
        db_session.add(key)
        db_session.commit()

        response = client.get(f"/api/apikeys/{key.id}")

        assert response.status_code == 200
        data = response.json()
        # Verify secret is masked (should not be full value)
        assert data["secret_value_masked"] != "sk-verylongsecretvalue1234567890"
        assert "sk-" in data["secret_value_masked"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_update_apikey_name(client, db_session):
    """Test: update APIKey name — expect 200, secret unchanged (immutable)."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        key = APIKey(
            id=str(uuid4()),
            user_id="test-user-123",
            name="Old Name",
            provider=ProviderEnum.openai,
            secret_value="sk-original",
        )
        db_session.add(key)
        db_session.commit()

        update_request = {
            "name": "New Name",
            "provider": "openai",
        }

        response = client.put(f"/api/apikeys/{key.id}", json=update_request)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        # Secret should remain unchanged
        db_session.refresh(key)
        assert key.secret_value == "sk-original"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_revoke_apikey_success(client, db_session):
    """Test: revoke APIKey — expect 200, revoked_at set."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        key = APIKey(
            id=str(uuid4()),
            user_id="test-user-123",
            name="Test Key",
            provider=ProviderEnum.openai,
            secret_value="sk-secret",
        )
        db_session.add(key)
        db_session.commit()

        response = client.delete(f"/api/apikeys/{key.id}")

        assert response.status_code == 200
        data = response.json()
        # revoked_at should be set (not None)
        assert data["revoked_at"] is not None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_list_filters_out_revoked_keys(client, db_session):
    """Test: revoked APIKey doesn't appear in list."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        active_key = APIKey(
            id=str(uuid4()),
            user_id="test-user-123",
            name="Active Key",
            provider=ProviderEnum.openai,
            secret_value="sk-active",
            revoked_at=None,
        )
        revoked_key = APIKey(
            id=str(uuid4()),
            user_id="test-user-123",
            name="Revoked Key",
            provider=ProviderEnum.anthropic,
            secret_value="sk-revoked",
            revoked_at=datetime.utcnow(),
        )
        db_session.add_all([active_key, revoked_key])
        db_session.commit()

        response = client.get("/api/apikeys")

        assert response.status_code == 200
        data = response.json()
        # Should only have active key
        assert len(data) == 1
        assert data[0]["name"] == "Active Key"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_get_apikey_not_found(client):
    """Test: GET APIKey for non-existent key returns 404."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        response = client.get("/api/apikeys/nonexistent-id")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
