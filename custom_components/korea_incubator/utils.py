from __future__ import annotations

import random
import re
from datetime import datetime
from typing import Dict, Any, Optional

from homeassistant.util import dt as dt_util

from custom_components.korea_incubator.const import TZ_ASIA_SEOUL


class RSAKey:
    """rsa.js의 RSAKey와 동일한 기능을 하는 Python 클래스"""

    def __init__(self):
        self.n = None
        self.e = 0

    def set_public(self, modulus_hex, exponent_hex):
        """RSA 공개키를 16진수 문자열로부터 설정"""
        if (
            modulus_hex
            and exponent_hex
            and len(modulus_hex) > 0
            and len(exponent_hex) > 0
        ):
            self.n = int(modulus_hex, 16)
            self.e = int(exponent_hex, 16)
        else:
            raise ValueError("Invalid RSA public key")

    def do_public(self, x):
        """x^e (mod n) 계산"""
        return pow(x, self.e, self.n)

    def encrypt(self, text):
        """PKCS#1 RSA 암호화"""
        key_size = (self.n.bit_length() + 7) // 8
        m = pkcs1pad2(text, key_size)
        if m is None:
            return None
        c = self.do_public(m)
        if c is None:
            return None
        h = hex(c)[2:]  # '0x' 제거
        # 홀수 길이면 앞에 '0' 추가
        if len(h) % 2 == 1:
            h = "0" + h
        return h


def pkcs1pad2(s, n):
    """rsa.js의 pkcs1pad2 함수와 동일한 PKCS#1 타입 2 패딩"""
    # UTF-8 인코딩
    s_bytes = s.encode("utf-8")
    s_len = len(s_bytes)

    if n < s_len + 11:
        raise ValueError("Message too long for RSA")

    # 바이트 배열 생성
    ba = bytearray(n)

    # 메시지를 뒤에서부터 배치
    ba[n - s_len : n] = s_bytes

    # 0x00 구분자
    ba[n - s_len - 1] = 0

    # 랜덤 논제로 패딩 (2부터 메시지 앞까지)
    for i in range(2, n - s_len - 1):
        # 0이 아닌 랜덤 바이트 생성
        while True:
            rand_byte = random.randint(1, 255)
            if rand_byte != 0:
                ba[i] = rand_byte
                break

    # PKCS#1 타입 2 헤더
    ba[0] = 0x00
    ba[1] = 0x02

    # 바이트 배열을 정수로 변환
    return int.from_bytes(ba, "big")


def get_value_from_path(data: Dict[str, Any], path: str) -> Any:
    """Get a value from a nested dictionary using a dot-separated path.

    Supports array indexing with square brackets, similar to jq:
    - "items.0" or "items[0]" for first element
    - "items[-1]" for last element
    - "data.history[2].value" for nested array access
    - "data.history[-2].value" for second to last element
    """
    keys = path.split(".")
    value = data

    for key in keys:
        if value is None:
            return None

        # Handle array indexing with square brackets: items[0] or items[-1]
        if "[" in key and key.endswith("]"):
            array_key, index_part = key.split("[", 1)
            index_str = index_part.rstrip("]")

            try:
                index = int(index_str)
            except ValueError:
                return None

            # Get the array first
            if isinstance(value, dict):
                value = value.get(array_key)
            else:
                return None

            # Then access the index (supports negative indexing)
            if isinstance(value, (list, tuple)):
                try:
                    value = value[index]
                except IndexError:
                    return None
            else:
                return None

        # Handle numeric string as array index: items.0 or items.-1
        elif key.lstrip("-").isdigit():
            index = int(key)
            if isinstance(value, (list, tuple)):
                try:
                    value = value[index]
                except IndexError:
                    return None
            else:
                return None

        # Handle regular dictionary key access
        else:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None

    return value


def parse_date_value(raw_value: str, current_year: int = None) -> Optional[datetime]:
    """Parse various date formats into datetime object with timezone information.

    Supported formats:
    - 2025-01-01
    - 20250101
    - 2025/01/01
    - 2025.01.01
    - 2025-01, 2025.01, 202501 (month only, defaults to 1st day)
    - 08/01 10 (assumes current year and hour, minute as 00)
    - 2025년 1월 11일 (Korean date format)
    - 2025년 1월 (Korean year-month format, defaults to 1st day)
    - 01/11/2025 (US format MM/DD/YYYY)
    - 1/11/2025 (US format M/D/YYYY)
    """
    if not isinstance(raw_value, str):
        return None

    if current_year is None:
        current_year = datetime.now().year

    # Remove extra whitespace
    value = raw_value.strip()

    parsed_dt = None

    # Pattern 1: YYYY-MM-DD
    pattern1 = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", value)
    if pattern1:
        try:
            year, month, day = map(int, pattern1.groups())
            parsed_dt = datetime(year, month, day)
        except ValueError:
            return None

    # Pattern 2: YYYYMMDD
    if not parsed_dt:
        pattern2 = re.match(r"^(\d{4})(\d{2})(\d{2})$", value)
        if pattern2:
            try:
                year = int(pattern2.group(1))
                month = int(pattern2.group(2))
                day = int(pattern2.group(3))
                parsed_dt = datetime(year, month, day, tzinfo=TZ_ASIA_SEOUL)
            except ValueError:
                return None

    # Pattern 3: YYYY/MM/DD
    if not parsed_dt:
        pattern3 = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", value)
        if pattern3:
            try:
                year, month, day = map(int, pattern3.groups())
                parsed_dt = datetime(year, month, day, tzinfo=TZ_ASIA_SEOUL)
            except ValueError:
                return None

    # Pattern 4: YYYY.MM.DD (dot separator)
    if not parsed_dt:
        pattern4 = re.match(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})$", value)
        if pattern4:
            try:
                year, month, day = map(int, pattern4.groups())
                parsed_dt = datetime(year, month, day, tzinfo=TZ_ASIA_SEOUL)
            except ValueError:
                return None

    # Pattern 5: YYYY-MM (year-month with dash, defaults to 1st day)
    if not parsed_dt:
        pattern5 = re.match(r"^(\d{4})-(\d{1,2})$", value)
        if pattern5:
            try:
                year, month = map(int, pattern5.groups())
                parsed_dt = datetime(year, month, 1, tzinfo=TZ_ASIA_SEOUL)
            except ValueError:
                return None

    # Pattern 6: YYYY.MM (year-month with dot, defaults to 1st day)
    if not parsed_dt:
        pattern6 = re.match(r"^(\d{4})\.(\d{1,2})$", value)
        if pattern6:
            try:
                year, month = map(int, pattern6.groups())
                parsed_dt = datetime(year, month, 1, tzinfo=TZ_ASIA_SEOUL)
            except ValueError:
                return None

    # Pattern 7: YYYYMM (year-month without separator, defaults to 1st day)
    if not parsed_dt:
        pattern7 = re.match(r"^(\d{4})(\d{2})$", value)
        if pattern7:
            try:
                year = int(pattern7.group(1))
                month = int(pattern7.group(2))
                parsed_dt = datetime(year, month, 1, tzinfo=TZ_ASIA_SEOUL)
            except ValueError:
                return None

    # Pattern 8: MM/DD HH (e.g., "08/01 10" -> 2025-08-01 10:00:00)
    if not parsed_dt:
        pattern8 = re.match(r"^(\d{1,2})/(\d{1,2})\s+(\d{1,2})$", value)
        if pattern8:
            try:
                month, day, hour = map(int, pattern8.groups())
                parsed_dt = datetime(
                    current_year, month, day, hour, 0, 0, tzinfo=TZ_ASIA_SEOUL
                )
            except ValueError:
                return None

    # Pattern 9: Korean date format (e.g., "2025년 1월 11일")
    if not parsed_dt:
        pattern9 = re.match(r"^(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일$", value)
        if pattern9:
            try:
                year, month, day = map(int, pattern9.groups())
                parsed_dt = datetime(year, month, day, tzinfo=TZ_ASIA_SEOUL)
            except ValueError:
                return None

    # Pattern 10: Korean year-month format (e.g., "2025년 1월", defaults to 1st day)
    if not parsed_dt:
        pattern10 = re.match(r"^(\d{4})년\s*(\d{1,2})월$", value)
        if pattern10:
            try:
                year, month = map(int, pattern10.groups())
                parsed_dt = datetime(year, month, 1, tzinfo=TZ_ASIA_SEOUL)
            except ValueError:
                return None

    # Pattern 11: US date format MM/DD/YYYY (e.g., "01/11/2025" or "1/11/2025")
    if not parsed_dt:
        pattern11 = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", value)
        if pattern11:
            try:
                month, day, year = map(int, pattern11.groups())
                parsed_dt = datetime(year, month, day, tzinfo=TZ_ASIA_SEOUL)
            except ValueError:
                return None

    # Pattern 12: US date format with dots MM.DD.YYYY
    if not parsed_dt:
        pattern12 = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", value)
        if pattern12:
            try:
                month, day, year = map(int, pattern12.groups())
                parsed_dt = datetime(year, month, day, tzinfo=TZ_ASIA_SEOUL)
            except ValueError:
                return None

    # Pattern 13: YYYY-MM-DD HH:mm:ss.S
    if not parsed_dt:
        pattern13 = re.match(
            r"^(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{1,2}):(\d{1,2})\.(\d+)$",
            value,
        )
        if pattern13:
            try:
                year, month, day, hour, minute, second, microsecond = map(
                    int, pattern13.groups()
                )
                parsed_dt = datetime(
                    year,
                    month,
                    day,
                    hour,
                    minute,
                    second,
                    microsecond=0,
                    tzinfo=TZ_ASIA_SEOUL,
                )
            except ValueError:
                return None

    # Add timezone information using Home Assistant's default timezone
    if parsed_dt:
        return dt_util.as_local(parsed_dt)

    return None
