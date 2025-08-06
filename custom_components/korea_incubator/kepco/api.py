from http.cookies import SimpleCookie
import ssl
import aiohttp
import random
import json
from bs4 import BeautifulSoup
from aiohttp import FormData
from .exceptions import KepcoAuthError
from ..const import LOGGER


class RSAKey:
    """rsa.js의 RSAKey와 동일한 기능을 하는 Python 클래스"""
    def __init__(self):
        self.n = None
        self.e = 0

    def set_public(self, modulus_hex, exponent_hex):
        """RSA 공개키를 16진수 문자열로부터 설정"""
        if modulus_hex and exponent_hex and len(modulus_hex) > 0 and len(exponent_hex) > 0:
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
    s_bytes = s.encode('utf-8')
    s_len = len(s_bytes)

    if n < s_len + 11:
        raise ValueError("Message too long for RSA")

    # 바이트 배열 생성
    ba = bytearray(n)

    # 메시지를 뒤에서부터 배치
    ba[n - s_len:n] = s_bytes

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
    return int.from_bytes(ba, 'big')


class KepcoApiClient:
    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        self._username = None
        self._password = None

    def set_credentials(self, username, password):
        self._username = username
        self._password = password

    async def async_get_session_and_rsa_key(self):
        url = "https://pp.kepco.co.kr:8030/intro.do"

        # HTTP/1.1 강제 설정을 위한 connector 생성
        connector = aiohttp.TCPConnector(
            force_close=True,
            enable_cleanup_closed=True,
            ssl=False
        )

        async with self._session.get(
                url=url,
                timeout=aiohttp.ClientTimeout(total=30),
                verify_ssl=False,
                compress=0,
                connector=connector,
                version=aiohttp.HttpVersion11,
        ) as response:
            response.raise_for_status()
            LOGGER.debug(f"Intro page response status: {response.status}")
            LOGGER.debug(f"Intro page response headers: {response.headers}")
            html_text = await response.text()

            # Python 3.13과 aiohttp 3.12+ 호환성을 위한 개선된 쿠키 처리
            jsessionid = None

            # 방법 1: response.cookies 사용 (권장)
            if 'JSESSIONID' in response.cookies:
                jsessionid = response.cookies['JSESSIONID'].value
            else:
                # 방법 2: Set-Cookie 헤더에서 직접 추출
                cookie_header = response.headers.get('Set-Cookie', '')
                if 'JSESSIONID=' in cookie_header:
                    # SimpleCookie를 사용한 안전한 파싱
                    cookies = SimpleCookie()
                    try:
                        cookies.load(cookie_header)
                        if 'JSESSIONID' in cookies:
                            jsessionid = cookies['JSESSIONID'].value
                    except Exception:
                        # 수동 파싱 fallback
                        jsessionid = cookie_header.split('JSESSIONID=')[1].split(';')[0]

            if not jsessionid:
                raise KepcoAuthError("Failed to get JSESSIONID from intro page.")

            soup = BeautifulSoup(html_text, 'html.parser')

            rsa_modulus_tag = soup.find('input', {'id': 'RSAModulus'})
            rsa_exponent_tag = soup.find('input', {'id': 'RSAExponent'})
            sessid_tag = soup.find('input', {'id': 'SESSID'})

            if not rsa_modulus_tag or not rsa_exponent_tag or not sessid_tag:
                raise KepcoAuthError("Failed to get RSA modulus, exponent or SESSID from intro page HTML.")

            rsa_modulus = rsa_modulus_tag.get('value').strip()
            rsa_exponent = rsa_exponent_tag.get('value').strip()
            sessid = sessid_tag.get('value').strip()

            LOGGER.debug(f"Return KEPCO value {jsessionid}, {rsa_modulus}, {rsa_exponent}, {sessid}")

            return jsessionid, rsa_modulus, rsa_exponent, sessid

    async def async_login(self, username, password):
        self.set_credentials(username, password)
        try:
            jsessionid, rsa_modulus, rsa_exponent, sessid = await self.async_get_session_and_rsa_key()
        except KepcoAuthError as e:
            LOGGER.error(f"KEPCO Login failed: {e}")
            return False

        LOGGER.debug(f"KEPCO Login Request with {username} and {password}")

        try:
            # RSA 키 생성 (rsa.js와 동일한 방식)
            rsa_key = RSAKey()
            rsa_key.set_public(rsa_modulus, rsa_exponent)

            # 사용자 이름과 비밀번호 암호화 (rsa.js의 RSAEncrypt와 동일)
            encrypted_username_hex = rsa_key.encrypt(username)
            encrypted_password_hex = rsa_key.encrypt(password)

            if not encrypted_username_hex or not encrypted_password_hex:
                raise ValueError("RSA encryption failed")

        except Exception as e:
            LOGGER.error(f"RSA encryption failed: {e}")
            return False

        LOGGER.debug(f"KEPCO ID/PW: {encrypted_username_hex} / {encrypted_password_hex}, Session ID: {sessid}")

        user_id = f"{sessid}_{encrypted_username_hex}"
        user_pw = f"{sessid}_{encrypted_password_hex}"

        login_url = "https://pp.kepco.co.kr:8030/login"

        payload = FormData()
        payload.add_field("USER_ID", user_id)
        payload.add_field("USER_PWD", user_pw)

        # Python 3.13과 aiohttp 3.12+ 호환성을 위한 개선된 헤더
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://pp.kepco.co.kr:8030/intro.do",
            "Cookie": f"XTVID=A250728153257353569; xloc=1728X1117; JSESSIONID={jsessionid}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

        # HTTP/1.1 강제 설정을 위한 connector 생성
        connector = aiohttp.TCPConnector(
            force_close=True,
            enable_cleanup_closed=True,
            ssl=False
        )

        try:
            async with self._session.post(
                login_url,
                data=payload,
                headers=headers,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=30),
                verify_ssl=False,
                connector=connector,
                version=aiohttp.HttpVersion11,
            ) as response:
                LOGGER.debug(f"Login response status: {response.status}")
                LOGGER.debug(f"Login response headers: {response.headers}")
                text = await response.text()
                LOGGER.debug(f"Login response body: {text}")
                if response.status == 200:
                    # 최종적으로 도달한 URL이 confirmInfo.do 이거나, 로그인 성공을 나타내는 페이지인지 확인
                    if "confirmInfo.do" in str(response.url):
                        return True
                LOGGER.error(f"KEPCO Login failed with status {response.status}: {text}")
                return False
        except Exception as e:
            LOGGER.error(f"Login request failed: {e}")
            return False

    async def _request(self, method, url, **kwargs):
        """Helper to handle API requests and re-authentication."""
        # Python 3.13과 aiohttp 3.12+ 호환성을 위한 기본 설정
        if 'timeout' not in kwargs:
            kwargs['timeout'] = aiohttp.ClientTimeout(total=30)

        if 'ssl' not in kwargs:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            kwargs['ssl'] = ssl_context

        # HTTP/1.1 강제 설정
        if 'version' not in kwargs:
            kwargs['version'] = aiohttp.HttpVersion11

        if 'connector' not in kwargs:
            kwargs['connector'] = aiohttp.TCPConnector(
                force_close=True,
                enable_cleanup_closed=True,
                ssl=False
            )

        try:
            async with self._session.request(method, url, **kwargs) as response:
                LOGGER.debug(f"API request to {url} response status: {response.status}")
                LOGGER.debug(f"API request to {url} response headers: {response.headers}")

                # Content-Type 확인 및 적절한 응답 처리
                content_type = response.headers.get('Content-Type', '').lower()
                if 'application/json' in content_type:
                    return await response.json()
                else:
                    text = await response.text()
                    LOGGER.debug(f"API request to {url} response body: {text}")
                    response.raise_for_status()

                    # JSON이 아닌 응답의 경우 텍스트 반환
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return {"text": text, "status": response.status}

        except aiohttp.ClientResponseError as e:
            LOGGER.error(f"API call to {url} failed with status {e.status}: {e.message}")
            if e.status == 401 and self._username and self._password:
                LOGGER.warning("API call failed with 401, attempting re-login.")
                if await self.async_login(self._username, self._password):
                    LOGGER.info("Re-login successful, retrying original request.")
                    try:
                        async with self._session.request(method, url, **kwargs) as response:
                            LOGGER.debug(f"Retried API request to {url} response status: {response.status}")
                            LOGGER.debug(f"Retried API request to {url} response headers: {response.headers}")

                            content_type = response.headers.get('Content-Type', '').lower()
                            if 'application/json' in content_type:
                                return await response.json()
                            else:
                                text = await response.text()
                                LOGGER.debug(f"Retried API request to {url} response body: {text}")
                                response.raise_for_status()
                                try:
                                    return json.loads(text)
                                except json.JSONDecodeError:
                                    return {"text": text, "status": response.status}
                    except Exception as retry_e:
                        LOGGER.error(f"Retry request failed: {retry_e}")
                        raise KepcoAuthError(f"Retry failed: {retry_e}")
                else:
                    LOGGER.error("KEPCO Re-login failed.")
            raise  # Re-raise if not 401 or re-login failed
        except Exception as e:
            LOGGER.error(f"Client error for {url}: {e}")
            raise KepcoAuthError(f"Connection error: {e}")

    async def async_get_recent_usage(self):
        url = "https://pp.kepco.co.kr:8030/low/main/recent_usage.do"
        return await self._request("POST", url, json={})

    async def async_get_usage_info(self):
        url = "https://pp.kepco.co.kr:8030/low/main/usage_info.do"
        return await self._request("POST", url, json={"tou": "N"})
