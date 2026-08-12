"""
Тесты для системы логирования с correlation ID.
"""

import pytest
import logging
from services.logging_config import (
    setup_logging,
    correlation_context,
    get_correlation_id,
    set_correlation_id,
    reset_correlation_id,
    with_correlation,
    CorrelationContext,
)


@pytest.fixture(autouse=True)
def setup_logging_for_tests():
    """Инициализирует логирование для всех тестов."""
    setup_logging(log_to_file=False, level=logging.DEBUG)


class TestCorrelationContext:
    """Тесты для контекстного менеджера correlation_id."""

    def test_correlation_context_sets_id(self):
        """Контекст устанавливает correlation_id."""
        assert get_correlation_id() is None

        with correlation_context("test-123"):
            assert get_correlation_id() == "test-123"

        assert get_correlation_id() is None

    def test_correlation_context_generates_id(self):
        """Контекст без параметров генерирует новый ID."""
        with correlation_context() as ctx:
            assert ctx.correlation_id is not None
            assert len(ctx.correlation_id) == 8  # uuid4[:8]
            assert get_correlation_id() == ctx.correlation_id

    def test_correlation_context_nested(self):
        """Вложенные контексты работают корректно."""
        with correlation_context("outer"):
            assert get_correlation_id() == "outer"

            with correlation_context("inner"):
                assert get_correlation_id() == "inner"

            assert get_correlation_id() == "outer"

        assert get_correlation_id() is None

    def test_correlation_context_exception(self):
        """Контекст корректно очищается при исключении."""
        try:
            with correlation_context("test"):
                assert get_correlation_id() == "test"
                raise ValueError("Test error")
        except ValueError:
            pass

        assert get_correlation_id() is None


class TestCorrelationIdFunctions:
    """Тесты для функций работы с correlation_id."""

    def test_set_and_reset_correlation_id(self):
        """Функции set/reset работают корректно."""
        assert get_correlation_id() is None

        token = set_correlation_id("manual-456")
        assert get_correlation_id() == "manual-456"

        reset_correlation_id(token)
        assert get_correlation_id() is None

    def test_set_correlation_id_none(self):
        """Установка None сбрасывает correlation_id."""
        with correlation_context("test"):
            assert get_correlation_id() == "test"

            token = set_correlation_id(None)
            assert get_correlation_id() is None

            reset_correlation_id(token)
            assert get_correlation_id() == "test"


class TestWithCorrelationDecorator:
    """Тесты для декоратора with_correlation."""

    @pytest.mark.asyncio
    async def test_async_decorator(self):
        """Декоратор работает с async функциями."""
        @with_correlation("async-test")
        async def async_func():
            return get_correlation_id()

        result = await async_func()
        assert result == "async-test"

        # После выполнения correlation_id сбрасывается
        assert get_correlation_id() is None

    def test_sync_decorator(self):
        """Декоратор работает с sync функциями."""
        @with_correlation("sync-test")
        def sync_func():
            return get_correlation_id()

        result = sync_func()
        assert result == "sync-test"

        # После выполнения correlation_id сбрасывается
        assert get_correlation_id() is None

    @pytest.mark.asyncio
    async def test_async_decorator_auto_generated_id(self):
        """Декоратор без параметров генерирует ID."""
        @with_correlation()
        async def async_func():
            return get_correlation_id()

        result = await async_func()
        assert result is not None
        assert len(result) == 8

    def test_sync_decorator_auto_generated_id(self):
        """Декоратор без параметров генерирует ID для sync."""
        @with_correlation()
        def sync_func():
            return get_correlation_id()

        result = sync_func()
        assert result is not None
        assert len(result) == 8


class TestCorrelationIdWithLogging:
    """Интеграционные тесты correlation_id с логированием."""

    def test_log_contains_correlation_id(self, caplog):
        """Логи содержат correlation_id."""
        with caplog.at_level(logging.INFO):
            with correlation_context("log-test"):
                logger = logging.getLogger("test")
                logger.info("Test message")

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert hasattr(record, 'correlation_id')
        assert record.correlation_id == "log-test"

    def test_log_without_correlation_id(self, caplog):
        """Логи без correlation_id содержат '-'."""
        with caplog.at_level(logging.INFO):
            logger = logging.getLogger("test")
            logger.info("Test message without context")

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert hasattr(record, 'correlation_id')
        assert record.correlation_id == '-'

    @pytest.mark.asyncio
    async def test_async_function_logging(self, caplog):
        """Логи в async функции с декоратором."""
        @with_correlation("async-log-test")
        async def async_func_with_log():
            logger = logging.getLogger("async_test")
            logger.info("Async log message")
            return "done"

        with caplog.at_level(logging.INFO):
            result = await async_func_with_log()

        assert result == "done"
        assert len(caplog.records) >= 1
        record = caplog.records[-1]
        assert record.correlation_id == "async-log-test"


class TestCorrelationContextClass:
    """Тесты для класса CorrelationContext."""

    def test_class_direct_usage(self):
        """Класс можно использовать напрямую."""
        ctx = CorrelationContext("direct-test")

        assert get_correlation_id() is None

        with ctx:
            assert get_correlation_id() == "direct-test"

        assert get_correlation_id() is None

    def test_class_with_custom_id(self):
        """Класс принимает кастомный ID."""
        ctx = CorrelationContext("custom-123")
        assert ctx.correlation_id == "custom-123"

    def test_class_auto_id(self):
        """Класс генерирует ID если не указан."""
        ctx = CorrelationContext()
        assert ctx.correlation_id is not None
        assert len(ctx.correlation_id) == 8
