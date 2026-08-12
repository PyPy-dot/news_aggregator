"""
Structured JSON Logging — структурированное логирование для ELK/Loki.

Формат логов:
{
    "timestamp": "2026-08-10T12:00:00.123Z",
    "level": "INFO",
    "message": "User logged in",
    "logger": "services.bot.handlers.commands",
    "module": "commands",
    "function": "start_handler",
    "line": 42,
    "thread": "MainThread",
    "thread_id": 12345,
    "extra": {"user_id": 123456, "action": "login"}
}

Usage:
    from services.logging_json import setup_json_logging, get_logger

    # Настройка логирования
    setup_json_logging(
        level="INFO",
        log_to_file=True,
        log_file="logs/app.json.log",
        include_extra_context=True,
    )

    # Получение логгера
    logger = get_logger(__name__)
    logger.info("User logged in", extra={"user_id": 123456})
"""

import logging
import sys
import json
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path
import asyncio


class JSONFormatter(logging.Formatter):
    """
    JSON форматтер для структурированного логирования.

    Добавляет поля:
    - timestamp (ISO 8601, UTC)
    - level (INFO, ERROR, и т.д.)
    - message (основное сообщение)
    - logger (имя логгера)
    - module, function, line (позиция в коде)
    - thread, thread_id (поток)
    - extra (дополнительный контекст из extra={})
    - exception (traceback при ошибке)
    """

    def __init__(
        self,
        include_extra: bool = True,
        include_stack_info: bool = True,
        include_thread: bool = True,
        timestamp_format: str = "iso",
    ) -> None:
        """
        Инициализация JSON форматтера.

        Args:
            include_extra: Включать ли extra контекст
            include_stack_info: Включать ли stack info
            include_thread: Включать ли информацию о потоке
            timestamp_format: Формат времени ("iso" или custom format string)
        """
        super().__init__()
        self.include_extra = include_extra
        self.include_stack_info = include_stack_info
        self.include_thread = include_thread
        self.timestamp_format = timestamp_format

    def format(self, record: logging.LogRecord) -> str:
        """Форматировать запись в JSON."""
        log_data: Dict[str, Any] = {}

        # Timestamp (ISO 8601, UTC)
        if self.timestamp_format == "iso":
            log_data["timestamp"] = datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat().replace("+00:00", "Z")
        else:
            log_data["timestamp"] = datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).strftime(self.timestamp_format)

        # Уровень логирования
        log_data["level"] = record.levelname

        # Сообщение
        log_data["message"] = record.getMessage()

        # Имя логгера
        log_data["logger"] = record.name

        # Позиция в коде
        log_data["module"] = record.module
        log_data["function"] = record.funcName
        log_data["line"] = record.lineno
        log_data["pathname"] = record.pathname

        # Поток
        if self.include_thread:
            log_data["thread"] = record.threadName
            log_data["thread_id"] = record.thread

        # Process info
        log_data["process"] = record.process
        log_data["process_name"] = record.processName

        # Extra контекст
        if self.include_extra:
            extra_data = self._extract_extra(record)
            if extra_data:
                log_data["extra"] = extra_data

        # Exception / Stack trace
        if self.include_stack_info:
            if record.exc_info:
                log_data["exception"] = {
                    "type": record.exc_info[0].__name__ if record.exc_info[0] else "Unknown",
                    "message": str(record.exc_info[1]) if record.exc_info[1] else "",
                    "traceback": self.formatException(record.exc_info),
                    "traceback_lines": traceback.format_exception(*record.exc_info),
                }
            elif record.stack_info:
                log_data["stack_info"] = self.formatStack(record.stack_info)

        # Асинхронный контекст (если есть)
        try:
            loop = asyncio.get_running_loop()
            log_data["async_context"] = {
                "loop_id": id(loop),
                "running": loop.is_running(),
            }
        except RuntimeError:
            # Нет активного event loop
            pass

        return json.dumps(log_data, ensure_ascii=False, default=str)

    def _extract_extra(self, record: logging.LogRecord) -> Dict[str, Any]:
        """
        Извлечь extra контекст из записи.

        Исключает стандартные атрибуты LogRecord.
        """
        standard_attrs = {
            'args', 'asctime', 'created', 'exc_info', 'filename',
            'funcName', 'getMessage', 'levelname', 'levelno', 'lineno',
            'module', 'msecs', 'msg', 'name', 'pathname', 'process',
            'processName', 'relativeCreated', 'stack_info', 'thread',
            'threadName', 'taskName', 'exc_text', 'message',
        }

        extra_data = {}
        for key, value in record.__dict__.items():
            if key not in standard_attrs:
                extra_data[key] = value

        return extra_data


class ColoredConsoleHandler(logging.StreamHandler):
    """
    Консольный хендлер с цветным выводом для разработки.

    Формат:
    [2026-08-10 12:00:00] [INFO] [module.function:42] Message
    """

    # ANSI color codes
    COLORS = {
        logging.DEBUG: "\033[36m",      # Cyan
        logging.INFO: "\033[32m",       # Green
        logging.WARNING: "\033[33m",    # Yellow
        logging.ERROR: "\033[31m",      # Red
        logging.CRITICAL: "\033[35m",   # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, stream=None, include_module: bool = True) -> None:
        super().__init__(stream)
        self.include_module = include_module
        self._fmt = self._create_format()

    def _create_format(self) -> logging.Formatter:
        """Создать форматтер для консоли."""
        if self.include_module:
            fmt = (
                "[%(asctime)s] [%(levelname)s] "
                "[%(module)s.%(funcName)s:%(lineno)d] "
                "%(message)s"
            )
        else:
            fmt = "[%(asctime)s] [%(levelname)s] %(message)s"

        formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter

    def emit(self, record: logging.LogRecord) -> None:
        """Эмитить запись с цветом."""
        try:
            msg = self.format(record)
            color = self.COLORS.get(record.levelno, self.RESET)
            self.stream.write(f"{color}{msg}{self.RESET}\n")
            self.flush()
        except Exception:
            self.handleError(record)


def setup_json_logging(
    level: str | int = "INFO",
    log_to_console: bool = True,
    log_to_file: bool = False,
    log_file: str | Path = "logs/app.json.log",
    log_file_max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    log_file_backup_count: int = 7,
    include_extra_context: bool = True,
    colored_console: bool = True,
    root_logger_name: str = "news_aggregator",
) -> logging.Logger:
    """
    Настроить структурированное JSON логирование.

    Args:
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_console: Логировать ли в консоль
        log_to_file: Логировать ли в файл
        log_file: Путь к файлу логов
        log_file_max_bytes: Макс. размер файла до ротации
        log_file_backup_count: Количество backup файлов
        include_extra_context: Включать ли extra контекст в JSON
        colored_console: Цветной ли вывод в консоль
        root_logger_name: Имя корневого логгера

    Returns:
        Настроенный корневой логгер
    """
    # Создаём корневой логгер
    root_logger = logging.getLogger(root_logger_name)
    root_logger.setLevel(level)

    # Очищаем существующие хендлеры
    root_logger.handlers.clear()

    # JSON форматтер для файла
    json_formatter = JSONFormatter(
        include_extra=include_extra_context,
        include_stack_info=True,
        include_thread=False,  # Не включаем thread для async приложения
    )

    # Файловый хендлер (RotatingFileHandler)
    if log_to_file:
        log_file_path = Path(log_file)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)

        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=log_file_max_bytes,
            backupCount=log_file_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(json_formatter)
        file_handler.setLevel(level)
        root_logger.addHandler(file_handler)

    # Консольный хендлер
    if log_to_console:
        if colored_console:
            console_handler = ColoredConsoleHandler(
                stream=sys.stdout,
                include_module=True,
            )
            # Консоль используем человекочитаемый формат
            console_handler.setFormatter(logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(module)s.%(funcName)s:%(lineno)d] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
        else:
            # Консоль с JSON форматом (для production)
            console_handler = logging.StreamHandler(stream=sys.stdout)
            console_handler.setFormatter(json_formatter)

        console_handler.setLevel(level)
        root_logger.addHandler(console_handler)

    # Логгируем запуск
    root_logger.info(
        f"📝 Structured logging initialized (level={level}, file={log_to_file})",
        extra={
            "config": {
                "level": level,
                "log_to_console": log_to_console,
                "log_to_file": log_to_file,
                "log_file": str(log_file) if log_to_file else None,
            }
        }
    )

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Получить логгер с указанным именем.

    Args:
        name: Имя логгера (обычно __name__)

    Returns:
        Логгер
    """
    return logging.getLogger(f"news_aggregator.{name}")


def log_async_context(func):
    """
    Декоратор для логирования асинхронных функций.

    Usage:
        @log_async_context
        async def my_function(user_id: int):
            ...
    """
    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)

        # Извлекаем контекст из args/kwargs
        context = {}
        if args:
            context["args_count"] = len(args)
        context.update(kwargs)

        logger.debug(
            f"▶️ Starting {func.__name__}",
            extra={"function": func.__name__, "context": context},
        )

        start_time = datetime.now(timezone.utc)

        try:
            result = await func(*args, **kwargs)
            elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            logger.debug(
                f"✅ Completed {func.__name__} ({elapsed_ms:.2f}ms)",
                extra={"function": func.__name__, "elapsed_ms": elapsed_ms},
            )

            return result

        except Exception as e:
            elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            logger.error(
                f"❌ Failed {func.__name__} ({elapsed_ms:.2f}ms): {e}",
                extra={
                    "function": func.__name__,
                    "elapsed_ms": elapsed_ms,
                    "exception_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise

    return wrapper


# =============================================================================
# Логгирование в несколько destinations (мультикастинг)
# =============================================================================

class MultiHandler(logging.Handler):
    """
    Хендлер для логирования в несколько destinations.

    Usage:
        multi = MultiHandler([handler1, handler2, handler3])
        logger.addHandler(multi)
    """

    def __init__(self, handlers: List[logging.Handler]) -> None:
        super().__init__()
        self.handlers = handlers

    def emit(self, record: logging.LogRecord) -> None:
        """Эмитить во все хендлеры."""
        for handler in self.handlers:
            try:
                handler.emit(record)
            except Exception:
                # Игнорируем ошибки отдельных хендлеров
                pass


# =============================================================================
# Фильтры для логирования
# =============================================================================

class ContextFilter(logging.Filter):
    """
    Фильтр для добавления контекста в каждую запись.

    Usage:
        logger.addFilter(ContextFilter({"app": "news_aggregator", "env": "prod"}))
    """

    def __init__(self, context: Dict[str, Any]) -> None:
        super().__init__()
        self.context = context

    def filter(self, record: logging.LogRecord) -> bool:
        """Добавить контекст к записи."""
        for key, value in self.context.items():
            setattr(record, key, value)
        return True


class LevelFilter(logging.Filter):
    """
    Фильтр для исключения определённых уровней.

    Usage:
        # Исключить DEBUG из file handler
        file_handler.addFilter(LevelFilter(min_level=logging.INFO))
    """

    def __init__(self, min_level: int = logging.INFO, max_level: Optional[int] = None) -> None:
        super().__init__()
        self.min_level = min_level
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        """Проверить уровень записи."""
        if record.levelno < self.min_level:
            return False
        if self.max_level and record.levelno > self.max_level:
            return False
        return True


# =============================================================================
# Утилиты для работы с логами
# =============================================================================

def parse_json_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Распарсить строку JSON лога.

    Args:
        line: Строка лога

    Returns:
        Dict с данными лога или None если не распарсилось
    """
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError:
        return None


def tail_json_log(
    file_path: str | Path,
    lines: int = 100,
    follow: bool = False,
):
    """
    Читать последние строки JSON лога (аналог tail -f).

    Args:
        file_path: Путь к файлу лога
        lines: Количество строк
        follow: Следить ли за изменениями (как tail -f)

    Yields:
        Dict с данными каждой записи
    """
    from collections import deque

    file_path = Path(file_path)

    if not file_path.exists():
        return

    # Читаем последние N строк
    with open(file_path, "r", encoding="utf-8") as f:
        last_lines = deque(f, maxlen=lines)

    for line in last_lines:
        parsed = parse_json_log_line(line)
        if parsed:
            yield parsed

    # Follow mode
    if follow:
        with open(file_path, "r", encoding="utf-8") as f:
            f.seek(0, 2)  # Go to end
            while True:
                line = f.readline()
                if line:
                    parsed = parse_json_log_line(line)
                    if parsed:
                        yield parsed
                else:
                    import time
                    time.sleep(0.1)


__all__ = [
    "JSONFormatter",
    "ColoredConsoleHandler",
    "MultiHandler",
    "ContextFilter",
    "LevelFilter",
    "setup_json_logging",
    "get_logger",
    "log_async_context",
    "parse_json_log_line",
    "tail_json_log",
]
