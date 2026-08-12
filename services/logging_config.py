"""
Централизованная настройка логирования для всего проекта.

Использование:
    from services.logging_config import setup_logging, get_logger, correlation_context

    # Настройка в начале приложения (main.py)
    setup_logging()

    # Получение логгера в любом модуле
    logger = get_logger(__name__)

    # Использование correlation ID для отслеживания запросов/задач
    with correlation_context("task-123"):
        logger.info("Начало обработки задачи")
        # Все логи внутри контекста будут содержать correlation_id
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler
from functools import wraps
from typing import Optional, Callable, Any


# Форматы логов с поддержкой correlation ID
CONSOLE_FORMAT = logging.Formatter(
    fmt='[%(levelname)s] %(asctime)s — %(name)s — [%(correlation_id)s] — %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

FILE_FORMAT = logging.Formatter(
    fmt='[%(levelname)s] %(asctime)s — %(name)s — [%(correlation_id)s] — %(filename)s:%(lineno)d — %(message)s',
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
    'sqlalchemy.pool': logging.WARNING,
    'telethon': logging.WARNING,
    'aiogram': logging.WARNING,
    'asyncio': logging.WARNING,
}

# Context variable для хранения текущего correlation ID
_correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)


class CorrelationIdFilter(logging.Filter):
    """Фильтр для добавления correlation_id в записи логов."""

    def filter(self, record):
        record.correlation_id = _correlation_id.get() or '-'
        return True


# Фильтр для скрытия конкретных предупреждений SQLAlchemy о сборке мусора
class SQLAlchemyPoolFilter(logging.Filter):
    """Фильтр для скрытия предупреждений SQLAlchemy о non-checked-in connections."""

    def filter(self, record):
        # Скрываем сообщения о сборке мусора соединений
        if 'non-checked-in connection' in record.getMessage():
            return False
        # Скрываем сообщения о termination соединений
        if 'will be terminated' in record.getMessage():
            return False
        return True


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
    console_handler.addFilter(CorrelationIdFilter())  # Добавляем correlation_id
    root_logger.addHandler(console_handler)

    # === Применяем фильтр к SQLAlchemy ===
    sqlalchemy_logger = logging.getLogger('sqlalchemy.pool')
    sqlalchemy_logger.addFilter(SQLAlchemyPoolFilter())

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
            file_handler.addFilter(CorrelationIdFilter())  # Добавляем correlation_id
            root_logger.addHandler(file_handler)
        except (PermissionError, OSError) as e:
            # Если не удалось создать файл, логируем в консоль предупреждение
            root_logger.warning(f"Не удалось создать файл лога: {e}. Логи только в консоль.")

    # === Настраиваем уровни для конкретных логгеров ===
    for logger_name, logger_level in LOGGERS_LEVELS.items():
        logging.getLogger(logger_name).setLevel(logger_level)

    # Логгируем успешную инициализацию (только в файл, не в консоль)
    logger = logging.getLogger('services.logging')
    if log_to_file:
        # Создаём временный файловый хендлер для сообщения об инициализации
        init_logger = logging.getLogger('services.logging.init')
        init_logger.info("📝 Система логирования инициализирована")
        init_logger.info(f"📁 Логи записываются в: {get_log_file_path()}")


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


class CorrelationContext:
    """
    Контекстный менеджер для установки correlation_id.

    Все логи внутри контекста будут содержать указанный correlation_id.

    Пример использования:
        with correlation_context("task-123"):
            logger.info("Обработка задачи")

        # Или с автоматически сгенерированным ID
        with correlation_context():
            logger.info("Запрос с новым ID")
    """

    def __init__(self, correlation_id: Optional[str] = None):
        self.correlation_id = correlation_id or str(uuid.uuid4())[:8]
        self._token: Any = None

    def __enter__(self):
        self._token = _correlation_id.set(self.correlation_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._token is not None:
            _correlation_id.reset(self._token)


def correlation_context(correlation_id: Optional[str] = None) -> CorrelationContext:
    """
    Фабричная функция для создания контекста correlation_id.

    Args:
        correlation_id: Опциональный ID. Если не указан, генерируется новый.

    Returns:
        CorrelationContext для использования в with

    Пример:
        with correlation_context("req-abc123"):
            logger.info("Лог с correlation_id=req-abc123")
    """
    return CorrelationContext(correlation_id)


def get_correlation_id() -> Optional[str]:
    """
    Получает текущий correlation_id из контекста.

    Returns:
        Текущий correlation_id или None, если не установлен
    """
    return _correlation_id.get()


def set_correlation_id(correlation_id: Optional[str]) -> Any:
    """
    Устанавливает correlation_id в текущий контекст.

    Args:
        correlation_id: ID для установки или None для сброса

    Returns:
        Token для последующего сброса через reset_correlation_id

    Пример:
        token = set_correlation_id("task-456")
        try:
            # обработка
        finally:
            reset_correlation_id(token)
    """
    return _correlation_id.set(correlation_id)


def reset_correlation_id(token: Any) -> None:
    """
    Сбрасывает correlation_id к предыдущему значению.

    Args:
        Token, полученный из set_correlation_id
    """
    _correlation_id.reset(token)


def with_correlation(correlation_id: Optional[str] = None) -> Callable:
    """
    Декоратор для автоматической установки correlation_id на время выполнения функции.

    Args:
        correlation_id: Опциональный ID. Если не указан, генерируется новый.

    Returns:
        Декоратор для функции

    Пример:
        @with_correlation("handler-123")
        async def handle_request():
            logger.info("Этот лог будет с correlation_id=handler-123")
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            ctx = CorrelationContext(correlation_id)
            with ctx:
                return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            ctx = CorrelationContext(correlation_id)
            with ctx:
                return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
