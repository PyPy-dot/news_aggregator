"""
Tests for NewsOrchestrator with strategies.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock

from sqlalchemy.ext.asyncio import AsyncSession

from services.news.orchestrator import NewsOrchestrator
from database import RepositoryFactory
from services.news.strategies.base import NewsProcessingStrategy
from services.news.strategies.urgent import UrgentNewsStrategy
from services.news.strategies.scheduled import ScheduledNewsStrategy
from services.news.strategies.trusted import TrustedSourceStrategy


@pytest.fixture
def mock_repos():
    """Фикстура для мок-репозиториев."""
    return {
        'posts': AsyncMock(),
        'events': AsyncMock(),
        'news': AsyncMock(),
        'publishers': AsyncMock(),
    }


@pytest.fixture
def mock_repo_factory(mock_repos):
    """Фикстура для мок-фабрики репозиториев."""
    factory = MagicMock(spec=RepositoryFactory)
    factory.posts.return_value = mock_repos['posts']
    factory.events.return_value = mock_repos['events']
    factory.news.return_value = mock_repos['news']
    factory.publishers.return_value = mock_repos['publishers']
    return factory


@pytest.fixture
def mock_session():
    """Фикстура для мок-сессии БД."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def mock_notification_service():
    """Фикстура для мок notification service."""
    return MagicMock()


class TestNewsOrchestrator:
    """Тесты для NewsOrchestrator."""

    def test_init(self, mock_repo_factory):
        """Тест инициализации."""
        # Создаём мок notification_service для теста
        mock_notification_service = MagicMock()

        orchestrator = NewsOrchestrator(
            repo_factory=mock_repo_factory,
            notification_service=mock_notification_service,
        )

        assert orchestrator.repo_factory is mock_repo_factory
        assert orchestrator.event_bus is not None
        assert orchestrator.notification_service is mock_notification_service
        assert orchestrator._running is False
        # Проверяем что стратегии инициализированы
        assert len(orchestrator._strategies) == 3
        assert 'urgent' in orchestrator._strategies
        assert 'scheduled' in orchestrator._strategies
        assert 'trusted' in orchestrator._strategies

    def test_strategies_types(self, mock_repo_factory, mock_notification_service):
        """Тест типов стратегий."""
        orchestrator = NewsOrchestrator(
            repo_factory=mock_repo_factory,
            notification_service=mock_notification_service,
        )
        
        assert isinstance(orchestrator._strategies['urgent'], UrgentNewsStrategy)
        assert isinstance(orchestrator._strategies['scheduled'], ScheduledNewsStrategy)
        assert isinstance(orchestrator._strategies['trusted'], TrustedSourceStrategy)

    def test_determine_priority_urgent(self, mock_repo_factory, mock_notification_service):
        """Тест определения приоритета для срочных новостей."""
        orchestrator = NewsOrchestrator(
            repo_factory=mock_repo_factory,
            notification_service=mock_notification_service,
        )
        
        priority = orchestrator._determine_priority(urgency=5, is_trusted_source=False)
        assert priority == 'urgent'
        
        priority = orchestrator._determine_priority(urgency=4, is_trusted_source=False)
        assert priority == 'urgent'

    def test_determine_priority_scheduled(self, mock_repo_factory):
        """Тест определения приоритета для плановых новостей."""
        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)
        
        priority = orchestrator._determine_priority(urgency=3, is_trusted_source=False)
        assert priority == 'scheduled'
        
        priority = orchestrator._determine_priority(urgency=1, is_trusted_source=False)
        assert priority == 'scheduled'

    def test_determine_priority_trusted(self, mock_repo_factory):
        """Тест определения приоритета для доверенных источников."""
        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)
        
        # Доверенный источник + срочность >= 4 = trusted
        priority = orchestrator._determine_priority(urgency=5, is_trusted_source=True)
        assert priority == 'trusted'
        
        priority = orchestrator._determine_priority(urgency=4, is_trusted_source=True)
        assert priority == 'trusted'

    def test_get_strategy(self, mock_repo_factory, mock_notification_service):
        """Тест получения стратегии."""
        orchestrator = NewsOrchestrator(
            repo_factory=mock_repo_factory,
            notification_service=mock_notification_service,
        )
        
        strategy = orchestrator._get_strategy('urgent')
        assert isinstance(strategy, NewsProcessingStrategy)
        assert strategy.name == 'urgent'
        
        strategy = orchestrator._get_strategy('scheduled')
        assert strategy.name == 'scheduled'
        
        strategy = orchestrator._get_strategy('trusted')
        assert strategy.name == 'trusted'

    def test_get_strategy_invalid(self, mock_repo_factory):
        """Тест получения несуществующей стратегии."""
        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)
        
        with pytest.raises(ValueError):
            orchestrator._get_strategy('invalid')

    @pytest.mark.asyncio
    async def test_process_news_trusted(self, mock_repo_factory, mock_repos, mock_notification_service):
        """Тест обработки новости от доверенного источника."""
        orchestrator = NewsOrchestrator(
            repo_factory=mock_repo_factory,
            notification_service=mock_notification_service,
        )
        orchestrator._running = True

        # Мок для publisher repo - возвращаем publisher с matching категорией
        mock_publisher = MagicMock()
        mock_publisher.id = 1
        mock_publisher.channel_id = 123
        mock_publisher.category = "Политика"
        mock_publisher.title = "Test Publisher"
        mock_repos['publishers'].get_all.return_value = [mock_publisher]

        # Мок для posts repo
        mock_post = MagicMock()
        mock_post.id = 1
        mock_post.urgency = 5
        mock_repos['posts'].get = AsyncMock(return_value=mock_post)
        mock_repos['posts'].mark_direct_publish = AsyncMock()

        # Мок для event_bus
        orchestrator.event_bus.emit = AsyncMock()

        # Мок для get_bot_instance_async и PublisherService (импортируются внутри метода)
        with patch('services.news.strategies.trusted.get_bot_instance_async', return_value=MagicMock()) as mock_get_bot, \
             patch('services.news.strategies.trusted.PublisherService') as MockPublisherService:

            mock_publisher_service = AsyncMock()
            mock_publisher_service.publish_to_channel = AsyncMock(return_value=True)
            MockPublisherService.return_value = mock_publisher_service

            await orchestrator.process_news(
                post_id=1,
                text="News text",
                category="Политика",
                urgency=5,
                channel_id=123,
                is_trusted_source=True
            )

            # Должен вызваться mark_direct_publish
            mock_repos['posts'].mark_direct_publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_news_urgent(self, mock_repo_factory, mock_repos, mock_notification_service):
        """Тест обработки срочной новости."""
        orchestrator = NewsOrchestrator(
            repo_factory=mock_repo_factory,
            notification_service=mock_notification_service,
        )
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
    async def test_process_news_scheduled(self, mock_repo_factory, mock_repos, mock_notification_service):
        """Тест обработки плановой новости."""
        orchestrator = NewsOrchestrator(
            repo_factory=mock_repo_factory,
            notification_service=mock_notification_service,
        )
        orchestrator._running = True

        # Мок для events repo
        mock_repos['events'].create_event = AsyncMock(return_value=MagicMock(id=99))

        await orchestrator.process_news(
            post_id=3,
            text="Scheduled news",
            category="Обычное",
            urgency=2,
            channel_id=123,
            is_trusted_source=False
        )

        # Должен быть создан event
        mock_repos['events'].create_event.assert_called_once()

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
    async def test_process_pending_news_batch_empty(self, mock_repo_factory, mock_repos):
        """Тест обработки пустой пачки новостей."""
        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)
        orchestrator._running = True

        # Мок для posts repo
        mock_repos['posts'].get_unanalyzed.return_value = []

        count = await orchestrator.process_pending_news_batch(hours=48)

        assert count == 0

    @pytest.mark.asyncio
    async def test_process_pending_news_batch(self, mock_repo_factory, mock_repos, mock_notification_service):
        """Тест обработки пачки новостей (группировка по категориям)."""
        orchestrator = NewsOrchestrator(
            repo_factory=mock_repo_factory,
            notification_service=mock_notification_service,
        )
        orchestrator._running = True

        # Мок для posts repo
        mock_post = MagicMock()
        mock_post.id = 1
        mock_post.category = "Политика"
        mock_post.urgency = "3"
        mock_post.text = "Test news text"
        mock_post.tags = '[]'
        mock_post.category_confidence = 0.5
        mock_post.checked_at = False

        mock_repos['posts'].get_unanalyzed.return_value = [mock_post]
        mock_repos['posts'].mark_analyzed = AsyncMock(return_value=True)

        # Мок для _process_analyzed_posts_batch метода (групповая обработка)
        orchestrator._process_analyzed_posts_batch = AsyncMock()

        count = await orchestrator.process_pending_news_batch(hours=48)

        # Проверяем, что новость была обработана
        assert count >= 1  # Должна обработать хотя бы одну новость
        # Проверяем, что _process_analyzed_posts_batch был вызван
        orchestrator._process_analyzed_posts_batch.assert_called()

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


class TestEventBusPriority:
    """Тесты для EventBus с приоритетами."""

    def test_event_high_priority(self):
        """Тест создания события с высоким приоритетом."""
        from services.ai_agent.events import Event, EventType
        
        event = Event.high_priority(EventType.GENERATE_NEWS, {'test': 'data'})
        assert event.priority == 1

    def test_event_low_priority(self):
        """Тест создания события с низким приоритетом."""
        from services.ai_agent.events import Event, EventType
        
        event = Event.low_priority(EventType.GENERATE_NEWS, {'test': 'data'})
        assert event.priority == 5
