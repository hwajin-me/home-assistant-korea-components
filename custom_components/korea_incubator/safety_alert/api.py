"""Safety Alert API client for Home Assistant integration."""

from __future__ import annotations

import ssl
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import aiohttp

from .exceptions import SafetyAlertConnectionError
from ..const import LOGGER, SSL_CONTEXT


class SafetyAlertApiClient:
    """API client for Safety Alert integration."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the Safety Alert API client."""
        self._session: aiohttp.ClientSession = session
        self._base_url: str = (
            "https://www.safekorea.go.kr/idsiSFK/sfk/cs/sua/web/DisasterSmsList.do"
        )
        self._ssl_context = None  # 지연 로딩을 위해 None으로 초기화

    def _get_ssl_context(self) -> ssl.SSLContext:
        """Get SSL context with lazy loading to avoid blocking calls in event loop."""
        if self._ssl_context is None:
            # SSL 컨텍스트 설정 - DH_KEY_TOO_SMALL 에러 해결
            self._ssl_context = SSL_CONTEXT
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE

            # DH 키 크기 문제 해결을 위한 설정
            self._ssl_context.set_ciphers(
                "ECDHE+AESGCM:ECDHE+CHACHA20:ECDHE+AES256:ECDHE+AES128:!DH:!aNULL:!eNULL:!EXPORT:!MD5:!DSS:!RC4"
            )

            # 최소 TLS 버전을 1.2로 설정하되, 연결 실패시 1.0까지 허용
            try:
                self._ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
            except Exception:
                self._ssl_context.minimum_version = ssl.TLSVersion.TLSv1

            # 안전하지 않은 프로토콜 비활성화
            self._ssl_context.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3

            # DH 관련 옵션 설정
            if hasattr(ssl, "OP_SINGLE_DH_USE"):
                self._ssl_context.options |= ssl.OP_SINGLE_DH_USE
            if hasattr(ssl, "OP_SINGLE_ECDH_USE"):
                self._ssl_context.options |= ssl.OP_SINGLE_ECDH_USE

        return self._ssl_context

    async def async_get_safety_alerts(
        self,
        area_code: str = "1156000000",
        area_code2: Optional[str] = None,
        area_code3: Optional[str] = None,
    ) -> Dict[str, Any]:
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
                "pageSize": 50,
            }
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "HomeAssistant-Korea-Components/1.0",
        }

        try:
            async with self._session.post(
                self._base_url,
                json=payload,
                headers=headers,
                ssl=self._get_ssl_context(),  # SSL 컨텍스트 적용
            ) as response:
                LOGGER.debug(f"Safety Alert API response status: {response.status}")

                if response.status != 200:
                    LOGGER.warning(f"Failed to get alerts: HTTP {response.status}")
                    raise SafetyAlertConnectionError(f"HTTP {response.status}")

                data = await response.json()
                LOGGER.debug(f"Safety Alert API response: {data}")

                return data

        except aiohttp.ClientError as e:
            LOGGER.error(f"Safety Alert API request failed: {e}")
            return {}
        except Exception as e:
            LOGGER.error(f"Unexpected error in Safety Alert API request: {e}")
            return {}
