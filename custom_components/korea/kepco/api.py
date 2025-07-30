from http.cookies import SimpleCookie

import aiohttp
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from bs4 import BeautifulSoup

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
        async with self._session.get(url) as response:
            response.raise_for_status()
            LOGGER.debug(f"Intro page response status: {response.status}")
            LOGGER.debug(f"Intro page response headers: {response.headers}")
            html_text = await response.text()
            cookies = SimpleCookie()
            for cookie_str in response.headers.getall("Set-Cookie"):
                cookies.load(cookie_str)

            jsessionid_cookie = cookies.get("JSESSIONID")
            if not jsessionid_cookie:
                raise KepcoAuthError("Failed to get JSESSIONID from intro page.")
            jsessionid = jsessionid_cookie.value

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
            LOGGER.error(f"Login failed: {e}")
            return False

        LOGGER.debug(f"KEPCO Login Request with {username} and {password}")

        modulus_int = int(rsa_modulus, 16)
        exponent_int = int(rsa_exponent, 16)

        key = RSA.construct((modulus_int, exponent_int))
        cipher = PKCS1_v1_5.new(key)

        encrypted_username_bytes = cipher.encrypt(username.encode('utf-8'))
        encrypted_password_bytes = cipher.encrypt(password.encode('utf-8'))

        encrypted_username_hex = encrypted_username_bytes.hex()
        encrypted_password_hex = encrypted_password_bytes.hex()

        LOGGER.debug(f"ID/PW: {encrypted_username_hex} / {encrypted_password_hex}")

        user_id = f"{sessid}_{encrypted_username_hex}"
        user_pw = f"{sessid}_{encrypted_password_hex}"

        login_url = "https://pp.kepco.co.kr:8030/login"
        payload = {
            "remember-me": "on",
            "USER_ID": user_id,
            "USER_PW": user_pw,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://pp.kepco.co.kr:8030/intro.do",
        }

        async with self._session.post(login_url, data=payload, headers=headers, allow_redirects=True) as response:
            LOGGER.debug(f"Login response status: {response.status}")
            LOGGER.debug(f"Login response headers: {response.headers}")
            text = await response.text()
            LOGGER.debug(f"Login response body: {text}")
            if response.status == 200:
                # 최종적으로 도달한 URL이 confirmInfo.do 이거나, 로그인 성공을 나타내는 페이지인지 확인
                if "confirmInfo.do" in str(response.url):  # or check for specific content on the final page
                    return True
            return False

    async def _request(self, method, url, **kwargs):
        """Helper to handle API requests and re-authentication."""
        try:
            async with self._session.request(method, url, **kwargs) as response:
                LOGGER.debug(f"API request to {url} response status: {response.status}")
                LOGGER.debug(f"API request to {url} response headers: {response.headers}")
                text = await response.text()
                LOGGER.debug(f"API request to {url} response body: {text}")
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            LOGGER.error(f"API call to {url} failed with status {e.status}: {e.message}")
            if e.status == 401 and self._username and self._password:
                LOGGER.warning("API call failed with 401, attempting re-login.")
                if await self.async_login(self._username, self._password):
                    LOGGER.info("Re-login successful, retrying original request.")
                    async with self._session.request(method, url, **kwargs) as response:
                        LOGGER.debug(f"Retried API request to {url} response status: {response.status}")
                        LOGGER.debug(f"Retried API request to {url} response headers: {response.headers}")
                        text = await response.text()
                        LOGGER.debug(f"Retried API request to {url} response body: {text}")
                        response.raise_for_status()
                        return await response.json()
                else:
                    LOGGER.error("Re-login failed.")
            raise  # Re-raise if not 401 or re-login failed

    async def async_get_recent_usage(self):
        url = "https://pp.kepco.co.kr:8030/low/main/recent_usage.do"
        return await self._request("POST", url, json={})

    async def async_get_usage_info(self):
        url = "https://pp.kepco.co.kr:8030/low/main/usage_info.do"
        return await self._request("POST", url, json={"tou": "N"})
