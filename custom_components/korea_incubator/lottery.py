"""Donghaeng Lottery client and Home Assistant entities.

The pension lottery uses the separate ``el.dhlottery.co.kr`` game service.  Its
requests are encrypted with a key derived from the game-session JSESSIONID.
"""

from __future__ import annotations

import base64
import asyncio
import datetime as dt
import json
import logging
import os
import re
from html import unescape
from dataclasses import dataclass
from urllib.parse import urlencode

import aiohttp
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import PBKDF2
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from yarl import URL

_LOGGER = logging.getLogger(__name__)
_WWW = "https://www.dhlottery.co.kr"
_EL = "https://el.dhlottery.co.kr"


class LotteryError(Exception):
    """A Donghaeng Lottery request could not be completed."""


class _RSAKey:
    def set_public(self, modulus: str, exponent: str) -> None:
        self.n = int(modulus, 16)
        self.e = int(exponent, 16)

    def encrypt(self, value: str) -> str:
        size = (self.n.bit_length() + 7) // 8
        raw = value.encode()
        if len(raw) + 11 > size:
            raise LotteryError("로그인 정보가 너무 깁니다.")
        padding = bytearray()
        while len(padding) < size - len(raw) - 3:
            byte = os.urandom(1)
            if byte != b"\0":
                padding.extend(byte)
        padded = b"\0\2" + bytes(padding) + b"\0" + raw
        return f"{pow(int.from_bytes(padded, 'big'), self.e, self.n):0{size * 2}x}"


@dataclass(frozen=True)
class Balance:
    deposit: int
    available: int


class LotteryClient:
    """Authenticated Donghaeng Lottery client; one instance belongs to one entry."""

    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self._password = password
        self.logged_in = False
        self._purchase_lock = asyncio.Lock()
        self._operation_lock = asyncio.Lock()
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
                "Connection": "keep-alive",
                "Cache-Control": "no-cache",
                "Origin": _WWW,
                "Referer": f"{_WWW}/login",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            },
        )

    async def close(self) -> None:
        await self.session.close()

    async def login(self) -> None:
        self.logged_in = False
        try:
            async with self.session.get(
                f"{_WWW}/login/selectRsaModulus.do"
            ) as response:
                if response.status != 200:
                    raise LotteryError("동행복권 RSA 공개키 요청이 거부되었습니다.")
                key_data = (await response.json(content_type=None)).get("data", {})
            key = _RSAKey()
            key.set_public(key_data["rsaModulus"], key_data["publicExponent"])
            async with self.session.post(
                f"{_WWW}/login/securityLoginCheck.do",
                data={
                    "userId": key.encrypt(self.username),
                    "userPswdEncn": key.encrypt(self._password),
                    "inpUserId": self.username,
                },
            ) as response:
                if response.status != 200:
                    raise LotteryError("로그인 요청이 거부되었습니다.")
                await response.read()
            self.logged_in = True
        except LotteryError:
            raise
        except Exception as err:
            raise LotteryError("동행복권 로그인에 실패했습니다.") from err

    async def _get_json(self, path: str, params: dict | None = None) -> dict:
        async with self.session.get(f"{_WWW}/{path}", params=params) as response:
            if response.status != 200:
                raise LotteryError("동행복권 서버 요청에 실패했습니다.")
            try:
                data = await response.json(content_type=None)
            except Exception as err:
                raise LotteryError(
                    "동행복권 서버가 JSON 응답을 반환하지 않았습니다."
                ) from err
        if not isinstance(data, dict):
            raise LotteryError("동행복권 서버 응답 형식이 올바르지 않습니다.")
        result = data.get("data", data)
        # The ledger returns {"data": null} for an account with no matching
        # history.  Treat that as an empty result rather than a setup failure.
        if result is None:
            return {}
        if not isinstance(result, dict):
            raise LotteryError("동행복권 서버 응답 형식이 올바르지 않습니다.")
        return result

    async def _get_json_with_login(
        self, path: str, params: dict | None = None, retry: int = 1
    ) -> dict:
        """Read an authenticated endpoint and refresh a stale session once."""
        try:
            return await self._get_json(path, params)
        except LotteryError:
            if retry <= 0:
                raise
            _LOGGER.info("Donghaeng Lottery session refresh required for %s", path)
            await self.login()
            return await self._get_json_with_login(path, params, retry - 1)

    async def balance(self, retry: int = 1) -> Balance:
        data = await self._get_json_with_login(
            "mypage/selectUserMndp.do",
            {"_": int(dt.datetime.now().timestamp() * 1000)},
        )
        value = data.get("userMndp", data)
        if not isinstance(value, dict) or "totalAmt" not in value:
            if retry > 0:
                _LOGGER.info("Donghaeng Lottery balance response requires re-login")
                await self.login()
                return await self.balance(retry - 1)
            raise LotteryError("동행복권 예치금 조회 인증이 거부되었습니다.")
        try:
            return Balance(
                int(value.get("totalAmt", 0)), int(value.get("crntEntrsAmt", 0))
            )
        except (TypeError, ValueError) as err:
            raise LotteryError("예치금 정보를 해석하지 못했습니다.") from err

    async def pension_winning_numbers(self) -> dict:
        """Return the latest Pension Lottery 720+ winning-number record."""
        data = await self._get_json("pt720/selectPstPt720Info.do")
        rows = data.get("result", [])
        if not rows:
            raise LotteryError("연금복권 당첨번호를 찾지 못했습니다.")
        row = max(rows, key=lambda item: int(item.get("psltEpsd", 0)))
        return {
            "round": int(row["psltEpsd"]),
            "group": str(row.get("wnBndNo", "")),
            "number": str(row.get("wnRnkVl", "")),
            "bonus_number": str(row.get("bnsRnkVl", "")),
            "draw_date": str(row.get("psltRflYmd", "")),
        }

    async def pension_purchase_history(
        self, days: int = 365, wins_only: bool = False
    ) -> list[dict]:
        """Read Pension Lottery purchases from the authenticated ledger API."""
        now = dt.datetime.now()
        params = {
            "srchStrDt": (now - dt.timedelta(days=days)).strftime("%Y%m%d"),
            "srchEndDt": now.strftime("%Y%m%d"),
            "ltGdsCd": "LP72",
            "pageNum": 1,
            "recordCountPerPage": 1000,
            "_": int(now.timestamp() * 1000),
        }
        if wins_only:
            params["winResult"] = "T"
        data = await self._get_json_with_login(
            "mypage/selectMyLotteryledger.do", params
        )
        records = data.get("list") or []
        if not isinstance(records, list):
            raise LotteryError("연금복권 구매내역 응답을 해석하지 못했습니다.")
        return [
            {
                "round": item.get("ltEpsd") or item.get("ltEpsdView"),
                "purchased_at": item.get("eltOrdrDt"),
                "result": item.get("ltWnResult"),
                "prize": int(item.get("ltWnAmt") or 0),
                "quantity": int(item.get("prchsQty") or 0),
                "order_no": item.get("ntslOrdrNo"),
                "barcode": item.get("gmInfo"),
            }
            for item in records
        ]

    async def pension_winning_history(self, days: int = 365) -> list[dict]:
        """Return only winning Pension Lottery ledger records."""
        return await self.pension_purchase_history(days=days, wins_only=True)

    async def pension_high_prize_history(
        self, days: int = 365, minimum_prize: int = 5_000_000
    ) -> list[dict]:
        """Return wins at or above the configurable high-prize threshold."""
        return [
            item
            for item in await self.pension_winning_history(days=days)
            if item["prize"] >= minimum_prize
        ]

    async def pension_unsettled_games(self) -> list[dict]:
        """Return one record per un-drawn Pension Lottery game number."""
        games: list[dict] = []
        for purchase in await self.pension_purchase_history(days=30):
            if str(purchase["result"]).strip() != "미추첨" or not purchase["order_no"]:
                continue
            try:
                data = await self._get_json_with_login(
                    "mypage/lottery720select.do",
                    {
                        "ntslOrdrNo": purchase["order_no"],
                        "_": int(dt.datetime.now().timestamp() * 1000),
                    },
                )
            except LotteryError:
                _LOGGER.warning("연금복권 구매번호 상세 조회에 실패했습니다.")
                data = {}
            details = data.get("list") or []
            if not isinstance(details, list):
                _LOGGER.warning("연금복권 구매번호 상세 응답 형식이 올바르지 않습니다.")
                details = []
            if not any(
                self._pension_numbers(detail)
                for detail in details
                if isinstance(detail, dict)
            ):
                details = [{"ltGmInfoCn": purchase["barcode"]}]
            for detail_index, detail in enumerate(details, start=1):
                if not isinstance(detail, dict):
                    continue
                # One detail row can represent a five-set purchase.  Preserve
                # every 1~5 group rather than only the first regex match.
                for game_index, (group, number) in enumerate(
                    self._pension_numbers(detail), start=1
                ):
                    games.append(
                        {
                            "game_id": (
                                f"pension_{purchase['order_no']}_"
                                f"{detail_index}_{game_index}"
                            ),
                            "order_no": purchase["order_no"],
                            "round": purchase["round"],
                            "purchased_at": purchase["purchased_at"],
                            "group": group,
                            "number": number,
                        }
                    )
        return games

    @staticmethod
    def _pension_numbers(detail: dict) -> list[tuple[str, str]]:
        """Decode labelled or compact seven-digit ticket numbers.

        HTML digit spans are presentation, not separators between digits.
        Never convert a lottery number to an integer: leading zeros matter.
        """
        raw = unescape(str(detail.get("ltGmInfoCn") or ""))
        raw = re.sub(r"<(?:br\b[^>]*|/p|/div)>", ";", raw, flags=re.I)
        raw = re.sub(r"<[^>]*>", "", raw)
        numbers = []
        for match in re.finditer(
            r"(?<!\d)([1-5])(?:\s*조\s*[:：-]?\s*|\s*[-:]\s*|(?=\d{6}(?!\d)))"
            r"((?:\d\s*){5}\d)(?!\d)",
            raw,
        ):
            numbers.append((match.group(1), re.sub(r"\s", "", match.group(2))))
        return numbers

    async def lotto_645_winning_numbers(self) -> dict:
        """Return the latest Lotto 6/45 winning numbers."""
        data = await self._get_json("lt645/selectPstLt645Info.do")
        rows = data.get("list", [])
        if not rows:
            raise LotteryError("로또 6/45 당첨번호를 찾지 못했습니다.")
        row = max(rows, key=lambda item: int(item.get("ltEpsd", 0)))
        numbers = [row.get(f"tm{index}WnNo") for index in range(1, 7)]
        return {
            "round": int(row["ltEpsd"]),
            "numbers": [int(number) for number in numbers],
            "bonus_number": int(row["bnsWnNo"]),
            "draw_date": str(row.get("ltRflYmd", "")),
        }

    async def lotto_645_purchase_history(
        self, days: int = 365, wins_only: bool = False
    ) -> list[dict]:
        """Read Lotto 6/45 purchases from the authenticated ledger API."""
        now = dt.datetime.now()
        params = {
            "srchStrDt": (now - dt.timedelta(days=days)).strftime("%Y%m%d"),
            "srchEndDt": now.strftime("%Y%m%d"),
            "ltGdsCd": "LO40",
            "pageNum": 1,
            "recordCountPerPage": 1000,
            "_": int(now.timestamp() * 1000),
        }
        if wins_only:
            params["winResult"] = "T"
        data = await self._get_json_with_login(
            "mypage/selectMyLotteryledger.do", params
        )
        records = data.get("list") or []
        if not isinstance(records, list):
            raise LotteryError("로또 6/45 구매내역 응답을 해석하지 못했습니다.")
        return [
            {
                "round": item.get("ltEpsd") or item.get("ltEpsdView"),
                "purchased_at": item.get("eltOrdrDt"),
                "result": item.get("ltWnResult"),
                "prize": int(item.get("ltWnAmt") or 0),
                "quantity": int(item.get("prchsQty") or 0),
                "order_no": item.get("ntslOrdrNo"),
                "barcode": item.get("gmInfo"),
            }
            for item in records
        ]

    async def lotto_645_winning_history(self, days: int = 365) -> list[dict]:
        return await self.lotto_645_purchase_history(days=days, wins_only=True)

    async def lotto_645_high_prize_history(
        self, days: int = 365, minimum_prize: int = 5_000_000
    ) -> list[dict]:
        return [
            item
            for item in await self.lotto_645_winning_history(days=days)
            if item["prize"] >= minimum_prize
        ]

    async def lotto_645_unsettled_games(self) -> list[dict]:
        """Return one record per un-drawn Lotto 6/45 game from ticket details."""
        games: list[dict] = []
        for purchase in await self.lotto_645_purchase_history(days=30):
            if (
                purchase["result"] != "미추첨"
                or not purchase["order_no"]
                or not purchase["barcode"]
            ):
                continue
            try:
                data = await self._get_json_with_login(
                    "mypage/lotto645TicketDetail.do",
                    {
                        "ntslOrdrNo": purchase["order_no"],
                        "barcd": purchase["barcode"],
                        "_": int(dt.datetime.now().timestamp() * 1000),
                    },
                )
            except LotteryError:
                _LOGGER.warning("로또 6/45 구매번호 상세 조회에 실패했습니다.")
                continue
            ticket = data.get("ticket") or {}
            if not isinstance(ticket, dict):
                _LOGGER.warning("로또 6/45 영수증 상세 응답 형식이 올바르지 않습니다.")
                continue
            details = ticket.get("game_dtl") or []
            if not isinstance(details, list):
                _LOGGER.warning("로또 6/45 게임 상세 응답 형식이 올바르지 않습니다.")
                continue
            for index, detail in enumerate(details, start=1):
                if not isinstance(detail, dict):
                    continue
                numbers = detail.get("num") or []
                if len(numbers) != 6:
                    continue
                try:
                    game_numbers = [int(number) for number in numbers]
                except (TypeError, ValueError):
                    continue
                games.append(
                    {
                        "game_id": f"lotto_{purchase['order_no']}_{index}",
                        "order_no": purchase["order_no"],
                        "round": purchase["round"],
                        "purchased_at": purchase["purchased_at"],
                        "slot": detail.get("idx", index),
                        "selection": detail.get("type"),
                        "numbers": game_numbers,
                    }
                )
        return games

    def _el_session_id(self) -> str:
        cookies = self.session.cookie_jar.filter_cookies(_EL)
        # Current browser traffic derives the key from DHJSESSIONID. An older
        # JSESSIONID may coexist after a refresh and must not override it.
        value = cookies.get("DHJSESSIONID") or cookies.get("JSESSIONID")
        if not value:
            raise LotteryError("연금복권 게임 세션을 만들지 못했습니다.")
        return value.value

    def _copy_game_session_cookie(self) -> None:
        """Make authenticated www session cookies available to the game host.

        Login can create host-only cookies for ``www.dhlottery.co.kr``. The
        browser navigation to TotalGame.jsp forwards them to the game host; an
        aiohttp cookie jar does not promote host-only cookies across hosts.
        """
        www_cookies = self.session.cookie_jar.filter_cookies(_WWW)
        # Always replace the game-host copy: a fresh login changes the www
        # cookie, while an old el-host cookie can otherwise keep the game page
        # on an expired anonymous session.
        for name in ("DHJSESSIONID", "JSESSIONID"):
            if cookie := www_cookies.get(name):
                self.session.cookie_jar.update_cookies(
                    {name: cookie.value}, response_url=URL(_EL)
                )

    async def _async_open_pension_game(self) -> str:
        """Establish the game SSO session and return its authenticated HTML."""
        self._copy_game_session_cookie()
        async with self.session.get(
            f"{_EL}/game/TotalGame.jsp?LottoId=LP72",
            allow_redirects=True,
            headers={"Referer": f"{_WWW}/"},
        ) as response:
            if response.status != 200:
                raise LotteryError("연금복권 게임 인증 페이지를 열지 못했습니다.")
            await response.read()
        async with self.session.get(
            f"{_EL}/game/pension720/game.jsp",
            headers={"Referer": f"{_EL}/game/TotalGame.jsp?LottoId=LP72"},
        ) as response:
            if response.status != 200:
                raise LotteryError("연금복권 게임 페이지를 열지 못했습니다.")
            return await response.text()

    @staticmethod
    def _extract_game_user_id(game_page: str) -> str:
        """Read USER_ID from the hidden field without relying on attr order."""
        field = re.search(
            r"<input\b(?=[^>]*\bname=[\"']USER_ID[\"'])(?=[^>]*\bvalue=[\"'][^\"']+[\"'])[^>]*>",
            game_page,
            re.IGNORECASE,
        )
        if not field:
            raise LotteryError("연금복권 사용자 세션을 확인하지 못했습니다.")
        value = re.search(r"\bvalue=[\"']([^\"']+)[\"']", field.group(0), re.IGNORECASE)
        if not value:
            raise LotteryError("연금복권 사용자 세션을 확인하지 못했습니다.")
        return value.group(1)

    @staticmethod
    def _encrypt(plain: str, jsession_id: str) -> str:
        salt, iv = os.urandom(32), os.urandom(16)
        key = PBKDF2(jsession_id[:32], salt, 16, count=1000, hmac_hash_module=SHA256)
        pad = 16 - len(plain.encode()) % 16
        encrypted = AES.new(key, AES.MODE_CBC, iv).encrypt(
            plain.encode() + bytes([pad]) * pad
        )
        return salt.hex() + iv.hex() + base64.b64encode(encrypted).decode()

    @staticmethod
    def _decrypt(ciphertext: str, jsession_id: str) -> str:
        salt, iv = bytes.fromhex(ciphertext[:64]), bytes.fromhex(ciphertext[64:96])
        key = PBKDF2(jsession_id[:32], salt, 16, count=1000, hmac_hash_module=SHA256)
        raw = AES.new(key, AES.MODE_CBC, iv).decrypt(base64.b64decode(ciphertext[96:]))
        return raw[: -raw[-1]].decode()

    async def _pension_step(
        self,
        path: str,
        fields: list[tuple[str, str]],
        *,
        allow_non_json_response: bool = False,
    ) -> dict | None:
        """Call an encrypted Pension Lottery endpoint.

        ``connPro.do`` is the final payment endpoint and can navigate to an
        HTML receipt instead of returning the encrypted AJAX JSON used by the
        preliminary endpoints.  Its request must never be retried.
        """
        session_id = self._el_session_id()
        plain = urlencode(fields)
        # The browser's communiEncrypt transport escapes '+' twice. Keep this
        # asymmetric encoding (confirmed by the captured browser requests).
        q = (
            self._encrypt(plain, session_id)
            .replace("+", "%252B")
            .replace("/", "%2F")
            .replace("=", "%3D")
        )
        headers = {
            "Accept": "*/*",
            "Origin": _EL,
            "Referer": f"{_EL}/game/pension720/game.jsp",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        async with self.session.post(
            f"{_EL}{path}", data=f"q={q}", headers=headers
        ) as response:
            body = await response.text()
            status = response.status
            content_type = response.content_type
        if status != 200:
            raise LotteryError(
                f"연금복권 서버 응답 오류({path}, HTTP {status}) — "
                "구매 결과가 불명확합니다. 재시도하지 마세요."
            )
        try:
            envelope = json.loads(body)
        except json.JSONDecodeError as err:
            if allow_non_json_response:
                _LOGGER.info(
                    "Donghaeng Lottery payment returned a non-JSON receipt "
                    "(content type: %s)",
                    content_type,
                )
                return None
            raise LotteryError(f"연금복권 서버 응답 오류({path})") from err
        if not isinstance(envelope, dict):
            raise LotteryError(f"연금복권 서버 응답 형식이 올바르지 않습니다. ({path})")
        try:
            decrypted = (
                self._decrypt(envelope["q"], session_id) if envelope.get("q") else body
            )
            result = json.loads(decrypted)
        except (KeyError, ValueError, json.JSONDecodeError) as err:
            raise LotteryError(
                f"연금복권 서버 응답을 해석하지 못했습니다. ({path})"
            ) from err
        if not isinstance(result, dict):
            raise LotteryError(f"연금복권 서버 응답 형식이 올바르지 않습니다. ({path})")
        return result

    async def _pension_ticket_exists(
        self,
        round_no: int,
        group: str,
        number: str,
        *,
        excluded_orders: set[str] | None = None,
    ) -> bool:
        """Confirm a final-payment result from the read-only ticket ledger."""
        try:
            purchases = await self.pension_purchase_history(days=7)
            for purchase in purchases:
                if (
                    str(purchase["round"]) != str(round_no)
                    or not purchase["order_no"]
                    or str(purchase["order_no"]) in (excluded_orders or set())
                ):
                    continue
                if (group, number) in self._pension_numbers(
                    {"ltGmInfoCn": purchase.get("barcode")}
                ):
                    return True
                data = await self._get_json_with_login(
                    "mypage/lottery720select.do",
                    {
                        "ntslOrdrNo": purchase["order_no"],
                        "_": int(dt.datetime.now().timestamp() * 1000),
                    },
                )
                for detail in data.get("list") or []:
                    if not isinstance(detail, dict):
                        continue
                    if (group, number) in self._pension_numbers(detail):
                        return True
        except LotteryError as err:
            _LOGGER.warning("연금복권 결제 결과 구매내역 확인에 실패했습니다: %s", err)
        return False

    async def _pension_round_remain_time(self) -> dict:
        """Validate the game server's current sales window before ordering."""
        fields = {
            "ROUND": "",
            "SEL_NO": "",
            "BUY_CNT": "",
            "AUTO_SEL_SET": "",
            "SEL_CLASS": "",
            "BUY_TYPE": "A",
            "ACCS_TYPE": "01",
        }
        headers = {
            "Origin": _EL,
            "Referer": f"{_EL}/game/pension720/game.jsp",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        async with self.session.post(
            f"{_EL}/roundRemainTime.do", data=urlencode(fields), headers=headers
        ) as response:
            body = await response.text()
        if response.status != 200 or not body.lstrip().startswith("{"):
            raise LotteryError("연금복권 판매 시간 정보를 가져오지 못했습니다.")
        try:
            data = json.loads(body)
        except json.JSONDecodeError as err:
            raise LotteryError(
                "연금복권 판매 시간 응답을 해석하지 못했습니다."
            ) from err
        if data.get("resultCode") and str(data["resultCode"]) != "100":
            raise LotteryError(
                f"현재 연금복권 판매 시간이 아닙니다. ({data.get('resultMsg', '')})"
            )
        is_sale = str(data.get("IS_SALE_FLAG", "true")).strip().lower()
        if (
            is_sale not in {"true", "y", "1"}
            or str(data.get("NTSL_DDLN_YN", "N")).upper() == "Y"
        ):
            raise LotteryError("현재 연금복권 판매 시간이 아닙니다.")
        if not str(data.get("ROUND", "")).isdigit():
            raise LotteryError("연금복권 판매 회차 정보를 찾지 못했습니다.")
        return data

    async def _check_pension_deposit(self, fields: list[tuple[str, str]]) -> int:
        """Read the game-host deposit before creating an order."""
        result = await self._pension_step("/checkDeposit.do", fields)
        if str(result.get("resultCode", "100")) != "100":
            raise LotteryError(
                f"연금복권 예치금 확인 실패: {result.get('resultMsg', '')}"
            )
        try:
            return int(result["deposit"])
        except (KeyError, TypeError, ValueError) as err:
            raise LotteryError("연금복권 게임 예치금을 확인하지 못했습니다.") from err

    @staticmethod
    def _pension_payment_form(game_page: str) -> dict[str, str]:
        """Read successful input controls from the actual browser payment form."""
        form = BeautifulSoup(game_page, "html.parser").find("form", id="frm")
        if form is None:
            raise LotteryError("연금복권 결제 양식을 찾지 못했습니다.")
        fields = {}
        for field in form.find_all("input", attrs={"name": True}):
            if field.find_parent("form") is not form or field.has_attr("disabled"):
                continue
            if field.get("type", "text").lower() in {
                "submit",
                "button",
                "reset",
                "file",
                "image",
            }:
                continue
            if field.get("type", "text").lower() in {
                "radio",
                "checkbox",
            } and not field.has_attr("checked"):
                continue
            fields[field["name"]] = field.get(
                "value", "on" if field.get("type") in {"radio", "checkbox"} else ""
            )
        if not fields.get("USER_ID"):
            raise LotteryError("연금복권 사용자 세션을 확인하지 못했습니다.")
        return fields

    async def buy_pension_auto(self, games: int) -> list[dict[str, str | int]]:
        """Reject overlapping purchases and keep refreshes out of game SSO."""
        if self._purchase_lock.locked():
            raise LotteryError(
                "복권 구매 요청이 이미 진행 중입니다. 구매내역을 확인하세요."
            )
        async with self._purchase_lock, self._operation_lock:
            return await self._buy_pension_auto(games)

    async def _buy_pension_auto(self, games: int) -> list[dict[str, str | int]]:
        """Follow the game page's automatic selection and single-order flow.

        Automatic numbers are already verified by makeAutoNo. The browser
        skips checkVerifyNo for them. Five games use one all-group (SA) number.
        Never retry an order or payment after a failure.
        """
        if (
            not isinstance(games, int)
            or isinstance(games, bool)
            or games not in range(1, 6)
        ):
            raise LotteryError("연금복권 자동 구매 수는 1~5개여야 합니다.")
        balance = await self.balance()
        if balance.available < games * 1000:
            raise LotteryError(
                f"구매 가능 예치금이 부족합니다. (현재 {balance.available:,}원)"
            )

        for attempt in range(2):
            try:
                payment = self._pension_payment_form(
                    await self._async_open_pension_game()
                )
                break
            except LotteryError:
                if attempt:
                    raise
                await self.login()
        sales = await self._pension_round_remain_time()
        round_no = int(sales["ROUND"])
        set_type = "SA" if games == 5 else "S"
        common = {
            "ROUND": str(round_no),
            "SEL_NO": "",
            "BUY_CNT": "",
            "AUTO_SEL_SET": set_type,
            "SEL_CLASS": "",
            "BUY_TYPE": "A",
            "ACCS_TYPE": "01",
        }
        deposit = await self._check_pension_deposit(list(common.items()))
        if deposit < games * 1000:
            raise LotteryError(f"구매 가능 예치금이 부족합니다. (현재 {deposit:,}원)")
        existing_orders = {
            str(item["order_no"])
            for item in await self.pension_purchase_history(days=7)
            if item["order_no"]
        }
        tickets = []
        for index in range(1 if games == 5 else games):
            common.update(
                SEL_NO="", BUY_CNT="", SEL_CLASS="" if games == 5 else str(index + 1)
            )
            assigned = await self._pension_step("/makeAutoNo.do", list(common.items()))
            if str(assigned.get("resultCode")) != "100" or assigned.get("selYN") != "Y":
                raise LotteryError(
                    f"연금복권 번호 자동 선택 실패: {assigned.get('resultMsg', '')}"
                )
            number = str(assigned.get("selLotNo") or "").split(",")[0].strip()
            group = (
                str(assigned.get("selClsNo") or common["SEL_CLASS"])
                .split(",")[0]
                .strip()
            )
            if (
                not re.fullmatch(r"[0-9]{6}", number)
                or str(assigned.get("round")) != str(round_no)
                or assigned.get("autoSelSet") != set_type
                or (set_type == "S" and group not in {"1", "2", "3", "4", "5"})
            ):
                raise LotteryError(
                    "자동 선택된 연금복권 번호 형식이 올바르지 않습니다."
                )
            for selected_group in range(1, 6) if games == 5 else [int(group)]:
                tickets.append(
                    {"round": round_no, "group": selected_group, "number": number}
                )
            # frmauto retains the last selection when the browser creates the
            # order. The payment form carries the complete selected ticket list.
            common.update(
                SEL_NO=number,
                BUY_CNT="5" if games == 5 else "1",
                SEL_CLASS="" if games == 5 else group,
            )

        order = await self._pension_step("/makeOrderNo.do", list(common.items()))
        if (
            str(order.get("resultCode")) != "100"
            or not order.get("orderNo")
            or not order.get("orderDate")
        ):
            raise LotteryError(f"연금복권 주문 생성 실패: {order.get('resultMsg', '')}")
        # addBuyData resets the number-entry controls before doOrderRequest.
        # waiting(true) sets WORKING_FLAG before the form is serialized.
        payment.update(
            {
                "ROUND": str(round_no),
                "BUY_KIND": "01",
                "BUY_NO": ",".join(
                    f"{item['group']}{item['number']}" for item in tickets
                ),
                "BUY_CNT": str(len(tickets)),
                "BUY_SET_TYPE": ",".join([set_type] * len(tickets)),
                "BUY_TYPE": ",".join(["A"] * len(tickets)),
                "ACCS_TYPE": "01",
                "orderNo": str(order["orderNo"]),
                "orderDate": str(order["orderDate"]),
                "WORKING_FLAG": "true",
                "auto_process": "N",
                "set_type": "SA",
                "classnum": "",
                "selnum": "",
                "buytype": "M",
                "verifyYN": "N",
                "curdeposit": str(deposit),
                "curpay": str(len(tickets) * 1000),
            }
        )
        payment.update({f"num{i}": "" for i in range(1, 7)})
        payment_error = None
        try:
            result = await self._pension_step(
                "/connPro.do", list(payment.items()), allow_non_json_response=True
            )
        except (LotteryError, aiohttp.ClientError, TimeoutError) as err:
            result = None
            payment_error = err
        # 110 is partial completion; 120 means no ticket was sold. Do not
        # mistake either for an indeterminate failure or automatically resubmit.
        if result is not None and str(result.get("resultCode")) in {
            "100",
            "110",
            "120",
        }:
            sold = set(self._pension_numbers({"ltGmInfoCn": result.get("saleTicket")}))
            confirmed = [
                item for item in tickets if (str(item["group"]), item["number"]) in sold
            ]
            try:
                sale_count = int(result["saleCnt"])
            except (KeyError, TypeError, ValueError):
                sale_count = -1
            if confirmed and sale_count == len(confirmed) == len(sold):
                return confirmed
            if sale_count == 0 and not sold:
                raise LotteryError(
                    "연금복권 구매 가능한 티켓이 없습니다. 구매내역을 확인하세요."
                )
        else:
            confirmed = []
        # A receipt or transport error may follow payment. Match only new
        # ledger orders, so a previous purchase of the same number is no proof.
        confirmed = [
            item
            for item in tickets
            if await self._pension_ticket_exists(
                round_no,
                str(item["group"]),
                item["number"],
                excluded_orders=existing_orders,
            )
        ]
        if confirmed:
            return confirmed
        message = result.get("resultMsg", "") if result else "결제 응답 확인 불가"
        code = result.get("resultCode", "") if result else ""
        raise LotteryError(
            "연금복권 구매 결과를 확인하지 못했습니다. "
            "재시도하지 말고 구매내역을 확인하세요. "
            f"({code}: {message})"
        ) from payment_error

    async def buy_lotto_645_auto(self, games: int) -> dict:
        """Keep Lotto purchases out of concurrent pension SSO and refreshes."""
        if self._purchase_lock.locked():
            raise LotteryError(
                "복권 구매 요청이 이미 진행 중입니다. 구매내역을 확인하세요."
            )
        async with self._purchase_lock, self._operation_lock:
            return await self._buy_lotto_645_auto(games)

    async def _buy_lotto_645_auto(self, games: int) -> dict:
        """Buy server-selected Lotto 6/45 games (the original component's core flow)."""
        if games not in range(1, 6):
            raise LotteryError("로또 6/45 자동 구매 수는 1~5개여야 합니다.")
        now = dt.datetime.now()
        if now.hour < 6 or (now.weekday() == 5 and now.hour >= 20):
            raise LotteryError("현재는 로또 6/45 판매 시간이 아닙니다.")
        balance = await self.balance()
        if balance.available < games * 1000:
            raise LotteryError(
                f"구매 가능 예치금이 부족합니다. (현재 {balance.available:,}원)"
            )
        history = await self._get_json(
            "mypage/selectMyLotteryledger.do",
            {
                "srchStrDt": (now - dt.timedelta(days=7)).strftime("%Y%m%d"),
                "srchEndDt": now.strftime("%Y%m%d"),
                "ltGdsCd": "LO40",
                "pageNum": 1,
                "recordCountPerPage": 1000,
                "_": int(now.timestamp() * 1000),
            },
        )
        bought = sum(
            int(item.get("prchsQty", 0))
            for item in history.get("list", [])
            if item.get("ltWnResult") == "미추첨"
        )
        games = min(games, max(0, 5 - bought))
        if games == 0:
            raise LotteryError(
                "이번 회차의 온라인 로또 6/45 구매 한도를 모두 사용했습니다."
            )
        info = await self._get_json(
            "lt645/selectPstLt645Info.do", {"_": int(now.timestamp() * 1000)}
        )
        rows = info.get("list", [])
        if not rows:
            raise LotteryError("로또 6/45 회차 정보를 찾지 못했습니다.")
        live_round = int(rows[0]["ltEpsd"]) + 1
        async with self.session.post(
            "https://ol.dhlottery.co.kr/olotto/game/egovUserReadySocket.json"
        ) as response:
            ready = await response.json(content_type=None)
        direct = ready.get("ready_ip")
        if not direct:
            raise LotteryError("로또 구매 서버 연결 정보를 가져오지 못했습니다.")
        selections = [
            {"genType": "0", "arrGameChoiceNum": None, "alpabet": "ABCDE"[i]}
            for i in range(games)
        ]
        async with self.session.post(
            "https://ol.dhlottery.co.kr/olotto/game/execBuy.do",
            data={
                "round": str(live_round),
                "direct": direct,
                "nBuyAmount": str(games * 1000),
                "param": json.dumps(selections),
                "gameCnt": games,
                "saleMdaDcd": "10",
            },
        ) as response:
            body = await response.json(content_type=None)
        result = body.get("result", {})
        if result.get("resultCode") != "100":
            raise LotteryError(
                f"로또 6/45 구매 실패: {result.get('resultMsg', '알 수 없는 오류')}"
            )
        return result


class LotteryCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass, client: LotteryClient) -> None:
        # Purchases can also happen on the official site, so keep ticket
        # entities current without requiring Home Assistant to be restarted.
        super().__init__(
            hass,
            _LOGGER,
            name="Donghaeng Lottery",
            update_interval=dt.timedelta(minutes=15),
        )
        self.client = client

    async def _async_update_data(self) -> dict:
        async with self.client._operation_lock:
            return await self._async_read_data()

    async def _async_read_data(self) -> dict:
        try:
            balance = await self.client.balance()
            (
                pension_winning,
                pension_purchases,
                pension_wins,
                pension_high_prizes,
                lotto_winning,
                lotto_purchases,
                lotto_wins,
                lotto_high_prizes,
                pension_unsettled_games,
                lotto_unsettled_games,
            ) = await asyncio.gather(
                self.client.pension_winning_numbers(),
                self.client.pension_purchase_history(days=30),
                self.client.pension_winning_history(),
                self.client.pension_high_prize_history(),
                self.client.lotto_645_winning_numbers(),
                self.client.lotto_645_purchase_history(days=30),
                self.client.lotto_645_winning_history(),
                self.client.lotto_645_high_prize_history(),
                self.client.pension_unsettled_games(),
                self.client.lotto_645_unsettled_games(),
            )
            return {
                "balance": balance,
                "winning": pension_winning,
                "purchases": pension_purchases,
                "wins": pension_wins,
                "high_prizes": pension_high_prizes,
                "lotto_winning": lotto_winning,
                "lotto_purchases": lotto_purchases,
                "lotto_wins": lotto_wins,
                "lotto_high_prizes": lotto_high_prizes,
                "pension_unsettled_games": pension_unsettled_games,
                "lotto_unsettled_games": lotto_unsettled_games,
                "updated": dt.datetime.now().isoformat(timespec="seconds"),
            }
        except LotteryError as err:
            raise UpdateFailed(str(err)) from err


def lottery_device_info(client: LotteryClient) -> DeviceInfo:
    """Return the shared Donghaeng Lottery device descriptor."""
    return DeviceInfo(
        identifiers={("korea_incubator", f"donghaeng_lottery_{client.username}")},
        name="동행복권",
        manufacturer="동행복권",
        configuration_url=_WWW,
    )


class LotteryBalanceSensor(CoordinatorEntity[LotteryCoordinator], SensorEntity):
    _attr_name = "동행복권 예치금"
    _attr_icon = "mdi:cash"
    _attr_native_unit_of_measurement = "KRW"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: LotteryCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"donghaeng_lottery_{coordinator.client.username}_balance"
        )
        self._attr_device_info = lottery_device_info(coordinator.client)

    @property
    def native_value(self):
        return self.coordinator.data["balance"].deposit

    @property
    def extra_state_attributes(self):
        return {
            "구매 가능 금액": self.coordinator.data["balance"].available,
            "업데이트": self.coordinator.data["updated"],
        }


class LotteryWinningNumbersSensor(CoordinatorEntity[LotteryCoordinator], SensorEntity):
    """Latest Pension Lottery 720+ winning number and draw details."""

    _attr_name = "연금복권 720+ 최근 당첨번호"
    _attr_icon = "mdi:star-circle-outline"

    def __init__(self, coordinator: LotteryCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"donghaeng_lottery_{coordinator.client.username}_pension_winning"
        )
        self._attr_device_info = lottery_device_info(coordinator.client)

    @property
    def native_value(self):
        item = self.coordinator.data["winning"]
        return f"{item['group']}조 {item['number']}"

    @property
    def extra_state_attributes(self):
        item = self.coordinator.data["winning"]
        return {
            "회차": item["round"],
            "추첨일": item["draw_date"],
            "보너스 번호": item["bonus_number"],
        }


class LotteryHistorySensor(CoordinatorEntity[LotteryCoordinator], SensorEntity):
    """Expose Pension Lottery ledger records as sensor attributes."""

    def __init__(
        self, coordinator: LotteryCoordinator, key: str, name: str, icon: str
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"donghaeng_lottery_{coordinator.client.username}_{key}"
        self._attr_device_info = lottery_device_info(coordinator.client)

    @property
    def native_value(self):
        return len(self.coordinator.data[self._key])

    @property
    def extra_state_attributes(self):
        records = self.coordinator.data[self._key]
        return {"records": records[:50], "업데이트": self.coordinator.data["updated"]}


class Lotto645WinningNumbersSensor(CoordinatorEntity[LotteryCoordinator], SensorEntity):
    """Latest Lotto 6/45 winning numbers and draw details."""

    _attr_name = "로또 6/45 최근 당첨번호"
    _attr_icon = "mdi:star-circle-outline"

    def __init__(self, coordinator: LotteryCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"donghaeng_lottery_{coordinator.client.username}_lotto_645_winning"
        )
        self._attr_device_info = lottery_device_info(coordinator.client)

    @property
    def native_value(self):
        item = self.coordinator.data["lotto_winning"]
        return " ".join(map(str, item["numbers"]))

    @property
    def extra_state_attributes(self):
        item = self.coordinator.data["lotto_winning"]
        return {
            "회차": item["round"],
            "추첨일": item["draw_date"],
            "보너스 번호": item["bonus_number"],
        }


class LotteryUnsettledGameSensor(CoordinatorEntity[LotteryCoordinator], SensorEntity):
    """Expose an un-drawn game through an account-owned reusable slot."""

    _attr_icon = "mdi:ticket-confirmation-outline"

    def __init__(
        self, coordinator: LotteryCoordinator, lottery_type: str, slot: int
    ) -> None:
        super().__init__(coordinator)
        self._lottery_type = lottery_type
        self._slot = slot
        self._key = f"{lottery_type}_unsettled_games"
        self._attr_unique_id = (
            f"donghaeng_lottery_{coordinator.client.username}_{lottery_type}_game_{slot}"
        )
        self._attr_device_info = lottery_device_info(coordinator.client)
        if lottery_type == "pension":
            self._attr_name = f"연금복권 720+ 게임 {slot}"
        else:
            label = chr(64 + slot) if slot <= 26 else str(slot)
            self._attr_name = f"로또 6/45 게임 {label}"

    @property
    def _game(self) -> dict:
        games = self.coordinator.data.get(self._key, [])
        return games[self._slot - 1] if len(games) >= self._slot else {}

    @property
    def available(self) -> bool:
        """A ticket is unavailable once it is no longer an un-drawn purchase."""
        return super().available and bool(self._game)

    @property
    def native_value(self):
        game = self._game
        if not game:
            return None
        if self._lottery_type == "pension":
            return f"{game['group']}조 {game['number']}"
        return " ".join(map(str, game["numbers"]))

    @property
    def extra_state_attributes(self):
        game = self._game
        if not game:
            return {"업데이트": self.coordinator.data.get("updated")}
        attributes = {
            "회차": game["round"],
            "구매일시": game["purchased_at"],
            "업데이트": self.coordinator.data.get("updated"),
        }
        if self._lottery_type == "pension":
            attributes["조"] = game["group"]
            attributes["번호"] = game["number"]
        else:
            attributes["게임"] = game["slot"]
            attributes["선택방식"] = game.get("selection")
            attributes["번호"] = game["numbers"]
        return attributes


class LotteryLatestPurchasedGamesSensor(
    CoordinatorEntity[LotteryCoordinator], SensorEntity
):
    """Show the game numbers from the most recently purchased un-drawn ticket."""

    _attr_icon = "mdi:ticket-confirmation-outline"

    def __init__(self, coordinator: LotteryCoordinator, lottery_type: str) -> None:
        super().__init__(coordinator)
        self._lottery_type = lottery_type
        self._key = f"{lottery_type}_unsettled_games"
        label = "연금복권 720+" if lottery_type == "pension" else "로또 6/45"
        self._attr_name = f"{label} 최근 미추첨 구매 번호"
        self._attr_unique_id = f"donghaeng_lottery_{coordinator.client.username}_{lottery_type}_latest_games"
        self._attr_device_info = lottery_device_info(coordinator.client)

    @property
    def _games(self) -> list[dict]:
        games = self.coordinator.data.get(self._key, [])
        if not games:
            return []
        latest_order = max(
            games,
            key=lambda game: (
                str(game.get("purchased_at") or ""),
                str(game.get("order_no") or ""),
            ),
        ).get("order_no")
        return [game for game in games if game.get("order_no") == latest_order]

    @property
    def native_value(self):
        games = self._games
        if not games:
            return "구매 내역 없음"
        if self._lottery_type == "pension":
            return " · ".join(f"{game['group']}조 {game['number']}" for game in games)
        return " · ".join(" ".join(map(str, game["numbers"])) for game in games)

    @property
    def extra_state_attributes(self):
        games = self._games
        attributes = {
            "게임 수": len(games),
            "회차": games[0].get("round") if games else None,
            "구매일시": games[0].get("purchased_at") if games else None,
            "games": games,
            "업데이트": self.coordinator.data.get("updated"),
        }
        if self._lottery_type == "pension":
            by_group = {str(game["group"]): game["number"] for game in games}
            attributes.update(
                {f"{group}조": by_group.get(str(group)) for group in range(1, 6)}
            )
        return attributes
