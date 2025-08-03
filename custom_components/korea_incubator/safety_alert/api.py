"""Safety Alert API client for Home Assistant integration."""
from __future__ import annotations

import aiohttp
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from .exceptions import SafetyAlertConnectionError, SafetyAlertDataError
from ..const import LOGGER


class SafetyAlertApiClient:
    """API client for Safety Alert integration."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the Safety Alert API client."""
        self._session: aiohttp.ClientSession = session
        self._base_url: str = "https://www.safekorea.go.kr/idsiSFK/sfk/cs/sua/web/DisasterSmsList.do"

    async def async_get_safety_alerts(
        self,
        area_code: str = "1156000000",
        area_code2: Optional[str] = None,
        area_code3: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get safety alerts for the specified areas."""
        # Calculate date range (last 7 days)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        # Prepare request payload with all area codes
        payload = {
            "searchInfo": {
                "firstIndex": "1",
                "rcv_Area_Id": "",
                "pageIndex": "1",
                "sbLawArea1": area_code,  # 첫 번째 지역 코드
                "dstr_se_Id": "",
                "lastIndex": "1",
                "searchBgnDe": start_date.strftime("%Y-%m-%d"),
                "searchEndDe": end_date.strftime("%Y-%m-%d"),
                "sbLawArea3": area_code3 if area_code3 else "",  # 세 번째 지역 코드
                "recordCountPerPage": "50",
                "searchWrd": "",
                "searchGb": "1",
                "c_ocrc_type": "",
                "sbLawArea2": area_code2 if area_code2 else "",  # 두 번째 지역 코드
                "pageUnit": "50",
                "pageSize": 50
            }
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "HomeAssistant-Korea-Components/1.0"
        }

        try:
            async with self._session.post(
                self._base_url,
                json=payload,
                headers=headers
            ) as response:
                LOGGER.debug(f"Safety Alert API response status: {response.status}")

                if response.status != 200:
                    LOGGER.warning(f"Failed to get alerts: HTTP {response.status}")
                    raise SafetyAlertConnectionError(f"HTTP {response.status}")

                data = await response.json()
                LOGGER.debug(f"Safety Alert API response: {data}")

                alerts = data.get("disasterSmsList", [])

                # 생성일시 기준으로 정렬 (최신순)
                alerts.sort(key=lambda x: x.get("CREAT_DT", ""), reverse=True)

                return alerts

        except aiohttp.ClientError as e:
            LOGGER.error(f"Safety Alert API request failed: {e}")
            raise SafetyAlertConnectionError(f"Connection failed: {e}")
        except Exception as e:
            LOGGER.error(f"Unexpected error in Safety Alert API request: {e}")
            raise SafetyAlertDataError(f"Unexpected error: {e}")

    def parse_alert_data(self, alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse and organize alert data."""
        if not alerts:
            return {
                "total_alerts": 0,
                "latest_alert": None,
                "alert_types": {},
                "alerts_by_type": {}
            }

        # Count alerts by type
        alert_types: Dict[str, int] = {}
        alerts_by_type: Dict[str, List[Dict[str, Any]]] = {}

        for alert in alerts:
            alert_type = alert.get("DSSTR_SE_NM", "기타")
            if alert_type not in alert_types:
                alert_types[alert_type] = 0
                alerts_by_type[alert_type] = []

            alert_types[alert_type] += 1
            alerts_by_type[alert_type].append({
                "message": alert.get("MSG_CN", ""),
                "created_date": alert.get("CREAT_DT", ""),
                "area": alert.get("RCV_AREA_NM", ""),
                "emergency_level": alert.get("EMRGNCY_STEP_NM", "")
            })

        # Get latest alert
        latest_alert: Optional[Dict[str, Any]] = None
        if alerts:
            latest_alert = {
                "type": alerts[0].get("DSSTR_SE_NM", ""),
                "message": alerts[0].get("MSG_CN", ""),
                "created_date": alerts[0].get("CREAT_DT", ""),
                "area": alerts[0].get("RCV_AREA_NM", ""),
                "emergency_level": alerts[0].get("EMRGNCY_STEP_NM", "")
            }

        return {
            "total_alerts": len(alerts),
            "latest_alert": latest_alert,
            "alert_types": alert_types,
            "alerts_by_type": alerts_by_type
        }
