"""
News repository для работы с сгенерированными новостями.
"""

import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import GeneratedNews
from database.repositories.base import BaseRepository


class NewsRepository(BaseRepository[GeneratedNews]):
    """
    Репозиторий для работы с сгенерированными новостями.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GeneratedNews)

    async def get_pending(self, limit: int = 20) -> list[GeneratedNews]:
        """
        Получить новости, ожидающие модерации.

        Args:
            limit: Максимальное количество новостей

        Returns:
            Список новостей со статусом pending
        """
        result = await self.session.execute(
            select(GeneratedNews)
            .where(GeneratedNews.moderation_status == 'pending')
            .order_by(desc(GeneratedNews.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def approve(self, news_id: int, admin_id: int) -> bool:
        """
        Одобрить новость.

        Args:
            news_id: ID новости
            admin_id: ID админа

        Returns:
            True если одобрена, False если не найдена
        """
        news = await self.get(news_id)
        if news:
            news.moderation_status = 'approved'
            news.admin_id = admin_id
            await self.session.commit()
            return True
        return False

    async def reject(self, news_id: int, admin_id: int) -> bool:
        """
        Отклонить новость.

        Args:
            news_id: ID новости
            admin_id: ID админа

        Returns:
            True если отклонена, False если не найдена
        """
        news = await self.get(news_id)
        if news:
            news.moderation_status = 'rejected'
            news.admin_id = admin_id
            await self.session.commit()
            return True
        return False

    async def get_by_post(self, original_post_id: int) -> Optional[GeneratedNews]:
        """
        Получить сгенерированную новость по ID оригинального поста.

        Args:
            original_post_id: ID оригинального поста

        Returns:
            Новость или None
        """
        # Ищем новость, где source_post_ids содержит original_post_id
        result = await self.session.execute(
            select(GeneratedNews)
            .where(GeneratedNews.source_post_ids.contains(str(original_post_id)))
            .order_by(desc(GeneratedNews.created_at))
        )
        return result.scalars().first()

    async def get_recent(self, limit: int = 10) -> list[GeneratedNews]:
        """
        Получить последние сгенерированные новости.

        Args:
            limit: Максимальное количество новостей

        Returns:
            Список новостей
        """
        result = await self.session.execute(
            select(GeneratedNews)
            .order_by(desc(GeneratedNews.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def mark_published(
        self,
        news_id: int,
        publisher_channel_id: int,
        published_at: datetime
    ) -> bool:
        """
        Отметить новость как опубликованную.

        Args:
            news_id: ID новости
            publisher_channel_id: ID канала публикации
            published_at: Время публикации

        Returns:
            True если обновлена, False если не найдена
        """
        news = await self.get(news_id)
        if not news:
            return False

        news.bypass_ara = True
        news.publisher_channel_id = publisher_channel_id
        news.published_at = published_at

        await self.session.commit()
        return True

    async def create_news(
        self,
        text: str,
        category: str,
        source_post_ids: list[int],
        source_event_ids: Optional[list[int]] = None,
        tags: Optional[list[str]] = None,
        moderation_status: str = 'pending',
        bypass_ara: bool = False,
        publisher_channel_id: Optional[int] = None,
    ) -> GeneratedNews:
        """
        Создать сгенерированную новость.

        Args:
            text: Текст новости
            category: Категория
            source_post_ids: ID исходных постов
            source_event_ids: ID событий
            tags: Теги новости
            moderation_status: Статус модерации
            bypass_ara: Флаг обхода АРА
            publisher_channel_id: ID канала публикации

        Returns:
            Созданная новость
        """
        news = GeneratedNews(
            text=text,
            category=category,
            source_post_ids=json.dumps(source_post_ids, ensure_ascii=False),
            source_event_ids=json.dumps(source_event_ids or [], ensure_ascii=False),
            tags=json.dumps(tags or [], ensure_ascii=False),
            moderation_status=moderation_status,
            bypass_ara=bypass_ara,
            publisher_channel_id=publisher_channel_id,
            created_at=datetime.now(timezone.utc)
        )
        self.session.add(news)
        await self.session.commit()
        await self.session.refresh(news)
        return news
