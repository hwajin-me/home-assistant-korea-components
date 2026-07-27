"""Safety Alert API client for Home Assistant integration."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import curl_cffi
from bs4 import BeautifulSoup

from .exceptions import SafetyAlertConnectionError
from ..const import LOGGER, TZ_ASIA_SEOUL

_BASE_URL = "https://www.safekorea.go.kr/safekorea-kor/ctim/cmsg/calamitySms.do"
_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.safekorea.go.kr/safekorea-kor/ctim/cmsg/calamitySms.do",
}


class SafetyAlertApiClient:
    """API client for Safety Alert integration."""

    def __init__(self, session=None) -> None:
        pass

    async def async_get_safety_alerts(
        self,
        area_code: str = "1100000000",
        area_code2: Optional[str] = None,
        area_code3: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get safety alerts by scraping calamitySms.do HTML response."""
        end_date = datetime.now(TZ_ASIA_SEOUL)
        start_date = end_date - timedelta(days=7)

        params = {
            "menuSn": "34",
            "currentPage": "1",
            "readYn": "Y",
            "firstYn": "N",
            "sbLawArea1": area_code,
            "sbLawArea2": area_code2 or "",
            "sbLawArea3": area_code3 or "",
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
        }

        try:
            async with curl_cffi.AsyncSession(impersonate="chrome120") as session:
                response = await session.get(
                    _BASE_URL,
                    params=params,
                    headers=_HEADERS,
                    verify=False,
                    timeout=15,
                )

                if response.status_code != 200:
                    raise SafetyAlertConnectionError(f"HTTP {response.status_code}")

                html = response.text
                LOGGER.debug("Safety Alert HTML length: %d", len(html))
                return self._parse_html(html)

        except SafetyAlertConnectionError:
            raise
        except Exception as e:
            LOGGER.error("Safety Alert API request failed: %s", e)
            raise SafetyAlertConnectionError(f"Request failed: {e}")

    def _parse_html(self, html: str) -> Dict[str, Any]:
        """Parse disaster SMS data from HTML response."""
        soup = BeautifulSoup(html, "html.parser")
        alerts: List[Dict[str, Any]] = []

        # 전체 건수
        count_span = soup.select_one("div.board-count span")
        total_count = int(count_span.get_text(strip=True)) if count_span else 0

        # 웹용 테이블 파싱 (board-listarea)
        rows = soup.select("div.board-listarea table tbody tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            if cells[0].get("colspan"):
                continue

            disaster_type = cells[0].get_text(strip=True)
            msg_cell = cells[1]

            # 메시지 내용 (a 태그)
            msg_link = msg_cell.find("a")
            msg_content = msg_link.get_text(strip=True) if msg_link else ""

            # 발송일시 / 긴급단계 / 송출지역 (p 태그)
            info_p = msg_cell.find("p")
            info_text = info_p.get_text(" ", strip=True) if info_p else ""

            regist_dt = ""
            emrgncy_step = ""
            rcv_area = ""

            dt_match = re.search(r"발송일시\s*:\s*([\d/\s:]+)", info_text)
            if dt_match:
                regist_dt = dt_match.group(1).strip()

            step_match = re.search(r"긴급단계\s*:\s*([^\ㆍ]+)", info_text)
            if step_match:
                emrgncy_step = step_match.group(1).strip()

            area_match = re.search(r"송출지역\s*:\s*(.+?)$", info_text)
            if area_match:
                rcv_area = area_match.group(1).strip()

            alerts.append({
                "DSSTR_SE_NM": disaster_type,
                "EMRGNCY_STEP_NM": emrgncy_step,
                "MSG_CN": msg_content,
                "RCV_AREA_NM": rcv_area,
                "REGIST_DT": regist_dt,
            })

        LOGGER.debug("Parsed %d alerts (total: %d)", len(alerts), total_count)

        return {
            "disasterSmsList": alerts,
            "rtnResult": {"totCnt": total_count},
        }
