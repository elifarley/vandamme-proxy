"""Unit tests for OAuthClientMixin module."""

from unittest.mock import MagicMock

import pytest

from src.core.oauth_client_mixin import OAuthClientMixin


@pytest.mark.unit
class TestOAuthClientMixin:
    """Test cases for OAuthClientMixin."""

    def test_get_oauth_token_success(self):
        """Test successful token retrieval from TokenManager."""

        class TestClient(OAuthClientMixin):
            def __init__(self, token_manager):
                self._oauth_token_manager = token_manager

        # Mock TokenManager that returns valid token and account ID
        mock_token_manager = MagicMock()
        mock_token_manager.get_access_token.return_value = ("test_access_token", "user_123")

        client = TestClient(mock_token_manager)
        access_token, account_id = client._get_oauth_token()

        assert access_token == "test_access_token"
        assert account_id == "user_123"
        mock_token_manager.get_access_token.assert_called_once()

    def test_get_oauth_token_not_authenticated(self):
        """Test error when TokenManager is None."""

        class TestClient(OAuthClientMixin):
            def __init__(self):
                self._oauth_token_manager = None

        client = TestClient()

        with pytest.raises(ValueError) as exc_info:
            client._get_oauth_token()

        assert "OAuth authentication not available" in str(exc_info.value)
        assert "vdm oauth login" in str(exc_info.value)

    def test_get_oauth_token_no_access_token(self):
        """Test error when TokenManager returns None for access token."""

        class TestClient(OAuthClientMixin):
            def __init__(self, token_manager):
                self._oauth_token_manager = token_manager

        # Mock TokenManager that returns None for access token
        mock_token_manager = MagicMock()
        mock_token_manager.get_access_token.return_value = (None, "user_123")

        client = TestClient(mock_token_manager)

        with pytest.raises(ValueError) as exc_info:
            client._get_oauth_token()

        assert "Not authenticated" in str(exc_info.value)
        assert "vdm oauth login" in str(exc_info.value)

    def test_get_oauth_token_no_account_id(self):
        """Test error when TokenManager returns None for account ID."""

        class TestClient(OAuthClientMixin):
            def __init__(self, token_manager):
                self._oauth_token_manager = token_manager

        # Mock TokenManager that returns None for account ID
        mock_token_manager = MagicMock()
        mock_token_manager.get_access_token.return_value = ("test_token", None)

        client = TestClient(mock_token_manager)

        with pytest.raises(ValueError) as exc_info:
            client._get_oauth_token()

        assert "No account ID found" in str(exc_info.value)
        assert "vdm oauth login" in str(exc_info.value)

    def test_inject_oauth_headers(self):
        """Test header injection produces correct format."""

        class TestClient(OAuthClientMixin):
            def __init__(self, token_manager):
                self._oauth_token_manager = token_manager

        mock_token_manager = MagicMock()
        mock_token_manager.get_access_token.return_value = ("secret_token", "user_456")

        client = TestClient(mock_token_manager)
        headers = {"Content-Type": "application/json"}

        result = client._inject_oauth_headers(headers)

        assert result["Authorization"] == "Bearer secret_token"
        assert result["x-account-id"] == "user_456"
        assert result["Content-Type"] == "application/json"  # Original header preserved

    def test_inject_oauth_headers_modifies_in_place(self):
        """Test that headers dict is modified in-place."""

        class TestClient(OAuthClientMixin):
            def __init__(self, token_manager):
                self._oauth_token_manager = token_manager

        mock_token_manager = MagicMock()
        mock_token_manager.get_access_token.return_value = ("token_xyz", "user_789")

        client = TestClient(mock_token_manager)
        headers = {"Existing": "header"}

        result = client._inject_oauth_headers(headers)

        # Result should be the same object (modified in-place)
        assert result is headers
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer token_xyz"

    def test_inject_oauth_headers_not_authenticated(self):
        """Test error when injecting headers without authentication."""

        class TestClient(OAuthClientMixin):
            def __init__(self):
                self._oauth_token_manager = None

        client = TestClient()
        headers = {}

        with pytest.raises(ValueError) as exc_info:
            client._inject_oauth_headers(headers)

        assert "OAuth authentication not available" in str(exc_info.value)
