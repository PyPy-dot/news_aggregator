"""
Тесты для 2FA сервиса (TOTP).

Проверяет:
1. Генерация TOTP секретов
2. Создание provisioning URI
3. Проверка TOTP кодов
4. Генерация и проверка резервных кодов
"""

import pytest
import json

from services.auth.two_factor_auth import TwoFactorAuthService, get_2fa_service


class TestTwoFactorAuthService:
    """Тесты для TwoFactorAuthService."""

    @pytest.fixture
    def service(self) -> TwoFactorAuthService:
        """Создать сервис для тестов."""
        return TwoFactorAuthService(issuer="Test News Aggregator")

    def test_generate_secret(self, service: TwoFactorAuthService):
        """Генерация TOTP секрета."""
        secret = service.generate_secret()

        # Секрет должен быть строкой Base32 (32 символа)
        assert isinstance(secret, str)
        assert len(secret) == 32
        # Base32 использует A-Z и 2-7
        assert all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567=' for c in secret)

    def test_generate_secret_unique(self, service: TwoFactorAuthService):
        """Каждый вызов generate_secret возвращает уникальный секрет."""
        secrets = [service.generate_secret() for _ in range(10)]
        # Все секреты должны быть уникальны
        assert len(set(secrets)) == 10

    def test_get_provisioning_uri(self, service: TwoFactorAuthService):
        """Создание provisioning URI."""
        secret = service.generate_secret()
        username = "test_admin"

        uri = service.get_provisioning_uri(secret, username)

        assert uri.startswith("otpauth://totp/")
        assert "test_admin" in uri
        assert "Test+News+Aggregator" in uri or "Test%20News%20Aggregator" in uri
        assert secret in uri

    def test_generate_qr_code(self, service: TwoFactorAuthService):
        """Генерация QR-кода."""
        secret = service.generate_secret()
        uri = service.get_provisioning_uri(secret, "test_admin")

        qr_bytes = service.generate_qr_code(uri)

        # QR-код должен быть PNG изображением
        assert isinstance(qr_bytes, bytes)
        assert len(qr_bytes) > 0
        # PNG начинается с сигнатуры
        assert qr_bytes[:8] == b'\x89PNG\r\n\x1a\n'

    def test_get_qr_code_as_base64(self, service: TwoFactorAuthService):
        """Получение QR-кода в base64."""
        secret = service.generate_secret()
        uri = service.get_provisioning_uri(secret, "test_admin")

        base64_qr = service.get_qr_code_as_base64(uri)

        assert isinstance(base64_qr, str)
        assert len(base64_qr) > 0
        # Base64 содержит только допустимые символы
        assert all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=' for c in base64_qr)

    def test_verify_code_correct(self, service: TwoFactorAuthService):
        """Проверка правильного TOTP кода."""
        secret = service.generate_secret()

        # Генерируем текущий код
        import pyotp
        totp = pyotp.TOTP(secret, digits=6, interval=30, issuer=service.issuer)
        current_code = totp.now()

        # Проверяем код
        assert service.verify_code(secret, current_code) is True

    def test_verify_code_incorrect(self, service: TwoFactorAuthService):
        """Проверка неправильного TOTP кода."""
        secret = service.generate_secret()

        # Неправильный код
        assert service.verify_code(secret, "000000") is False
        assert service.verify_code(secret, "999999") is False
        assert service.verify_code(secret, "abcdef") is False

    def test_verify_code_empty_secret(self, service: TwoFactorAuthService):
        """Проверка кода с пустым секретом."""
        assert service.verify_code("", "123456") is False

    def test_generate_backup_codes(self, service: TwoFactorAuthService):
        """Генерация резервных кодов."""
        codes = service.generate_backup_codes(count=10)

        assert isinstance(codes, list)
        assert len(codes) == 10
        # Все коды уникальны
        assert len(set(codes)) == 10
        # Каждый код - строка
        assert all(isinstance(code, str) for code in codes)
        # Коды достаточно длинные (минимум 6 символов)
        assert all(len(code) >= 6 for code in codes)

    def test_generate_backup_codes_custom_count(self, service: TwoFactorAuthService):
        """Генерация резервных кодов с_custom количеством."""
        codes = service.generate_backup_codes(count=5)
        assert len(codes) == 5

        codes = service.generate_backup_codes(count=20)
        assert len(codes) == 20

    def test_serialize_backup_codes(self, service: TwoFactorAuthService):
        """Сериализация резервных кодов в JSON."""
        codes = ["code1", "code2", "code3"]

        json_str = service.serialize_backup_codes(codes)

        assert isinstance(json_str, str)
        # Можно распарсить обратно
        parsed = json.loads(json_str)
        assert parsed == codes

    def test_verify_backup_code_correct(
        self, service: TwoFactorAuthService
    ):
        """Проверка правильного резервного кода."""
        codes = ["code1", "code2", "code3"]
        codes_json = service.serialize_backup_codes(codes)

        # Проверяем code2
        is_valid, new_codes_json = service.verify_backup_code(codes_json, "code2")

        assert is_valid is True
        assert new_codes_json is not None

        # Проверяем, что code2 удалён
        new_codes = json.loads(new_codes_json)
        assert "code2" not in new_codes
        assert "code1" in new_codes
        assert "code3" in new_codes
        assert len(new_codes) == 2

    def test_verify_backup_code_incorrect(
        self, service: TwoFactorAuthService
    ):
        """Проверка неправильного резервного кода."""
        codes = ["code1", "code2", "code3"]
        codes_json = service.serialize_backup_codes(codes)

        # Неправильный код
        is_valid, new_codes_json = service.verify_backup_code(codes_json, "wrong_code")

        assert is_valid is False
        assert new_codes_json is None

    def test_verify_backup_code_empty(
        self, service: TwoFactorAuthService
    ):
        """Проверка резервного кода при отсутствии кодов."""
        is_valid, new_codes_json = service.verify_backup_code(None, "code1")
        assert is_valid is False
        assert new_codes_json is None

        is_valid, new_codes_json = service.verify_backup_code("[]", "code1")
        assert is_valid is False
        assert new_codes_json is None

    def test_verify_backup_code_consumed(
        self, service: TwoFactorAuthService
    ):
        """Повторное использование резервного кода невозможно."""
        codes = ["single_code"]
        codes_json = service.serialize_backup_codes(codes)

        # Первое использование — успешно
        is_valid, new_codes_json = service.verify_backup_code(codes_json, "single_code")
        assert is_valid is True

        # Повторное использование — неудачно (код уже удалён)
        is_valid, new_codes_json = service.verify_backup_code(new_codes_json, "single_code")
        assert is_valid is False


class TestTwoFactorService_Integration:
    """Интеграционные тесты для 2FA."""

    def test_full_2fa_flow(self):
        """Полный цикл настройки и использования 2FA."""
        service = TwoFactorAuthService(issuer="Test")

        # 1. Генерация секрета
        secret = service.generate_secret()
        assert len(secret) == 32

        # 2. Создание URI
        uri = service.get_provisioning_uri(secret, "test_user")
        assert "test_user" in uri

        # 3. Генерация QR-кода
        qr_bytes = service.generate_qr_code(uri)
        assert len(qr_bytes) > 0

        # 4. Проверка TOTP кода
        import pyotp
        totp = pyotp.TOTP(secret, digits=6, interval=30)
        current_code = totp.now()
        assert service.verify_code(secret, current_code) is True

        # 5. Генерация резервных кодов
        backup_codes = service.generate_backup_codes(count=5)
        assert len(backup_codes) == 5

        # 6. Использование резервного кода
        codes_json = service.serialize_backup_codes(backup_codes)
        is_valid, new_codes_json = service.verify_backup_code(codes_json, backup_codes[0])
        assert is_valid is True
        assert new_codes_json is not None

        # 7. Проверка, что код удалён
        new_codes = json.loads(new_codes_json)
        assert backup_codes[0] not in new_codes
        assert len(new_codes) == 4

    def test_get_2fa_service_singleton(self):
        """get_2fa_service возвращает singleton."""
        service1 = get_2fa_service()
        service2 = get_2fa_service()

        # Должен возвращаться один и тот же экземпляр
        assert service1 is service2
