"""Test GasApp API client with both mock and real API calls."""

import pytest
import aiohttp
from unittest.mock import AsyncMock

from custom_components.korea_incubator.gasapp.api import GasAppApiClient
from custom_components.korea_incubator.gasapp.exceptions import (
    GasAppAuthError,
    GasAppConnectionError,
    GasAppDataError,
)


class TestGasAppApiMock:
    """Test GasApp API with mocked responses."""

    @pytest.fixture
    async def api_client(self, mock_session):
        """Create GasApp API client with mock session."""
        client = GasAppApiClient(mock_session)
        client.set_credentials("test_token", "test_member", "test_contract")
        return client

    @pytest.mark.asyncio
    async def test_validate_credentials_success(
        self, api_client, mock_session, gasapp_mock_response
    ):
        """Test successful credential validation."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = gasapp_mock_response
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_validate_credentials()
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_credentials_failure(self, api_client, mock_session):
        """Test credential validation failure."""
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.reason = "Unauthorized"
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_validate_credentials()
        assert result is False

    @pytest.mark.asyncio
    async def test_get_home_data_success(
        self, api_client, mock_session, gasapp_mock_response
    ):
        """Test successful home data retrieval."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = gasapp_mock_response
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_get_home_data()
        assert result == gasapp_mock_response
        assert "cards" in result
        assert "bill" in result["cards"]

    @pytest.mark.asyncio
    async def test_get_home_data_auth_error(self, api_client, mock_session):
        """Test home data with authentication error."""
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.reason = "Unauthorized"
        mock_session.get.return_value.__aenter__.return_value = mock_response

        with pytest.raises(GasAppAuthError):
            await api_client.async_get_home_data()

    @pytest.mark.asyncio
    async def test_get_home_data_forbidden(self, api_client, mock_session):
        """Test home data with forbidden error."""
        mock_response = AsyncMock()
        mock_response.status = 403
        mock_response.reason = "Forbidden"
        mock_session.get.return_value.__aenter__.return_value = mock_response

        with pytest.raises(GasAppAuthError):
            await api_client.async_get_home_data()

    @pytest.mark.asyncio
    async def test_get_home_data_connection_error(self, api_client, mock_session):
        """Test home data with connection error."""
        mock_session.get.side_effect = aiohttp.ClientError("Connection failed")

        with pytest.raises(GasAppConnectionError):
            await api_client.async_get_home_data()

    @pytest.mark.asyncio
    async def test_get_bill_history_success(
        self, api_client, mock_session, gasapp_mock_response
    ):
        """Test successful bill history retrieval."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = gasapp_mock_response
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_get_bill_history()
        assert result == gasapp_mock_response["cards"]["bill"]["history"]
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_get_bill_history_no_data(self, api_client, mock_session):
        """Test bill history with no data."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"cards": {}}
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_get_bill_history()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_current_bill_success(
        self, api_client, mock_session, gasapp_mock_response
    ):
        """Test successful current bill retrieval."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = gasapp_mock_response
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_get_current_bill()
        assert result == gasapp_mock_response["cards"]["bill"]
        assert "title1" in result
        assert "history" in result

    @pytest.mark.asyncio
    async def test_credentials_not_set(self, mock_session):
        """Test API call without setting credentials."""
        client = GasAppApiClient(mock_session)

        with pytest.raises(GasAppAuthError, match="Credentials not set"):
            await client.async_get_home_data()

    @pytest.mark.parametrize(
        "token,member_id,contract_num",
        [
            ("", "member", "contract"),
            ("token", "", "contract"),
            ("token", "member", ""),
            (None, "member", "contract"),
            ("token", None, "contract"),
            ("token", "member", None),
        ],
    )
    def test_invalid_credentials(self, mock_session, token, member_id, contract_num):
        """Test API client with invalid credentials."""
        client = GasAppApiClient(mock_session)
        client.set_credentials(token, member_id, contract_num)

        # Should store the credentials even if invalid
        assert client._token == token
        assert client._member_id == member_id
        assert client._use_contract_num == contract_num

    @pytest.mark.asyncio
    async def test_get_headers_without_credentials(self, mock_session):
        """Test header generation without credentials."""
        client = GasAppApiClient(mock_session)

        with pytest.raises(GasAppAuthError):
            client._get_headers()


class TestGasAppApiIntegration:
    """Integration tests with real API calls."""

    @pytest.fixture
    async def real_session(self):
        """Create real aiohttp session."""
        session = aiohttp.ClientSession()
        yield session
        await session.close()

    @pytest.fixture
    def real_api_client(self, real_session):
        """Create GasApp API client with real session."""
        return GasAppApiClient(real_session)

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled",
    )
    async def test_real_api_invalid_credentials(self, real_api_client):
        """Test real API with invalid credentials."""
        real_api_client.set_credentials(
            "invalid_token", "invalid_member", "invalid_contract"
        )

        with pytest.raises((GasAppAuthError, GasAppConnectionError)):
            await real_api_client.async_get_home_data()

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled",
    )
    async def test_real_credential_validation_failure(self, real_api_client):
        """Test real credential validation with invalid data."""
        real_api_client.set_credentials(
            "invalid_token", "invalid_member", "invalid_contract"
        )

        result = await real_api_client.async_validate_credentials()
        assert result is False

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled",
    )
    async def test_real_api_connection(self, real_api_client):
        """Test real API connection (should fail without valid credentials)."""
        real_api_client.set_credentials("test", "test", "test")

        try:
            await real_api_client.async_get_home_data()
            assert False, "Should have raised an exception"
        except (GasAppAuthError, GasAppConnectionError):
            # Expected to fail without proper authentication
            pass
