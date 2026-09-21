"""Donghaeng Lottery client and Home Assistant entities.

The pension lottery uses the separate ``el.dhlottery.co.kr`` game service.  Its
requests are encrypted with a key derived from the game-session JSESSIONID.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import logging
import os
import re
from dataclasses import dataclass
from urllib.parse import urlencode

import aiohttp
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import PBKDF2
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator, UpdateFailed
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
            async with self.session.get(f"{_WWW}/login/selectRsaModulus.do") as response:
                if response.status != 200:
                    raise LotteryError("동행복권 RSA 공개키 요청이 거부되었습니다.")
                key_data = (await response.json(content_type=None)).get("data", {})
            key = _RSAKey()
            key.set_public(key_data["rsaModulus"], key_data["publicExponent"])
            async with self.session.post(
                f"{_WWW}/login/securityLoginCheck.do",
                data={"userId": key.encrypt(self.username), "userPswdEncn": key.encrypt(self._password), "inpUserId": self.username},
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
                raise LotteryError("동행복권 서버가 JSON 응답을 반환하지 않았습니다.") from err
        return data.get("data", data)

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
            return Balance(int(value.get("totalAmt", 0)), int(value.get("crntEntrsAmt", 0)))
        except (TypeError, ValueError) as err:
            raise LotteryError("예치금 정보를 해석하지 못했습니다.") from err

    def _el_session_id(self) -> str:
        cookies = self.session.cookie_jar.filter_cookies(_EL)
        # The game page JavaScript reads JSESSIONID.  Recent sessions can also
        # expose the identical value as DHJSESSIONID, so retain that fallback.
        value = cookies.get("JSESSIONID") or cookies.get("DHJSESSIONID")
        if not value:
            raise LotteryError("연금복권 게임 세션을 만들지 못했습니다.")
        return value.value

    def _copy_game_session_cookie(self) -> None:
        """Make the authenticated www JSESSIONID available to the game host.

        Login can create a host-only cookie for ``www.dhlottery.co.kr``.  The
        browser navigation to TotalGame.jsp forwards it to the game host; an
        aiohttp cookie jar does not promote host-only cookies across hosts.
        """
        www_cookie = self.session.cookie_jar.filter_cookies(_WWW).get("JSESSIONID")
        if www_cookie and not self.session.cookie_jar.filter_cookies(_EL).get(
            "JSESSIONID"
        ):
            self.session.cookie_jar.update_cookies(
                {"JSESSIONID": www_cookie.value}, response_url=URL(_EL)
            )

    async def _async_open_pension_game(self) -> str:
        """Establish the game SSO session and return its authenticated HTML."""
        self._copy_game_session_cookie()
        async with self.session.get(
            f"{_EL}/game/TotalGame.jsp?LottoId=LP72",
            allow_redirects=True,
            headers={"Referer": f"{_WWW}/"},
        ):
            pass
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
            r"<input\\b(?=[^>]*\\bname=[\"']USER_ID[\"'])(?=[^>]*\\bvalue=[\"'][^\"']+[\"'])[^>]*>",
            game_page,
            re.IGNORECASE,
        )
        if not field:
            raise LotteryError("연금복권 사용자 세션을 확인하지 못했습니다.")
        value = re.search(r"\\bvalue=[\"']([^\"']+)[\"']", field.group(0), re.IGNORECASE)
        if not value:
            raise LotteryError("연금복권 사용자 세션을 확인하지 못했습니다.")
        return value.group(1)

    @staticmethod
    def _encrypt(plain: str, jsession_id: str) -> str:
        salt, iv = os.urandom(32), os.urandom(16)
        key = PBKDF2(jsession_id[:32], salt, 16, count=1000, hmac_hash_module=SHA256)
        pad = 16 - len(plain.encode()) % 16
        encrypted = AES.new(key, AES.MODE_CBC, iv).encrypt(plain.encode() + bytes([pad]) * pad)
        return salt.hex() + iv.hex() + base64.b64encode(encrypted).decode()

    @staticmethod
    def _decrypt(ciphertext: str, jsession_id: str) -> str:
        salt, iv = bytes.fromhex(ciphertext[:64]), bytes.fromhex(ciphertext[64:96])
        key = PBKDF2(jsession_id[:32], salt, 16, count=1000, hmac_hash_module=SHA256)
        raw = AES.new(key, AES.MODE_CBC, iv).decrypt(base64.b64decode(ciphertext[96:]))
        return raw[:-raw[-1]].decode()

    async def _pension_step(self, path: str, fields: list[tuple[str, str]]) -> dict:
        session_id = self._el_session_id()
        plain = urlencode(fields)
        q = self._encrypt(plain, session_id).replace("+", "%252B").replace("/", "%2F").replace("=", "%3D")
        headers = {
            "Origin": _EL,
            "Referer": f"{_EL}/game/pension720/game.jsp",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        async with self.session.post(f"{_EL}{path}", data=f"q={q}", headers=headers) as response:
            body = await response.text()
            if response.status != 200 or not body.lstrip().startswith("{"):
                raise LotteryError(f"연금복권 서버 응답 오류({path}) — 구매 결과가 불명확합니다. 재시도하지 마세요.")
        envelope = json.loads(body)
        decrypted = self._decrypt(envelope["q"], session_id) if envelope.get("q") else body
        return json.loads(decrypted)

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
            raise LotteryError("연금복권 판매 시간 응답을 해석하지 못했습니다.") from err
        if data.get("resultCode") and str(data["resultCode"]) != "100":
            raise LotteryError(f"현재 연금복권 판매 시간이 아닙니다. ({data.get('resultMsg', '')})")
        is_sale = str(data.get("IS_SALE_FLAG", "true")).strip().lower()
        if is_sale not in {"true", "y", "1"} or str(
            data.get("NTSL_DDLN_YN", "N")
        ).upper() == "Y":
            raise LotteryError("현재 연금복권 판매 시간이 아닙니다.")
        if not str(data.get("ROUND", "")).isdigit():
            raise LotteryError("연금복권 판매 회차 정보를 찾지 못했습니다.")
        return data

    async def _check_pension_deposit(
        self, round_no: int, group: str, number: str
    ) -> None:
        """Run the same encrypted deposit check used by the game page.

        The endpoint is a pre-payment check only.  It never changes purchase
        state, so a failure here is safe to surface as a normal rejection.
        """
        result = await self._pension_step(
            "/checkDeposit.do",
            [
                ("ROUND", str(round_no)),
                ("SEL_NO", number),
                ("BUY_CNT", "1"),
                ("AUTO_SEL_SET", "S"),
                ("SEL_CLASS", group),
                ("BUY_TYPE", "A"),
                ("ACCS_TYPE", "01"),
            ],
        )
        code = str(result.get("resultCode", "100"))
        if code != "100":
            raise LotteryError(
                f"연금복권 예치금 확인 실패: {result.get('resultMsg', '구매 가능 금액을 확인하세요.') }"
            )

    async def buy_pension_auto(self, games: int) -> list[dict[str, str | int]]:
        """Buy 1–5 pension tickets with server-assigned numbers.

        ``connPro.do`` is the payment step.  It is intentionally never retried:
        an interrupted response must be checked in the Donghaeng purchase history.
        """
        if games not in range(1, 6):
            raise LotteryError("연금복권 자동 구매 수는 1~5개여야 합니다.")
        user_id = self._extract_game_user_id(await self._async_open_pension_game())
        sales = await self._pension_round_remain_time()
        round_no, tickets = int(sales["ROUND"]), []
        for index in range(games):
            group = str(index % 5 + 1)
            common = [("ROUND", str(round_no)), ("SEL_NO", ""), ("BUY_CNT", ""), ("AUTO_SEL_SET", "S"), ("SEL_CLASS", group), ("BUY_TYPE", "A"), ("ACCS_TYPE", "01")]
            assigned = await self._pension_step("/makeAutoNo.do", common)
            if assigned.get("resultCode") != "100":
                raise LotteryError(f"연금복권 번호 자동 선택 실패: {assigned.get('resultMsg', '')}")
            number = assigned.get("selLotNo", "").split(",")[0]
            group = assigned.get("selClsNo", group).split(",")[0]
            if not re.fullmatch(r"\d{6}", number):
                raise LotteryError("자동 선택된 연금복권 번호 형식이 올바르지 않습니다.")
            order = await self._pension_step("/makeOrderNo.do", [("ROUND", str(round_no)), ("SEL_NO", number), ("BUY_CNT", "1"), ("AUTO_SEL_SET", "S"), ("SEL_CLASS", group), ("BUY_TYPE", "A"), ("ACCS_TYPE", "01")])
            if order.get("resultCode") != "100" or not order.get("orderNo"):
                raise LotteryError(f"연금복권 주문 생성 실패: {order.get('resultMsg', '')}")
            await self._check_pension_deposit(round_no, group, number)
            payment = [("ROUND", str(round_no)), ("FLAG", ""), ("BUY_KIND", "01"), ("BUY_NO", f"{group}{number}"), ("BUY_CNT", "1"), ("BUY_SET_TYPE", "S"), ("BUY_TYPE", "A"), ("ACCS_TYPE", "01"), ("orderNo", order["orderNo"]), ("orderDate", order["orderDate"]), ("TRANSACTION_ID", ""), ("WIN_DATE", ""), ("USER_ID", user_id), ("PAY_TYPE", ""), ("resultErrorCode", ""), ("resultErrorMsg", ""), ("resultOrderNo", ""), ("WORKING_FLAG", "false"), ("NUM_CHANGE_TYPE", ""), ("auto_process", "Y"), ("set_type", "S"), ("classnum", group), ("selnum", number), ("buytype", "A"), ("num1", number[0]), ("num2", number[1]), ("num3", number[2]), ("num4", number[3]), ("num5", number[4]), ("num6", number[5]), ("DSEC", "0"), ("CLOSE_DATE", ""), ("verifyYN", "N"), ("curdeposit", "0"), ("curpay", "1000")]
            result = await self._pension_step("/connPro.do", payment)
            if result.get("resultCode") != "100":
                raise LotteryError(f"연금복권 구매 응답이 실패했습니다 — 결과가 불명확합니다. 재시도하지 말고 구매내역을 확인하세요. ({result.get('resultMsg', '')})")
            tickets.append({"round": round_no, "group": int(group), "number": number})
        return tickets

    async def buy_lotto_645_auto(self, games: int) -> dict:
        """Buy server-selected Lotto 6/45 games (the original component's core flow)."""
        if games not in range(1, 6):
            raise LotteryError("로또 6/45 자동 구매 수는 1~5개여야 합니다.")
        now = dt.datetime.now()
        if now.hour < 6 or (now.weekday() == 5 and now.hour >= 20):
            raise LotteryError("현재는 로또 6/45 판매 시간이 아닙니다.")
        balance = await self.balance()
        if balance.available < games * 1000:
            raise LotteryError(f"구매 가능 예치금이 부족합니다. (현재 {balance.available:,}원)")
        history = await self._get_json("mypage/selectMyLotteryledger.do", {
            "srchStrDt": (now - dt.timedelta(days=7)).strftime("%Y%m%d"),
            "srchEndDt": now.strftime("%Y%m%d"), "ltGdsCd": "LO40", "pageNum": 1,
            "recordCountPerPage": 1000, "_": int(now.timestamp() * 1000),
        })
        bought = sum(int(item.get("prchsQty", 0)) for item in history.get("list", []) if item.get("ltWnResult") == "미추첨")
        games = min(games, max(0, 5 - bought))
        if games == 0:
            raise LotteryError("이번 회차의 온라인 로또 6/45 구매 한도를 모두 사용했습니다.")
        info = await self._get_json("lt645/selectPstLt645Info.do", {"_": int(now.timestamp() * 1000)})
        rows = info.get("list", [])
        if not rows:
            raise LotteryError("로또 6/45 회차 정보를 찾지 못했습니다.")
        live_round = int(rows[0]["ltEpsd"]) + 1
        async with self.session.post("https://ol.dhlottery.co.kr/olotto/game/egovUserReadySocket.json") as response:
            ready = await response.json(content_type=None)
        direct = ready.get("ready_ip")
        if not direct:
            raise LotteryError("로또 구매 서버 연결 정보를 가져오지 못했습니다.")
        selections = [{"genType": "0", "arrGameChoiceNum": None, "alpabet": "ABCDE"[i]} for i in range(games)]
        async with self.session.post("https://ol.dhlottery.co.kr/olotto/game/execBuy.do", data={
            "round": str(live_round), "direct": direct, "nBuyAmount": str(games * 1000),
            "param": json.dumps(selections), "gameCnt": games, "saleMdaDcd": "10",
        }) as response:
            body = await response.json(content_type=None)
        result = body.get("result", {})
        if result.get("resultCode") != "100":
            raise LotteryError(f"로또 6/45 구매 실패: {result.get('resultMsg', '알 수 없는 오류')}")
        return result


class LotteryCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass, client: LotteryClient) -> None:
        super().__init__(hass, _LOGGER, name="Donghaeng Lottery", update_interval=dt.timedelta(hours=1))
        self.client = client

    async def _async_update_data(self) -> dict:
        try:
            balance = await self.client.balance()
            return {"balance": balance, "updated": dt.datetime.now().isoformat(timespec="seconds")}
        except LotteryError as err:
            raise UpdateFailed(str(err)) from err


class LotteryBalanceSensor(CoordinatorEntity[LotteryCoordinator], SensorEntity):
    _attr_name = "동행복권 예치금"
    _attr_icon = "mdi:cash"
    _attr_native_unit_of_measurement = "KRW"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: LotteryCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"donghaeng_lottery_{coordinator.client.username}_balance"
        self._attr_device_info = DeviceInfo(identifiers={("korea_incubator", f"donghaeng_lottery_{coordinator.client.username}")}, name="동행복권", manufacturer="동행복권", configuration_url=_WWW)

    @property
    def native_value(self):
        return self.coordinator.data["balance"].deposit

    @property
    def extra_state_attributes(self):
        return {"구매 가능 금액": self.coordinator.data["balance"].available, "업데이트": self.coordinator.data["updated"]}
