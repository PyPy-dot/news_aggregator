"""
Tests for NewsGenerationService.
"""

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch

from services.news.generation import NewsGenerationService


@pytest.fixture
def mock_repos():
    """Фикстура мок-репозиториев."""
    return {
        'posts': AsyncMock(),
        'events': AsyncMock(),
        'news': AsyncMock(),
        'channels': AsyncMock(),
    }


@pytest.fixture
def mock_notification_service():
    """Фикстура мок-сервиса уведомлений."""
    return AsyncMock()


@pytest.fixture
def generation_service(mock_repos, mock_notification_service):
    """Фикстура сервиса генерации."""
    return NewsGenerationService(
        posts_repo=mock_repos['posts'],
        events_repo=mock_repos['events'],
        news_repo=mock_repos['news'],
        channels_repo=mock_repos['channels'],
        notification_service=mock_notification_service,
    )


class TestNewsGenerationService:
    """Тесты для сервиса генерации новостей."""

    @pytest.mark.asyncio
    async def test_generate_news_success(self, generation_service, mock_repos, mock_notification_service):
        """Тест успешной генерации новости."""
        # Мок для EditorAgent
        with patch('services.news.generation.EditorAgent') as MockEditor:
            mock_editor = AsyncMock()
            mock_editor.generate_news = AsyncMock(return_value={
                'text': 'Сгенерированный текст новости',
                'news_tags': ['тег1', 'тег2']
            })
            MockEditor.return_value = mock_editor

            # Мок для ArchivistAgent
            with patch('services.news.generation.ArchivistAgent') as MockArchivist:
                mock_archivist = AsyncMock()
                mock_archivist.create_context = AsyncMock(return_value={
                    'context_data': {'event_description': 'Test event'},
                    'tags': ['тег1']
                })
                MockArchivist.return_value = mock_archivist

                # Мок для add_generated_news
                with patch('services.news.generation.add_generated_news', AsyncMock(return_value=1)):
                    # Мок для репозиториев
                    mock_repos['channels'].get_by_telegram_id = AsyncMock(
                        return_value=MagicMock(title='Test Channel')
                    )

                    # Запускаем генерацию
                    news_id = await generation_service.generate_news(
                        post_id=1,
                        post_text='Тестовый текст',
                        post_category='Политика',
                        post_tags=['тег1'],
                        post_category_confidence=0.9,
                        similar_events=[],
                        similar_posts=[],
                    )

                    assert news_id == 1
                    mock_editor.generate_news.assert_called_once()
                    mock_archivist.create_context.assert_called_once()
                    mock_notification_service.notify_pending_news.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_news_with_similar_events(self, generation_service, mock_repos):
        """Тест генерации с похожими событиями."""
        similar_events = [
            {
                'id': 123,
                'metadata': {
                    'context_data': json.dumps({'event_description': 'Similar event'})
                }
            }
        ]

        with patch('services.news.generation.EditorAgent') as MockEditor:
            mock_editor = AsyncMock()
            mock_editor.generate_news = AsyncMock(return_value={
                'text': 'News text',
                'news_tags': []
            })
            MockEditor.return_value = mock_editor

            with patch('services.news.generation.ArchivistAgent') as MockArchivist:
                mock_archivist = AsyncMock()
                mock_archivist.create_context = AsyncMock(return_value={
                    'context_data': {},
                    'tags': []
                })
                MockArchivist.return_value = mock_archivist

                with patch('services.news.generation.add_generated_news', AsyncMock(return_value=1)):
                    mock_repos['channels'].get_by_telegram_id = AsyncMock(
                        return_value=MagicMock(title='Test Channel')
                    )

                    await generation_service.generate_news(
                        post_id=1,
                        post_text='Test',
                        post_category='Test',
                        post_tags=[],
                        post_category_confidence=0.5,
                        similar_events=similar_events,
                        similar_posts=[],
                    )

                    # Проверяем, что контекст передан в Editor
                    call_args = mock_editor.generate_news.call_args
                    assert call_args[1]['event_context'] == {'event_description': 'Similar event'}

    @pytest.mark.asyncio
    async def test_generate_news_error_returns_none(self, generation_service, mock_repos):
        """Тест возврата None при ошибке."""
        with patch('services.news.generation.EditorAgent') as MockEditor:
            mock_editor = AsyncMock()
            mock_editor.generate_news = AsyncMock(side_effect=Exception("AI error"))
            MockEditor.return_value = mock_editor

            news_id = await generation_service.generate_news(
                post_id=1,
                post_text='Test',
                post_category='Test',
                post_tags=[],
                post_category_confidence=0.5,
                similar_events=[],
                similar_posts=[],
            )

            assert news_id is None

    @pytest.mark.asyncio
    async def test_notify_moderation_no_service(self, mock_repos):
        """Тест уведомления без сервиса."""
        service = NewsGenerationService(
            posts_repo=mock_repos['posts'],
            events_repo=mock_repos['events'],
            news_repo=mock_repos['news'],
            channels_repo=mock_repos['channels'],
            notification_service=None,
        )

        # Не должно падать
        await service._notify_moderation(
            news_id=1,
            post_id=1,
            news_text='Test',
            category='Test',
        )

    @pytest.mark.asyncio
    async def test_notify_moderation_channel_error(self, generation_service, mock_repos, mock_notification_service):
        """Тест уведомления с ошибкой получения канала."""
        mock_repos['posts'].get = AsyncMock(return_value=None)

        # Не должно падать
        await generation_service._notify_moderation(
            news_id=1,
            post_id=1,
            news_text='Test',
            category='Test',
        )

        # Уведомление должно быть отправлено с fallback названием
        mock_notification_service.notify_pending_news.assert_called_once()
        call_args = mock_notification_service.notify_pending_news.call_args
        assert 'Post ID=1' in call_args[1]['channel_title']
