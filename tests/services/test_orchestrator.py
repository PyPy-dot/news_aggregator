"""
Tests for NewsOrchestrator.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from services.news.orchestrator import NewsOrchestrator, NewsPriority
from database import RepositoryFactory


@pytest.fixture
def mock_repo_factory():
    """Фикстура для мок-фабрики репозиториев."""
    factory = MagicMock(spec=RepositoryFactory)

    # Мок-репозитории
    factory.posts = MagicMock(return_value=AsyncMock())
    factory.events = MagicMock(return_value=AsyncMock())
    factory.news = MagicMock(return_value=AsyncMock())
    factory.publishers = MagicMock(return_value=AsyncMock())

    return factory


@pytest.fixture
def mock_session():
    """Фикстура для мок-сессии БД."""
    session = AsyncMock(spec=AsyncSession)
    return session


class TestNewsPriority:
    """Тесты для NewsPriority enum."""

    def test_priority_values(self):
        """Тест значений приоритетов."""
        assert NewsPriority.URGENT.value == 'urgent'
        assert NewsPriority.SCHEDULED.value == 'scheduled'
        assert NewsPriority.TRUSTED.value == 'trusted'


class TestNewsOrchestrator:
    """Тесты для NewsOrchestrator."""

    def test_init(self, mock_repo_factory):
        """Тест инициализации."""
        orchestrator = NewsOrchestrator(
            repo_factory=mock_repo_factory,
            model='test-model'
        )

        assert orchestrator.repo_factory is mock_repo_factory
        assert orchestrator.model == 'test-model'
        assert orchestrator.analyst is not None
        assert orchestrator.editor is not None
        assert orchestrator.archivist is not None
        assert orchestrator.event_bus is not None
        assert orchestrator.notification_service is not None
        assert orchestrator._running is False

    def test_init_default_model(self, mock_repo_factory):
        """Тест инициализации с моделью по умолчанию."""
        from config.settings import settings

        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)

        assert orchestrator.model == settings.agent_model

    @pytest.mark.asyncio
    async def test_process_news_trusted(self, mock_repo_factory):
        """Тест обработки новости от доверенного источника."""
        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)

        # Запускаем оркестратор (устанавливаем флаг _running)
        orchestrator._running = True

        # Мок для publish repo
        mock_publisher = AsyncMock()
        mock_publisher.get_all.return_value = [MagicMock(id=1)]
        mock_repo_factory.publishers.return_value = mock_publisher

        # Мок для post repo
        mock_post_repo = AsyncMock()
        mock_repo_factory.posts.return_value = mock_post_repo

        await orchestrator.process_news(
            post_id=1,
            text="News text",
            category="Политика",
            urgency=5,
            channel_id=123,
            is_trusted_source=True
        )

        # Должен вызваться mark_direct_publish
        mock_post_repo.mark_direct_publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_news_urgent(self, mock_repo_factory):
        """Тест обработки срочной новости."""
        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)
        orchestrator._running = True

        # Мок для event_bus
        orchestrator.event_bus.emit = AsyncMock()

        await orchestrator.process_news(
            post_id=2,
            text="Urgent news",
            category="Срочное",
            urgency=4,
            channel_id=123,
            is_trusted_source=False
        )

        # Должны быть вызваны события CREATE_CONTEXT и GENERATE_NEWS
        assert orchestrator.event_bus.emit.call_count >= 1

    @pytest.mark.asyncio
    async def test_process_news_scheduled(self, mock_repo_factory):
        """Тест обработки плановой новости."""
        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)
        orchestrator._running = True

        # Мок для events repo
        mock_events_repo = AsyncMock()
        mock_events_repo.create_event.return_value = MagicMock(id=99)
        mock_repo_factory.events.return_value = mock_events_repo

        await orchestrator.process_news(
            post_id=3,
            text="Scheduled news",
            category="Обычное",
            urgency=2,
            channel_id=123,
            is_trusted_source=False
        )

        # Должен быть создан event
        mock_events_repo.create_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_news_not_running(self, mock_repo_factory, caplog):
        """Тест обработки новости когда оркестратор не запущен."""
        import logging
        caplog.set_level(logging.WARNING)

        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)
        # _running = False по умолчанию

        await orchestrator.process_news(
            post_id=1,
            text="News text",
            category="Политика",
            urgency=5,
            channel_id=123,
        )

        assert "не запущен" in caplog.text

    @pytest.mark.asyncio
    async def test_process_pending_news_batch_empty(self, mock_repo_factory):
        """Тест обработки пустой пачки новостей."""
        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)
        orchestrator._running = True

        # Мок для posts repo
        mock_posts_repo = AsyncMock()
        mock_posts_repo.get_unanalyzed.return_value = []
        mock_repo_factory.posts.return_value = mock_posts_repo

        count = await orchestrator.process_pending_news_batch(hours=48)

        assert count == 0

    @pytest.mark.asyncio
    async def test_process_pending_news_batch(self, mock_repo_factory):
        """Тест обработки пачки новостей."""
        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)
        orchestrator._running = True

        # Мок для posts repo
        mock_post = MagicMock()
        mock_post.id = 1
        mock_post.category = "Политика"
        mock_post.urgency = "3"

        mock_posts_repo = AsyncMock()
        mock_posts_repo.get_unanalyzed.return_value = [mock_post]
        mock_posts_repo.is_analyzed.return_value = False
        mock_repo_factory.posts.return_value = mock_posts_repo

        # Мок для event_bus
        orchestrator.event_bus.emit = AsyncMock()

        count = await orchestrator.process_pending_news_batch(hours=48)

        assert count == 1
        orchestrator.event_bus.emit.assert_called()

    @pytest.mark.asyncio
    async def test_process_pending_news_batch_not_running(self, mock_repo_factory):
        """Тест обработки когда оркестратор не запущен."""
        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)
        # _running = False по умолчанию

        count = await orchestrator.process_pending_news_batch(hours=48)

        assert count == 0

    @pytest.mark.asyncio
    async def test_start_event_bus(self, mock_repo_factory):
        """Тест запуска шины событий."""
        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)

        # Мок для event_bus.run
        orchestrator.event_bus.run = AsyncMock()

        # Запускаем на короткое время
        import asyncio

        async def run_and_stop():
            task = asyncio.create_task(orchestrator.start_event_bus())
            await asyncio.sleep(0.01)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await run_and_stop()
        assert orchestrator._running is True

    @pytest.mark.asyncio
    async def test_stop(self, mock_repo_factory):
        """Тест остановки."""
        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)
        orchestrator._running = True

        await orchestrator.stop()
        # Флаг должен быть сброшен
        assert orchestrator._running is False
