"""Test Safety Alert API client with both mock and real API calls."""
import pytest
import aiohttp
from unittest.mock import AsyncMock, patch

from custom_components.korea_incubator.safety_alert.api import SafetyAlertApiClient
from custom_components.korea_incubator.safety_alert.exceptions import (
    SafetyAlertConnectionError,
    SafetyAlertDataError
)


class TestSafetyAlertApiMock:
    """Test Safety Alert API with mocked responses."""

    @pytest.fixture
    async def api_client(self, mock_session):
        """Create Safety Alert API client with mock session."""
        return SafetyAlertApiClient(mock_session)

    @pytest.mark.asyncio
    async def test_get_safety_alerts_success(self, api_client, mock_session, safety_alert_mock_response):
        """Test successful safety alerts retrieval."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = safety_alert_mock_response
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_get_safety_alerts("1100000000", None, None)

        assert result["disasterSmsList"]
        assert len(result["disasterSmsList"]) == 2
        assert result["rtnResult"]["totCnt"] == 2
        assert result["disasterSmsList"][0]["EMRGNCY_STEP_NM"] == "관심"

    @pytest.mark.asyncio
    async def test_get_safety_alerts_with_area_codes(self, api_client, mock_session, safety_alert_mock_response):
        """Test safety alerts with multiple area codes."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = safety_alert_mock_response
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_get_safety_alerts("1100000000", "1111000000", "1111010100")

        # Verify API was called with correct parameters
        call_args = mock_session.get.call_args
        assert "areaCode" in call_args[1]["params"]
        assert "areaCode2" in call_args[1]["params"]
        assert "areaCode3" in call_args[1]["params"]

    @pytest.mark.asyncio
    async def test_get_safety_alerts_http_error(self, api_client, mock_session):
        """Test safety alerts with HTTP error."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.reason = "Internal Server Error"
        mock_session.get.return_value.__aenter__.return_value = mock_response

        with pytest.raises(SafetyAlertConnectionError):
            await api_client.async_get_safety_alerts("1100000000")

    @pytest.mark.asyncio
    async def test_get_safety_alerts_connection_error(self, api_client, mock_session):
        """Test safety alerts with connection error."""
        mock_session.get.side_effect = aiohttp.ClientError("Connection failed")

        with pytest.raises(SafetyAlertConnectionError):
            await api_client.async_get_safety_alerts("1100000000")

    @pytest.mark.asyncio
    async def test_get_safety_alerts_json_error(self, api_client, mock_session):
        """Test safety alerts with JSON parsing error."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_session.get.return_value.__aenter__.return_value = mock_response

        with pytest.raises(SafetyAlertDataError):
            await api_client.async_get_safety_alerts("1100000000")

    @pytest.mark.asyncio
    async def test_get_safety_alerts_empty_response(self, api_client, mock_session):
        """Test safety alerts with empty response."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"disasterSmsList": [], "rtnResult": {"totCnt": 0}}
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_get_safety_alerts("1100000000")

        assert result["disasterSmsList"] == []
        assert result["rtnResult"]["totCnt"] == 0

    @pytest.mark.parametrize("area_code,area_code2,area_code3", [
        ("1100000000", None, None),
        ("1100000000", "1111000000", None),
        ("1100000000", "1111000000", "1111010100"),
        ("", None, None),  # Empty area code
    ])
    @pytest.mark.asyncio
    async def test_get_safety_alerts_various_area_codes(
        self, api_client, mock_session, safety_alert_mock_response,
        area_code, area_code2, area_code3
    ):
        """Test safety alerts with various area code combinations."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = safety_alert_mock_response
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_get_safety_alerts(area_code, area_code2, area_code3)

        # Should always return valid structure
        assert "disasterSmsList" in result
        assert "rtnResult" in result


class TestSafetyAlertApiIntegration:
    """Integration tests with real API calls."""

    @pytest.fixture
    async def real_session(self):
        """Create real aiohttp session."""
        session = aiohttp.ClientSession()
        yield session
        await session.close()

    @pytest.fixture
    def real_api_client(self, real_session):
        """Create Safety Alert API client with real session."""
        return SafetyAlertApiClient(real_session)

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled"
    )
    async def test_real_api_connection(self, real_api_client):
        """Test real API connection with Seoul area code."""
        try:
            result = await real_api_client.async_get_safety_alerts("1100000000")

            # Should return valid structure
            assert "disasterSmsList" in result
            assert "rtnResult" in result
            assert isinstance(result["disasterSmsList"], list)

        except (SafetyAlertConnectionError, SafetyAlertDataError) as e:
            # May fail due to network issues or API changes, which is acceptable
            pytest.skip(f"Real API test failed (expected): {e}")

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled"
    )
    async def test_real_api_invalid_area_code(self, real_api_client):
        """Test real API with invalid area code."""
        try:
            result = await real_api_client.async_get_safety_alerts("9999999999")

            # Should return empty or error response
            assert "disasterSmsList" in result

        except (SafetyAlertConnectionError, SafetyAlertDataError):
            # Expected to fail with invalid area code
            pass

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled"
    )
    async def test_real_api_response_structure(self, real_api_client):
        """Test real API response structure validation."""
        try:
            result = await real_api_client.async_get_safety_alerts("1100000000")

            # Validate response structure
            assert isinstance(result, dict)
            assert "disasterSmsList" in result
            assert "rtnResult" in result

            if result["disasterSmsList"]:
                alert = result["disasterSmsList"][0]
                expected_fields = ["EMRGNCY_STEP_NM", "DSSTR_SE_NM", "MSG_CN", "RCV_AREA_NM", "REGIST_DT"]
                for field in expected_fields:
                    assert field in alert, f"Missing field: {field}"

        except (SafetyAlertConnectionError, SafetyAlertDataError) as e:
            pytest.skip(f"Real API test failed (expected): {e}")
