"""
Тесты для Circuit Breaker.

Проверяют:
- Переход между состояниями (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Retry логику
- Статистику
- Декоратор
- Менеджер circuit breaker'ов
"""

import pytest
import asyncio

from services.core.circuit_breaker import (
    CircuitState,
    CircuitBreaker,
    CircuitBreakerError,
    CircuitStats,
    CircuitBreakerManager,
    get_circuit_breaker_manager,
    create_circuit_breaker,
    get_circuit_breaker,
)


# =============================================================================
# Вспомогательные функции
# =============================================================================

class TestException(Exception):
    """Тестовое исключение."""


# =============================================================================
# Тесты CircuitBreaker
# =============================================================================

class TestCircuitBreaker:
    """Тесты для CircuitBreaker."""

    @pytest.mark.asyncio
    async def test_initial_state_closed(self):
        """Тест: начальное состояние CLOSED."""
        breaker = CircuitBreaker(name="test")
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_closed
        assert not breaker.is_open
        assert not breaker.is_half_open

    @pytest.mark.asyncio
    async def test_success_keeps_closed(self):
        """Тест: успешные вызовы сохраняют CLOSED."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)

        async def success_func():
            return "ok"

        for _ in range(10):
            result = await breaker.call(success_func)
            assert result == "ok"

        assert breaker.is_closed
        assert breaker.stats.successful_calls == 10

    @pytest.mark.asyncio
    async def test_failures_open_circuit(self):
        """Тест: ошибки открывают circuit."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)

        async def fail_func():
            raise TestException("fail")

        for _ in range(3):
            with pytest.raises(TestException):
                await breaker.call(fail_func)

        assert breaker.is_open
        assert breaker.stats.failed_calls == 3

    @pytest.mark.asyncio
    async def test_open_rejects_calls(self):
        """Тест: OPEN состояние отклоняет вызовы."""
        breaker = CircuitBreaker(name="test", failure_threshold=2)

        async def fail_func():
            raise TestException("fail")

        # Открываем breaker
        for _ in range(2):
            with pytest.raises(TestException):
                await breaker.call(fail_func)

        assert breaker.is_open

        # Вызовы должны отклоняться
        with pytest.raises(CircuitBreakerError) as exc_info:
            await breaker.call(fail_func)

        assert exc_info.value.state == CircuitState.OPEN
        assert breaker.stats.rejected_calls == 1

    @pytest.mark.asyncio
    async def test_recovery_timeout_to_half_open(self):
        """Тест: recovery timeout переводит в HALF_OPEN."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.1  # 100ms для теста
        )

        async def fail_func():
            raise TestException("fail")

        # Открываем breaker
        for _ in range(2):
            with pytest.raises(TestException):
                await breaker.call(fail_func)

        assert breaker.is_open

        # Ждём recovery timeout
        await asyncio.sleep(0.15)

        # Проверка состояния (должна сработать при следующем вызове)
        await breaker._check_state()
        assert breaker.is_half_open

    @pytest.mark.asyncio
    async def test_half_open_success_to_closed(self):
        """Тест: успешный вызов в HALF_OPEN закрывает circuit."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.1,
            half_open_max_calls=1
        )

        call_count = [0]

        async def fail_then_success():
            call_count[0] += 1
            if call_count[0] <= 2:
                raise TestException("fail")
            return "success"

        # Открываем breaker
        for _ in range(2):
            with pytest.raises(TestException):
                await breaker.call(fail_then_success)

        assert breaker.is_open

        # Ждём recovery timeout
        await asyncio.sleep(0.15)

        # Успешный вызов в HALF_OPEN
        result = await breaker.call(fail_then_success)
        assert result == "success"
        assert breaker.is_closed

    @pytest.mark.asyncio
    async def test_half_open_failure_to_open(self):
        """Тест: ошибка в HALF_OPEN возвращает в OPEN."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.1
        )

        async def always_fail():
            raise TestException("fail")

        # Открываем breaker
        for _ in range(2):
            with pytest.raises(TestException):
                await breaker.call(always_fail)

        assert breaker.is_open

        # Ждём recovery timeout
        await asyncio.sleep(0.15)

        # Ошибка в HALF_OPEN
        with pytest.raises(TestException):
            await breaker.call(always_fail)

        assert breaker.is_open  # Снова открыт

    @pytest.mark.asyncio
    async def test_timeout_exception(self):
        """Тест: таймаут вызова."""
        breaker = CircuitBreaker(name="test", timeout=0.1)

        async def slow_func():
            await asyncio.sleep(1.0)
            return "slow"

        with pytest.raises(asyncio.TimeoutError):
            await breaker.call(slow_func)

        assert breaker.stats.timeout_calls == 1
        assert breaker.stats.failed_calls == 1

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        """Тест: отслеживание статистики."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)

        async def success_func():
            await asyncio.sleep(0.01)
            return "ok"

        async def fail_func():
            raise TestException("fail")

        # Успешные вызовы
        for _ in range(5):
            await breaker.call(success_func)

        # Неудачные вызовы
        for _ in range(2):
            with pytest.raises(TestException):
                await breaker.call(fail_func)

        stats = breaker.stats
        assert stats.total_calls == 7
        assert stats.successful_calls == 5
        assert stats.failed_calls == 2
        assert stats.consecutive_failures == 2
        assert stats.consecutive_successes == 0
        assert stats.avg_response_time_ms > 0

    @pytest.mark.asyncio
    async def test_reset(self):
        """Тест: сброс breaker."""
        breaker = CircuitBreaker(name="test", failure_threshold=2)

        async def fail_func():
            raise TestException("fail")

        # Открываем breaker
        for _ in range(2):
            with pytest.raises(TestException):
                await breaker.call(fail_func)

        assert breaker.is_open

        # Сброс
        await breaker.reset()

        assert breaker.is_closed
        assert breaker.stats.total_calls == 0
        assert breaker.stats.state_changes >= 1

    @pytest.mark.asyncio
    async def test_decorator_usage(self):
        """Тест: использование как декоратор."""
        breaker = CircuitBreaker(name="test", failure_threshold=2)

        @breaker
        async def my_func(value):
            return value * 2

        result = await my_func(5)
        assert result == 10

        result = await my_func(10)
        assert result == 20

    @pytest.mark.asyncio
    async def test_get_state_dict(self):
        """Тест: получение состояния как dict."""
        breaker = CircuitBreaker(
            name="test_api",
            failure_threshold=5,
            recovery_timeout=30.0,
            timeout=10.0
        )

        state = breaker.get_state_dict()

        assert state['name'] == 'test_api'
        assert state['state'] == 'closed'
        assert state['is_closed'] is True
        assert state['config']['failure_threshold'] == 5
        assert state['config']['recovery_timeout'] == 30.0
        assert state['config']['timeout'] == 10.0


# =============================================================================
# Тесты CircuitBreakerManager
# =============================================================================

class TestCircuitBreakerManager:
    """Тесты для CircuitBreakerManager."""

    @pytest.mark.asyncio
    async def test_add_and_get(self):
        """Тест: добавление и получение breaker."""
        manager = CircuitBreakerManager()
        breaker = CircuitBreaker(name="test")

        manager.add(breaker)
        retrieved = manager.get("test")

        assert retrieved is breaker

    @pytest.mark.asyncio
    async def test_get_or_create(self):
        """Тест: получение или создание."""
        manager = CircuitBreakerManager()

        breaker1 = manager.get_or_create("test", failure_threshold=3)
        breaker2 = manager.get_or_create("test", failure_threshold=3)

        assert breaker1 is breaker2
        assert breaker1.failure_threshold == 3

    @pytest.mark.asyncio
    async def test_remove(self):
        """Тест: удаление breaker."""
        manager = CircuitBreakerManager()
        breaker = CircuitBreaker(name="test")

        manager.add(breaker)
        removed = manager.remove("test")

        assert removed is breaker
        assert manager.get("test") is None

    @pytest.mark.asyncio
    async def test_reset_all(self):
        """Тест: сброс всех breaker'ов."""
        manager = CircuitBreakerManager()

        breaker1 = CircuitBreaker(name="test1", failure_threshold=2)
        breaker2 = CircuitBreaker(name="test2", failure_threshold=2)

        manager.add(breaker1)
        manager.add(breaker2)

        # Открываем оба breaker
        async def fail():
            raise TestException("fail")

        for _ in range(2):
            for b in [breaker1, breaker2]:
                with pytest.raises(TestException):
                    await b.call(fail)

        assert breaker1.is_open
        assert breaker2.is_open

        # Сброс всех
        await manager.reset_all()

        assert breaker1.is_closed
        assert breaker2.is_closed

    @pytest.mark.asyncio
    async def test_get_open_breakers(self):
        """Тест: получение открытых breaker'ов."""
        manager = CircuitBreakerManager()

        b1 = CircuitBreaker(name="healthy", failure_threshold=2)
        b2 = CircuitBreaker(name="unhealthy", failure_threshold=2)
        b3 = CircuitBreaker(name="also_healthy", failure_threshold=2)

        manager.add(b1)
        manager.add(b2)
        manager.add(b3)

        # Открываем только b2
        async def fail():
            raise TestException("fail")

        for _ in range(2):
            with pytest.raises(TestException):
                await b2.call(fail)

        open_breakers = manager.get_open_breakers()
        assert open_breakers == ["unhealthy"]

    @pytest.mark.asyncio
    async def test_all_closed_property(self):
        """Тест: свойство all_closed."""
        manager = CircuitBreakerManager()

        b1 = CircuitBreaker(name="test1")
        b2 = CircuitBreaker(name="test2")

        manager.add(b1)
        manager.add(b2)

        assert manager.all_closed is True

        # Открываем один
        async def fail():
            raise TestException("fail")

        for _ in range(5):
            with pytest.raises(TestException):
                await b1.call(fail)

        assert manager.all_closed is False

    @pytest.mark.asyncio
    async def test_get_all_states(self):
        """Тест: получение всех состояний."""
        manager = CircuitBreakerManager()
        manager.add(CircuitBreaker(name="test1"))
        manager.add(CircuitBreaker(name="test2"))

        states = manager.get_all_states()

        assert "test1" in states
        assert "test2" in states
        assert states["test1"]["state"] == "closed"
        assert states["test2"]["state"] == "closed"


# =============================================================================
# Тесты глобальных функций
# =============================================================================

class TestGlobalFunctions:
    """Тесты для глобальных функций."""

    def test_get_circuit_breaker_manager_singleton(self):
        """Тест: менеджер — singleton."""
        manager1 = get_circuit_breaker_manager()
        manager2 = get_circuit_breaker_manager()
        assert manager1 is manager2

    def test_create_circuit_breaker_registers(self):
        """Тест: create_circuit_breaker регистрирует в менеджере."""
        # Сбрасываем глобальный менеджер
        import services.core.circuit_breaker as cb
        cb._global_manager = None

        breaker = create_circuit_breaker("test_global", failure_threshold=10)

        assert breaker.name == "test_global"
        assert breaker.failure_threshold == 10

        manager = get_circuit_breaker_manager()
        assert manager.get("test_global") is breaker

    def test_get_circuit_breaker(self):
        """Тест: получение breaker по имени."""
        import services.core.circuit_breaker as cb
        cb._global_manager = None

        create_circuit_breaker("test_get", failure_threshold=5)
        breaker = get_circuit_breaker("test_get")

        assert breaker is not None
        assert breaker.name == "test_get"


# =============================================================================
# Тесты CircuitStats
# =============================================================================

class TestCircuitStats:
    """Тесты для CircuitStats."""

    def test_default_values(self):
        """Тест: значения по умолчанию."""
        stats = CircuitStats()

        assert stats.total_calls == 0
        assert stats.successful_calls == 0
        assert stats.failed_calls == 0
        assert stats.rejected_calls == 0
        assert stats.timeout_calls == 0
        assert stats.consecutive_failures == 0
        assert stats.consecutive_successes == 0
        assert stats.avg_response_time_ms == 0.0

    def test_reset(self):
        """Тест: сброс статистики."""
        stats = CircuitStats()
        stats.total_calls = 100
        stats.successful_calls = 90
        stats.failed_calls = 10
        stats.state_changes = 5  # Не сбрасывается

        stats.reset()

        assert stats.total_calls == 0
        assert stats.successful_calls == 0
        assert stats.failed_calls == 0
        # state_changes не сбрасывается в методе reset()
