"""
Tests for PostRepository.

Запуск:
    pytest tests/test_repositories/test_posts.py -v
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone, timedelta

from database.repositories.posts import PostRepository


class TestPostRepository:
    """Тесты для PostRepository."""

    @pytest.mark.asyncio
    async def test_create_post(self, db_session: AsyncSession, mock_post_data: dict):
        """Тест создания поста."""
        repo = PostRepository(db_session)

        post = await repo.create_post(
            channel_id=mock_post_data['channel_id'],
            text=mock_post_data['text'],
            category=mock_post_data['category'],
            urgency=mock_post_data['urgency']
        )

        assert post is not None
        assert post.channel_id == mock_post_data['channel_id']
        assert post.text == mock_post_data['text']
        assert post.category == mock_post_data['category']

    @pytest.mark.asyncio
    async def test_get_unanalyzed(self, db_session: AsyncSession, mock_post_data: dict):
        """Тест получения необработанных постов."""
        repo = PostRepository(db_session)

        # Создаём пост
        await repo.create_post(
            channel_id=mock_post_data['channel_id'],
            text=mock_post_data['text'],
            category=mock_post_data['category'],
            urgency=mock_post_data['urgency']
        )

        # Получаем необработанные
        posts = await repo.get_unanalyzed(hours=48)

        assert len(posts) >= 1
        assert posts[0].category == mock_post_data['category']

    @pytest.mark.asyncio
    async def test_mark_analyzed(self, db_session: AsyncSession, mock_post_data: dict):
        """Тест отметки поста как обработанного."""
        repo = PostRepository(db_session)

        # Создаём пост
        post = await repo.create_post(
            channel_id=mock_post_data['channel_id'],
            text=mock_post_data['text'],
            category=mock_post_data['category'],
            urgency=mock_post_data['urgency']
        )

        # Отмечаем как обработанный
        result = await repo.mark_analyzed(post.id, generated_news_id=1)

        assert result is True

        # Проверяем
        updated_post = await repo.get(post.id)
        assert updated_post.checked_at is True
        assert updated_post.generated_news_id == 1

    @pytest.mark.asyncio
    async def test_is_analyzed_false(self, db_session: AsyncSession, mock_post_data: dict):
        """Тест проверки: пост не обработан."""
        repo = PostRepository(db_session)

        post = await repo.create_post(
            channel_id=mock_post_data['channel_id'],
            text=mock_post_data['text'],
            category=mock_post_data['category'],
            urgency=mock_post_data['urgency']
        )

        is_analyzed = await repo.is_analyzed(post.id)

        assert is_analyzed is False

    @pytest.mark.asyncio
    async def test_is_analyzed_true(self, db_session: AsyncSession, mock_post_data: dict):
        """Тест проверки: пост обработан."""
        repo = PostRepository(db_session)

        post = await repo.create_post(
            channel_id=mock_post_data['channel_id'],
            text=mock_post_data['text'],
            category=mock_post_data['category'],
            urgency=mock_post_data['urgency']
        )

        # Отмечаем как обработанный
        await repo.mark_analyzed(post.id)

        is_analyzed = await repo.is_analyzed(post.id)

        assert is_analyzed is True

    @pytest.mark.asyncio
    async def test_update_category_confidence(self, db_session: AsyncSession, mock_post_data: dict):
        """Тест обновления уверенности категории."""
        repo = PostRepository(db_session)

        post = await repo.create_post(
            channel_id=mock_post_data['channel_id'],
            text=mock_post_data['text'],
            category=mock_post_data['category'],
            urgency=mock_post_data['urgency']
        )

        # Обновляем уверенность
        result = await repo.update_category_confidence(post.id, 0.85)

        assert result is True

        # Проверяем
        updated_post = await repo.get(post.id)
        assert updated_post.category_confidence == 0.85

    @pytest.mark.asyncio
    async def test_get_by_channel(self, db_session: AsyncSession, mock_post_data: dict):
        """Тест получения постов по каналу."""
        repo = PostRepository(db_session)

        # Создаём несколько постов для одного канала
        await repo.create_post(
            channel_id=mock_post_data['channel_id'],
            text='Post 1',
            category='Политика',
            urgency=3
        )
        await repo.create_post(
            channel_id=mock_post_data['channel_id'],
            text='Post 2',
            category='Экономика',
            urgency=2
        )

        # Получаем посты канала
        posts = await repo.get_by_channel(mock_post_data['channel_id'], limit=10)

        assert len(posts) >= 2
