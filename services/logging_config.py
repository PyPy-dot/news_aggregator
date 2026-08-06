"""
Централизованная настройка логирования для всего проекта.

Использование:
    from services.logging_config import setup_logging, get_logger

    # Настройка в начале приложения (main.py)
    setup_logging()

    # Получение логгера в любом модуле
    logger = get_logger(__name__)
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler


# Форматы логов
CONSOLE_FORMAT = logging.Formatter(
    fmt='[%(levelname)s] %(asctime)s — %(name)s — %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

FILE_FORMAT = logging.Formatter(
    fmt='[%(levelname)s] %(asctime)s — %(name)s — %(filename)s:%(lineno)d — %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Уровни логирования по умолчанию
DEFAULT_LEVEL = logging.INFO
LOGGERS_LEVELS = {
    '__main__': logging.INFO,
    'services': logging.INFO,
    'database': logging.INFO,
    'sqlalchemy': logging.WARNING,
    'sqlalchemy.engine': logging.ERROR,
    'telethon': logging.WARNING,
    'aiogram': logging.WARNING,
    'asyncio': logging.WARNING,
}


def get_log_directory() -> Path:
    """Возвращает путь к директории для логов."""
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)
    return log_dir


def get_log_file_path() -> Path:
    """Возвращает путь к файлу лога с текущей датой."""
    log_dir = get_log_directory()
    date_str = datetime.now().strftime('%Y-%m-%d')
    return log_dir / f'news_aggregator_{date_str}.log'


def setup_logging(
    level: int = DEFAULT_LEVEL,
    log_to_file: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 7,
) -> None:
    """
    Настраивает централизованное логирование для всего приложения.

    Args:
        level: Базовый уровень логирования
        log_to_file: Писать ли логи в файл
        max_bytes: Максимальный размер файла лога перед ротацией
        backup_count: Количество файлов резервных копий
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Корневой логгер ловит всё

    # Очищаем существующие хендлеры (чтобы не дублировать при перезапуске)
    root_logger.handlers.clear()

    # === Консольный хендлер ===
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(CONSOLE_FORMAT)
    root_logger.addHandler(console_handler)

    # === Файловый хендлер с ротацией ===
    if log_to_file:
        try:
            log_path = get_log_file_path()
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8',
                delay=True  # Не создавать файл пока не будет первой записи
            )
            file_handler.setLevel(logging.DEBUG)  # В файл пишем всё
            file_handler.setFormatter(FILE_FORMAT)
            root_logger.addHandler(file_handler)
        except (PermissionError, OSError) as e:
            # Если не удалось создать файл, логируем в консоль предупреждение
            root_logger.warning(f"Не удалось создать файл лога: {e}. Логи только в консоль.")

    # === Настраиваем уровни для конкретных логгеров ===
    for logger_name, logger_level in LOGGERS_LEVELS.items():
        logging.getLogger(logger_name).setLevel(logger_level)

    # Логгируем успешную инициализацию
    logger = logging.getLogger('services.logging')
    logger.info("📝 Система логирования инициализирована")
    if log_to_file:
        logger.info(f"📁 Логи записываются в: {get_log_file_path()}")


def get_logger(name: str) -> logging.Logger:
    """
    Получает настроенный логгер по имени.

    Args:
        name: Имя логгера (обычно __name__ модуля)

    Returns:
        Настроенный экземпляр logging.Logger
    """
    return logging.getLogger(name)


def get_error_logger() -> logging.Logger:
    """
    Получает специализированный логгер для ошибок.
    Удобен для записи критических ошибок.

    Returns:
        Логгер с именем 'services.errors'
    """
    return logging.getLogger('services.errors')


class LoggingContext:
    """
    Контекстный менеджер для временного изменения уровня логирования.

    Пример использования:
        with LoggingContext('sqlalchemy', logging.DEBUG):
            # В этом блоке sqlalchemy будет логировать DEBUG
            perform_operation()
    """

    def __init__(self, logger_name: str, temporary_level: int):
        self.logger_name = logger_name
        self.temporary_level = temporary_level
        self._original_level: int | None = None
        self._logger: logging.Logger | None = None

    def __enter__(self):
        self._logger = logging.getLogger(self.logger_name)
        self._original_level = self._logger.level
        self._logger.setLevel(self.temporary_level)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._logger is not None and self._original_level is not None:
            self._logger.setLevel(self._original_level)
