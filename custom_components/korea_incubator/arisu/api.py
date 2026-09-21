"""Arisu API client for Home Assistant integration."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Dict, Any

import aiohttp
from bs4 import BeautifulSoup

from .exceptions import ArisuAuthError, ArisuConnectionError, ArisuDataError
from ..const import LOGGER


class ArisuApiClient:
    """API client for Arisu integration."""

    BILL_LOOKBACK_MONTHS = 12

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the Arisu API client."""
        self._session: aiohttp.ClientSession = session
        self._csrf_token: str | None = None
        self._base_url: str = (
            "https://i121.seoul.go.kr/cyber/front/cgcalc/NR_cgJungInfo.do"
        )
        self._main_url: str = (
            "https://i121.seoul.go.kr/cyber/front/cgcalc/NR_cgJungInfo.do?_m=m1_1_1"
        )

    async def async_get_water_bill_data(
        self, customer_number: str, customer_name: str
    ) -> Dict[str, Any]:
        """Return the newest available statement within the last twelve months."""
        month = datetime.now().replace(day=1)
        tried_months = []
        for _ in range(self.BILL_LOOKBACK_MONTHS):
            billing_month = month.strftime("%Y-%m")
            tried_months.append(billing_month)
            bill = await self.async_get_water_bill(
                customer_number, customer_name, billing_month
            )
            if bill.get("success", False):
                return {**bill, "billing_month": billing_month}
            if not bill.get("no_bill_data", False):
                raise ArisuDataError(bill.get("error", "Unrecognized Arisu response"))
            month = (month - timedelta(days=1)).replace(day=1)

        return {
            "success": False,
            "no_bill_data": True,
            "error": f"No bill data found for {', '.join(tried_months)}",
            "tried_months": tried_months,
        }

    async def async_get_water_bill(
        self, customer_number: str, customer_name: str, billing_month: str
    ) -> Dict[str, Any]:
        """Get water bill information from Arisu."""
        try:
            # Step 1: 초기 페이지에서 세션과 CSRF 토큰을 설정한다.
            await self._init_session()

            if not self._csrf_token:
                raise ArisuConnectionError(
                    "Could not obtain the CSRF token required by Arisu"
                )

            form_data = {
                "searchMkey": customer_number,  # 고객번호 필수로 전송
                "searchNapgi": billing_month,
                "searchCsNm": re.sub(r"\s+", "", customer_name),
                "_csrf": self._csrf_token,
            }

            headers = {
                "X-Requested-With": "XMLHttpRequest",
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
                "X-CSRF-TOKEN": self._csrf_token,
            }

            if not await self._check_bill_available(form_data, headers):
                return {"success": False, "no_bill_data": True}

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
                return self._parse_html_response(html_content)

        except (ArisuAuthError, ArisuConnectionError, ArisuDataError):
            raise
        except aiohttp.ClientError as e:
            LOGGER.error(f"Arisu API request failed: {e}")
            raise ArisuConnectionError(f"Request failed: {e}")
        except Exception as e:
            LOGGER.error(f"Unexpected error in Arisu API request: {e}")
            raise ArisuDataError(f"Unexpected error: {e}")

    async def _check_bill_available(self, form_data: dict, headers: dict) -> bool:
        """Follow the site's customer validation and monthly publication checks."""

        async def request(path: str) -> dict:
            async with self._session.post(
                "https://i121.seoul.go.kr" + path,
                data=form_data,
                headers={**headers, "Accept": "application/json"},
            ) as response:
                if response.status != 200:
                    raise ArisuConnectionError(
                        f"Arisu bill validation HTTP {response.status}: {response.reason}"
                    )
                try:
                    result = await response.json()
                except (ValueError, aiohttp.ContentTypeError) as err:
                    raise ArisuDataError(
                        "Invalid Arisu bill validation response"
                    ) from err
                if not isinstance(result, dict):
                    raise ArisuDataError("Invalid Arisu bill validation response")
                return result

        customer = await request("/cyber/front/mkey/JR_getCsNmFlag.do")
        if customer.get("csNmFlag") == "N" or (
            customer.get("status") == "FAILURE"
            and customer.get("message") == "조회결과가 없습니다."
        ):
            raise ArisuAuthError("Arisu customer number and name do not match")
        if customer.get("csNmFlag") != "Y":
            raise ArisuDataError("Missing Arisu customer validation result")
        if str(customer.get("area")) == "7" or str(customer.get("seq")) == "0000":
            raise ArisuDataError(
                "Arisu bills are managed by the building management office"
            )
        publication = await request("/cyber/front/cgcalc/JR_getpcaDeciFlag.do")
        flag = publication.get("pcaDeciFlag")
        if flag not in ("Y", "N"):
            raise ArisuDataError("Missing Arisu bill publication result")
        return flag == "Y"

    async def _init_session(self) -> None:
        """Initialize session by visiting the main page first."""
        self._csrf_token = None
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
                    html_content = await response.text()
                    soup = BeautifulSoup(html_content, "html.parser")
                    token_input = soup.find("input", {"name": "_csrf"})
                    self._csrf_token = token_input.get("value") if token_input else None
                    if not self._csrf_token:
                        LOGGER.warning(
                            "Arisu session page did not contain a CSRF token"
                        )
                        return
                    LOGGER.debug("Session initialized successfully")
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
                if any(
                    re.search(r"\bvar\s+noResult\s*=\s*true\s*;", script.get_text())
                    for script in soup.find_all("script")
                ):
                    return {"success": False, "no_bill_data": True}
                raise ArisuDataError(
                    "Unrecognized Arisu response: neither a bill nor an explicit no-result response"
                )

            total_amount_value = total_amount_input.get("value", "").strip()
            if not re.fullmatch(r"[\d,]+(?:\s*원)?", total_amount_value):
                raise ArisuDataError("Invalid Arisu bill amount")

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

        except ArisuDataError:
            raise
        except Exception as e:
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
