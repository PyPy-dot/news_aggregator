"""
Tests for NewsOrchestrator.process_news_cycle().

Запуск:
    pytest tests/services/test_news_cycle.py -v
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from services.news.orchestrator import NewsOrchestrator
from database import RepositoryFactory


@pytest.fixture
def mock_repo_factory():
    """Фикстура для мок-фабрики репозиториев."""
    factory = MagicMock(spec=RepositoryFactory)
    return factory


@pytest.fixture
def mock_repos():
    """Фикстура для мок-репозиториев."""
    return {
        'posts': MagicMock(),
        'events': MagicMock(),
        'news': MagicMock(),
        'publishers': MagicMock(),
    }


class TestNewsCycle:
    """Тесты цикла обработки новостей."""

    @pytest.mark.asyncio
    async def test_process_news_cycle_empty(self, mock_repo_factory, mock_repos):
        """Тест цикла обработки с пустой очередью."""
        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)
        orchestrator._running = True

        # Мок для posts repo — нет необработанных постов
        mock_repos['posts'].get_unanalyzed = AsyncMock(return_value=[])

        # Подменяем репозитории
        mock_repo_factory.posts = MagicMock(return_value=mock_repos['posts'])
        mock_repo_factory.events = MagicMock(return_value=mock_repos['events'])
        mock_repo_factory.news = MagicMock(return_value=mock_repos['news'])

        count = await orchestrator.process_news_cycle()

        assert count == 0
        mock_repos['posts'].get_unanalyzed.assert_called()

    @pytest.mark.asyncio
    async def test_process_news_cycle_not_running(self, mock_repo_factory):
        """Тест цикла обработки когда оркестратор не запущен."""
        orchestrator = NewsOrchestrator(repo_factory=mock_repo_factory)
        # _running = False по умолчанию

        count = await orchestrator.process_news_cycle()

        assert count == 0

    # TODO: Переписать тест с правильными моками для EditorAgent.generate_news
    # Тест требует комплексного мока AI агентов, векторного поиска и БД
    # Это интеграционный тест, который сложно поддерживать
