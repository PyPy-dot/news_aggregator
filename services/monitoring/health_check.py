"""
Health Check — проверка состояния сервисов приложения.

Предоставляет API для проверки здоровья:
- База данных
- LLM провайдеры (Ollama, OpenAI, Anthropic)
- Telegram бот (Admin Bot, Listener Bot)
- Векторный поиск (ChromaDB)
- Очереди задач
- Планировщик

Usage:
    from services.monitoring.health_check import HealthChecker, HealthStatus

    checker = HealthChecker()
    status = await checker.check_all()

    # Или через API (FastAPI):
    # GET /health — краткий статус
    # GET /health/full — полная проверка
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Awaitable
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Статус здоровья компонента."""
    HEALTHY = "healthy"      # Компонент здоров
    DEGRADED = "degraded"    # Работает с проблемами
    UNHEALTHY = "unhealthy"  # Компонент недоступен
    UNKNOWN = "unknown"      # Статус неизвестен


class SeverityLevel(Enum):
    """Уровень важности компонента."""
    CRITICAL = "critical"    # Критичный компонент (система неработоспособна)
    HIGH = "high"           # Важный компонент (деградация функциональности)
    MEDIUM = "medium"       # Средней важности (частичная деградация)
    LOW = "low"             # Низкой важности (не влияет на основную функцию)


@dataclass
class ComponentHealth:
    """Здоровье отдельного компонента."""
    name: str
    status: HealthStatus
    severity: SeverityLevel
    message: str = ""
    latency_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """Преобразовать в dict."""
        return {
            "name": self.name,
            "status": self.status.value,
            "severity": self.severity.value,
            "message": self.message,
            "latency_ms": round(self.latency_ms, 2),
            "details": self.details,
            "checked_at": datetime.fromtimestamp(self.checked_at, tz=timezone.utc).isoformat(),
        }


@dataclass
class SystemHealth:
    """Общее здоровье системы."""
    status: HealthStatus
    components: List[ComponentHealth] = field(default_factory=list)
    checked_at: float = field(default_factory=time.time)
    version: str = "3.5.0"

    @property
    def healthy_components(self) -> int:
        """Количество здоровых компонентов."""
        return sum(1 for c in self.components if c.status == HealthStatus.HEALTHY)

    @property
    def unhealthy_components(self) -> int:
        """Количество нездоровых компонентов."""
        return sum(1 for c in self.components if c.status in (HealthStatus.UNHEALTHY, HealthStatus.DEGRADED))

    @property
    def critical_issues(self) -> List[ComponentHealth]:
        """Критичные проблемы."""
        return [c for c in self.components if c.severity == SeverityLevel.CRITICAL and c.status != HealthStatus.HEALTHY]

    def to_dict(self) -> dict:
        """Преобразовать в dict."""
        return {
            "status": self.status.value,
            "version": self.version,
            "checked_at": datetime.fromtimestamp(self.checked_at, tz=timezone.utc).isoformat(),
            "summary": {
                "total_components": len(self.components),
                "healthy": self.healthy_components,
                "unhealthy": self.unhealthy_components,
                "critical_issues": len(self.critical_issues),
            },
            "components": [c.to_dict() for c in self.components],
        }


class HealthChecker:
    """
    Проверка здоровья системы.

    Usage:
        checker = HealthChecker()

        # Добавить проверку
        checker.add_check("database", check_database, SeverityLevel.CRITICAL)

        # Выполнить все проверки
        health = await checker.check_all()
    """

    def __init__(self) -> None:
        self._checks: Dict[str, tuple[Callable[..., Awaitable[ComponentHealth]], SeverityLevel]] = {}
        self._last_results: Dict[str, ComponentHealth] = {}
        self._lock = asyncio.Lock()

    def add_check(
        self,
        name: str,
        check_func: Callable[..., Awaitable[ComponentHealth]],
        severity: SeverityLevel = SeverityLevel.MEDIUM,
    ) -> None:
        """
        Добавить проверку компонента.

        Args:
            name: Имя компонента
            check_func: Асинхронная функция проверки
            severity: Уровень важности
        """
        self._checks[name] = (check_func, severity)
        logger.debug(f"✅ Добавлена проверка здоровья: {name}")

    def remove_check(self, name: str) -> None:
        """Удалить проверку компонента."""
        self._checks.pop(name, None)

    async def check_component(self, name: str) -> ComponentHealth:
        """
        Проверить конкретный компонент.

        Args:
            name: Имя компонента

        Returns:
            ComponentHealth результат
        """
        if name not in self._checks:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNKNOWN,
                severity=SeverityLevel.MEDIUM,
                message=f"Проверка '{name}' не найдена",
            )

        check_func, severity = self._checks[name]

        start_time = time.time()
        try:
            result = await check_func()
            result.latency_ms = (time.time() - start_time) * 1000
            result.severity = severity

            async with self._lock:
                self._last_results[name] = result

            return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            result = ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                severity=severity,
                message=f"{type(e).__name__}: {e}",
                latency_ms=latency_ms,
            )

            async with self._lock:
                self._last_results[name] = result

            return result

    async def check_all(self, timeout: float = 10.0) -> SystemHealth:
        """
        Проверить все компоненты.

        Args:
            timeout: Общий таймаут всех проверок (сек)

        Returns:
            SystemHealth результат
        """
        start_time = time.time()

        # Создаём задачи для всех проверок
        tasks = {
            name: asyncio.create_task(self.check_component(name))
            for name in self._checks
        }

        # Ждём выполнения с таймаутом
        try:
            done, pending = await asyncio.wait(
                tasks.values(),
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED,
            )

            # Отменяем невыполненные задачи
            for task in pending:
                task.cancel()

        except Exception as e:
            logger.error(f"❌ Ошибка при проверке здоровья: {e}")
            done = set()

        # Собираем результаты
        components: List[ComponentHealth] = []

        for name, task in tasks.items():
            if not task.done():
                components.append(ComponentHealth(
                    name=name,
                    status=HealthStatus.UNKNOWN,
                    severity=self._checks[name][1],
                    message="Timeout при проверке",
                ))
            elif task.cancelled():
                components.append(ComponentHealth(
                    name=name,
                    status=HealthStatus.UNKNOWN,
                    severity=self._checks[name][1],
                    message="Проверка отменена",
                ))
            else:
                try:
                    components.append(task.result())
                except Exception as e:
                    components.append(ComponentHealth(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        severity=self._checks[name][1],
                        message=f"{type(e).__name__}: {e}",
                    ))

        # Сортируем: критичные первыми
        components.sort(key=lambda c: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}[c.severity.value],
            c.name,
        ))

        # Определяем общий статус
        overall_status = HealthStatus.HEALTHY
        for comp in components:
            if comp.severity == SeverityLevel.CRITICAL and comp.status != HealthStatus.HEALTHY:
                overall_status = HealthStatus.UNHEALTHY
                break
            elif comp.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.DEGRADED
            elif comp.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.DEGRADED

        return SystemHealth(
            status=overall_status,
            components=components,
            checked_at=time.time(),
        )

    def get_last_results(self) -> Dict[str, ComponentHealth]:
        """Получить последние результаты проверок."""
        return self._last_results.copy()

    def get_summary(self) -> dict:
        """Получить краткую сводку."""
        if not self._last_results:
            return {"status": "unknown", "message": "Проверки ещё не выполнялись"}

        healthy = sum(1 for c in self._last_results.values() if c.status == HealthStatus.HEALTHY)
        total = len(self._last_results)

        critical_issues = [
            c for c in self._last_results.values()
            if c.severity == SeverityLevel.CRITICAL and c.status != HealthStatus.HEALTHY
        ]

        if critical_issues:
            status = "unhealthy"
        elif healthy == total:
            status = "healthy"
        else:
            status = "degraded"

        return {
            "status": status,
            "healthy_components": healthy,
            "total_components": total,
            "critical_issues": len(critical_issues),
            "critical_issue_names": [c.name for c in critical_issues],
        }


# =============================================================================
# Встроенные проверки для News Aggregator
# =============================================================================

async def check_database_health() -> ComponentHealth:
    """Проверка здоровья базы данных."""
    start_time = time.time()

    try:
        from services.core.database import get_database_service

        db_service = get_database_service()

        # Проверка подключения — используем session_context (общий для старого и нового API)
        async with db_service.session_context() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))

        latency_ms = (time.time() - start_time) * 1000

        # Определяем тип БД
        db_type = getattr(db_service, 'db_type', None)
        # У DatabaseService (обёртка) db_type нет напрямую — ищем через _service
        if db_type is None and hasattr(db_service, '_service') and db_service._service:
            db_type = db_service._service.db_type
        db_type_label = db_type.name if db_type else "unknown"
        db_type_value = db_type.value if db_type else "unknown"

        return ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            severity=SeverityLevel.CRITICAL,
            message=f"БД подключена ({db_type_label})",
            latency_ms=latency_ms,
            details={
                "db_type": db_type_value,
            },
        )

    except Exception as e:
        return ComponentHealth(
            name="database",
            status=HealthStatus.UNHEALTHY,
            severity=SeverityLevel.CRITICAL,
            message=f"Ошибка БД: {type(e).__name__}: {e}",
            latency_ms=(time.time() - start_time) * 1000,
        )


async def check_ollama_health() -> ComponentHealth:
    """Проверка здоровья Ollama."""
    from services.core.llm_provider import OllamaProvider

    start_time = time.time()

    try:
        # Кэшируем — конструктор лёгкий, но is_available() делает HTTP-запрос
        if not hasattr(check_ollama_health, '_provider'):
            check_ollama_health._provider = OllamaProvider()
        provider = check_ollama_health._provider

        available = await provider.is_available()
        stats = provider.get_stats()

        latency_ms = (time.time() - start_time) * 1000

        if available:
            return ComponentHealth(
                name="ollama",
                status=HealthStatus.HEALTHY,
                severity=SeverityLevel.HIGH,
                message="Ollama доступен",
                latency_ms=latency_ms,
                details={
                    "model": provider.default_model,
                    "base_url": provider.base_url,
                },
            )
        else:
            return ComponentHealth(
                name="ollama",
                status=HealthStatus.UNHEALTHY,
                severity=SeverityLevel.HIGH,
                message=f"Ollama недоступен",
                latency_ms=latency_ms,
            )

    except Exception as e:
        return ComponentHealth(
            name="ollama",
            status=HealthStatus.UNHEALTHY,
            severity=SeverityLevel.HIGH,
            message=f"Ollama ошибка: {type(e).__name__}: {e}",
            latency_ms=(time.time() - start_time) * 1000,
        )


async def check_llm_fallback_health() -> ComponentHealth:
    """Проверка здоровья Fallback LLM провайдера."""
    from services.core.llm_provider import get_llm_provider, FallbackLLMProvider

    try:
        provider = get_llm_provider()

        if not isinstance(provider, FallbackLLMProvider):
            return ComponentHealth(
                name="llm_fallback",
                status=HealthStatus.DEGRADED,
                severity=SeverityLevel.HIGH,
                message="Fallback не настроен, используется одиночный провайдер",
                details={"provider_type": type(provider).__name__},
            )

        # Проверка доступности хотя бы одного провайдера
        available = await provider.is_available()
        all_stats = provider.get_all_stats()

        healthy_providers = [name for name, stats in all_stats.items() if stats.is_healthy]
        unhealthy_providers = [name for name, stats in all_stats.items() if not stats.is_healthy]

        if available:
            return ComponentHealth(
                name="llm_fallback",
                status=HealthStatus.HEALTHY,
                severity=SeverityLevel.HIGH,
                message=f"LLM fallback работает ({len(healthy_providers)}/{len(provider.providers)} провайдеров здоровы)",
                details={
                    "healthy_providers": healthy_providers,
                    "unhealthy_providers": unhealthy_providers,
                    "fallback_count": provider.get_stats().fallback_count,
                },
            )
        else:
            return ComponentHealth(
                name="llm_fallback",
                status=HealthStatus.UNHEALTHY,
                severity=SeverityLevel.HIGH,
                message="Все LLM провайдеры недоступны",
                details={"unhealthy_providers": unhealthy_providers},
            )

    except Exception as e:
        return ComponentHealth(
            name="llm_fallback",
            status=HealthStatus.UNHEALTHY,
            severity=SeverityLevel.HIGH,
            message=f"LLM fallback ошибка: {type(e).__name__}: {e}",
        )


async def check_circuit_breakers_health() -> ComponentHealth:
    """Проверка состояния circuit breaker'ов."""
    from services.core.circuit_breaker import get_circuit_breaker_manager

    try:
        manager = get_circuit_breaker_manager()
        states = manager.get_all_states()
        open_breakers = manager.get_open_breakers()

        if not states:
            return ComponentHealth(
                name="circuit_breakers",
                status=HealthStatus.UNKNOWN,
                severity=SeverityLevel.MEDIUM,
                message="Circuit breaker'ы не настроены",
            )

        if open_breakers:
            return ComponentHealth(
                name="circuit_breakers",
                status=HealthStatus.DEGRADED,
                severity=SeverityLevel.MEDIUM,
                message=f"{len(open_breakers)} circuit breaker'ов открыты",
                details={
                    "open_breakers": open_breakers,
                    "total_breakers": len(states),
                    "states": {name: s["state"] for name, s in states.items()},
                },
            )

        return ComponentHealth(
            name="circuit_breakers",
            status=HealthStatus.HEALTHY,
            severity=SeverityLevel.MEDIUM,
            message=f"Все {len(states)} circuit breaker'ов закрыты",
            details={
                "total_breakers": len(states),
                "states": {name: s["state"] for name, s in states.items()},
            },
        )

    except Exception as e:
        return ComponentHealth(
            name="circuit_breakers",
            status=HealthStatus.UNHEALTHY,
            severity=SeverityLevel.MEDIUM,
            message=f"Circuit breaker ошибка: {type(e).__name__}: {e}",
        )


async def check_telegram_bot_health() -> ComponentHealth:
    """Проверка здоровья Telegram бота."""
    start_time = time.time()

    try:
        from services.bot.bot import get_bot_instance_async

        bot = await get_bot_instance_async(wait=False, timeout=5.0)

        if bot is None:
            return ComponentHealth(
                name="telegram_bot",
                status=HealthStatus.UNHEALTHY,
                severity=SeverityLevel.CRITICAL,
                message="Бот не инициализирован или ещё не готов",
                latency_ms=(time.time() - start_time) * 1000,
            )

        # Проверка сессии
        if bot.session.closed:
            return ComponentHealth(
                name="telegram_bot",
                status=HealthStatus.UNHEALTHY,
                severity=SeverityLevel.CRITICAL,
                message="HTTP сессия бота закрыта",
                latency_ms=(time.time() - start_time) * 1000,
            )

        # Проверка что polling активен через BotService.is_alive()
        from services.service_manager import get_service_manager

        manager = get_service_manager()
        bot_service = manager._get_service("bot")

        polling_alive = False
        bot_error = None
        if bot_service is not None:
            polling_alive = bot_service.is_alive()
            bot_error = getattr(bot_service, '_last_error', None)

        # Проверка connection через getMe
        me = await bot.get_me()
        latency_ms = (time.time() - start_time) * 1000

        if not polling_alive:
            state = manager.get_state("bot").value
            return ComponentHealth(
                name="telegram_bot",
                status=HealthStatus.UNHEALTHY,
                severity=SeverityLevel.CRITICAL,
                message=f"Бот @{me.username} жив, но polling не активен (состояние: {state})",
                latency_ms=latency_ms,
                details={
                    "bot_id": me.id,
                    "bot_name": me.first_name,
                    "bot_username": me.username,
                    "polling_active": False,
                    "last_error": bot_error,
                },
            )

        return ComponentHealth(
            name="telegram_bot",
            status=HealthStatus.HEALTHY,
            severity=SeverityLevel.CRITICAL,
            message=f"Бот @{me.username} активен",
            latency_ms=latency_ms,
            details={
                "bot_id": me.id,
                "bot_name": me.first_name,
                "bot_username": me.username,
                "is_premium": me.is_premium,
            },
        )

    except Exception as e:
        return ComponentHealth(
            name="telegram_bot",
            status=HealthStatus.UNHEALTHY,
            severity=SeverityLevel.CRITICAL,
            message=f"Бот ошибка: {type(e).__name__}: {e}",
            latency_ms=(time.time() - start_time) * 1000,
        )


async def check_vector_search_health() -> ComponentHealth:
    """Проверка здоровья ChromaDB с reconnect при сбое."""
    start_time = time.time()

    try:
        from services.vector_search.chroma_client import ChromaVectorStore

        # Кэшируем клиент — нет смысла пересоздавать PersistentClient каждый раз
        if not hasattr(check_vector_search_health, '_store'):
            check_vector_search_health._store = ChromaVectorStore()
        store = check_vector_search_health._store

        client = store._client

        # list_collections() в ChromaDB 0.5.x — синхронный метод
        collections = client.list_collections()

        collection_names = [c.name if hasattr(c, 'name') else str(c) for c in collections]

        # Дополнительно проверяем что к коллекции можно обратиться через count()
        counts: Dict[str, Any] = {}
        try:
            for name in collection_names:
                try:
                    counts[name] = store.count(name)
                except Exception as count_err:
                    counts[name] = f"error: {count_err}"
        except Exception:
            # Если collections не итерируются (пустой список) — пропускаем
            pass

        latency_ms = (time.time() - start_time) * 1000

        # Проверяем есть ли ошибки в count — признак частичной деградации
        has_errors = any(isinstance(v, str) for v in counts.values())

        if has_errors:
            return ComponentHealth(
                name="vector_search",
                status=HealthStatus.DEGRADED,
                severity=SeverityLevel.HIGH,
                message=f"ChromaDB подключён, но часть коллекций недоступна",
                latency_ms=latency_ms,
                details={
                    "collections": collection_names,
                    "collection_counts": counts,
                },
            )

        return ComponentHealth(
            name="vector_search",
            status=HealthStatus.HEALTHY,
            severity=SeverityLevel.HIGH,
            message=f"ChromaDB подключён ({len(collections)} коллекций)",
            latency_ms=latency_ms,
            details={
                "collections": collection_names,
                "collection_counts": counts,
            },
        )

    except Exception as e:
        # Попытка пересоздать клиент — ChromaDB процесс мог перезапуститься
        try:
            logger.warning(f"⚠️ ChromaDB ошибка, пробую пересоздать клиент: {e}")
            check_vector_search_health._store = ChromaVectorStore()
            check_vector_search_health._store._client.list_collections()

            latency_ms = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="vector_search",
                status=HealthStatus.DEGRADED,
                severity=SeverityLevel.HIGH,
                message=f"ChromaDB восстановлен после ошибки ({type(e).__name__})",
                latency_ms=latency_ms,
                details={"recovered_from": str(e)},
            )
        except Exception as reconnect_err:
            latency_ms = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="vector_search",
                status=HealthStatus.UNHEALTHY,
                severity=SeverityLevel.HIGH,
                message=f"Векторный поиск ошибка: {type(e).__name__}: {e}",
                latency_ms=latency_ms,
                details={"original_error": str(e)},
            )


async def check_scheduler_health() -> ComponentHealth:
    """Проверка здоровья планировщика."""
    start_time = time.time()

    try:
        # Проверка реального состояния scheduler через ServiceManager
        from services.service_manager import get_service_manager

        manager = get_service_manager()
        scheduler = manager._get_service("scheduler")

        scheduler_alive = False
        scheduler_error = None
        if scheduler is not None:
            scheduler_alive = scheduler.is_alive()
            scheduler_error = getattr(scheduler, '_last_error', None)

        state = manager.get_state("scheduler").value

        # Проверка наличия задач в БД
        from services.database import get_database_service
        from sqlalchemy import select, func
        from database.models import Task

        async with get_database_service().session_context() as session:
            query = select(Task.status, func.count(Task.id)).group_by(Task.status)
            result = await session.execute(query)
            task_counts = {row[0]: row[1] for row in result.all()}

        latency_ms = (time.time() - start_time) * 1000

        pending = task_counts.get('pending', 0)
        active = task_counts.get('active', 0)

        if not scheduler_alive and state != "stopped":
            return ComponentHealth(
                name="scheduler",
                status=HealthStatus.UNHEALTHY,
                severity=SeverityLevel.MEDIUM,
                message=f"Планировщик упал (состояние: {state})",
                latency_ms=latency_ms,
                details={
                    "task_counts": task_counts,
                    "total_tasks": sum(task_counts.values()),
                    "last_error": scheduler_error,
                },
            )

        if state == "stopped":
            return ComponentHealth(
                name="scheduler",
                status=HealthStatus.UNKNOWN,
                severity=SeverityLevel.MEDIUM,
                message=f"Планировщик остановлен ({pending} ожидает, {active} в работе)",
                latency_ms=latency_ms,
                details={
                    "task_counts": task_counts,
                    "total_tasks": sum(task_counts.values()),
                },
            )

        return ComponentHealth(
            name="scheduler",
            status=HealthStatus.HEALTHY,
            severity=SeverityLevel.MEDIUM,
            message=f"Планировщик активен ({pending} ожидает, {active} в работе)",
            latency_ms=latency_ms,
            details={
                "task_counts": task_counts,
                "total_tasks": sum(task_counts.values()),
            },
        )

    except Exception as e:
        return ComponentHealth(
            name="scheduler",
            status=HealthStatus.UNHEALTHY,
            severity=SeverityLevel.MEDIUM,
            message=f"Планировщик ошибка: {type(e).__name__}: {e}",
            latency_ms=(time.time() - start_time) * 1000,
        )


async def check_listener_health() -> ComponentHealth:
    """Проверка здоровья ListenerBot (Telethon)."""
    start_time = time.time()

    try:
        from services.service_manager import get_service_manager

        manager = get_service_manager()
        listener = manager._get_service("listener")

        if listener is None:
            return ComponentHealth(
                name="listener",
                status=HealthStatus.UNHEALTHY,
                severity=SeverityLevel.HIGH,
                message="ListenerBot не зарегистрирован в ServiceManager",
                latency_ms=(time.time() - start_time) * 1000,
            )

        # is_alive() проверяет _running, client, и client.is_connected()
        alive = listener.is_alive()

        latency_ms = (time.time() - start_time) * 1000
        details: Dict[str, Any] = {}

        # Дополнительно: покажем последнюю ошибку если есть
        last_error = getattr(listener, '_last_error', None)
        if last_error:
            details["last_error"] = last_error

        if alive:
            return ComponentHealth(
                name="listener",
                status=HealthStatus.HEALTHY,
                severity=SeverityLevel.HIGH,
                message="ListenerBot подключён к Telegram",
                latency_ms=latency_ms,
                details=details,
            )
        else:
            state = manager.get_state("listener").value
            return ComponentHealth(
                name="listener",
                status=HealthStatus.UNHEALTHY,
                severity=SeverityLevel.HIGH,
                message=f"ListenerBot не активен (состояние: {state})",
                latency_ms=latency_ms,
                details=details,
            )

    except Exception as e:
        return ComponentHealth(
            name="listener",
            status=HealthStatus.UNHEALTHY,
            severity=SeverityLevel.HIGH,
            message=f"ListenerBot ошибка: {type(e).__name__}: {e}",
            latency_ms=(time.time() - start_time) * 1000,
        )


async def check_categorization_queue_health() -> ComponentHealth:
    """Проверка здоровья очереди категоризации и AI agent queue."""
    start_time = time.time()

    try:
        from services.categorization.queue import CategorizationQueue
        from services.ai_agent.agent_queue import get_agent_queue

        # Кэшируем CategorizationQueue — singleton
        if not hasattr(check_categorization_queue_health, '_queue'):
            check_categorization_queue_health._queue = CategorizationQueue()
        queue = check_categorization_queue_health._queue

        # Проверяем AgentTaskQueue — реальный статус воркеров
        agent_queue = get_agent_queue()
        agent_running = getattr(agent_queue, '_running', False)
        agent_stats = {}
        if hasattr(agent_queue, '_stats'):
            agent_stats = dict(agent_queue._stats)

        # Проверяем размер очереди
        current_size = len(queue._queue) if hasattr(queue, '_queue') else 0
        max_size = queue._maxlen if hasattr(queue, '_maxlen') else "N/A"

        latency_ms = (time.time() - start_time) * 1000

        if agent_running:
            return ComponentHealth(
                name="categorization_queue",
                status=HealthStatus.HEALTHY,
                severity=SeverityLevel.MEDIUM,
                message=f"Очередь активна (AI воркеры работают, {current_size}/{max_size} задач)",
                latency_ms=latency_ms,
                details={
                    "current_size": current_size,
                    "max_size": max_size,
                    "agent_queue_running": agent_running,
                    "agent_stats": agent_stats,
                },
            )
        else:
            # AI воркеры не запущены — деградация, но не критично
            # (очередь может работать локально без Redis воркеров)
            return ComponentHealth(
                name="categorization_queue",
                status=HealthStatus.DEGRADED,
                severity=SeverityLevel.MEDIUM,
                message=f"Очередь существует, но AI воркеры не запущены ({current_size}/{max_size} задач)",
                latency_ms=latency_ms,
                details={
                    "current_size": current_size,
                    "max_size": max_size,
                    "agent_queue_running": agent_running,
                    "agent_stats": agent_stats,
                },
            )

    except Exception as e:
        return ComponentHealth(
            name="categorization_queue",
            status=HealthStatus.UNHEALTHY,
            severity=SeverityLevel.MEDIUM,
            message=f"Очередь категоризации ошибка: {type(e).__name__}: {e}",
            latency_ms=(time.time() - start_time) * 1000,
        )


# =============================================================================
# Создание checker'а со встроенными проверками
# =============================================================================

def create_default_health_checker() -> HealthChecker:
    """
    Создать health checker со стандартными проверками.

    Returns:
        HealthChecker с настроенными проверками
    """
    checker = HealthChecker()

    # Критичные компоненты
    checker.add_check("database", check_database_health, SeverityLevel.CRITICAL)
    checker.add_check("telegram_bot", check_telegram_bot_health, SeverityLevel.CRITICAL)

    # Важные компоненты
    checker.add_check("listener", check_listener_health, SeverityLevel.HIGH)
    checker.add_check("llm_fallback", check_llm_fallback_health, SeverityLevel.HIGH)
    checker.add_check("ollama", check_ollama_health, SeverityLevel.HIGH)
    checker.add_check("vector_search", check_vector_search_health, SeverityLevel.HIGH)

    # Компоненты средней важности
    checker.add_check("circuit_breakers", check_circuit_breakers_health, SeverityLevel.MEDIUM)
    checker.add_check("scheduler", check_scheduler_health, SeverityLevel.MEDIUM)
    checker.add_check("categorization_queue", check_categorization_queue_health, SeverityLevel.MEDIUM)

    return checker


# Глобальный checker
_default_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Получить health checker (singleton)."""
    global _default_checker
    if _default_checker is None:
        _default_checker = create_default_health_checker()
    return _default_checker


async def check_system_health(timeout: float = 10.0) -> SystemHealth:
    """
    Проверить здоровье системы.

    Args:
        timeout: Таймаут проверки (сек)

    Returns:
        SystemHealth результат
    """
    checker = get_health_checker()
    return await checker.check_all(timeout=timeout)


async def get_health_summary() -> dict:
    """Получить краткую сводку здоровья."""
    checker = get_health_checker()
    return checker.get_summary()


__all__ = [
    'HealthStatus',
    'SeverityLevel',
    'ComponentHealth',
    'SystemHealth',
    'HealthChecker',
    'create_default_health_checker',
    'get_health_checker',
    'check_system_health',
    'get_health_summary',
    # Встроенные проверки
    'check_database_health',
    'check_ollama_health',
    'check_llm_fallback_health',
    'check_circuit_breakers_health',
    'check_telegram_bot_health',
    'check_listener_health',
    'check_vector_search_health',
    'check_scheduler_health',
    'check_categorization_queue_health',
]
