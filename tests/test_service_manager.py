"""
Тесты ServiceManager — watchdog и обнаружение упавших сервисов.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.service_manager import ServiceManager, ServiceState


@pytest.fixture(autouse=True)
def reset_singleton():
    """Сбросить синглтон перед каждым тестом."""
    ServiceManager._instance = None
    ServiceManager._initialized = False
    yield
    ServiceManager._instance = None
    ServiceManager._initialized = False


@pytest.fixture
def sm(reset_singleton):
    return ServiceManager()


# =============================================================================
# Watchdog — обнаружение упавших задач
# =============================================================================

class TestWatchdog:
    """Тесты watchdog механизма."""

    @pytest.mark.asyncio
    async def test_watchdog_detects_crashed_service(self, sm):
        """Watchdog должен обнаружить упавшую задачу и сбросить состояние."""
        # Имитируем запущенный listener
        sm._states["listener"] = ServiceState.RUNNING
        sm._started_at["listener"] = 1000000.0
        sm._listener = MagicMock()
        sm._listener._last_error = None

        # Создаём завершённую задачу (как будто сервис упал)
        async def crashed_task():
            raise ConnectionError("Connection refused")

        task = asyncio.create_task(crashed_task())
        # Ждём пока задача упадёт
        try:
            await task
        except Exception:
            pass

        sm._listener_task = task

        # Запускаем один проход watchdog
        try:
            await asyncio.wait_for(sm._watchdog_loop(), timeout=6.0)
        except asyncio.TimeoutError:
            pytest.fail("watchdog loop should have finished within 6s")

        # Проверяем что состояние сброшено
        assert sm._states["listener"] == ServiceState.STOPPED
        assert sm._started_at["listener"] == 0.0
        assert sm._listener._last_error is not None
        assert "ConnectionError" in sm._listener._last_error

    @pytest.mark.asyncio
    async def test_watchdog_ignores_stopped_services(self, sm):
        """Watchdog не должен трогать остановленные сервисы."""
        sm._states["listener"] = ServiceState.STOPPED

        # Даже если задача завершена, состояние не должно меняться
        completed_task = asyncio.create_task(asyncio.sleep(0))
        await completed_task
        sm._listener_task = completed_task

        try:
            await asyncio.wait_for(sm._watchdog_loop(), timeout=6.0)
        except asyncio.TimeoutError:
            pass

        assert sm._states["listener"] == ServiceState.STOPPED

    @pytest.mark.asyncio
    async def test_watchdog_ignores_alive_services(self, sm):
        """Watchdog не должен трогать живые задачи."""
        sm._states["bot"] = ServiceState.RUNNING
        sm._started_at["bot"] = 1000000.0
        sm._bot_service = MagicMock()
        sm._bot_service._last_error = None

        # Живая задача (не завершена)
        event = asyncio.Event()

        async def alive_task():
            await event.wait()

        sm._bot_task = asyncio.create_task(alive_task())

        # Один проход watchdog (5 сек sleep + проверка)
        try:
            await asyncio.wait_for(sm._watchdog_loop(), timeout=6.0)
        except asyncio.TimeoutError:
            pass

        assert sm._states["bot"] == ServiceState.RUNNING
        assert sm._bot_service._last_error is None

        # Чистим
        sm._bot_task.cancel()
        try:
            await sm._bot_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_ensure_watchdog_starts_once(self, sm):
        """_ensure_watchdog должен запустить watchdog только один раз."""
        sm._ensure_watchdog()
        first_task = sm._watchdog_task

        sm._ensure_watchdog()
        assert sm._watchdog_task is first_task  # Та же задача

        # Чистим
        sm._watchdog_task.cancel()
        try:
            await sm._watchdog_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_ensure_watchdog_restarts_after_done(self, sm):
        """После завершения старого watchdog _ensure создаёт новый."""
        sm._ensure_watchdog()
        old_task = sm._watchdog_task

        old_task.cancel()
        try:
            await old_task
        except asyncio.CancelledError:
            pass

        assert old_task.done()

        sm._ensure_watchdog()
        assert sm._watchdog_task is not old_task
        assert not sm._watchdog_task.done()

        # Чистим
        sm._watchdog_task.cancel()
        try:
            await sm._watchdog_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_stop_all_cancels_watchdog(self, sm):
        """stop_all должен остановить watchdog."""
        sm._ensure_watchdog()
        assert sm._watchdog_task is not None
        assert not sm._watchdog_task.done()

        # Сбрасываем задачи чтобы stop_all не падал
        sm._bot_task = None
        sm._listener_task = None
        sm._scheduler_task = None

        await sm.stop_all()

        assert sm._watchdog_task is None
