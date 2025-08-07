import unittest
from unittest.mock import patch, MagicMock
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from custom_components.korea_incubator.kepco.api import KepcoApiClient
import aiohttp


class TestKepcoRSAEncryption(unittest.TestCase):

    def setUp(self):
        """테스트 초기화"""
        self.session = MagicMock(spec=aiohttp.ClientSession)
        self.client = KepcoApiClient(self.session)

        # 테스트용 RSA 키 생성
        self.test_key = RSA.generate(1024)
        self.test_modulus = hex(self.test_key.n)[2:]  # 0x 제거
        self.test_exponent = hex(self.test_key.e)[2:]  # 0x 제거
        self.test_sessid = "TEST_SESSION_ID_123"

    def test_rsa_key_construction(self):
        """RSA 키 구성 테스트"""
        # Given
        modulus_hex = self.test_modulus
        exponent_hex = self.test_exponent

        # When
        modulus_int = int(modulus_hex, 16)
        exponent_int = int(exponent_hex, 16)
        key = RSA.construct((modulus_int, exponent_int))

        # Then
        self.assertIsInstance(key, RSA.RsaKey)
        self.assertEqual(key.n, modulus_int)
        self.assertEqual(key.e, exponent_int)

    def test_rsa_encryption_decryption(self):
        """RSA 암호화/복호화 테스트"""
        # Given
        test_username = "testuser"
        test_password = "testpass123"

        # When - 암호화
        cipher_encrypt = PKCS1_v1_5.new(self.test_key.publickey())
        encrypted_username = cipher_encrypt.encrypt(test_username.encode('utf-8'))
        encrypted_password = cipher_encrypt.encrypt(test_password.encode('utf-8'))

        # When - 복호화 (검증용)
        cipher_decrypt = PKCS1_v1_5.new(self.test_key)
        decrypted_username = cipher_decrypt.decrypt(encrypted_username, None)
        decrypted_password = cipher_decrypt.decrypt(encrypted_password, None)

        # Then
        self.assertEqual(decrypted_username.decode('utf-8'), test_username)
        self.assertEqual(decrypted_password.decode('utf-8'), test_password)

    def test_hex_conversion(self):
        """16진수 변환 테스트"""
        # Given
        test_data = "test_string"

        # When
        cipher = PKCS1_v1_5.new(self.test_key.publickey())
        encrypted_bytes = cipher.encrypt(test_data.encode('utf-8'))
        encrypted_hex = encrypted_bytes.hex()

        # Then
        self.assertIsInstance(encrypted_hex, str)
        self.assertTrue(all(c in '0123456789abcdef' for c in encrypted_hex))
        self.assertEqual(len(encrypted_hex) % 2, 0)  # 짝수 길이여야 함

    def test_user_credential_formatting(self):
        """사용자 인증 정보 포매팅 테스트"""
        # Given
        sessid = "TEST_SESSION_123"
        encrypted_username_hex = "deadbeef"
        encrypted_password_hex = "cafebabe"

        # When
        user_id = f"{sessid}_{encrypted_username_hex}"
        user_pw = f"{sessid}_{encrypted_password_hex}"

        # Then
        self.assertEqual(user_id, "TEST_SESSION_123_deadbeef")
        self.assertEqual(user_pw, "TEST_SESSION_123_cafebabe")
        self.assertIn("_", user_id)
        self.assertIn("_", user_pw)

    def test_encryption_with_invalid_key_params(self):
        """잘못된 키 매개변수로 암호화 테스트"""
        # Given
        invalid_modulus = "invalid_hex"
        valid_exponent = "10001"

        # When & Then
        with self.assertRaises(ValueError):
            modulus_int = int(invalid_modulus, 16)

    def test_encryption_with_empty_credentials(self):
        """빈 인증 정보로 암호화 테스트"""
        # Given
        empty_username = ""
        empty_password = ""

        # When
        cipher = PKCS1_v1_5.new(self.test_key.publickey())
        encrypted_username = cipher.encrypt(empty_username.encode('utf-8'))
        encrypted_password = cipher.encrypt(empty_password.encode('utf-8'))

        # Then
        self.assertIsInstance(encrypted_username, bytes)
        self.assertIsInstance(encrypted_password, bytes)
        self.assertGreater(len(encrypted_username), 0)
        self.assertGreater(len(encrypted_password), 0)

    def test_encryption_with_unicode_credentials(self):
        """유니코드 인증 정보로 암호화 테스트"""
        # Given
        unicode_username = "사용자명"
        unicode_password = "비밀번호123"

        # When
        cipher = PKCS1_v1_5.new(self.test_key.publickey())
        encrypted_username = cipher.encrypt(unicode_username.encode('utf-8'))
        encrypted_password = cipher.encrypt(unicode_password.encode('utf-8'))

        # Then
        self.assertIsInstance(encrypted_username, bytes)
        self.assertIsInstance(encrypted_password, bytes)

        # 복호화로 검증
        cipher_decrypt = PKCS1_v1_5.new(self.test_key)
        decrypted_username = cipher_decrypt.decrypt(encrypted_username, None)
        decrypted_password = cipher_decrypt.decrypt(encrypted_password, None)

        self.assertEqual(decrypted_username.decode('utf-8'), unicode_username)
        self.assertEqual(decrypted_password.decode('utf-8'), unicode_password)


if __name__ == '__main__':
    unittest.main()
