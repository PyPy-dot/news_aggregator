"""
2FA Service (TOTP) для администраторов.

Сервис для управления двухфакторной аутентификацией:
- Генерация TOTP секретов
- Создание QR-кодов для Google Authenticator / Яндекс.Ключ / Authy
- Проверка TOTP кодов
- Генерация и проверка резервных кодов

Использует библиотеку pyotp для TOTP.

Поддерживаемые провайдеры:
- google — Google Authenticator (стандартный otpauth://)
- yandex — Яндекс.Ключ (специальный формат URI)
"""

import base64
import json
import logging
import secrets
from typing import Optional, Tuple, Literal

import pyotp
import qrcode
from io import BytesIO

logger = logging.getLogger(__name__)

# Типы провайдеров
ProviderType = Literal['google', 'yandex']


class TwoFactorAuthService:
    """
    Сервис для управления 2FA (TOTP) аутентификацией.

    TOTP (Time-based One-Time Password) — алгоритм генерации
    одноразовых паролей на основе времени и секретного ключа.

    Параметры:
    - issuer: Название сервиса для отображения в аутентификаторе
    - digits: Количество цифр в коде (по умолчанию 6)
    - interval: Интервал обновления кода в секундах (по умолчанию 30)
    - provider: Провайдер аутентификатора ('google' или 'yandex')
    """

    def __init__(
        self,
        issuer: str = "News Aggregator",
        digits: int = 6,
        interval: int = 30,
        provider: ProviderType = 'google'
    ):
        self.issuer = issuer
        self.digits = digits
        self.interval = interval
        self.provider = provider

    def generate_secret(self) -> str:
        """
        Сгенерировать новый TOTP секрет.

        Returns:
            str: Base32-encoded секрет (32 символа)
        """
        secret = pyotp.random_base32()
        logger.debug(f"Сгенерирован новый TOTP секрет (длина: {len(secret)})")
        return secret

    def get_provisioning_uri(
        self,
        secret: str,
        username: str
    ) -> str:
        """
        Создать URI для настройки аутентификатора.

        Args:
            secret: TOTP секрет
            username: Имя пользователя (email или username)

        Returns:
            str: otpauth:// URI для QR-кода
        """
        if self.provider == 'yandex':
            # Яндекс.Ключ использует специальный формат
            # См: https://yandex.ru/dev/id/doc/en/authorized/one-time-passwords
            uri = (
                f"otpauth://totp/{self.issuer}:{username}?"
                f"secret={secret}&"
                f"issuer={self.issuer}&"
                f"algorithm=SHA1&"
                f"digits={self.digits}&"
                f"period={self.interval}"
            )
            logger.debug(f"Создан provisioning URI для Яндекс.Ключ ({username})")
            return uri
        else:
            # Стандартный формат для Google Authenticator
            totp = pyotp.TOTP(
                secret,
                digits=self.digits,
                interval=self.interval,
                issuer=self.issuer
            )
            uri = totp.provisioning_uri(
                name=username,
                issuer_name=self.issuer
            )
            logger.debug(f"Создан provisioning URI для Google Authenticator ({username})")
            return uri

    def get_setup_instructions(self) -> str:
        """
        Получить инструкцию по настройке для текущего провайдера.

        Returns:
            str: Текст инструкции
        """
        if self.provider == 'yandex':
            return (
                "🔐 **Настройка 2FA через Яндекс.Ключ**\n\n"
                "1. Откройте приложение **Яндекс.Ключ**\n"
                "2. Нажмите **"+"** (добавить ключ)\n"
                "3. Выберите **Ввести ключ вручную** или отсканируйте QR-код\n"
                "4. Введите название: `News Aggregator`\n"
                "5. Введите ключ из сообщения ниже\n"
                "6. Введите 6-значный код из приложения\n\n"
                "_Яндекс.Ключ доступен для [iOS](https://apps.apple.com/app/yandex-key/id1553694557) "
                "и [Android](https://play.google.com/store/apps/details?id=com.yandex.key)_"
            )
        else:
            return (
                "🔐 **Настройка 2FA через Google Authenticator**\n\n"
                "1. Откройте приложение **Google Authenticator**\n"
                "2. Нажмите **"+"** → **Сканировать QR-код**\n"
                "3. Отсканируйте QR-код ниже\n"
                "4. Введите 6-значный код из приложения\n\n"
                "_Также поддерживается **Authy**, **Microsoft Authenticator**, **2FAS** и другие TOTP-приложения_"
            )

    def generate_qr_code(self, uri: str) -> bytes:
        """
        Сгенерировать QR-код для URI.

        Args:
            uri: otpauth:// URI

        Returns:
            bytes: PNG изображение QR-кода
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4
        )
        qr.add_data(uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Сохраняем в bytes
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        logger.debug(f"Сгенерирован QR-код (размер: {buffer.tell()} байт)")
        return buffer.getvalue()

    def verify_code(self, secret: str, code: str) -> bool:
        """
        Проверить TOTP код.

        Args:
            secret: TOTP секрет пользователя
            code: 6-значный код из аутентификатора

        Returns:
            bool: True если код верный
        """
        totp = pyotp.TOTP(
            secret,
            digits=self.digits,
            interval=self.interval,
            issuer=self.issuer
        )

        # Проверяем код с допуском ±1 интервала (90 секунд)
        is_valid = totp.verify(code, valid_window=1)

        if is_valid:
            logger.debug("TOTP код верный")
        else:
            logger.warning("TOTP код неверный")

        return is_valid

    def generate_backup_codes(self, count: int = 10) -> list[str]:
        """
        Сгенерировать резервные коды для восстановления.

        Args:
            count: Количество кодов (по умолчанию 10)

        Returns:
            list[str]: Список кодов (по 8 символов каждый)
        """
        codes = []
        for _ in range(count):
            # Генерируем код из 8 символов (буквы + цифры)
            code = secrets.token_urlsafe(6)  # ~8 символов
            codes.append(code)

        logger.debug(f"Сгенерировано {len(codes)} резервных кодов")
        return codes

    def verify_backup_code(
        self,
        backup_codes_json: Optional[str],
        code: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Проверить резервный код и удалить его после использования.

        Args:
            backup_codes_json: JSON строка с резервными кодами
            code: Код для проверки

        Returns:
            Tuple[bool, Optional[str]]:
                - True если код верный, и новая JSON строка без использованного кода
                - (False, None) если код неверный или коды отсутствуют
        """
        if not backup_codes_json:
            logger.warning("Резервные коды отсутствуют")
            return False, None

        try:
            codes = json.loads(backup_codes_json)
        except json.JSONDecodeError:
            logger.error("Ошибка парсинга резервных кодов")
            return False, None

        if code in codes:
            # Удаляем использованный код
            codes.remove(code)
            new_codes_json = json.dumps(codes, ensure_ascii=False)
            logger.info(f"Резервный код использован, осталось {len(codes)} кодов")
            return True, new_codes_json

        logger.warning("Неверный резервный код")
        return False, None

    def serialize_backup_codes(self, codes: list[str]) -> str:
        """
        Сериализовать резервные коды в JSON строку.

        Args:
            codes: Список кодов

        Returns:
            str: JSON строка
        """
        return json.dumps(codes, ensure_ascii=False)

    def get_qr_code_as_base64(self, uri: str) -> str:
        """
        Получить QR-код в формате base64 для отображения в Telegram.

        Args:
            uri: otpauth:// URI

        Returns:
            str: Base64-encoded PNG изображение
        """
        qr_bytes = self.generate_qr_code(uri)
        return base64.b64encode(qr_bytes).decode('utf-8')


# Singleton для глобального доступа
_2fa_service: Optional[TwoFactorAuthService] = None
_2fa_provider: Optional[ProviderType] = None


def get_2fa_service(provider: Optional[ProviderType] = None) -> TwoFactorAuthService:
    """
    Получить экземпляр 2FA сервиса.

    Args:
        provider: Провайдер ('google' или 'yandex'). Если не указан, используется из настроек.

    Returns:
        TwoFactorAuthService экземпляр
    """
    global _2fa_service, _2fa_provider

    # Определяем провайдер
    if provider is None:
        # Читаем из настроек
        try:
            from config.settings import settings
            provider = getattr(settings, 'listener_2fa_provider', 'google')
            if provider not in ('google', 'yandex'):
                provider = 'google'
        except Exception:
            provider = 'google'

    # Создаём новый сервис если провайдер изменился или сервис ещё не создан
    if _2fa_service is None or _2fa_provider != provider:
        _2fa_service = TwoFactorAuthService(provider=provider)
        _2fa_provider = provider
        logger.info(f"2FA сервис инициализирован с провайдером: {provider}")

    return _2fa_service
