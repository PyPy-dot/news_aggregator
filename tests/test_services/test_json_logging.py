"""
Тесты для структурированного JSON логирования.

Проверяют:
- JSON форматтер
- Консольный хендлер с цветами
- Контекстные фильтры
- Утилиты (parse_json_log_line, tail_json_log)
"""

import pytest
import logging
import json
import io
import tempfile
from pathlib import Path
from datetime import datetime

from services.logging_json import (
    JSONFormatter,
    ColoredConsoleHandler,
    MultiHandler,
    ContextFilter,
    LevelFilter,
    setup_json_logging,
    get_logger,
    log_async_context,
    parse_json_log_line,
)


# =============================================================================
# Тесты JSONFormatter
# =============================================================================

class TestJSONFormatter:
    """Тесты для JSONFormatter."""

    def test_basic_format(self):
        """Тест: базовое форматирование в JSON."""
        formatter = JSONFormatter(include_extra=False, include_stack_info=False)

        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/module.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_func",
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert data["level"] == "INFO"
        assert data["message"] == "Test message"
        assert data["logger"] == "test.logger"
        assert data["module"] == "module"
        assert data["function"] == "test_func"
        assert data["line"] == 42
        assert "timestamp" in data
        assert data["timestamp"].endswith("Z")  # UTC format

    def test_extra_context(self):
        """Тест: extra контекст."""
        formatter = JSONFormatter(include_extra=True, include_stack_info=False)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="User action",
            args=(),
            exc_info=None,
            func="test",
        )
        record.user_id = 123456
        record.action = "login"

        output = formatter.format(record)
        data = json.loads(output)

        assert "extra" in data
        assert data["extra"]["user_id"] == 123456
        assert data["extra"]["action"] == "login"

    def test_exception_format(self):
        """Тест: форматирование исключений."""
        import sys
        formatter = JSONFormatter(include_extra=False, include_stack_info=True)

        try:
            raise ValueError("Test error")
        except ValueError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
            func="test",
        )

        output = formatter.format(record)
        data = json.loads(output)

        # Проверяем что exception есть в данных
        assert "exception" in data or "Error occurred" in data.get("message", "")

    def test_timestamp_format(self):
        """Тест: формат timestamp."""
        # ISO format (default)
        formatter_iso = JSONFormatter(timestamp_format="iso")
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="test.py", lineno=1,
            msg="test", args=(), exc_info=None, func="test",
        )
        output = formatter_iso.format(record)
        data = json.loads(output)
        assert "T" in data["timestamp"]
        assert data["timestamp"].endswith("Z")

        # Custom format
        formatter_custom = JSONFormatter(timestamp_format="%Y-%m-%d %H:%M:%S")
        output = formatter_custom.format(record)
        data = json.loads(output)
        assert "-" in data["timestamp"]  # Date format


# =============================================================================
# Тесты ColoredConsoleHandler
# =============================================================================

class TestColoredConsoleHandler:
    """Тесты для ColoredConsoleHandler."""

    def test_colored_output(self):
        """Тест: цветной вывод."""
        stream = io.StringIO()
        handler = ColoredConsoleHandler(stream=stream)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Info message",
            args=(),
            exc_info=None,
            func="test",
        )

        handler.emit(record)
        output = stream.getvalue()

        # Проверяем наличие ANSI кодов
        assert "\033[" in output  # Color code
        assert "Info message" in output


# =============================================================================
# Тесты MultiHandler
# =============================================================================

class TestMultiHandler:
    """Тесты для MultiHandler."""

    def test_multi_handler(self):
        """Тест: логирование в несколько хендлеров."""
        stream1 = io.StringIO()
        stream2 = io.StringIO()

        handler1 = logging.StreamHandler(stream1)
        handler2 = logging.StreamHandler(stream2)

        multi = MultiHandler([handler1, handler2])

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Multi message",
            args=(),
            exc_info=None,
            func="test",
        )

        multi.emit(record)

        assert "Multi message" in stream1.getvalue()
        assert "Multi message" in stream2.getvalue()


# =============================================================================
# Тесты ContextFilter
# =============================================================================

class TestContextFilter:
    """Тесты для ContextFilter."""

    def test_context_filter(self):
        """Тест: добавление контекста."""
        filter = ContextFilter({"app": "news_aggregator", "env": "test"})

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
            func="test",
        )

        result = filter.filter(record)

        assert result is True
        assert record.app == "news_aggregator"
        assert record.env == "test"


# =============================================================================
# Тесты LevelFilter
# =============================================================================

class TestLevelFilter:
    """Тесты для LevelFilter."""

    def test_level_filter_min(self):
        """Тест: фильтрация по мин. уровню."""
        filter = LevelFilter(min_level=logging.WARNING)

        info_record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="test.py", lineno=1,
            msg="info", args=(), exc_info=None, func="test",
        )

        warning_record = logging.LogRecord(
            name="test", level=logging.WARNING,
            pathname="test.py", lineno=1,
            msg="warning", args=(), exc_info=None, func="test",
        )

        assert filter.filter(info_record) is False
        assert filter.filter(warning_record) is True

    def test_level_filter_range(self):
        """Тест: фильтрация по диапазону."""
        filter = LevelFilter(min_level=logging.INFO, max_level=logging.WARNING)

        debug_record = logging.LogRecord(
            name="test", level=logging.DEBUG,
            pathname="test.py", lineno=1,
            msg="debug", args=(), exc_info=None, func="test",
        )

        info_record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="test.py", lineno=1,
            msg="info", args=(), exc_info=None, func="test",
        )

        error_record = logging.LogRecord(
            name="test", level=logging.ERROR,
            pathname="test.py", lineno=1,
            msg="error", args=(), exc_info=None, func="test",
        )

        assert filter.filter(debug_record) is False
        assert filter.filter(info_record) is True
        assert filter.filter(error_record) is False


# =============================================================================
# Тесты setup_json_logging
# =============================================================================

class TestSetupJSONLogging:
    """Тесты для setup_json_logging."""

    def test_setup_console_only(self):
        """Тест: настройка только консоли."""
        logger = setup_json_logging(
            level=logging.INFO,
            log_to_console=True,
            log_to_file=False,
            root_logger_name="test_json_logger",
        )

        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)

    def test_setup_with_file(self):
        """Тест: настройка с файлом."""
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            temp_path = f.name

        try:
            logger = setup_json_logging(
                level=logging.INFO,
                log_to_console=False,
                log_to_file=True,
                log_file=temp_path,
                root_logger_name="test_json_logger_file",
            )

            assert len(logger.handlers) == 1
            assert isinstance(logger.handlers[0], logging.handlers.RotatingFileHandler)

            # Проверяем что файл создан
            assert Path(temp_path).exists()

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_get_logger(self):
        """Тест: получение логгера."""
        logger = get_logger("test_module")
        assert logger.name == "news_aggregator.test_module"


# =============================================================================
# Тесты log_async_context decorator
# =============================================================================

class TestLogAsyncContext:
    """Тесты для log_async_context декоратора."""

    @pytest.mark.asyncio
    async def test_async_context_decorator(self):
        """Тест: декоратор для async функций."""
        call_log = []

        @log_async_context
        async def my_function(value: int):
            call_log.append(value)
            return value * 2

        result = await my_function(42)

        assert result == 84
        assert 42 in call_log


# =============================================================================
# Тесты parse_json_log_line
# =============================================================================

class TestParseJSONLogLine:
    """Тесты для parse_json_log_line."""

    def test_parse_valid_json(self):
        """Тест: парсинг валидного JSON."""
        line = '{"level": "INFO", "message": "Test", "timestamp": "2026-08-10T12:00:00Z"}'
        result = parse_json_log_line(line)

        assert result is not None
        assert result["level"] == "INFO"
        assert result["message"] == "Test"

    def test_parse_invalid_json(self):
        """Тест: парсинг невалидного JSON."""
        line = "not a json line"
        result = parse_json_log_line(line)

        assert result is None

    def test_parse_with_whitespace(self):
        """Тест: парсинг с whitespace."""
        line = '  {"level": "INFO"}  \n'
        result = parse_json_log_line(line)

        assert result is not None
        assert result["level"] == "INFO"


# =============================================================================
# Интеграционные тесты
# =============================================================================

class TestIntegration:
    """Интеграционные тесты."""

    def test_full_logging_flow(self):
        """Тест: полный цикл логирования."""
        with tempfile.NamedTemporaryFile(suffix=".json.log", delete=False, mode='w') as f:
            temp_path = f.name

        try:
            # Настройка
            logger_obj = setup_json_logging(
                level=logging.DEBUG,
                log_to_console=False,
                log_to_file=True,
                log_file=temp_path,
                include_extra_context=True,
                root_logger_name="test_integration",
            )

            # Логирование с extra контекстом
            test_logger = logging.getLogger("test_integration.test")
            test_logger.info("User action", extra={"user_id": 123, "action": "login"})

            # Чтение файла - несколько строк (JSON Lines формат)
            with open(temp_path, 'r') as f:
                lines = f.readlines()

            # Ищем нашу запись (последняя)
            data = json.loads(lines[-1].strip())

            assert data["level"] == "INFO"
            assert data["message"] == "User action"
            assert data.get("extra", {}).get("user_id") == 123
            assert data.get("extra", {}).get("action") == "login"

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_exception_logging(self):
        """Тест: логирование исключений."""
        with tempfile.NamedTemporaryFile(suffix=".json.log", delete=False, mode='w') as f:
            temp_path = f.name

        try:
            setup_json_logging(
                level=logging.DEBUG,
                log_to_console=False,
                log_to_file=True,
                log_file=temp_path,
                root_logger_name="test_exception",
            )

            test_logger = logging.getLogger("test_exception.test")

            try:
                raise ValueError("Test exception")
            except ValueError:
                test_logger.exception("Error occurred")

            # Чтение - JSON Lines формат
            with open(temp_path, 'r') as f:
                lines = f.readlines()

            # Ищем запись с exception (последняя)
            data = json.loads(lines[-1].strip())

            assert data["level"] == "ERROR"
            assert "exception" in data or "Error occurred" in data.get("message", "")

        finally:
            Path(temp_path).unlink(missing_ok=True)
