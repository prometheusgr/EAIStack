"""Phase 0 test: Prove the testing harness is wired correctly."""

import pytest


@pytest.mark.unit
def test_ci_harness_works():
    """This test should pass to prove CI is working."""
    assert True


@pytest.mark.unit
def test_mock_llm_fixture(mock_llm):
    """Test that the mocked LLM fixture is available."""
    assert mock_llm is not None
    assert mock_llm.response == "This is a fake response from the mocked LLM."


@pytest.mark.unit
def test_db_session_fixture(db_session):
    """Test that the database session fixture is available."""
    assert db_session is not None


@pytest.mark.unit
def test_config_loads():
    """Test that configuration loads without errors."""
    from app.core.config import settings

    assert settings.app_name == "EAIStack Backend"
    assert settings.debug is False
