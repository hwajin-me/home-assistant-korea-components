import pytest
import aiohttp
from unittest.mock import AsyncMock, patch, MagicMock
from Crypto.PublicKey import RSA
from custom_components.korea_incubator.kepco.api import KepcoApiClient
from custom_components.korea_incubator.kepco.exceptions import KepcoAuthError


@pytest.mark.asyncio
async def test_decrypt():
    """복호화 테스트"""
    async with aiohttp.ClientSession() as session:
        api_client = KepcoApiClient(session)

        # Mock RSA key
        rsa_modulus = "8c5263400b6e86b9eebcdeb12aa2f3a6f1525b717d03e727f2e046e5a7a44e6ba3099f7f6e6c0001386ab64ff84e2a6f6f1241ed33c319f0dfc4b4776b74190cecd03467fff3b578ede33b89c6886301b7220fb477a9ccf07bb11e84ba74825c8a0a2ab37ed0140eb09770062cd999b2c5c85543f25e52841f74a336657c0cc8f6da232ada5d8e4d1d62f417823de1b403b1d5af037c2e5a0e0f867f7a00791c1d0a534f00762f44bb2cf20e45d853bc4ca10e24da82dc1a5b56dbb198c78ba0988a8a7b850ce1d5ddea0f0bfcd041d48882db0bb6ee327586a8cf1087e56f4af8b0b5f98c9dd3db0fa1ad4e99bd17e20cf189a8b4112c2bd4f0e113fd91a7bb"
        rsa_exponent = "10001"
        key = api_client._create_rsa_key(rsa_modulus, rsa_exponent)

        # Mock encrypted text
        encrypted_text = "1113d5ca3753d6af98699ece78eb9c09c0eb65d9bc72afaa59da79819af99195b7d4c6d828f8b33f423513bff4649d4929e16b4921b3b53d56c943c67b8575f3bd9214c62f093daab6c9b161aadd9bf755e15c45a0c8063a001f54b9e78ed27b3a1e29dab902b20cfc66d9ceb64e0fbe450427f840f51cffd53c633b6e21e69f979ee76fb6b0bfa89c84a8ed7b4ac99d352d820f1906dbda6ea5109d3aad31e575d4bd333ba28d156dd961f182bb58987d539ca432a6437a98654b805d2703e88478861490069e745ef38eeb6512e8f3abf77d1516066d32c0339b3f2441f592018001567f233055b3710a171291e3fe5da09d72b9fa4a07f930e75198592f1f"

        decrypted_text = api_client._decrypt_with_rsa(key, encrypted_text)

        assert isinstance(decrypted_text, str)
        assert len(decrypted_text) > 0


@pytest.fixture
async def api_client():
    async with aiohttp.ClientSession() as session:
        yield KepcoApiClient(session)


@pytest.mark.asyncio
async def test_async_get_session_and_rsa_key():
    """세션 및 RSA 키 획득 테스트"""
    async with aiohttp.ClientSession() as session:
        api_client = KepcoApiClient(session)

        # Mock HTML response
        mock_html = """
        <html>
            <input type="hidden" id="RSAModulus" value="d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3">
            <input type="hidden" id="RSAExponent" value="10001">
            <input type="hidden" id="SESSID" value="test_sessid_12345">
        </html>
        """

        # Mock response object
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=mock_html)
        mock_response.headers = MagicMock()
        mock_response.headers.getall.return_value = ["JSESSIONID=test_jsessionid; Path=/; HttpOnly"]
        mock_response.raise_for_status = MagicMock()

        # Mock session.get
        with patch.object(session, 'get') as mock_get:
            mock_get.return_value.__aenter__.return_value = mock_response

            jsessionid, rsa_modulus, rsa_exponent, sessid = await api_client.async_get_session_and_rsa_key()

            assert jsessionid == "test_jsessionid"
            assert rsa_modulus == "d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3"
            assert rsa_exponent == "10001"
            assert sessid == "test_sessid_12345"


@pytest.mark.asyncio
async def test_rsa_key_creation():
    """RSA 키 생성 테스트"""
    async with aiohttp.ClientSession() as session:
        api_client = KepcoApiClient(session)
        rsa_modulus = "d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3"
        rsa_exponent = "10001"

        key = api_client._create_rsa_key(rsa_modulus, rsa_exponent)

        assert isinstance(key, RSA.RsaKey)
        assert key.e == int(rsa_exponent, 16)
        assert key.n == int(rsa_modulus, 16)


@pytest.mark.asyncio
async def test_rsa_encryption():
    """RSA 암호화 테스트"""
    async with aiohttp.ClientSession() as session:
        api_client = KepcoApiClient(session)
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
async def test_prepare_encrypted_credentials():
    """암호화된 인증 정보 준비 테스트"""
    async with aiohttp.ClientSession() as session:
        api_client = KepcoApiClient(session)
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
async def test_async_login_success():
    """성공적인 로그인 테스트"""
    async with aiohttp.ClientSession() as session:
        api_client = KepcoApiClient(session)

        # Mock async_get_session_and_rsa_key
        with patch.object(api_client, 'async_get_session_and_rsa_key') as mock_session:
            mock_session.return_value = ("test_jsessionid", "d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3", "10001", "test_sessid_12345")

            # Mock login POST response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.url = "https://pp.kepco.co.kr:8030/confirmInfo.do"
            mock_response.text = AsyncMock(return_value="로그인 성공")
            mock_response.headers = {}

            with patch.object(session, 'post') as mock_post:
                mock_post.return_value.__aenter__.return_value = mock_response

                result = await api_client.async_login("test_user", "test_password")
                assert result is True


@pytest.mark.asyncio
async def test_async_login_failure():
    """실패한 로그인 테스트"""
    async with aiohttp.ClientSession() as session:
        api_client = KepcoApiClient(session)

        # Mock async_get_session_and_rsa_key
        with patch.object(api_client, 'async_get_session_and_rsa_key') as mock_session:
            mock_session.return_value = ("test_jsessionid", "d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c2d4e6f8a0b2c4d6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3", "10001", "test_sessid_12345")

            # Mock failed login POST response (no confirmInfo.do in URL)
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.url = "https://pp.kepco.co.kr:8030/login"
            mock_response.text = AsyncMock(return_value="로그인 실패")
            mock_response.headers = {}

            with patch.object(session, 'post') as mock_post:
                mock_post.return_value.__aenter__.return_value = mock_response

                result = await api_client.async_login("test_user", "wrong_password")
                assert result is False


@pytest.mark.asyncio
async def test_async_login_missing_rsa_data():
    """RSA 정보가 누락된 경우 테스트"""
    async with aiohttp.ClientSession() as session:
        api_client = KepcoApiClient(session)

        # Mock session method to raise KepcoAuthError
        with patch.object(api_client, 'async_get_session_and_rsa_key') as mock_session:
            mock_session.side_effect = KepcoAuthError("Failed to get RSA data")

            result = await api_client.async_login("test_user", "test_password")
            assert result is False


@pytest.mark.asyncio
async def test_async_get_recent_usage():
    """최근 사용량 조회 테스트"""
    async with aiohttp.ClientSession() as session:
        api_client = KepcoApiClient(session)

        # Mock _request method
        expected_data = {"result": {"F_AP_QT": "123.45", "KWH_BILL": "678"}}
        with patch.object(api_client, '_request') as mock_request:
            mock_request.return_value = expected_data

            data = await api_client.async_get_recent_usage()
            assert data["result"]["F_AP_QT"] == "123.45"
            assert data["result"]["KWH_BILL"] == "678"


@pytest.mark.asyncio
async def test_async_get_usage_info():
    """사용량 정보 조회 테스트"""
    async with aiohttp.ClientSession() as session:
        api_client = KepcoApiClient(session)

        # Mock _request method
        expected_data = {"result": {"BILL_LAST_MONTH": "10000", "PREDICT_TOTAL_CHARGE_REV": "15000"}}
        with patch.object(api_client, '_request') as mock_request:
            mock_request.return_value = expected_data

            data = await api_client.async_get_usage_info()
            assert data["result"]["BILL_LAST_MONTH"] == "10000"
            assert data["result"]["PREDICT_TOTAL_CHARGE_REV"] == "15000"


@pytest.mark.asyncio
async def test_set_credentials():
    """인증 정보 설정 테스트"""
    async with aiohttp.ClientSession() as session:
        api_client = KepcoApiClient(session)
        api_client.set_credentials("test_user", "test_password")
        assert api_client._username == "test_user"
        assert api_client._password == "test_password"

