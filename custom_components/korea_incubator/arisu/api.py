"""Arisu API client for Home Assistant integration."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Dict, Any

import aiohttp
from bs4 import BeautifulSoup

from .exceptions import ArisuConnectionError, ArisuDataError
from ..const import LOGGER


class ArisuApiClient:
    """API client for Arisu integration."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the Arisu API client."""
        self._session: aiohttp.ClientSession = session
        self._base_url: str = (
            "https://i121.seoul.go.kr/cs/cyber/front/cgcalc/NR_cgJungInfo.do"
        )
        self._main_url: str = (
            "https://i121.seoul.go.kr/cs/cyber/front/cgcalc/NR_cgJungInfo.do?_m=m1_1"
        )

    async def async_get_water_bill_data(
        self, customer_number: str, customer_name: str
    ) -> Dict[str, Any]:
        """Get water bill information from Arisu for current and previous month."""
        current_date = datetime.now()
        current_month = current_date.strftime("%Y-%m")

        # 지난달 계산
        previous_date = current_date - timedelta(days=current_date.day)
        previous_month = previous_date.strftime("%Y-%m")

        pprevious_date = previous_date - timedelta(days=previous_date.day)
        pprevious_month = pprevious_date.strftime("%Y-%m")

        LOGGER.debug(
            f"Trying to get Arisu data for {customer_name} (#{customer_number}): current month={current_month}, previous month={previous_month}"
        )

        # 현재 월 먼저 시도
        current_data = await self.async_get_water_bill(
            customer_number, customer_name, current_month
        )

        if current_data.get("success", False):
            LOGGER.debug(
                f"Successfully got current month data for {customer_name} (#{customer_number})"
            )
            current_data["billing_month"] = current_month
            return current_data

        LOGGER.debug(
            f"No current month data, trying previous month for {customer_name} (#{customer_number})"
        )
        previous_data = await self.async_get_water_bill(
            customer_number, customer_name, previous_month
        )

        if previous_data.get("success", False):
            LOGGER.debug(
                f"Successfully got previous month data for {customer_name} (#{customer_number})"
            )
            previous_data["billing_month"] = previous_month
            return previous_data

        LOGGER.debug(
            f"No current month data, trying previous month for {customer_name} (#{pprevious_month})"
        )
        pprevious_data = await self.async_get_water_bill(
            customer_number, customer_name, pprevious_month
        )

        if pprevious_data.get("success", False):
            LOGGER.debug(
                f"Successfully got previous month data for {customer_name} (#{customer_number})"
            )
            pprevious_data["billing_month"] = previous_month
            return pprevious_data

        # 둘 다 실패하면 오류 반환
        return {
            "success": False,
            "error": f"No bill data found for {current_month} and {previous_month} {pprevious_month}",
            "tried_months": [current_month, previous_month, pprevious_month],
        }

    async def async_get_water_bill(
        self, customer_number: str, customer_name: str, billing_month: str
    ) -> Dict[str, Any]:
        """Get water bill information from Arisu."""
        try:
            # Step 1: 초기 페이지 접속으로 세션 설정
            await self._init_session()

            form_data = {
                "searchMkey": customer_number,  # 고객번호 필수로 전송
                "searchNapgi": billing_month,
                "searchCsNm": customer_name,
                "_m": "m1_1",
                "_csNm": "null",
                "_mkey": "null",
                "_napgi": "null",
                "resultKey": "",
                "ocrBand1": "",
                "ocrBand2": "",
                "levyYear": "",
                "levyMonth": "0",
                "levyDay": "0",
                "epayNo": "",
                "sujunNm": "",
            }

            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
                "Cache-Control": "max-age=0",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://i121.seoul.go.kr",
                "Referer": self._main_url,
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            }

            LOGGER.debug(
                f"Sending Arisu request with customer_number: {customer_number}, customer_name: {customer_name}, billing_month: {billing_month}"
            )

            async with self._session.post(
                self._base_url,
                data=form_data,
                headers=headers,
                allow_redirects=True,
            ) as response:
                LOGGER.debug(f"Arisu API response status: {response.status}")

                if response.status != 200:
                    raise ArisuConnectionError(
                        f"HTTP {response.status}: {response.reason}"
                    )

                html_content = await response.text()
                LOGGER.debug(f"Response content: {html_content}")

                if 'id="totAmt"' in html_content and "value=" in html_content:
                    return self._parse_html_response(html_content)
                else:
                    LOGGER.warning(
                        f"No bill data structure found for customer: {customer_name} (#{customer_number})"
                    )
                    return {"success": False, "error": "No bill data structure found"}

        except aiohttp.ClientError as e:
            LOGGER.error(f"Arisu API request failed: {e}")
            raise ArisuConnectionError(f"Request failed: {e}")
        except Exception as e:
            LOGGER.error(f"Unexpected error in Arisu API request: {e}")
            raise ArisuDataError(f"Unexpected error: {e}")

    async def _init_session(self) -> None:
        """Initialize session by visiting the main page first."""
        try:
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
                "Cache-Control": "max-age=0",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }

            async with self._session.get(
                self._main_url,
                headers=headers,
            ) as response:
                if response.status == 200:
                    LOGGER.debug("Session initialized successfully")
                    # 세션 쿠키가 자동으로 저장됨
                else:
                    LOGGER.warning(f"Session initialization failed: {response.status}")

        except Exception as e:
            LOGGER.warning(f"Failed to initialize session: {e}")
            # 세션 초기화 실패해도 계속 진행

    def _parse_html_response(self, html_content: str) -> Dict[str, Any]:
        """Parse HTML response to extract water bill information based on HAR analysis."""
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # HAR 파일에서 확인된 구조: totAmt input 찾기
            total_amount_input = soup.find("input", {"id": "totAmt"})
            if not total_amount_input:
                return {"success": False, "error": "No bill data found"}

            total_amount_value = total_amount_input.get("value", "0")
            if not total_amount_value or total_amount_value == "0":
                return {"success": False, "error": "No bill amount found"}

            # Extract customer information from the response
            customer_info = self._extract_customer_info_from_har(soup)

            # Extract usage information
            usage_info = self._extract_usage_info_from_har(soup)

            # Extract arrears information
            arrears_info = self._extract_arrears_info_from_har(soup)

            return {
                "success": True,
                "total_amount": self._clean_amount(total_amount_value),
                "customer_info": customer_info,
                "usage_info": usage_info,
                "arrears_info": arrears_info,
            }

        except Exception as e:
            LOGGER.error(f"Error parsing HTML response: {e}")
            raise ArisuDataError(f"HTML parsing failed: {e}")

    def _extract_customer_info_from_har(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract customer information based on HAR file structure."""
        info = {}

        try:
            # HAR에서 확인된 고객번호 패턴: 042389659
            customer_num_cell = soup.find(
                "td",
                string=lambda text: text and re.match(r"^\d{9}$", text.strip())
                if text
                else False,
            )
            if customer_num_cell:
                info["customer_number"] = customer_num_cell.get_text(strip=True)

            # 주소 정보 추출 (HAR에서 확인된 패턴)
            address_text = soup.find(
                "label", string=lambda text: text and "주소:" in text if text else False
            )
            if address_text and address_text.parent:
                # label 다음의 텍스트 찾기
                address_content = address_text.parent.get_text()
                if "주소:" in address_content:
                    address = address_content.split("주소:")[1].strip()
                    if address:
                        info["address"] = address

            # 납부방법 정보 (HAR에서 확인된 구조)
            payment_row = soup.find("th", string="납부방법")
            if payment_row:
                payment_cell = payment_row.find_next_sibling("td")
                if payment_cell:
                    info["payment_method"] = payment_cell.get_text(strip=True)

        except Exception as e:
            LOGGER.warning(f"Error extracting customer info: {e}")

        return info

    def _extract_usage_info_from_har(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract usage information based on HAR file structure."""
        usage = {}

        try:
            # HAR에서 확인된 사용량 패턴: "사용량" 행 찾기
            usage_rows = soup.find_all(
                "td", string=lambda text: text and "사용량" in text if text else False
            )
            for usage_row in usage_rows:
                if usage_row.parent:
                    cells = usage_row.parent.find_all("td")
                    if len(cells) >= 2:
                        # 사용량 값 추출
                        for i, cell in enumerate(cells):
                            if "사용량" in cell.get_text():
                                if i + 1 < len(cells):
                                    usage_value = cells[i + 1].get_text(strip=True)
                                    if usage_value and usage_value.isdigit():
                                        usage["current_usage"] = int(usage_value)

            # 지침 정보 추출 (HAR에서 확인된 패턴)
            meter_readings = soup.find_all(
                "td", string=lambda text: text and "지침" in text if text else False
            )
            reading_values = []

            for reading_row in meter_readings:
                if reading_row.parent:
                    cells = reading_row.parent.find_all("td")
                    for cell in cells:
                        cell_text = cell.get_text(strip=True)
                        if cell_text.isdigit():
                            reading_values.append(int(cell_text))

            if len(reading_values) >= 2:
                usage["current_reading"] = max(reading_values)
                usage["previous_reading"] = min(reading_values)

        except Exception as e:
            LOGGER.warning(f"Error extracting usage info: {e}")

        return usage

    def _extract_arrears_info_from_har(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract arrears information based on HAR file structure."""
        arrears = {}

        try:
            # HAR에서 확인된 체납 테이블 구조
            arrears_table = soup.find("table", class_="table-type1 pink")
            if arrears_table:
                rows = arrears_table.find_all("tr")
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)

                        if "체납금액" in label:
                            arrears["overdue_amount"] = self._clean_amount(value)
                        elif "미납금액" in label:
                            arrears["unpaid_amount"] = self._clean_amount(value)

        except Exception as e:
            LOGGER.warning(f"Error extracting arrears info: {e}")

        return arrears

    def _clean_amount(self, amount_str: str) -> int:
        """Clean and convert amount string to integer."""
        if not amount_str:
            return 0
        # Remove commas and non-numeric characters except digits
        cleaned = re.sub(r"[^\d]", "", amount_str)
        return int(cleaned) if cleaned else 0
