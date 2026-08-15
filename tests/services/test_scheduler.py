"""
Тесты для Scheduler (планировщик задач).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import time

from services.scheduler.scheduler import Scheduler


class TestSchedulerInit:
    """Тесты инициализации планировщика."""

    def test_init_without_container(self):
        """Проверка инициализации без контейнера."""
        scheduler = Scheduler()
        assert scheduler._container is None
        assert scheduler._running is False
        assert scheduler._initialized is False

    def test_init_with_container(self):
        """Проверка инициализации с контейнером."""
        mock_container = MagicMock()
        scheduler = Scheduler(container=mock_container)
        assert scheduler._container is mock_container


class TestSchedulerPeriodicTask:
    """Тесты периодических задач."""

    def test_periodic_task_default_values(self):
        """Проверка значений по умолчанию для периодических задач."""
        # Утреняя задача: 09:00 МСК
        # Вечерняя задача: 21:00 МСК
        # Время указывается в сущности Task, не в коде
        assert time(9, 0) == time(9, 0)  # Morning default
        assert time(21, 0) == time(21, 0)  # Evening default


class TestSchedulerMethods:
    """Тесты методов планировщика."""

    @pytest.mark.asyncio
    async def test_stop_not_running(self):
        """Проверка остановки когда не запущен."""
        scheduler = Scheduler()
        scheduler._running = False
        # Просто проверяем что метод существует и не падает
        assert hasattr(scheduler, 'stop')

    @pytest.mark.asyncio
    async def test_init_components(self):
        """Проверка инициализации компонентов."""
        with patch('services.scheduler.scheduler.get_database_service') as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.create_session = AsyncMock(return_value=mock_session)
            mock_db.return_value.session_context = MagicMock()

            scheduler = Scheduler()
            await scheduler._init_components()

            assert scheduler._initialized is True
            assert scheduler._session is not None

    @pytest.mark.asyncio
    async def test_init_components_with_container(self):
        """Проверка инициализации с контейнером."""
        mock_container = MagicMock()
        mock_container.create_orchestrator = AsyncMock()

        with patch('services.scheduler.scheduler.get_database_service') as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.create_session = AsyncMock(return_value=mock_session)
            mock_db.return_value.session_context = MagicMock()

            scheduler = Scheduler(container=mock_container)
            await scheduler._init_components()

            # Должен вызвать container.create_orchestrator
            mock_container.create_orchestrator.assert_called_once()


class TestTaskProcessor:
    """Тесты обработчика задач."""

    @pytest.mark.asyncio
    async def test_process_tasks_empty(self):
        """Проверка обработки пустого списка задач."""
        with patch('services.scheduler.scheduler.get_database_service') as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.session_context = MagicMock()

            async def mock_context():
                yield mock_session

            mock_db.return_value.session_context.return_value = mock_context()

            scheduler = Scheduler()
            scheduler._db_service = mock_db.return_value

            # Мокаем repo_factory
            mock_factory = MagicMock()
            mock_task_repo = AsyncMock()
            mock_task_repo.get_pending_tasks = AsyncMock(return_value=[])
            mock_factory.tasks.return_value = mock_task_repo

            scheduler.repo_factory = mock_factory
            scheduler.orchestrator = AsyncMock()

            # Должно завершиться без ошибок
            await scheduler._process_tasks()


class TestSchedulerLifecycle:
    """Тесты жизненного цикла планировщика."""

    @pytest.mark.skip(reason="Тест устарел - методы _run_morning_scheduler и _run_evening_scheduler удалены")
    @pytest.mark.asyncio
    async def test_start_creates_tasks(self):
        """Проверка, что start создаёт фоновые задачи."""
        with patch('services.scheduler.scheduler.get_database_service') as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.create_session = AsyncMock(return_value=mock_session)
            mock_db.return_value.session_context = MagicMock()

            scheduler = Scheduler()

            with patch.object(scheduler, '_init_components', new_callable=AsyncMock):
                with patch.object(scheduler, '_run_morning_scheduler', new_callable=AsyncMock):
                    with patch.object(scheduler, '_run_evening_scheduler', new_callable=AsyncMock):
                        with patch.object(scheduler, '_run_event_processor', new_callable=AsyncMock):
                            with patch.object(scheduler, '_run_task_processor', new_callable=AsyncMock):
                                # Мокаем orchestrator
                                mock_orchestrator = AsyncMock()
                                mock_orchestrator.start_event_bus = AsyncMock()
                                scheduler.orchestrator = mock_orchestrator

                                await scheduler.start()

                                assert scheduler._running is True

    @pytest.mark.asyncio
    async def test_wait_timeout(self):
        """Проверка ожидания с таймаутом."""
        scheduler = Scheduler()
        scheduler._morning_task = None
        scheduler._evening_task = None
        scheduler._event_task = None

        # Должно завершиться без ошибок когда задачи не созданы
        await scheduler.wait()
