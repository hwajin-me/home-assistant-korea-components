"""Safety Alert Region API client for getting region codes."""

from __future__ import annotations

import ssl
from typing import Dict, List

import aiohttp

from ..const import LOGGER, SSL_CONTEXT


class SafetyAlertRegionApiClient:
    """API client for Safety Alert region code retrieval."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the Safety Alert Region API client."""
        self._session: aiohttp.ClientSession = session
        self._base_url: str = "https://www.safekorea.go.kr/idsiSFK/sfk/cs/sua/web"
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

    async def async_get_sido_list(self) -> List[Dict[str, str]]:
        """Get list of sido (시도) regions."""
        url = f"{self._base_url}/Get_CBS_Sido_List.do"
        payload = {}

        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            async with self._session.post(
                url, json=payload, headers=headers, ssl=self._get_ssl_context()
            ) as response:
                if response.status != 200:
                    LOGGER.error(
                        f"Sido list API request failed with status: {response.status}"
                    )
                    return []

                data = await response.json()
                sido_list = data.get("cbs_sido_list", [])

                # Format for easier use
                result = []
                for sido in sido_list:
                    result.append(
                        {
                            "code": sido.get("BDONG_CD", ""),
                            "name": sido.get("CBS_AREA_NM", ""),
                            "id": sido.get("CBS_AREA_ID", ""),
                        }
                    )

                # Sort by name for better UX
                result.sort(key=lambda x: x["name"])
                return result

        except aiohttp.ClientError as e:
            LOGGER.error(f"Sido list API request failed: {e}")
            return []

    async def async_get_sgg_list(self, sido_code: str) -> List[Dict[str, str]]:
        """Get list of sgg (시군구) regions for a given sido."""
        url = f"{self._base_url}/Get_CBS_Sgg_List.do"
        payload = {"sgg_searchInfo": {"BDONG_CD": "", "bdong_cd": sido_code}}

        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            async with self._session.post(
                url, json=payload, headers=headers, ssl=self._get_ssl_context()
            ) as response:
                if response.status != 200:
                    LOGGER.warning(
                        f"Sgg list API request failed with status: {response.status}"
                    )
                    return []

                data = await response.json()
                sgg_list = data.get("cbs_sgg_list", [])

                # Format for easier use
                result = []
                for sgg in sgg_list:
                    result.append(
                        {
                            "code": sgg.get("BDONG_CD", ""),
                            "name": sgg.get("CBS_AREA_NM", ""),
                        }
                    )

                # Sort by name for better UX
                result.sort(key=lambda x: x["name"])
                return result

        except aiohttp.ClientError as e:
            LOGGER.warning(f"Sgg list API request failed: {e}")
            return []

    async def async_get_emd_list(
        self, sido_code: str, sgg_code: str
    ) -> List[Dict[str, str]]:
        """Get list of emd (읍면동) regions for a given sido and sgg."""
        url = f"{self._base_url}/Get_CBS_Emd_List.do"
        payload = {
            "emd_searchInfo": {
                "BDONG_CD": "",
                "area1_bdong_cd": sido_code,
                "area2_bdong_cd": sgg_code,
            }
        }

        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            async with self._session.post(
                url, json=payload, headers=headers, ssl=self._get_ssl_context()
            ) as response:
                if response.status != 200:
                    LOGGER.warning(
                        f"Emd list API request failed with status: {response.status}"
                    )
                    return []

                data = await response.json()
                emd_list = data.get("cbs_emd_list", [])

                # Format for easier use
                result = []
                for emd in emd_list:
                    result.append(
                        {
                            "code": emd.get("BDONG_CD", ""),
                            "name": emd.get("CBS_AREA_NM", ""),
                        }
                    )

                # Sort by name for better UX
                result.sort(key=lambda x: x["name"])
                return result

        except aiohttp.ClientError as e:
            LOGGER.warning(f"Emd list API request failed: {e}")
            return []
