"""
Correlation ID для логирования.

Позволяет отслеживать запросы через всю систему:
- Генерация уникального ID для каждого запроса
- Добавление ID во все лог-сообщения
- Передача ID между асинхронными вызовами

Usage:
    from services.logging.correlation import get_correlation_id, set_correlation_id

    async def handle_request():
        set_correlation_id(generate_correlation_id())
        logger.info("Начало обработки")
        # ... обработка ...
        logger.info(f"Завершено (correlation_id={get_correlation_id()})")
"""

import logging
import uuid
import asyncio
from contextvars import ContextVar
from typing import Optional
from functools import wraps

# ContextVar для хранения correlation ID в асинхронном контексте
_correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)


def generate_correlation_id() -> str:
    """
    Сгенерировать уникальный correlation ID.

    Returns:
        Уникальный ID формата 'corr-<uuid>'
    """
    return f"corr-{uuid.uuid4().hex[:12]}"


def get_correlation_id() -> Optional[str]:
    """
    Получить текущий correlation ID.

    Returns:
        correlation ID или None
    """
    return _correlation_id.get()


def set_correlation_id(correlation_id: str) -> None:
    """
    Установить correlation ID для текущего контекста.

    Args:
        correlation_id: correlation ID
    """
    _correlation_id.set(correlation_id)


def clear_correlation_id() -> None:
    """Очистить correlation ID."""
    _correlation_id.set(None)


class CorrelationIdFilter(logging.Filter):
    """
    Фильтр для добавления correlation ID в лог-сообщения.

    Usage:
        logger = logging.getLogger('my_logger')
        logger.addFilter(CorrelationIdFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Добавить correlation ID в запись лога.

        Args:
            record: Лог-запись

        Returns:
            True (всегда пропускать)
        """
        correlation_id = get_correlation_id()
        record.correlation_id = correlation_id or 'no-correlation-id'
        return True


def setup_correlation_logging(logger_name: Optional[str] = None) -> logging.Logger:
    """
    Настроить логгер с поддержкой correlation ID.

    Args:
        logger_name: Имя логгера (по умолчанию root)

    Returns:
        Настроенный логгер
    """
    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()

    # Добавляем фильтр
    logger.addFilter(CorrelationIdFilter())

    # Обновляем форматтер для включения correlation ID
    for handler in logger.handlers:
        formatter = handler.formatter
        if formatter:
            # Сохраняем старый формат и добавляем correlation_id
            old_format = formatter._fmt
            if '[%(correlation_id)]' not in old_format:
                new_format = old_format.replace(
                    '%(levelname)s',
                    '[%(correlation_id)] %(levelname)s'
                )
                formatter._fmt = new_format
                handler.setFormatter(formatter)

    return logger


def with_correlation_id(func):
    """
    Декоратор для автоматической установки correlation ID.

    Генерирует новый correlation ID для каждого вызова функции.

    Usage:
        @with_correlation_id
        async def handle_request(request):
            logger.info("Обработка запроса")
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Генерируем новый ID
        correlation_id = generate_correlation_id()
        token = _correlation_id.set(correlation_id)

        try:
            return await func(*args, **kwargs)
        finally:
            # Восстанавливаем предыдущее значение
            _correlation_id.reset(token)

    return wrapper


def with_correlation_id_sync(func):
    """
    Синхронная версия декоратора with_correlation_id.

    Usage:
        @with_correlation_id_sync
        def sync_function():
            logger.info("Синхронная функция")
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        correlation_id = generate_correlation_id()
        token = _correlation_id.set(correlation_id)

        try:
            return func(*args, **kwargs)
        finally:
            _correlation_id.reset(token)

    return wrapper


class CorrelationIdMiddleware:
    """
    Middleware для добавления correlation ID в запросы.

    Можно использовать с aiohttp, fastapi и другими фреймворками.

    Usage:
        app = Application()
        app.middleware(CorrelationIdMiddleware())
    """

    async def __call__(self, request, call_next):
        """
        Обработать запрос с correlation ID.

        Args:
            request: Запрос
            call_next: Следующий обработчик

        Returns:
            Ответ
        """
        # Получаем correlation ID из заголовков или генерируем новый
        correlation_id = request.headers.get(
            'X-Correlation-ID',
            generate_correlation_id()
        )

        # Устанавливаем в контекст
        set_correlation_id(correlation_id)

        # Вызываем следующий обработчик
        response = await call_next(request)

        # Добавляем correlation ID в ответ
        response.headers['X-Correlation-ID'] = correlation_id

        return response


def log_with_correlation(logger: logging.Logger, level: int, message: str, **kwargs) -> None:
    """
    Логировать сообщение с correlation ID.

    Args:
        logger: Логгер
        level: Уровень логирования
        message: Сообщение
        **kwargs: Дополнительные аргументы для лога
    """
    correlation_id = get_correlation_id()
    extra = kwargs.get('extra', {})
    extra['correlation_id'] = correlation_id
    kwargs['extra'] = extra

    logger.log(level, message, **kwargs)


# =============================================================================
# Интеграция с существующим логированием
# =============================================================================

def patch_existing_loggers():
    """
    Добавить поддержку correlation ID во все существующие логгеры.

    Вызывается один раз при старте приложения.
    """
    # Добавляем фильтр ко всем существующим хендлерам
    for logger_name in logging.root.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        if not any(isinstance(f, CorrelationIdFilter) for f in logger.filters):
            logger.addFilter(CorrelationIdFilter())

    # Добавляем фильтр к root логгеру
    if not any(isinstance(f, CorrelationIdFilter) for f in logging.root.filters):
        logging.root.addFilter(CorrelationIdFilter())
