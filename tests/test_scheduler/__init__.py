"""
Tests for Scheduler.

Запуск:
    pytest tests/test_scheduler/test_scheduler.py -v
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from services.scheduler.scheduler import Scheduler


class TestScheduler:
    """Тесты для планировщика."""

    def test_init(self):
        """Тест инициализации планировщика."""
        scheduler = Scheduler()

        assert scheduler._running is False
        assert scheduler.repo_factory is not None
        assert scheduler.analyst is not None
        assert scheduler.editor is not None
        assert scheduler.archivist is not None

    @pytest.mark.asyncio
    async def test_start(self):
        """Тест запуска планировщика."""
        scheduler = Scheduler()

        with patch('asyncio.create_task') as mock_create_task:
            mock_create_task.return_value = asyncio.Future()
            mock_create_task.return_value.set_result(None)

            with patch.object(scheduler.event_bus, 'run', new_callable=AsyncMock) as mock_run:
                mock_run.return_value = asyncio.Future()
                mock_run.return_value.set_result(None)

                # Запускаем (но сразу отменяем)
                task = asyncio.create_task(scheduler.start())
                await asyncio.sleep(0.1)  # Даём запуститься
                task.cancel()

                try:
                    await task
                except asyncio.CancelledError:
                    pass

                assert scheduler._running is True

    @pytest.mark.asyncio
    async def test_stop(self):
        """Тест остановки планировщика."""
        scheduler = Scheduler()
        scheduler._running = True

        await scheduler.stop()

        assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_process_pending_news_no_posts(self):
        """Тест обработки новостей, когда постов нет."""
        scheduler = Scheduler()

        with patch.object(scheduler.repo_factory, 'posts') as mock_posts_factory:
            mock_posts_repo = AsyncMock()
            mock_posts_repo.get_unanalyzed = AsyncMock(return_value=[])
            mock_posts_factory.return_value = mock_posts_repo

            # Не должно быть ошибок
            await scheduler._process_pending_news()

            mock_posts_repo.get_unanalyzed.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_events_no_events(self):
        """Тест обработки событий, когда событий нет."""
        scheduler = Scheduler()

        with patch.object(scheduler.repo_factory, 'events') as mock_events_factory:
            mock_events_repo = AsyncMock()
            mock_events_repo.get_for_scheduler = AsyncMock(return_value=[])
            mock_events_factory.return_value = mock_events_repo

            # Не должно быть ошибок
            await scheduler._process_events()

            mock_events_repo.get_for_scheduler.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_urgent_news(self):
        """Тест обработки срочной новости."""
        scheduler = Scheduler()

        with patch.object(scheduler.event_bus, 'emit', new_callable=AsyncMock) as mock_emit:
            await scheduler.process_urgent_news(
                post_id=1,
                text='Срочная новость',
                category='Воздушная тревога',
                urgency=5
            )

            assert mock_emit.called
            assert mock_emit.call_args[0][0].type.value == 1  # CREATE_CONTEXT
