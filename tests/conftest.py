"""Test configuration and fixtures for Korea integration tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock
import aiohttp

from custom_components.korea_incubator.const import DOMAIN


def pytest_addoption(parser):
    """Add command-line options for pytest."""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests with real API calls",
    )


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test requiring real API access",
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle integration tests."""
    if config.getoption("--integration"):
        # Integration tests enabled, run all tests
        return

    # Skip integration tests by default
    skip_integration = pytest.mark.skip(
        reason="Integration tests disabled (use --integration to enable)"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


# Common fixtures
@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {}
    return entry


@pytest.fixture
def mock_coordinator():
    """Create a mock DataUpdateCoordinator."""
    coordinator = MagicMock()
    coordinator.data = {}
    coordinator.last_update_success = True
    return coordinator


@pytest.fixture
async def mock_session():
    """Create a mock aiohttp session."""
    session = AsyncMock(spec=aiohttp.ClientSession)
    session.closed = False
    return session


# Service-specific config fixtures
@pytest.fixture
def kepco_config_data():
    """KEPCO configuration data."""
    return {"service": "kepco", "username": "test_user", "password": "test_password"}


@pytest.fixture
def mock_entry_kepco(kepco_config_data):
    """Create mock config entry for KEPCO."""
    entry = MagicMock()
    entry.entry_id = "test_kepco_entry"
    entry.data = kepco_config_data
    return entry


@pytest.fixture
def gasapp_config_data():
    """GasApp configuration data."""
    return {
        "service": "gasapp",
        "token": "test_token",
        "member_id": "test_member",
        "use_contract_num": "test_contract",
    }


@pytest.fixture
def mock_entry_gasapp(gasapp_config_data):
    """Create mock config entry for GasApp."""
    entry = MagicMock()
    entry.entry_id = "test_gasapp_entry"
    entry.data = gasapp_config_data
    return entry


@pytest.fixture
def safety_alert_config_data():
    """Safety Alert configuration data."""
    return {
        "service": "safety_alert",
        "area_code": "1100000000",
        "area_name": "서울특별시",
        "sido_code": "1100000000",
        "sido_name": "서울특별시",
    }


@pytest.fixture
def mock_entry_safety_alert(safety_alert_config_data):
    """Create mock config entry for Safety Alert."""
    entry = MagicMock()
    entry.entry_id = "test_safety_alert_entry"
    entry.data = safety_alert_config_data
    return entry


# Mock response fixtures
@pytest.fixture
def kepco_mock_response():
    """Mock KEPCO API response."""
    return {
        "recent_usage": {
            "result": {"F_AP_QT": "123.45", "ST_TIME": "2025-01-15 14:30:00"}
        },
        "usage_info": {
            "result": {
                "BILL_LAST_MONTH": "25000",
                "PREDICT_TOTAL_CHARGE_REV": "30000",
                "PREDICT_KWH": "150.5",
                "F_AP_QT": "123.45",
                "KWH_LAST_MONTH": "120.3",
                "TOTAL_CHARGE": "28000",
                "BILL_LEVEL": "2",
            },
            "SESS_CUSTNO": "123456789",
            "SESS_CNTR_KND_NM": "주택용",
            "SESS_MR_ST_DT": "2025-01-01",
            "SESS_MR_END_DT": "2025-01-31",
        },
    }


@pytest.fixture
def gasapp_mock_response():
    """Mock GasApp API response."""
    return {
        "cards": {
            "bill": {
                "title1": "2025년 1월 청구서",
                "title2": "총 50,000원",
                "history": [
                    {
                        "requestYm": "2025-01",
                        "usageQty": "25.5",
                        "chargeAmtQty": "50000",
                    },
                    {
                        "requestYm": "2024-12",
                        "usageQty": "23.2",
                        "chargeAmtQty": "45000",
                    },
                    {
                        "requestYm": "2024-11",
                        "usageQty": "20.1",
                        "chargeAmtQty": "40000",
                    },
                ],
            }
        }
    }


@pytest.fixture
def safety_alert_mock_response():
    """Mock Safety Alert API response."""
    return {
        "disasterSmsList": [
            {
                "EMRGNCY_STEP_NM": "관심",
                "DSSTR_SE_NM": "태풍",
                "MSG_CN": "태풍 경보 발령",
                "RCV_AREA_NM": "서울특별시",
                "REGIST_DT": "2025-01-15 14:30:00",
            },
            {
                "EMRGNCY_STEP_NM": "주의",
                "DSSTR_SE_NM": "강풍",
                "MSG_CN": "강풍 주의보 발령",
                "RCV_AREA_NM": "서울특별시",
                "REGIST_DT": "2025-01-14 10:00:00",
            },
        ],
        "rtnResult": {"totCnt": 2},
    }


@pytest.fixture
def arisu_mock_response():
    """Mock Arisu API response."""
    return {
        "success": True,
        "total_amount": 45000,
        "billing_month": "2025-01",
        "customer_info": {
            "customer_number": "042389659",
            "address": "서울시 강남구 테헤란로 123",
            "payment_method": "자동이체",
        },
        "usage_info": {
            "current_usage": 15,
            "current_reading": 12345,
            "previous_reading": 12330,
        },
        "arrears_info": {"overdue_amount": 0, "unpaid_amount": 0},
    }


@pytest.fixture
def goodsflow_mock_response():
    """Mock GoodsFlow API response."""
    return {
        "success": True,
        "data": {
            "transList": {
                "totalCount": 5,
                "rows": [
                    {
                        "status": "배송중",
                        "company": "CJ대한통운",
                        "trackingNumber": "123456789",
                    },
                    {
                        "status": "배송완료",
                        "company": "한진택배",
                        "trackingNumber": "987654321",
                    },
                ],
            }
        },
    }


@pytest.fixture
def kakaomap_mock_address_response():
    """Mock KakaoMap address response."""
    return {
        "success": True,
        "address": "서울시 광진구 건대입구역",
        "region": "서울시 광진구",
        "coordinates": {"x": 515290, "y": 1122478},
    }


@pytest.fixture
def kakaomap_mock_route_response():
    """Mock KakaoMap route response."""
    return {
        "in_local": {
            "routes": [
                {
                    "time": {"value": 1680},  # 28 minutes in seconds
                    "fare": {"value": 1370},
                    "distance": {"value": 15000},  # 15km in meters
                    "type": "지하철+버스",
                    "transfers": 1,
                    "walkingDistance": {"value": 500},
                    "walkingTime": {"value": 300},
                    "recommended": True,
                    "shortestTime": False,
                    "leastTransfer": False,
                    "steps": [
                        {
                            "information": "건대입구역에서 지하철 탑승",
                            "action": "지하철 탑승",
                            "type": "subway",
                        },
                        {
                            "information": "강남역에서 버스로 환승",
                            "type": "transfer",
                            "distance": {"value": 200},
                            "time": {"value": 180},
                        },
                    ],
                }
            ]
        }
    }
