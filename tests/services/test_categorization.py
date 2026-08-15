"""
Tests for Categorization module (new architecture).

Tests for:
- CategorizationQueue
- NewsClassifier
- NewsSaver
- CategorizationProcessor
"""

import pytest
from unittest.mock import AsyncMock

from services.categorization.queue import CategorizationQueue, CategorizationTask
from services.categorization.classifier import NewsClassifier, ClassificationResult
from services.categorization.saver import NewsSaver


class TestCategorizationTask:
    """Тесты для CategorizationTask."""

    def test_init(self):
        """Тест инициализации задачи."""
        task = CategorizationTask(
            channel_id=123,
            prompt="Test prompt",
            original_text="Original text",
            title="Title",
            desc="Description"
        )

        assert task.channel_id == 123
        assert task.prompt == "Test prompt"
        assert task.original_text == "Original text"
        assert task.title == "Title"
        assert task.desc == "Description"


class TestCategorizationQueue:
    """Тесты для CategorizationQueue."""

    @pytest.mark.asyncio
    async def test_stop(self):
        """Тест остановки очереди."""
        queue = CategorizationQueue()
        await queue.stop()
        assert queue._running is False


class TestNewsClassifier:
    """Тесты для NewsClassifier."""

    def test_parse_valid_json_response(self):
        """Тест парсинга валидного JSON ответа."""
        classifier = NewsClassifier()
        response = '''```json
{
    "category": "Политика",
    "urgency": 4,
    "text": "Текст новости",
    "is_advertisement": false
}
```'''
        result = classifier.parse_ai_response(response)

        assert isinstance(result, ClassificationResult)
        assert result.category == "Политика"
        assert result.urgency == 4
        assert result.text == "Текст новости"
        assert result.is_advertisement is False

    def test_parse_advertisement(self):
        """Тест определения рекламы."""
        classifier = NewsClassifier()
        response = '''{
    "category": "Реклама",
    "urgency": 1,
    "text": "Купите слона",
    "is_advertisement": true
}'''
        result = classifier.parse_ai_response(response)

        assert result.is_advertisement is True


class TestNewsSaver:
    """Тесты для NewsSaver."""

    @pytest.mark.asyncio
    async def test_save_urgent_news(self):
        """Тест сохранения срочной новости."""
        # Моки для репозиториев
        posts_repo = AsyncMock()
        channels_repo = AsyncMock()
        events_repo = AsyncMock()

        saver = NewsSaver(posts_repo, channels_repo, events_repo)

        classification = ClassificationResult(
            text="Срочная новость",
            category="Политика",
            urgency=5,
            is_advertisement=False
        )

        post_id = await saver.save_urgent_news(channel_id=123, classification=classification)

        # Проверяем вызов репозитория
        posts_repo.create_post.assert_called_once()


