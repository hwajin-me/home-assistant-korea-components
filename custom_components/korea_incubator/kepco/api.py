from http.cookies import SimpleCookie
import ssl

import aiohttp
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from bs4 import BeautifulSoup
from aiohttp import FormData
from .exceptions import KepcoAuthError
from ..const import LOGGER


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

        async with self._session.get(
                url=url,
                timeout=aiohttp.ClientTimeout(total=30),
                verify_ssl=False,
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

            rsa_modulus = rsa_modulus_tag.get('value')
            rsa_exponent = rsa_exponent_tag.get('value')
            sessid = sessid_tag.get('value')

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
            modulus_int = int(rsa_modulus, 16)
            exponent_int = int(rsa_exponent, 16)

            key = RSA.construct((modulus_int, exponent_int))
            cipher = PKCS1_v1_5.new(key)

            encrypted_username_bytes = cipher.encrypt(username.encode('utf-8'))
            encrypted_password_bytes = cipher.encrypt(password.encode('utf-8'))

            encrypted_username_hex = encrypted_username_bytes.hex()
            encrypted_password_hex = encrypted_password_bytes.hex()
        except Exception as e:
            LOGGER.error(f"RSA encryption failed: {e}")
            return False

        LOGGER.debug(f"KEPCO ID/PW: {encrypted_username_hex} / {encrypted_password_hex}, Session ID: {sessid}")

        user_id = f"{sessid}_{encrypted_username_hex}"
        user_pw = f"{sessid}_{encrypted_password_hex}"

        login_url = "https://pp.kepco.co.kr:8030/login"

        payload = FormData()
        payload.add_field("remember-me", "on")
        payload.add_field("USER_ID", user_id)
        payload.add_field("USER_PW", user_pw)

        # Python 3.13과 aiohttp 3.12+ 호환성을 위한 개선된 헤더
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://pp.kepco.co.kr:8030/intro.do",
            "Cookie": f"JSESSIONID={jsessionid}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }

        try:
            async with self._session.post(
                login_url,
                data=payload,
                headers=headers,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=30),
                verify_ssl=False
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
                        import json
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
                                    import json
                                    return json.loads(text)
                                except json.JSONDecodeError:
                                    return {"text": text, "status": response.status}
                    except Exception as retry_e:
                        LOGGER.error(f"Retry request failed: {retry_e}")
                        raise KepcoAuthError(f"Retry failed: {retry_e}")
                else:
                    LOGGER.error("KEPCO Re-login failed.")
            raise  # Re-raise if not 401 or re-login failed
            LOGGER.error(f"Client error for {url}: {e}")
            raise KepcoAuthError(f"Connection error: {e}")

    async def async_get_recent_usage(self):
        url = "https://pp.kepco.co.kr:8030/low/main/recent_usage.do"
        return await self._request("POST", url, json={})

    async def async_get_usage_info(self):
        url = "https://pp.kepco.co.kr:8030/low/main/usage_info.do"
        return await self._request("POST", url, json={"tou": "N"})
