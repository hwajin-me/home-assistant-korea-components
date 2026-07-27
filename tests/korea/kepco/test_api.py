"""
Test KEPCO API client with both mock and real API calls.
"""

import pytest
import aiohttp
from unittest.mock import AsyncMock, patch
from curl_cffi import AsyncSession

from custom_components.korea_incubator.kepco.api import KepcoApiClient
from custom_components.korea_incubator.kepco.exceptions import KepcoAuthError


class TestKepcoApiMock:
    """Test KEPCO API with mocked responses."""

    @pytest.fixture
    async def api_client(self, mock_session):
        """Create KEPCO API client with mock session."""
        client = KepcoApiClient(mock_session)
        client.set_credentials("test_user", "test_pass")
        return client

    @pytest.mark.asyncio
    async def test_login_success(self, api_client, mock_session):
        """Test successful login."""
        # Mock successful login response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = '{"result": "success", "loginYn": "Y"}'
        mock_response.json.return_value = {"result": "success", "loginYn": "Y"}
        mock_session.post.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_login("test_user", "test_pass")
        assert result is True

    @pytest.mark.asyncio
    async def test_login_failure(self, api_client, mock_session):
        """Test login failure."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = '{"result": "fail", "loginYn": "N"}'
        mock_response.json.return_value = {"result": "fail", "loginYn": "N"}
        mock_session.post.return_value.__aenter__.return_value = mock_response

        with pytest.raises(KepcoAuthError):
            await api_client.async_login("test_user", "wrong_pass")

    @pytest.mark.asyncio
    async def test_login_http_error(self, api_client, mock_session):
        """Test login with HTTP error."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.reason = "Internal Server Error"
        mock_session.post.return_value.__aenter__.return_value = mock_response

        with pytest.raises():
            await api_client.async_login("test_user", "test_pass")

    @pytest.mark.asyncio
    async def test_get_recent_usage_success(self, api_client, mock_session):
        """Test successful recent usage retrieval."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "result": {"F_AP_QT": "123.45", "ST_TIME": "2025-01-15 14:30:00"}
        }
        mock_session.post.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_get_recent_usage()
        assert result["result"]["F_AP_QT"] == "123.45"
        assert result["result"]["ST_TIME"] == "2025-01-15 14:30:00"

    @pytest.mark.asyncio
    async def test_get_usage_info_success(self, api_client, mock_session):
        """Test successful usage info retrieval."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "result": {
                "BILL_LAST_MONTH": "25000",
                "PREDICT_TOTAL_CHARGE_REV": "30000",
                "PREDICT_KWH": "150.5",
            }
        }
        mock_session.post.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_get_usage_info()
        assert result["result"]["BILL_LAST_MONTH"] == "25000"
        assert result["result"]["PREDICT_TOTAL_CHARGE_REV"] == "30000"

    @pytest.mark.asyncio
    async def test_auth_error_on_api_call(self, api_client, mock_session):
        """Test authentication error during API call."""
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.reason = "Unauthorized"
        mock_session.post.return_value.__aenter__.return_value = mock_response

        with pytest.raises(KepcoAuthError):
            await api_client.async_get_recent_usage()

    @pytest.mark.asyncio
    async def test_connection_error(self, api_client, mock_session):
        """Test connection error."""
        mock_session.post.side_effect = aiohttp.ClientError("Connection failed")

        with pytest.raises():
            await api_client.async_get_recent_usage()


class TestKepcoApiIntegration:
    """Integration tests with real API calls (optional, requires credentials)."""

    @pytest.fixture
    async def real_session(self):
        """Create real curl_cffi session."""
        session = AsyncSession()
        yield session
        await session.close()

    @pytest.fixture
    def real_api_client(self, real_session):
        """Create KEPCO API client with real session."""
        return KepcoApiClient(real_session)

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled",
    )
    async def test_real_login_invalid_credentials(self, real_api_client):
        """Test real API with invalid credentials."""
        with pytest.raises(KepcoAuthError):
            await real_api_client.async_login("invalid_user", "invalid_pass")

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled",
    )
    async def test_real_api_connection(self, real_api_client):
        """Test real API connection (should fail without valid credentials)."""
        try:
            await real_api_client.async_get_recent_usage()
            assert False, "Should have raised an exception"
        except KepcoAuthError:
            # Expected to fail without proper authentication
            pass

    @pytest.mark.parametrize(
        "username,password",
        [
            ("", "password"),
            ("username", ""),
            ("", ""),
            (None, "password"),
            ("username", None),
        ],
    )
    async def test_invalid_credentials_validation(
        self, real_api_client, username, password
    ):
        """Test validation of invalid credentials."""
        with pytest.raises((KepcoAuthError, ValueError)):
            await real_api_client.async_login(username, password)
