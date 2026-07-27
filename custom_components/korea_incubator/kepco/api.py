import json

from bs4 import BeautifulSoup
from curl_cffi import AsyncSession

from .exceptions import KepcoAuthError
from ..const import LOGGER
from ..utils import RSAKey


class KepcoApiClient:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._username = None
        self._password = None

    def set_credentials(self, username, password):
        self._username = username
        self._password = password

    async def async_get_session_and_rsa_key(self):
        url = "https://pp.kepco.co.kr:8030/intro.do"

        result = await self._session.get(url=url)
        result.raise_for_status()
        LOGGER.debug(f"Intro page response status: {result.status_code}")
        LOGGER.debug(f"Intro page response headers: {result.headers}")
        html_text = result.text

        soup = BeautifulSoup(html_text, "html.parser")

        rsa_modulus_tag = soup.find("input", {"id": "RSAModulus"})
        rsa_exponent_tag = soup.find("input", {"id": "RSAExponent"})
        sessid_tag = soup.find("input", {"id": "SESSID"})

        if not rsa_modulus_tag or not rsa_exponent_tag or not sessid_tag:
            raise KepcoAuthError(
                "Failed to get RSA modulus, exponent or SESSID from intro page HTML."
            )

        rsa_modulus = rsa_modulus_tag.get("value").strip()
        rsa_exponent = rsa_exponent_tag.get("value").strip()
        sessid = sessid_tag.get("value").strip()

        LOGGER.debug(f"Return KEPCO value {rsa_modulus}, {rsa_exponent}, {sessid}")

        return rsa_modulus, rsa_exponent, sessid

    async def async_login(self, username, password):
        self.set_credentials(username, password)
        try:
            (
                rsa_modulus,
                rsa_exponent,
                sessid,
            ) = await self.async_get_session_and_rsa_key()
        except KepcoAuthError as e:
            LOGGER.error(f"KEPCO Login failed: {e}")
            return False

        LOGGER.debug(f"KEPCO Login Request with {username} and {password}")

        try:
            rsa_key = RSAKey()
            rsa_key.set_public(rsa_modulus, rsa_exponent)

            encrypted_username_hex = rsa_key.encrypt(username)
            encrypted_password_hex = rsa_key.encrypt(password)

            if not encrypted_username_hex or not encrypted_password_hex:
                raise ValueError("RSA encryption failed")

        except Exception as e:
            LOGGER.error(f"RSA encryption failed: {e}")
            return False

        LOGGER.debug(
            f"KEPCO ID/PW: {encrypted_username_hex} / {encrypted_password_hex}, Session ID: {sessid}"
        )

        user_id = f"{sessid}_{encrypted_username_hex}"
        user_pw = f"{sessid}_{encrypted_password_hex}"

        login_url = "https://pp.kepco.co.kr:8030/login"

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://pp.kepco.co.kr:8030/intro.do",
            "Cookie": f"JSESSIONID={sessid}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

        try:
            response = await self._session.post(
                login_url,
                data={"USER_ID": user_id, "USER_PW": user_pw},
                headers=headers,
                allow_redirects=True,
            )
            LOGGER.debug(f"Login response status: {response.status_code}")
            LOGGER.debug(f"Login response headers: {response.headers}")
            text = response.text
            LOGGER.debug(f"Login response body: {text}")
            if response.status_code == 200:
                # 최종적으로 도달한 URL이 confirmInfo.do 이거나, 로그인 성공을 나타내는 페이지인지 확인
                if "confirmInfo.do" in str(response.url):
                    return True
            LOGGER.error(
                f"KEPCO Login failed with status {response.status_code}: {text}"
            )
            return False
        except Exception as e:
            LOGGER.error(f"Login request failed: {e}")
            return False

    async def _request(self, method, url, **kwargs):
        try:
            response = await self._session.request(method, url, **kwargs)
            LOGGER.debug(
                f"API request to {url} response status: {response.status_code}"
            )
            LOGGER.debug(f"API request to {url} response headers: {response.headers}")
            LOGGER.debug(f"API request to {url} response body: {response.text}")
            return json.loads(response.text)
        except Exception as e:
            LOGGER.error(f"API call to {url} failed", e)
            LOGGER.warning("API call failed with 401, attempting re-login.")
            if await self.async_login(self._username, self._password):
                LOGGER.info("Re-login successful, retrying original request.")
                try:
                    response = await self._session.request(method, url, **kwargs)
                    LOGGER.debug(
                        f"API request to {url} response status: {response.status_code}"
                    )
                    LOGGER.debug(
                        f"API request to {url} response headers: {response.headers}"
                    )
                    return json.loads(response.text)
                except Exception as retry_e:
                    LOGGER.error(f"Retry request failed: {retry_e}", retry_e)
                    raise KepcoAuthError(f"Retry failed: {retry_e}", retry_e)
            else:
                LOGGER.error("KEPCO Re-login failed.")
            raise  # Re-raise if not 401 or re-login failed

    async def async_get_recent_usage(self):
        url = "https://pp.kepco.co.kr:8030/low/main/recent_usage.do"
        return await self._request("POST", url, json={})

    async def async_get_usage_info(self):
        url = "https://pp.kepco.co.kr:8030/low/main/usage_info.do"
        return await self._request("POST", url, json={"tou": "N"})
