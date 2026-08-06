"""
Утилиты для сервиса.
"""

import logging
import os
import traceback
from base64 import b64encode, b64decode
from hashlib import sha256
from pathlib import Path
from typing import Any

from services.logging_config import get_logger

logger = get_logger(__name__)


def load_prompt(name: str, prompts_dir: Path | None = None) -> str:
    """
    Загружает промпт из файла prompts/<name>.txt.

    Args:
        name: Имя файла без расширения
        prompts_dir: Директория с промптами (по умолчанию: проект/prompts)

    Returns:
        Содержимое файла промпта

    Raises:
        FileNotFoundError: Если файл не найден
    """
    if prompts_dir is None:
        # Путь относительно корня проекта
        prompts_dir = Path(__file__).parent.parent / 'prompts'

    prompt_path = prompts_dir / f'{name}.txt'

    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Промпт не найден: {prompt_path}"
        )

    content = prompt_path.read_text(encoding='utf8')
    logger.debug(f"Промпт загружен из: {prompt_path}")

    return content


def truncate_text(text: str, max_length: int = 100, suffix: str = '...') -> str:
    """
    Обрезает текст до указанной длины.

    Args:
        text: Текст для обрезки
        max_length: Максимальная длина
        suffix: Суффикс для обрезанного текста

    Returns:
        Обрезанный текст
    """
    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


def format_number(number: int | float, locale: str = 'ru') -> str:
    """
    Форматирует число с разделителями тысяч.

    Args:
        number: Число для форматирования
        locale: Локаль ('ru' или 'en')

    Returns:
        Отформатированное число
    """
    if locale == 'ru':
        return f'{number:,}'.replace(',', ' ').replace('.', ',')
    else:
        return f'{number:,}'


def log_error(
    error: Exception,
    context: dict[str, Any] | None = None,
    logger_name: str | None = None,
) -> None:
    """
    Логирует ошибку с полным трассировкой и контекстом.

    Args:
        error: Исключение для логирования
        context: Дополнительный контекст (dict)
        logger_name: Имя логгера (по умолчанию использует logger из util.py)
    """
    log = get_logger(logger_name) if logger_name else logger

    error_info = {
        'type': type(error).__name__,
        'message': str(error),
        'traceback': traceback.format_exc(),
    }

    if context:
        error_info['context'] = context

    log.error(
        f"❌ Ошибка: {error_info['type']} — {error_info['message']}\n"
        f"Трассировка:\n{error_info['traceback']}"
    )


def log_execution_time(func_name: str, elapsed_ms: float) -> None:
    """
    Логирует время выполнения функции.

    Args:
        func_name: Имя функции
        elapsed_ms: Время выполнения в миллисекундах
    """
    if elapsed_ms > 1000:
        logger.warning(f"⏱ {func_name} выполнено за {elapsed_ms:.0f} мс (>1с)")
    else:
        logger.debug(f"⏱ {func_name} выполнено за {elapsed_ms:.2f} мс")


class ExecutionTimer:
    """
    Контекстный менеджер для замера и логирования времени выполнения блока кода.

    Пример использования:
        with ExecutionTimer("process_news", logger_name="services.news"):
            process_news(data)
    """

    def __init__(
        self,
        operation_name: str,
        logger_name: str | None = None,
        log_level: int = logging.DEBUG,
    ):
        self.operation_name = operation_name
        self.logger_name = logger_name
        self.log_level = log_level
        self._start_time: float | None = None
        self._logger: logging.Logger | None = None

    def __enter__(self):
        import time
        self._start_time = time.time()
        self._logger = get_logger(self.logger_name) if self.logger_name else logger
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        elapsed_ms = (time.time() - self._start_time) * 1000

        if exc_type is not None:
            self._logger.error(
                f"❌ {self.operation_name} завершился ошибкой за {elapsed_ms:.0f} мс: {exc_val}"
            )
        else:
            self._logger.log(
                self.log_level if elapsed_ms <= 1000 else logging.WARNING,
                f"✅ {self.operation_name} выполнен за {elapsed_ms:.2f} мс"
            )

        return False  # Не подавляем исключения


# === Шифрование user_id ===

DEFAULT_ENCRYPTION_KEY = "news_aggregator_default_key_change_in_prod"


def get_encryption_key() -> bytes:
    """
    Получить ключ шифрования из окружения или использовать дефолтный.

    Returns:
        32-байтовый ключ для AES-256
    """
    key = os.getenv('ENCRYPTION_KEY', DEFAULT_ENCRYPTION_KEY)
    return sha256(key.encode()).digest()


def encrypt_user_id(user_id: int, key: bytes | None = None) -> str:
    """
    Зашифровать user_id используя AES-256-GCM.

    Args:
        user_id: ID пользователя Telegram
        key: Ключ шифрования (если None, берётся из окружения)

    Returns:
        Base64-encoded строка с encrypted_data (nonce + ciphertext + tag)
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if key is None:
        key = get_encryption_key()

    nonce = os.urandom(12)
    plaintext = str(user_id).encode('utf-8')

    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    encrypted = b64encode(nonce + ciphertext).decode('utf-8')
    return encrypted


def decrypt_user_id(encrypted: str, key: bytes | None = None) -> int:
    """
    Расшифровать user_id.

    Args:
        encrypted: Base64-encoded строка с encrypted_data
        key: Ключ шифрования (если None, берётся из окружения)

    Returns:
        Оригинальный user_id как int

    Raises:
        ValueError: Если не удалось расшифровать
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if key is None:
        key = get_encryption_key()

    data = b64decode(encrypted)
    nonce = data[:12]
    ciphertext = data[12:]

    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)

    return int(plaintext.decode('utf-8'))


def hash_user_id_for_lookup(user_id: int, key: bytes | None = None) -> str:
    """
    Создать детерминированный хэш user_id для поиска в БД.

    Использует HMAC-SHA256 для получения стабильного значения,
    которое можно использовать для поиска в базе данных.

    Args:
        user_id: ID пользователя Telegram
        key: Ключ шифрования (если None, берётся из окружения)

    Returns:
        Base64-encoded HMAC-SHA256 хэш
    """
    import hmac

    if key is None:
        key = get_encryption_key()

    h = hmac.new(key, str(user_id).encode('utf-8'), 'sha256')
    return b64encode(h.digest()).decode('utf-8')
