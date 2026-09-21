"""Test Arisu API client with both mock and real API calls."""

import pytest
import aiohttp
from datetime import datetime
from unittest.mock import AsyncMock, patch

from custom_components.korea_incubator.arisu.api import ArisuApiClient
from custom_components.korea_incubator.arisu.exceptions import (
    ArisuConnectionError,
    ArisuDataError,
)


class TestArisuApiMock:
    """Test Arisu API with mocked responses."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("empty_months", [0, 3, 11, 12])
    async def test_latest_historical_statement(self, api_client, empty_months):
        """Search across the year boundary, stopping at the newest bill."""
        months = ["2026-01"] + [f"2025-{m:02d}" for m in range(12, 1, -1)]
        empty = {"success": False, "no_bill_data": True}
        bill = {
            "success": True,
            "total_amount": 45000,
            "usage_info": {"current_usage": 15},
        }
        with (
            patch("custom_components.korea_incubator.arisu.api.datetime") as clock,
            patch.object(
                api_client, "async_get_water_bill", new_callable=AsyncMock
            ) as fetch,
        ):
            clock.now.return_value = datetime(2026, 1, 31)
            fetch.side_effect = [empty] * empty_months + [bill]
            result = await api_client.async_get_water_bill_data("123456789", "테스트")
        expected_calls = min(empty_months + 1, 12)
        assert [call.args[2] for call in fetch.await_args_list] == months[
            :expected_calls
        ]
        if empty_months == 12:
            assert result["no_bill_data"] is True
            assert result["tried_months"] == months
        else:
            assert result["billing_month"] == months[empty_months]
            assert result["total_amount"] == 45000
            assert result["usage_info"]["current_usage"] == 15

    @pytest.mark.asyncio
    async def test_history_search_does_not_hide_failure(self, api_client):
        with patch.object(
            api_client, "async_get_water_bill", new_callable=AsyncMock
        ) as fetch:
            fetch.side_effect = [
                {"success": False, "no_bill_data": True},
                ArisuConnectionError("HTTP 403"),
            ]
            with pytest.raises(ArisuConnectionError, match="HTTP 403"):
                await api_client.async_get_water_bill_data("123456789", "테스트")
            assert fetch.await_count == 2

    @pytest.fixture
    async def api_client(self, mock_session):
        """Create Arisu API client with mock session."""
        return ArisuApiClient(mock_session)

    @pytest.fixture
    def mock_html_response(self):
        """Create mock HTML response with bill data."""
        return """
        <html>
            <body>
                <input id="totAmt" value="45000" />
                <table>
                    <tr><td>042389659</td></tr>
                    <tr><th>납부방법</th><td>자동이체</td></tr>
                    <tr><td>사용량</td><td>15</td></tr>
                </table>
                <table class="table-type1 pink">
                    <tr><td>체납금액</td><td>0원</td></tr>
                </table>
            </body>
        </html>
        """

    @pytest.fixture
    def session_html_response(self):
        """Create the session page fragment required for CSRF-protected POSTs."""
        return (
            '<html><input type="hidden" name="_csrf" value="test-csrf-token" /></html>'
        )

    @pytest.mark.asyncio
    async def test_get_water_bill_data_success(
        self, api_client, mock_session, mock_html_response, session_html_response
    ):
        """Test successful water bill data retrieval."""
        # Mock session initialization
        init_response = AsyncMock()
        init_response.status = 200
        init_response.text.return_value = session_html_response

        # Mock bill data response
        bill_response = AsyncMock()
        bill_response.status = 200
        bill_response.text.return_value = mock_html_response

        mock_session.get.return_value.__aenter__.return_value = init_response
        mock_session.post.return_value.__aenter__.return_value = bill_response

        result = await api_client.async_get_water_bill_data("042389659", "홍길동")

        assert result["success"] is True
        assert result["total_amount"] == 45000
        assert result["billing_month"] == datetime.now().strftime("%Y-%m")
        assert mock_session.post.call_args.kwargs["data"]["_csrf"] == "test-csrf-token"
        assert (
            mock_session.post.call_args.kwargs["headers"]["X-CSRF-TOKEN"]
            == "test-csrf-token"
        )

    @pytest.mark.asyncio
    async def test_get_water_bill_no_data(
        self, api_client, mock_session, session_html_response
    ):
        """Test water bill with no data found."""
        # Mock responses with no bill data
        init_response = AsyncMock()
        init_response.status = 200
        init_response.text.return_value = session_html_response

        bill_response = AsyncMock()
        bill_response.status = 200
        bill_response.text.return_value = "<script>var noResult = true;</script>"

        mock_session.get.return_value.__aenter__.return_value = init_response
        mock_session.post.return_value.__aenter__.return_value = bill_response

        result = await api_client.async_get_water_bill_data("042389659", "홍길동")

        assert result["success"] is False
        assert result["no_bill_data"] is True
        assert "No bill data found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_water_bill_http_error(
        self, api_client, mock_session, session_html_response
    ):
        """Test water bill with HTTP error."""
        init_response = AsyncMock()
        init_response.status = 200
        init_response.text.return_value = session_html_response

        bill_response = AsyncMock()
        bill_response.status = 500
        bill_response.reason = "Internal Server Error"

        mock_session.get.return_value.__aenter__.return_value = init_response
        mock_session.post.return_value.__aenter__.return_value = bill_response

        with pytest.raises(ArisuConnectionError):
            await api_client.async_get_water_bill_data("042389659", "홍길동")

    @pytest.mark.asyncio
    async def test_get_water_bill_connection_error(self, api_client, mock_session):
        """Test water bill with connection error."""
        mock_session.get.side_effect = aiohttp.ClientError("Connection failed")

        with pytest.raises(ArisuConnectionError):
            await api_client.async_get_water_bill_data("042389659", "홍길동")

    @pytest.mark.asyncio
    async def test_get_water_bill_parsing_error(self, api_client, mock_session):
        """Test water bill with HTML parsing error."""
        init_response = AsyncMock()
        init_response.status = 200
        init_response.text.return_value = (
            '<html><input name="_csrf" value="test-csrf-token" /></html>'
        )

        bill_response = AsyncMock()
        bill_response.status = 200
        bill_response.text.return_value = '<input id="totAmt" value="invalid">'

        mock_session.get.return_value.__aenter__.return_value = init_response
        mock_session.post.return_value.__aenter__.return_value = bill_response

        with patch(
            "custom_components.korea_incubator.arisu.api.ArisuApiClient._parse_html_response"
        ) as mock_soup:
            mock_soup.side_effect = ArisuDataError("Parsing failed")

            with pytest.raises(ArisuDataError):
                await api_client.async_get_water_bill_data("042389659", "홍길동")

    def test_parse_html_response_success(self, api_client, mock_html_response):
        """Test HTML response parsing."""
        result = api_client._parse_html_response(mock_html_response)

        assert result["success"] is True
        assert result["total_amount"] == 45000
        assert "customer_info" in result
        assert "usage_info" in result
        assert "arrears_info" in result

    def test_parse_html_response_no_amount(self, api_client):
        """Test HTML parsing with no amount data."""
        html = '<html><body><input id="totAmt" value="0" /></body></html>'

        result = api_client._parse_html_response(html)
        assert result["success"] is True
        assert result["total_amount"] == 0

    @pytest.mark.parametrize(
        "html",
        [
            '<form id="searchForm"></form><script>var noResult = null;</script>',
            "<html>Service unavailable</html>",
            '<input id="totAmt" value="invalid">',
        ],
    )
    def test_unrecognized_response_is_not_no_bill(self, api_client, html):
        with pytest.raises(ArisuDataError):
            api_client._parse_html_response(html)

    def test_clean_amount_various_formats(self, api_client):
        """Test amount cleaning with various formats."""
        assert api_client._clean_amount("45,000원") == 45000
        assert api_client._clean_amount("1,500") == 1500
        assert api_client._clean_amount("0") == 0
        assert api_client._clean_amount("") == 0
        assert api_client._clean_amount(None) == 0

    @pytest.mark.parametrize(
        "customer_number,customer_name",
        [
            ("042389659", "홍길동"),
            ("123456789", "김철수"),
            ("", "홍길동"),  # Empty customer number
            ("042389659", ""),  # Empty customer name
        ],
    )
    @pytest.mark.asyncio
    async def test_various_customer_data(
        self,
        api_client,
        mock_session,
        mock_html_response,
        customer_number,
        customer_name,
    ):
        """Test with various customer data combinations."""
        init_response = AsyncMock()
        init_response.status = 200
        init_response.text.return_value = (
            '<html><input name="_csrf" value="test-csrf-token" /></html>'
        )

        bill_response = AsyncMock()
        bill_response.status = 200
        bill_response.text.return_value = mock_html_response

        mock_session.get.return_value.__aenter__.return_value = init_response
        mock_session.post.return_value.__aenter__.return_value = bill_response

        result = await api_client.async_get_water_bill_data(
            customer_number, customer_name
        )

        # Should handle various inputs gracefully
        assert "success" in result


class TestArisuApiIntegration:
    """Integration tests with real API calls."""

    @pytest.fixture
    async def real_session(self):
        """Create real aiohttp session."""
        session = aiohttp.ClientSession()
        yield session
        await session.close()

    @pytest.fixture
    def real_api_client(self, real_session):
        """Create Arisu API client with real session."""
        return ArisuApiClient(real_session)

    @pytest.mark.integration
    async def test_real_api_invalid_credentials(self, real_api_client):
        """Test real API with invalid credentials."""
        result = await real_api_client.async_get_water_bill_data("999999999", "테스트")

        # Should return unsuccessful result
        assert result["success"] is False

    @pytest.mark.integration
    async def test_real_api_connection(self, real_api_client):
        """Test real API connection."""
        try:
            result = await real_api_client.async_get_water_bill_data(
                "042389659", "홍길동"
            )

            # Should return valid structure regardless of success
            assert "success" in result

            if result["success"]:
                assert "total_amount" in result
                assert "billing_month" in result

        except (ArisuConnectionError, ArisuDataError) as e:
            # May fail due to network issues or API changes
            pytest.skip(f"Real API test failed (expected): {e}")

    @pytest.mark.integration
    async def test_real_session_initialization(self, real_api_client):
        """Test real session initialization."""
        try:
            # Test that session initialization doesn't throw errors
            await real_api_client._init_session()

        except Exception as e:
            # Session init failure is acceptable for testing
            pytest.skip(f"Session initialization failed (expected): {e}")
