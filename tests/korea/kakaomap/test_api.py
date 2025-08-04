import pytest
import aiohttp
from aiohttp_mock import AioHTTPMock
from custom_components.korea_incubator.kakaomap.api import KakaoMapApiClient
from custom_components.korea_incubator.kakaomap.exceptions import KakaoMapConnectionError, KakaoMapDataError


@pytest.fixture
async def api_client():
    async with aiohttp.ClientSession() as session:
        yield KakaoMapApiClient(session)


@pytest.mark.asyncio
async def test_async_coordinate_to_address_success(api_client, aiohttp_mock: AioHTTPMock):
    expected_response = {
        "old": {
            "name": "서울특별시 광진구 능동 18"
        },
        "region": "서울특별시",
        "x": 515290,
        "y": 1122478
    }

    aiohttp_mock.get("https://map.kakao.com/etc/areaAddressInfo.json",
                     status=200, payload=expected_response)

    result = await api_client.async_coordinate_to_address(515290, 1122478)

    assert result["success"] is True
    assert result["address"] == "서울특별시 광진구 능동 18"
    assert result["region"] == "서울특별시"
    assert result["coordinates"]["x"] == 515290
    assert result["coordinates"]["y"] == 1122478


@pytest.mark.asyncio
async def test_async_coordinate_to_address_http_error(api_client, aiohttp_mock: AioHTTPMock):
    aiohttp_mock.get("https://map.kakao.com/etc/areaAddressInfo.json", status=500)

    with pytest.raises(KakaoMapConnectionError):
        await api_client.async_coordinate_to_address(515290, 1122478)


@pytest.mark.asyncio
async def test_async_get_public_transport_route_success(api_client, aiohttp_mock: AioHTTPMock):
    expected_response = {
        "in_local": {
            "routes": [
                {
                    "time": {"value": 1680},  # 28 minutes in seconds
                    "fare": {"value": 1550},
                    "distance": {"value": 12500},
                    "type": "지하철+도보",
                    "transfers": 0,
                    "walkingDistance": {"value": 800},
                    "walkingTime": {"value": 600},
                    "recommended": True,
                    "shortestTime": False,
                    "leastTransfer": True,
                    "steps": [
                        {
                            "information": "출발",
                            "action": "DEPARTURE"
                        },
                        {
                            "information": "건대입구역 승차",
                            "type": "SUBWAY",
                            "distance": {"value": 400},
                            "time": {"value": 300}
                        },
                        {
                            "information": "강남역 하차",
                            "type": "SUBWAY",
                            "distance": {"value": 11700},
                            "time": {"value": 1200}
                        },
                        {
                            "information": "도착",
                            "action": "ARRIVAL"
                        }
                    ]
                }
            ]
        }
    }

    aiohttp_mock.get("https://map.kakao.com/route/pubtrans.json",
                     status=200, payload=expected_response)

    result = await api_client.async_get_public_transport_route(515290, 1122478, 506190, 1110730)

    assert result == expected_response
    assert len(result["in_local"]["routes"]) == 1
    assert result["in_local"]["routes"][0]["time"]["value"] == 1680
    assert result["in_local"]["routes"][0]["fare"]["value"] == 1550


@pytest.mark.asyncio
async def test_async_get_public_transport_route_with_start_time(api_client, aiohttp_mock: AioHTTPMock):
    expected_response = {
        "in_local": {
            "routes": [
                {
                    "time": {"value": 1800},
                    "fare": {"value": 1550}
                }
            ]
        }
    }

    aiohttp_mock.get("https://map.kakao.com/route/pubtrans.json",
                     status=200, payload=expected_response)

    result = await api_client.async_get_public_transport_route(
        515290, 1122478, 506190, 1110730, start_time="202501150900"
    )

    assert result == expected_response


@pytest.mark.asyncio
async def test_async_get_public_transport_route_http_error(api_client, aiohttp_mock: AioHTTPMock):
    aiohttp_mock.get("https://map.kakao.com/route/pubtrans.json", status=500)

    with pytest.raises(KakaoMapConnectionError):
        await api_client.async_get_public_transport_route(515290, 1122478, 506190, 1110730)


@pytest.mark.asyncio
async def test_parse_address_response_success(api_client):
    response_data = {
        "old": {
            "name": "서울특별시 광진구 능동 18"
        },
        "region": "서울특별시",
        "x": 515290,
        "y": 1122478
    }

    result = api_client._parse_address_response(response_data)

    assert result["success"] is True
    assert result["address"] == "서울특별시 광진구 능동 18"
    assert result["region"] == "서울특별시"
    assert result["coordinates"]["x"] == 515290
    assert result["coordinates"]["y"] == 1122478


@pytest.mark.asyncio
async def test_parse_address_response_no_old_data(api_client):
    response_data = {
        "region": "서울특별시",
        "x": 515290,
        "y": 1122478
    }

    result = api_client._parse_address_response(response_data)

    assert result["success"] is True
    assert result["address"] is None


@pytest.mark.asyncio
async def test_get_route_summary_with_recommended(api_client):
    transport_data = {
        "success": True,
        "routes": [
            {
                "time": 28,
                "fare": 1550,
                "transfers": 0
            }
        ],
        "summary": {
            "recommended_route": {
                "time": 28,
                "fare": 1550,
                "transfers": 0
            }
        }
    }

    summary = api_client.get_route_summary(transport_data)
    assert "28" in summary
    assert "1550" in summary
    assert "0회" in summary


@pytest.mark.asyncio
async def test_get_route_summary_no_data(api_client):
    transport_data = {"success": False, "routes": []}

    summary = api_client.get_route_summary(transport_data)
    assert summary == "경로 정보 없음"
