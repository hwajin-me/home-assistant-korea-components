import pytest
import aiohttp
from aiohttp_mock import AioHTTPMock
from Crypto.PublicKey import RSA
from custom_components.korea_incubator.kepco.api import KepcoApiClient
from custom_components.korea_incubator.kepco.exceptions import KepcoAuthError


@pytest.fixture
async def api_client():
    async with aiohttp.ClientSession() as session:
        yield KepcoApiClient(session)


@pytest.mark.asyncio
async def test_async_get_session_and_rsa_key(api_client, aiohttp_mock: AioHTTPMock):
    mock_html = """
    <html>
        <input type="hidden" id="RSAModulus" value="d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3">
        <input type="hidden" id="RSAExponent" value="10001">
        <input type="hidden" id="SESSID" value="test_sessid_12345">
    </html>
    """

    aiohttp_mock.get("https://pp.kepco.co.kr:8030/intro.do", status=200, headers={
        "Set-Cookie": "JSESSIONID=test_jsessionid; Path=/; HttpOnly"
    }, payload=mock_html)

    jsessionid, rsa_modulus, rsa_exponent, sessid = await api_client.async_get_session_and_rsa_key()

    assert jsessionid == "test_jsessionid"
    assert rsa_modulus == "d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3"
    assert rsa_exponent == "10001"
    assert sessid == "test_sessid_12345"


@pytest.mark.asyncio
async def test_rsa_key_creation(api_client):
    """RSA 키 생성 테스트"""
    rsa_modulus = "d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3"
    rsa_exponent = "10001"

    key = api_client._create_rsa_key(rsa_modulus, rsa_exponent)

    assert isinstance(key, RSA.RsaKey)
    assert key.e == int(rsa_exponent, 16)
    assert key.n == int(rsa_modulus, 16)


@pytest.mark.asyncio
async def test_rsa_encryption(api_client):
    """RSA 암호화 테스트"""
    # 테스트용 작은 RSA 키 (실제로는 KEPCO에서 받은 키를 사용)
    rsa_modulus = "d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3"
    rsa_exponent = "10001"

    key = api_client._create_rsa_key(rsa_modulus, rsa_exponent)
    test_text = "test_username"

    encrypted_hex = api_client._encrypt_with_rsa(key, test_text)

    # 암호화된 결과가 hex 문자열인지 확인
    assert isinstance(encrypted_hex, str)
    assert len(encrypted_hex) > 0
    # hex 문자열인지 확인
    bytes.fromhex(encrypted_hex)


@pytest.mark.asyncio
async def test_prepare_encrypted_credentials(api_client):
    """암호화된 인증 정보 준비 테스트"""
    username = "test_user"
    password = "test_password"
    rsa_modulus = "d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3"
    rsa_exponent = "10001"
    sessid = "test_session_12345"

    user_id, user_pw = api_client._prepare_encrypted_credentials(
        username, password, rsa_modulus, rsa_exponent, sessid
    )

    # 결과 형식 확인
    assert user_id.startswith(f"{sessid}_")
    assert user_pw.startswith(f"{sessid}_")

    # 암호화된 부분 추출
    encrypted_username = user_id[len(sessid) + 1:]
    encrypted_password = user_pw[len(sessid) + 1:]

    # hex 문자열인지 확인
    bytes.fromhex(encrypted_username)
    bytes.fromhex(encrypted_password)

    # 두 번 호출했을 때 다른 결과가 나오는지 확인 (RSA 패딩 때문에)
    user_id2, user_pw2 = api_client._prepare_encrypted_credentials(
        username, password, rsa_modulus, rsa_exponent, sessid
    )
    assert user_id != user_id2  # RSA 패딩으로 인해 매번 다른 결과
    assert user_pw != user_pw2


@pytest.mark.asyncio
async def test_async_login_success(api_client, aiohttp_mock: AioHTTPMock):
    mock_html = """
    <html>
        <input type="hidden" id="RSAModulus" value="d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3">
        <input type="hidden" id="RSAExponent" value="10001">
        <input type="hidden" id="SESSID" value="test_sessid_12345">
    </html>
    """

    aiohttp_mock.get("https://pp.kepco.co.kr:8030/intro.do", status=200, headers={
        "Set-Cookie": "JSESSIONID=test_jsessionid; Path=/; HttpOnly"
    }, payload=mock_html)

    # confirmInfo.do로 리다이렉트되는 성공 응답 모킹
    aiohttp_mock.post("https://pp.kepco.co.kr:8030/login", status=200,
                     headers={"Location": "https://pp.kepco.co.kr:8030/confirmInfo.do"},
                     payload="로그인 성공")

    result = await api_client.async_login("test_user", "test_password")
    assert result is True


@pytest.mark.asyncio
async def test_async_login_failure(api_client, aiohttp_mock: AioHTTPMock):
    mock_html = """
    <html>
        <input type="hidden" id="RSAModulus" value="d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3">
        <input type="hidden" id="RSAExponent" value="10001">
        <input type="hidden" id="SESSID" value="test_sessid_12345">
    </html>
    """

    aiohttp_mock.get("https://pp.kepco.co.kr:8030/intro.do", status=200, headers={
        "Set-Cookie": "JSESSIONID=test_jsessionid; Path=/; HttpOnly"
    }, payload=mock_html)

    aiohttp_mock.post("https://pp.kepco.co.kr:8030/login", status=200, payload="로그인 실패")

    result = await api_client.async_login("test_user", "test_password")
    assert result is False


@pytest.mark.asyncio
async def test_async_login_missing_rsa_data(api_client, aiohttp_mock: AioHTTPMock):
    """RSA 정보가 누락된 경우 테스트"""
    mock_html = "<html><body>No RSA data</body></html>"

    aiohttp_mock.get("https://pp.kepco.co.kr:8030/intro.do", status=200, headers={
        "Set-Cookie": "JSESSIONID=test_jsessionid; Path=/; HttpOnly"
    }, payload=mock_html)

    result = await api_client.async_login("test_user", "test_password")
    assert result is False


@pytest.mark.asyncio
async def test_async_get_recent_usage(api_client, aiohttp_mock: AioHTTPMock):
    aiohttp_mock.post("https://pp.kepco.co.kr:8030/low/main/recent_usage.do", status=200, payload={"result": {"F_AP_QT": "123.45", "KWH_BILL": "678"}})

    data = await api_client.async_get_recent_usage()
    assert data["result"]["F_AP_QT"] == "123.45"
    assert data["result"]["KWH_BILL"] == "678"


@pytest.mark.asyncio
async def test_async_get_usage_info(api_client, aiohttp_mock: AioHTTPMock):
    aiohttp_mock.post("https://pp.kepco.co.kr:8030/low/main/usage_info.do", status=200, payload={"result": {"BILL_LAST_MONTH": "10000", "PREDICT_TOTAL_CHARGE_REV": "15000"}})

    data = await api_client.async_get_usage_info()
    assert data["result"]["BILL_LAST_MONTH"] == "10000"
    assert data["result"]["PREDICT_TOTAL_CHARGE_REV"] == "15000"


@pytest.mark.asyncio
async def test_set_credentials(api_client):
    api_client.set_credentials("test_user", "test_password")
    assert api_client._username == "test_user"
    assert api_client._password == "test_password"
