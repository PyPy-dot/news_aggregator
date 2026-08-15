"""
Circuit Breaker — паттерн для защиты от каскадных сбоев.

Предотвращает многократные вызовы недоступных сервисов, давая им время на восстановление.

Состояния:
- CLOSED: Нормальная работа, вызовы проходят
- OPEN: Сервис недоступен, вызовы блокируются
- HALF_OPEN: Проверка восстановления (один тестовый вызов)

Использование:
    breaker = CircuitBreaker(name="ollama", failure_threshold=5, recovery_timeout=30)

    @breaker
    async def call_ollama():
        ...

    # Или вручную:
    async with breaker.call():
        result = await some_async_operation()
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Optional, Callable, Any
from functools import wraps
from dataclasses import dataclass, field
from collections.abc import Awaitable

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Состояния circuit breaker."""
    CLOSED = "closed"      # Нормальная работа
    OPEN = "open"          # Сервис недоступен
    HALF_OPEN = "half_open"  # Проверка восстановления


class CircuitBreakerError(Exception):
    """Ошибка circuit breaker (вызов заблокирован)."""
    def __init__(self, name: str, state: CircuitState, message: str = ""):
        self.name = name
        self.state = state
        super().__init__(message or f"Circuit breaker '{name}' в состоянии {state.value}")


@dataclass
class CircuitStats:
    """Статистика circuit breaker."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0  # Отклонены из-за OPEN состояния
    timeout_calls: int = 0   # Превышено время ожидания
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    last_state_change: float = field(default_factory=time.time)
    state_changes: int = 0
    avg_response_time_ms: float = 0.0

    def reset(self) -> None:
        """Сбросить статистику (кроме state_changes)."""
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.rejected_calls = 0
        self.timeout_calls = 0
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.avg_response_time_ms = 0.0


class CircuitBreaker:
    """
    Circuit Breaker для защиты от каскадных сбоев.

    Attributes:
        name: Имя breaker (для логирования и метрик)
        failure_threshold: Порог ошибок для открытия (по умолчанию 5)
        recovery_timeout: Время до попытки восстановления (сек, по умолчанию 30)
        half_open_max_calls: Макс. вызовов в HALF_OPEN (по умолчанию 1)
        expected_exceptions: Исключения, считающиеся ошибками (по умолчанию все Exception)
        timeout: Таймаут вызова в секундах (None = без таймаута)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        expected_exceptions: tuple = (Exception,),
        timeout: Optional[float] = None,
    ) -> None:
        """
        Инициализация circuit breaker.

        Args:
            name: Имя breaker
            failure_threshold: Порог ошибок для открытия
            recovery_timeout: Время до попытки восстановления (сек)
            half_open_max_calls: Макс. вызовов в HALF_OPEN
            expected_exceptions: Типы исключений, считающиеся ошибками
            timeout: Таймаут вызова (сек)
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.expected_exceptions = expected_exceptions
        self.timeout = timeout

        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._lock = asyncio.Lock()
        self._half_open_calls = 0
        self._failure_timestamps: list[float] = []

    @property
    def state(self) -> CircuitState:
        """Текущее состояние."""
        return self._state

    @property
    def stats(self) -> CircuitStats:
        """Статистика breaker."""
        return self._stats

    @property
    def is_closed(self) -> bool:
        """Breaker закрыт (нормальная работа)."""
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Breaker открыт (вызовы блокируются)."""
        return self._state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Breaker в полуоткрытом состоянии (проверка)."""
        return self._state == CircuitState.HALF_OPEN

    async def _check_state(self) -> None:
        """Проверить и обновить состояние (для recovery)."""
        if self._state == CircuitState.OPEN:
            elapsed = time.time() - self._stats.last_failure_time
            if elapsed >= self.recovery_timeout:
                logger.info(f"🔁 Circuit breaker '{self.name}': попытка восстановления (OPEN → HALF_OPEN)")
                await self._change_state(CircuitState.HALF_OPEN)

    async def _change_state(self, new_state: CircuitState) -> None:
        """Изменить состояние."""
        if self._state != new_state:
            old_state = self._state
            self._state = new_state
            self._stats.state_changes += 1
            self._stats.last_state_change = time.time()

            if new_state == CircuitState.HALF_OPEN:
                self._half_open_calls = 0

            logger.info(
                f"🔄 Circuit breaker '{self.name}': {old_state.value} → {new_state.value}"
            )

    async def _record_success(self, response_time_ms: float) -> None:
        """Записать успешный вызов."""
        self._stats.successful_calls += 1
        self._stats.consecutive_successes += 1
        self._stats.consecutive_failures = 0
        self._stats.last_success_time = time.time()

        # Обновление среднего времени ответа
        n = self._stats.successful_calls
        self._stats.avg_response_time_ms = (
            (self._stats.avg_response_time_ms * (n - 1) + response_time_ms) / n
        )

        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.half_open_max_calls:
                logger.info(f"✅ Circuit breaker '{self.name}': восстановление успешно (HALF_OPEN → CLOSED)")
                await self._change_state(CircuitState.CLOSED)

        elif self._state == CircuitState.CLOSED:
            # Сброс счётчика ошибок при успехе в CLOSED
            self._failure_timestamps = []

    async def _record_failure(self, exception: Exception) -> None:
        """Записать неудачный вызов."""
        self._stats.failed_calls += 1
        self._stats.consecutive_failures += 1
        self._stats.consecutive_successes = 0
        self._stats.last_failure_time = time.time()
        self._failure_timestamps.append(time.time())

        # Удаляем старые ошибки (за пределами recovery_timeout)
        cutoff = time.time() - self.recovery_timeout
        self._failure_timestamps = [t for t in self._failure_timestamps if t > cutoff]

        if self._state == CircuitState.HALF_OPEN:
            # Немедленное открытие при ошибке в HALF_OPEN
            logger.warning(
                f"❌ Circuit breaker '{self.name}': ошибка при проверке (HALF_OPEN → OPEN): "
                f"{type(exception).__name__}: {exception}"
            )
            await self._change_state(CircuitState.OPEN)

        elif self._state == CircuitState.CLOSED:
            # Проверка порога ошибок
            if len(self._failure_timestamps) >= self.failure_threshold:
                logger.warning(
                    f"🚫 Circuit breaker '{self.name}': превышен порог ошибок "
                    f"({len(self._failure_timestamps)}/{self.failure_threshold}) → OPEN"
                )
                await self._change_state(CircuitState.OPEN)

    async def call(self, func: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        """
        Выполнить функцию с circuit breaker.

        Args:
            func: Асинхронная функция для вызова
            *args: Позиционные аргументы
            **kwargs: Ключевые аргументы

        Returns:
            Результат функции

        Raises:
            CircuitBreakerError: Вызов отклонён (OPEN состояние)
            Exception: Исключение от функции
        """
        async with self._lock:
            await self._check_state()

            if self._state == CircuitState.OPEN:
                self._stats.rejected_calls += 1
                raise CircuitBreakerError(
                    name=self.name,
                    state=self._state,
                    message=f"Circuit breaker открыт, вызов отклонён"
                )

            self._stats.total_calls += 1

        start_time = time.time()

        try:
            # Вызов с таймаутом если указан
            if self.timeout:
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=self.timeout)
            else:
                result = await func(*args, **kwargs)

            response_time_ms = (time.time() - start_time) * 1000
            await self._record_success(response_time_ms)
            return result

        except asyncio.TimeoutError as e:
            self._stats.timeout_calls += 1
            await self._record_failure(e)
            raise

        except self.expected_exceptions as e:
            await self._record_failure(e)
            raise

        except Exception as e:
            # Неожиданное исключение — тоже считаем ошибкой
            await self._record_failure(e)
            raise

    def __call__(self, func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        """
        Декоратор для автоматического применения circuit breaker.

        Usage:
            @circuit_breaker
            async def my_function():
                ...
        """
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await self.call(func, *args, **kwargs)
        return wrapper

    async def reset(self) -> None:
        """Сбросить breaker в CLOSED состояние."""
        async with self._lock:
            await self._change_state(CircuitState.CLOSED)
            self._stats.reset()
            self._failure_timestamps = []
            logger.info(f"🔄 Circuit breaker '{self.name}': сброшен в CLOSED")

    def get_state_dict(self) -> dict:
        """Получить состояние как dict (для мониторинга)."""
        return {
            'name': self.name,
            'state': self._state.value,
            'is_closed': self.is_closed,
            'is_open': self.is_open,
            'is_half_open': self.is_half_open,
            'stats': {
                'total_calls': self._stats.total_calls,
                'successful_calls': self._stats.successful_calls,
                'failed_calls': self._stats.failed_calls,
                'rejected_calls': self._stats.rejected_calls,
                'timeout_calls': self._stats.timeout_calls,
                'consecutive_failures': self._stats.consecutive_failures,
                'consecutive_successes': self._stats.consecutive_successes,
                'avg_response_time_ms': round(self._stats.avg_response_time_ms, 2),
                'state_changes': self._stats.state_changes,
                'last_failure_time': self._stats.last_failure_time,
                'last_success_time': self._stats.last_success_time,
            },
            'config': {
                'failure_threshold': self.failure_threshold,
                'recovery_timeout': self.recovery_timeout,
                'half_open_max_calls': self.half_open_max_calls,
                'timeout': self.timeout,
            }
        }


# =============================================================================
# Менеджер circuit breaker'ов
# =============================================================================

class CircuitBreakerManager:
    """
    Менеджер для управления несколькими circuit breaker'ами.

    Использование:
        manager = CircuitBreakerManager()
        manager.add(CircuitBreaker("ollama", failure_threshold=5))
        manager.add(CircuitBreaker("telegram", failure_threshold=3))

        # Получить breaker по имени
        breaker = manager.get("ollama")

        # Получить все состояния
        states = manager.get_all_states()
    """

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    def add(self, breaker: CircuitBreaker) -> None:
        """Добавить circuit breaker."""
        self._breakers[breaker.name] = breaker
        logger.debug(f"✅ Circuit breaker '{breaker.name}' добавлен")

    def remove(self, name: str) -> Optional[CircuitBreaker]:
        """Удалить circuit breaker по имени."""
        return self._breakers.pop(name, None)

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Получить circuit breaker по имени."""
        return self._breakers.get(name)

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        **kwargs
    ) -> CircuitBreaker:
        """Получить или создать circuit breaker."""
        if name not in self._breakers:
            self.add(CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                **kwargs
            ))
        return self._breakers[name]

    async def reset_all(self) -> None:
        """Сбросить все circuit breaker'ы."""
        for breaker in self._breakers.values():
            await breaker.reset()

    async def reset(self, name: str) -> None:
        """Сбросить конкретный circuit breaker."""
        breaker = self.get(name)
        if breaker:
            await breaker.reset()

    def get_all_states(self) -> dict[str, dict]:
        """Получить состояния всех breaker'ов."""
        return {
            name: breaker.get_state_dict()
            for name, breaker in self._breakers.items()
        }

    def get_open_breakers(self) -> list[str]:
        """Получить имена открытых breaker'ов."""
        return [
            name for name, breaker in self._breakers.items()
            if breaker.is_open
        ]

    @property
    def all_closed(self) -> bool:
        """Все breaker'ы закрыты (здоровы)."""
        return all(b.is_closed for b in self._breakers.values())


# =============================================================================
# Глобальный менеджер (для удобства)
# =============================================================================

_global_manager: Optional[CircuitBreakerManager] = None


def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """Получить глобальный менеджер circuit breaker'ов."""
    global _global_manager
    if _global_manager is None:
        _global_manager = CircuitBreakerManager()
    return _global_manager


def create_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    timeout: Optional[float] = None,
    **kwargs
) -> CircuitBreaker:
    """
    Создать и зарегистрировать circuit breaker.

    Args:
        name: Имя breaker
        failure_threshold: Порог ошибок
        recovery_timeout: Время восстановления (сек)
        timeout: Таймаут вызова (сек)
        **kwargs: Дополнительные параметры для CircuitBreaker

    Returns:
        CircuitBreaker экземпляр
    """
    manager = get_circuit_breaker_manager()
    breaker = CircuitBreaker(
        name=name,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        timeout=timeout,
        **kwargs
    )
    manager.add(breaker)
    return breaker


def get_circuit_breaker(name: str) -> Optional[CircuitBreaker]:
    """Получить circuit breaker по имени."""
    manager = get_circuit_breaker_manager()
    return manager.get(name)


__all__ = [
    'CircuitState',
    'CircuitBreakerError',
    'CircuitStats',
    'CircuitBreaker',
    'CircuitBreakerManager',
    'get_circuit_breaker_manager',
    'create_circuit_breaker',
    'get_circuit_breaker',
]
