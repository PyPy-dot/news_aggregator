"""
Post repository для работы с постами.
"""

import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, update, desc, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import TelegramPost
from database.repositories.base import BaseRepository


class PostRepository(BaseRepository[TelegramPost]):
    """
    Репозиторий для работы с постами.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, TelegramPost)

    async def get_unanalyzed(self, hours: int = 48) -> list[TelegramPost]:
        """
        Получить посты, которые ещё не были обработаны Аналитиком.

        Args:
            hours: За сколько часов искать посты (не используется, оставлен для совместимости)

        Returns:
            Список необработанных постов
        """
        result = await self.session.execute(
            select(TelegramPost)
            .where(TelegramPost.checked_at == False)
            .order_by(desc(TelegramPost.created_at))
        )
        return result.scalars().all()

    async def mark_analyzed(
        self,
        post_id: int,
        generated_news_id: Optional[int] = None
    ) -> bool:
        """
        Отметить пост как обработанный Аналитиком.

        Args:
            post_id: ID поста
            generated_news_id: ID сгенерированной новости

        Returns:
            True если обновлён, False если не найден
        """
        post = await self.get(post_id)
        if post:
            post.checked_at = True
            if generated_news_id:
                post.generated_news_id = generated_news_id
            await self.session.commit()
            return True
        return False

    async def update_category_confidence(
        self,
        post_id: int,
        confidence: float
    ) -> bool:
        """
        Обновить оценку уверенности категории.

        Args:
            post_id: ID поста
            confidence: Уверенность (0.0-1.0)

        Returns:
            True если обновлена, False если не найден
        """
        post = await self.get(post_id)
        if post:
            post.category_confidence = min(1.0, max(0.0, confidence))
            await self.session.commit()
            return True
        return False

    async def create_post(
        self,
        channel_id: int,
        text: str,
        category: str,
        urgency: int,
        rate: Optional[int] = None,
        source_trust_rating: float = 0.5,
        tags: str = '',
    ) -> TelegramPost:
        """
        Создать новый пост (case-insensitive tags).

        Args:
            channel_id: ID канала в Telegram
            text: Текст поста
            category: Категория
            urgency: Срочность (1-5)
            rate: Рейтинг новости
            source_trust_rating: Рейтинг доверия источника
            tags: Теги (JSON строка)

        Returns:
            Созданный пост
        """
        # Нормализация тэгов к нижнему регистру
        if tags:
            try:
                tags_list = json.loads(tags)
                tags = json.dumps([tag.lower() for tag in tags_list], ensure_ascii=False)
            except json.JSONDecodeError:
                tags = '[]'
        else:
            tags = '[]'

        post = TelegramPost(
            channel_id=channel_id,
            text=text,
            category=category,
            urgency=urgency,
            rate=rate or 50,
            source_trust_rating=source_trust_rating,
            tags=tags,
            created_at=datetime.now(timezone.utc)
        )
        self.session.add(post)
        await self.session.commit()
        await self.session.refresh(post)
        return post

    async def get_by_channel(self, channel_id: int, limit: int = 50) -> list[TelegramPost]:
        """
        Получить посты по каналу.

        Args:
            channel_id: ID канала в Telegram
            limit: Максимальное количество постов

        Returns:
            Список постов
        """
        result = await self.session.execute(
            select(TelegramPost)
            .where(TelegramPost.channel_id == channel_id)
            .order_by(desc(TelegramPost.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def is_analyzed(self, post_id: int) -> bool:
        """
        Проверить, был ли пост уже обработан Аналитиком.

        Args:
            post_id: ID поста

        Returns:
            True если обработан, False иначе
        """
        post = await self.get(post_id)
        if post:
            return post.checked_at == True
        return False

    async def mark_direct_publish(
        self,
        post_id: int,
        publisher_channel_id: Optional[int] = None
    ) -> bool:
        """
        Отметить пост как опубликованный напрямую (без АРА и generated_news).

        Args:
            post_id: ID поста
            publisher_channel_id: ID канала публикации

        Returns:
            True если обновлён, False если не найден
        """
        post = await self.get(post_id)
        if post:
            post.bypass_ara = True
            post.publisher_channel_id = publisher_channel_id
            await self.session.commit()
            return True
        return False

    async def add_tag(self, post_id: int, tag: str) -> bool:
        """
        Добавить тег посту (case-insensitive).

        Args:
            post_id: ID поста
            tag: Тег для добавления

        Returns:
            True если добавлен, False если не найден
        """
        post = await self.get(post_id)
        if post:
            tag_normalized = tag.lower()
            tags = [t.lower() for t in json.loads(post.tags or '[]')]
            if tag_normalized not in tags:
                tags.append(tag_normalized)
                post.tags = json.dumps(tags, ensure_ascii=False)
                await self.session.commit()
            return True
        return False

    async def update_post_tags(self, post_id: int, tags: list[str]) -> bool:
        """
        Обновить теги поста (case-insensitive).

        Args:
            post_id: ID поста
            tags: Новый список тегов

        Returns:
            True если обновлены, False если не найден
        """
        post = await self.get(post_id)
        if post:
            # Нормализация тэгов к нижнему регистру
            post.tags = json.dumps(
                [tag.lower() for tag in tags], ensure_ascii=False
            )
            await self.session.commit()
            return True
        return False

    async def delete_all(self) -> int:
        """
        Удалить все посты из базы данных.

        Returns:
            Количество удалённых записей
        """
        result = await self.session.execute(
            select(func.count()).select_from(TelegramPost)
        )
        count = result.scalar() or 0

        await self.session.execute(
            delete(TelegramPost)
        )
        await self.session.commit()

        return count
