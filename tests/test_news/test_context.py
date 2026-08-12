"""
Tests for EventContextService.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from services.news.context import EventContextService


@pytest.fixture
def mock_repos():
    """Фикстура мок-репозиториев."""
    return {
        'events': MagicMock(),
        'posts': MagicMock(),
    }


@pytest.fixture
def context_service(mock_repos):
    """Фикстура сервиса контекста."""
    return EventContextService(
        events_repo=mock_repos['events'],
        posts_repo=mock_repos['posts'],
    )


class TestEventContextService:
    """Тесты для сервиса управления контекстом."""

    @pytest.mark.asyncio
    async def test_find_similar(self, context_service):
        """Тест поиска похожих событий и постов."""
        with patch('services.news.helpers.find_similar_events', AsyncMock(return_value=[
            {'id': 1, 'score': 0.9}
        ])):
            with patch('services.news.helpers.find_similar_posts', AsyncMock(return_value=[
                {'id': 2, 'score': 0.8}
            ])):
                result = await context_service.find_similar(
                    text='Test text',
                    category='Politics',
                )

                assert 'events' in result
                assert 'posts' in result
                assert len(result['events']) == 1
                assert len(result['posts']) == 1

    @pytest.mark.asyncio
    async def test_find_similar_empty(self, context_service):
        """Тест поиска без результатов."""
        with patch('services.news.helpers.find_similar_events', AsyncMock(return_value=[])):
            with patch('services.news.helpers.find_similar_posts', AsyncMock(return_value=[])):
                result = await context_service.find_similar(
                    text='Test text',
                    category='Politics',
                )

                assert result['events'] == []
                assert result['posts'] == []

    @pytest.mark.asyncio
    async def test_create_context(self, context_service, mock_repos):
        """Тест создания контекста события."""
        mock_repos['events'].create_event = AsyncMock(return_value=123)

        with patch('services.news.helpers.add_event_to_vector_index', AsyncMock()):
            event_id = await context_service.create_context(
                post_id=1,
                context_data={'description': 'Test event'},
                event_category='Politics',
                tags=['tag1', 'tag2'],
            )

            assert event_id == 123
            mock_repos['events'].create_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_context_no_vector_index(self, context_service, mock_repos):
        """Тест создания контекста без добавления в векторный индекс."""
        mock_repos['events'].create_event = AsyncMock(return_value=123)

        event_id = await context_service.create_context(
            post_id=1,
            context_data={'description': 'Test'},
            event_category='Politics',
            tags=[],
            add_to_vector_index=False,
        )

        assert event_id == 123
        # add_event_to_vector_index не должен вызываться

    @pytest.mark.asyncio
    async def test_get_or_create_context_found(self, context_service):
        """Тест поиска существующего контекста."""
        with patch('services.news.helpers.find_similar_events', AsyncMock(return_value=[
            {'id': 999, 'score': 0.85}
        ])):
            context, is_new = await context_service.get_or_create_context(
                post_id=1,
                text='Test text',
                category='Politics',
            )

            assert context is not None
            assert context['id'] == 999
            assert is_new is False  # Нашли существующий

    @pytest.mark.asyncio
    async def test_get_or_create_context_not_found(self, context_service):
        """Тест когда контекст не найден."""
        with patch('services.news.helpers.find_similar_events', AsyncMock(return_value=[])):
            context, is_new = await context_service.get_or_create_context(
                post_id=1,
                text='Test text',
                category='Politics',
            )

            assert context is None
            assert is_new is True  # Новый контекст

    @pytest.mark.asyncio
    async def test_build_initial_context(self, context_service):
        """Тест построения начального контекста."""
        long_text = 'Длинный текст события ' * 100
        context = context_service.build_initial_context(
            text=long_text,
            category='Politics',
            participants=['Participant 1', 'Participant 2'],
            location='Moscow',
            timestamp='2026-08-08',
            cause='Some cause',
            consequences=['Consequence 1'],
        )

        # event_description обрезается до 200 символов
        assert context['event_description'] == long_text[:200]
        assert context['participants'] == ['Participant 1', 'Participant 2']
        assert context['location'] == 'Moscow'
        assert context['timestamp'] == '2026-08-08'
        assert context['cause'] == 'Some cause'
        assert context['consequences'] == ['Consequence 1']
        assert context['related_topics'] == ['Politics']
        assert context['key_facts'] == []

    @pytest.mark.asyncio
    async def test_build_initial_context_minimal(self, context_service):
        """Тест построения минимального контекста."""
        context = context_service.build_initial_context(
            text='Test',
            category='Other',
        )

        assert context['event_description'] == 'Test'
        assert context['participants'] == []
        assert context['location'] is None
        assert context['timestamp'] is None
        assert context['cause'] is None
        assert context['consequences'] == []
        assert context['related_topics'] == ['Other']
