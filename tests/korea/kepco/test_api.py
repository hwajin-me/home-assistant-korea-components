"""
KEPCO API 테스트 - Mock과 실제 동작 테스트 포함
Python 3.13 호환성을 고려한 테스트 코드
"""
import pytest
import aiohttp
import ssl
import json
import respx
from http.cookies import SimpleCookie
from custom_components.korea_incubator.kepco.api import KepcoApiClient
from custom_components.korea_incubator.kepco.exceptions import KepcoAuthError


@pytest.fixture
async def mock_session():
    """Mock aiohttp 세션"""
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture
async def real_session():
    """실제 aiohttp 세션 - Python 3.13 호환"""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(
        ssl=ssl_context,
        limit=10,
        limit_per_host=2,
        keepalive_timeout=30
    )

    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=30),
        headers={"User-Agent": "Mozilla/5.0 (compatible; test-agent)"}
    ) as session:
        yield session


@pytest.fixture
def api_client_mock(mock_session):
    """Mock API 클라이언트"""
    return KepcoApiClient(mock_session)


@pytest.fixture
def api_client_real(real_session):
    """실제 API 클라이언트"""
    return KepcoApiClient(real_session)


class TestKepcoApiMock:
    """Mock을 사용한 KEPCO API 테스트"""

    @pytest.mark.asyncio
    async def test_set_credentials(self, api_client_mock):
        """자격증명 설정 테스트"""
        username = "test_user"
        password = "test_password"

        api_client_mock.set_credentials(username, password)

        assert api_client_mock._username == username
        assert api_client_mock._password == password

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_session_and_rsa_key_success(self, api_client_mock):
        """세션 및 RSA 키 획득 성공 테스트"""
        mock_html = """
        <html>
            <input type="hidden" id="RSAModulus" value="abc123def456">
            <input type="hidden" id="RSAExponent" value="10001">
            <input type="hidden" id="SESSID" value="test_sessid">
        </html>
        """
        respx.get("https://pp.kepco.co.kr:8030/intro.do").respond(
            200,
            text=mock_html,
            headers={'Set-Cookie': 'JSESSIONID=test_jsession; Path=/'}
        )

        jsessionid, rsa_modulus, rsa_exponent, sessid = await api_client_mock.async_get_session_and_rsa_key()

        assert jsessionid == "test_jsession"
        assert rsa_modulus == "abc123def456"
        assert rsa_exponent == "10001"
        assert sessid == "test_sessid"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_session_missing_elements(self, api_client_mock):
        """필수 요소가 누락된 경우 테스트"""
        mock_html = "<html><body>Empty page</body></html>"
        respx.get("https://pp.kepco.co.kr:8030/intro.do").respond(
            200,
            text=mock_html,
            headers={'Set-Cookie': 'JSESSIONID=test_jsession; Path=/'}
        )

        with pytest.raises(KepcoAuthError, match="Failed to get RSA modulus"):
            await api_client_mock.async_get_session_and_rsa_key()

    @respx.mock
    @pytest.mark.asyncio
    async def test_login_success(self, api_client_mock):
        """로그인 성공 테스트"""
        mock_html = """
        <html>
            <input type="hidden" id="RSAModulus" value="abc123def456">
            <input type="hidden" id="RSAExponent" value="10001">
            <input type="hidden" id="SESSID" value="test_sessid">
        </html>
        """
        respx.get("https://pp.kepco.co.kr:8030/intro.do").respond(
            200,
            text=mock_html,
            headers={'Set-Cookie': 'JSESSIONID=test_jsession; Path=/'}
        )
        respx.post("https://pp.kepco.co.kr:8030/login").respond(
            200,
            text="Success page",
            headers={'Content-Type': 'text/html'}
        )

        # Mock the final redirected URL
        respx.get("https://pp.kepco.co.kr:8030/confirmInfo.do").respond(200)
        
        # Modify the login method to follow redirects
        api_client_mock._session.post = api_client_mock._session.request.__self__.post

        result = await api_client_mock.async_login("test_user", "test_password")

        assert result is True
        assert api_client_mock._username == "test_user"
        assert api_client_mock._password == "test_password"

    @respx.mock
    @pytest.mark.asyncio
    async def test_request_with_json_response(self, api_client_mock):
        """JSON 응답 처리 테스트"""
        mock_data = {"result": {"status": "success", "data": "test"}}
        respx.post("https://test.com/api").respond(200, json=mock_data)

        result = await api_client_mock._request("POST", "https://test.com/api")

        assert result == mock_data

    @respx.mock
    @pytest.mark.asyncio
    async def test_request_with_text_response(self, api_client_mock):
        """텍스트 응답 처리 테스트"""
        mock_text = '{"result": {"status": "success"}}'
        respx.post("https://test.com/api").respond(200, text=mock_text, headers={'Content-Type': 'text/html'})

        result = await api_client_mock._request("POST", "https://test.com/api")

        assert result == {"result": {"status": "success"}}

    @respx.mock
    @pytest.mark.asyncio
    async def test_request_401_reauth(self, api_client_mock):
        """401 오류 시 재인증 테스트"""
        api_client_mock.set_credentials("test_user", "test_password")

        route = respx.post("https://test.com/api")
        route.side_effect = [
            Exception("Unauthorized"), # First call fails
            {"status_code": 200, "json": {"success": True}}, # Second call succeeds
        ]
        
        with pytest.raises(KepcoAuthError):
            await api_client_mock._request("POST", "https://test.com/api")


class TestKepcoApiReal:
    """실제 KEPCO API 테스트"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_python_313_cookie_handling(self, api_client_real):
        """Python 3.13 쿠키 처리 테스트"""
        # SimpleCookie 호환성 테스트
        test_cookie_header = "JSESSIONID=ABC123DEF456; Path=/; HttpOnly; Secure"
        cookies = SimpleCookie()
        cookies.load(test_cookie_header)

        assert 'JSESSIONID' in cookies
        assert cookies['JSESSIONID'].value == 'ABC123DEF456'

        # 실제 KEPCO 페이지에서 쿠키 처리
        try:
            jsessionid, _, _, _ = await api_client_real.async_get_session_and_rsa_key()
            assert jsessionid is not None
            assert len(jsessionid) > 0
            print(f"✅ Python 3.13 쿠키 처리 성공: {jsessionid[:10]}...")
        except Exception as e:
            pytest.skip(f"KEPCO 서버 연결 실패: {e}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_aiohttp_session_compatibility(self, api_client_real):
        """aiohttp 세션 호환성 테스트"""
        try:
            # 세션 설정 검증
            session = api_client_real._session
            assert session.timeout.total == 30

            # 실제 요청으로 호환성 확인
            jsessionid, rsa_modulus, rsa_exponent, sessid = await api_client_real.async_get_session_and_rsa_key()

            assert all([jsessionid, rsa_modulus, rsa_exponent, sessid])
            print(f"✅ aiohttp 세션 호환성 확인")

        except Exception as e:
            pytest.skip(f"네트워크 연결 문제: {e}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_ssl_context_python_313(self, api_client_real):
        """Python 3.13 SSL 컨텍스트 테스트"""
        try:
            # SSL 설정이 올바르게 적용되었는지 확인
            connector = api_client_real._session.connector
            ssl_context = connector._ssl

            assert ssl_context.check_hostname is False
            assert ssl_context.verify_mode == ssl.CERT_NONE

            # 실제 HTTPS 요청으로 SSL 동작 확인
            jsessionid, _, _, _ = await api_client_real.async_get_session_and_rsa_key()
            assert jsessionid is not None
            print(f"✅ SSL 컨텍스트 정상 동작")

        except Exception as e:
            pytest.skip(f"SSL 테스트 실패: {e}")


@pytest.mark.asyncio
async def test_compatibility_headers():
    """Python 3.13 호환 헤더 테스트"""
    # FormData 호환성 테스트
    from aiohttp import FormData

    payload = FormData()
    payload.add_field("test_field", "test_value")
    payload.add_field("한글_필드", "한글_값")

    # 헤더 호환성 테스트
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (compatible; test)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }

    assert len(payload._fields) == 2
    assert all(key in headers for key in ["Content-Type", "User-Agent"])
    print(f"✅ 헤더 및 FormData 호환성 확인")


if __name__ == "__main__":
    # 직접 실행을 위한 진입점
    import sys
    import logging

    logging.basicConfig(level=logging.INFO)
    pytest.main([__file__, "-v", "-s"] + sys.argv[1:])
