import pytest
import aiohttp
from aiohttp_mock import AioHTTPMock
from custom_components.korea_incubator.arisu.api import ArisuApiClient
from custom_components.korea_incubator.arisu.exceptions import ArisuAuthError, ArisuConnectionError, ArisuDataError


@pytest.fixture
async def api_client():
    async with aiohttp.ClientSession() as session:
        yield ArisuApiClient(session)


@pytest.mark.asyncio
async def test_async_get_water_bill_data_success(api_client, aiohttp_mock: AioHTTPMock):
    # Mock initial session request
    aiohttp_mock.get("https://i121.seoul.go.kr/cs/cyber/front/cgcalc/NR_cgJungInfo.do?_m=m1_1",
                     status=200, payload="")

    # Mock successful bill data response
    bill_html = '''
    <html>
        <body>
            <input id="totAmt" value="25000">
            <td>042389659</td>
            <th>납부방법</th><td>계좌이체</td>
            <table class="table-type1 pink">
                <tr><td>체납금액</td><td>0</td></tr>
            </table>
        </body>
    </html>
    '''

    aiohttp_mock.post("https://i121.seoul.go.kr/cs/cyber/front/cgcalc/NR_cgJungInfo.do",
                     status=200, payload=bill_html, content_type="text/html")

    result = await api_client.async_get_water_bill_data("042389659", "홍길동")

    assert result["success"] is True
    assert result["total_amount"] == 25000
    assert result["customer_info"]["customer_number"] == "042389659"
    assert result["customer_info"]["payment_method"] == "계좌이체"
    assert result["arrears_info"]["overdue_amount"] == 0


@pytest.mark.asyncio
async def test_async_get_water_bill_data_no_data(api_client, aiohttp_mock: AioHTTPMock):
    # Mock initial session request
    aiohttp_mock.get("https://i121.seoul.go.kr/cs/cyber/front/cgcalc/NR_cgJungInfo.do?_m=m1_1",
                     status=200, payload="")

    # Mock response without bill data
    aiohttp_mock.post("https://i121.seoul.go.kr/cs/cyber/front/cgcalc/NR_cgJungInfo.do",
                     status=200, payload="<html><body>No data</body></html>", content_type="text/html")

    result = await api_client.async_get_water_bill_data("000000000", "없는사람")

    assert result["success"] is False
    assert "No bill data found" in result["error"]


@pytest.mark.asyncio
async def test_async_get_water_bill_http_error(api_client, aiohttp_mock: AioHTTPMock):
    aiohttp_mock.get("https://i121.seoul.go.kr/cs/cyber/front/cgcalc/NR_cgJungInfo.do?_m=m1_1",
                     status=500)

    with pytest.raises(ArisuConnectionError):
        await api_client.async_get_water_bill_data("042389659", "홍길동")


@pytest.mark.asyncio
async def test_async_get_water_bill_fallback_to_previous_month(api_client, aiohttp_mock: AioHTTPMock):
    # Mock initial session request
    aiohttp_mock.get("https://i121.seoul.go.kr/cs/cyber/front/cgcalc/NR_cgJungInfo.do?_m=m1_1",
                     status=200, payload="")

    # First request (current month) - no data
    aiohttp_mock.post("https://i121.seoul.go.kr/cs/cyber/front/cgcalc/NR_cgJungInfo.do",
                     status=200, payload="<html><body>No data</body></html>", content_type="text/html")

    # Second request (previous month) - with data
    bill_html = '''
    <html>
        <body>
            <input id="totAmt" value="30000">
            <td>042389659</td>
        </body>
    </html>
    '''
    aiohttp_mock.post("https://i121.seoul.go.kr/cs/cyber/front/cgcalc/NR_cgJungInfo.do",
                     status=200, payload=bill_html, content_type="text/html")

    result = await api_client.async_get_water_bill_data("042389659", "홍길동")

    assert result["success"] is True
    assert result["total_amount"] == 30000


@pytest.mark.asyncio
async def test_clean_amount_method(api_client):
    assert api_client._clean_amount("25,000원") == 25000
    assert api_client._clean_amount("1,500") == 1500
    assert api_client._clean_amount("") == 0
    assert api_client._clean_amount("abc") == 0


@pytest.mark.asyncio
async def test_parse_html_response_with_complete_data(api_client):
    html_content = '''
    <html>
        <body>
            <input id="totAmt" value="45000">
            <td>042389659</td>
            <label>주소: 서울특별시 강남구 역삼동</label>
            <tr><th>납부방법</th><td>계좌이체</td></tr>
            <td>사용량</td><td>25</td>
            <table class="table-type1 pink">
                <tr><td>체납금액</td><td>5,000</td></tr>
            </table>
        </body>
    </html>
    '''

    result = api_client._parse_html_response(html_content)

    assert result["success"] is True
    assert result["total_amount"] == 45000
    assert result["customer_info"]["customer_number"] == "042389659"
    assert result["customer_info"]["payment_method"] == "계좌이체"
    assert result["usage_info"]["current_usage"] == 25
    assert result["arrears_info"]["overdue_amount"] == 5000
