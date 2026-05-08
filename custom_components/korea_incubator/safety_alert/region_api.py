"""Safety Alert Region API client for getting region codes."""

from __future__ import annotations

from typing import Dict, List, Optional

import curl_cffi

from ..const import LOGGER

_TIMEOUT = 15
_BASE_URL = "https://www.safekorea.go.kr/safekorea-kor/ctim/cmsg"
_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.safekorea.go.kr",
    "Referer": "https://www.safekorea.go.kr/safekorea-kor/ctim/cmsg/calamitySms.do",
}

# 전국 17개 시도 — 행정구역이므로 하드코딩
_SIDO_LIST = [
    {"code": "1100000000", "name": "서울특별시"},
    {"code": "2600000000", "name": "부산광역시"},
    {"code": "2700000000", "name": "대구광역시"},
    {"code": "2800000000", "name": "인천광역시"},
    {"code": "2900000000", "name": "광주광역시"},
    {"code": "3000000000", "name": "대전광역시"},
    {"code": "3100000000", "name": "울산광역시"},
    {"code": "3600000000", "name": "세종특별자치시"},
    {"code": "4100000000", "name": "경기도"},
    {"code": "4200000000", "name": "강원특별자치도"},
    {"code": "4300000000", "name": "충청북도"},
    {"code": "4400000000", "name": "충청남도"},
    {"code": "4500000000", "name": "전북특별자치도"},
    {"code": "4600000000", "name": "전라남도"},
    {"code": "4700000000", "name": "경상북도"},
    {"code": "4800000000", "name": "경상남도"},
    {"code": "5000000000", "name": "제주특별자치도"},
]


class SafetyAlertRegionApiClient:
    """API client for Safety Alert region code retrieval."""

    def __init__(self, session=None) -> None:
        pass

    async def async_get_sido_list(self) -> List[Dict[str, str]]:
        """Return hardcoded list of sido (시도) regions."""
        return _SIDO_LIST

    async def async_get_sgg_list(self, sido_code: str) -> Optional[List[Dict[str, str]]]:
        """Get list of sgg (시군구) regions for a given sido via POST JSON."""
        url = f"{_BASE_URL}/changeSidoList.do"
        try:
            async with curl_cffi.AsyncSession(impersonate="chrome120") as session:
                response = await session.post(
                    url,
                    json={"sbLawArea1": sido_code},
                    headers=_HEADERS,
                    verify=False,
                    timeout=_TIMEOUT,
                )
                if response.status_code != 200:
                    LOGGER.warning("Sgg list API failed with status: %s", response.status_code)
                    return None
                text = response.text
                LOGGER.debug("Sgg list raw response: %s", text[:300])
                if not text.strip() or text.strip().startswith("<"):
                    LOGGER.warning("Sgg list API returned non-JSON response")
                    return None
                data = response.json()
                result = [
                    {"code": s.get("bdongCd", ""), "name": s.get("cbsAreaNm", "")}
                    for s in data
                    if s.get("cbsAreaNm")
                ]
                result.sort(key=lambda x: x["name"])
                return result if result else None
        except Exception as e:
            LOGGER.warning("Sgg list API request failed: %s", e)
            return None

    async def async_get_emd_list(self, sido_code: str, sgg_code: str) -> Optional[List[Dict[str, str]]]:
        """Get list of emd (읍면동) regions for a given sido and sgg via POST JSON."""
        url = f"{_BASE_URL}/changeSggList.do"
        try:
            async with curl_cffi.AsyncSession(impersonate="chrome120") as session:
                response = await session.post(
                    url,
                    json={"sbLawArea1": sido_code, "sbLawArea2": sgg_code},
                    headers=_HEADERS,
                    verify=False,
                    timeout=_TIMEOUT,
                )
                if response.status_code != 200:
                    LOGGER.warning("Emd list API failed with status: %s", response.status_code)
                    return None
                text = response.text
                LOGGER.debug("Emd list raw response: %s", text[:300])
                if not text.strip() or text.strip().startswith("<"):
                    LOGGER.warning("Emd list API returned non-JSON response")
                    return None
                data = response.json()
                result = [
                    {"code": e.get("bdongCd", ""), "name": e.get("cbsAreaNm", "")}
                    for e in data
                    if e.get("cbsAreaNm")
                ]
                result.sort(key=lambda x: x["name"])
                return result if result else None
        except Exception as e:
            LOGGER.warning("Emd list API request failed: %s", e)
            return None
