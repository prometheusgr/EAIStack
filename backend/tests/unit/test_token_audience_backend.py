"""Test token audience validation."""

import pytest
from app.core.auth import extract_user_from_payload


class TestTokenAudienceValidation:
    """Test that token audiences are properly validated."""

    def test_token_with_correct_audience_accepted(self):
        """Token with matching audience should be accepted."""
        # Payload as if it came from Keycloak with correct audience
        payload = {
            "sub": "user-123",
            "preferred_username": "testuser",
            "email": "test@example.com",
            "name": "Test User",
            "aud": "eaistack-web",  # This should match one of the valid audiences
        }

        user = extract_user_from_payload(payload)

        assert user["user_id"] == "user-123"
        assert user["username"] == "testuser"

    def test_token_with_backend_api_audience_accepted(self):
        """Token issued for eaistack-api should also work."""
        payload = {
            "sub": "user-456",
            "preferred_username": "anotheruser",
            "aud": "eaistack-api",  # Alternative valid audience
        }

        user = extract_user_from_payload(payload)

        assert user["user_id"] == "user-456"

    def test_token_missing_sub_claim_rejected(self):
        """Token without subject claim should be rejected."""
        payload = {
            "preferred_username": "testuser",
            "aud": "eaistack-web",
            # Missing "sub"
        }

        with pytest.raises(Exception):
            extract_user_from_payload(payload)

    def test_token_with_all_claims(self):
        """Token with all claims should extract correctly."""
        payload = {
            "sub": "user-789",
            "preferred_username": "fulluser",
            "email": "full@example.com",
            "name": "Full User",
            "aud": ["eaistack-web", "eaistack-api"],  # Can be an array
        }

        user = extract_user_from_payload(payload)

        assert user["user_id"] == "user-789"
        assert user["username"] == "fulluser"
        assert user["email"] == "full@example.com"
        assert user["name"] == "Full User"

    def test_token_preserves_entire_payload(self):
        """Extracted user should have access to full token payload."""
        payload = {
            "sub": "user-xyz",
            "preferred_username": "tokentest",
            "aud": "eaistack-web",
            "exp": 9999999999,  # Far future
            "iat": 1000000000,
            "custom_claim": "custom_value",
        }

        user = extract_user_from_payload(payload)

        # Payload should be preserved for future use
        assert user["token"] == payload
        assert user["token"]["custom_claim"] == "custom_value"
