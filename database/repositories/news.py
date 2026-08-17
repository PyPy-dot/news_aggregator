"""
News repository для работы с сгенерированными новостями.
"""

import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, desc, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import GeneratedNews
from database.repositories.base import BaseRepository


class NewsRepository(BaseRepository[GeneratedNews]):
    """
    Репозиторий для работы с сгенерированными новостями.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GeneratedNews)

    async def get_by_id(self, news_id: int) -> GeneratedNews | None:
        """
        Получить новость по ID.

        Args:
            news_id: ID новости

        Returns:
            Новость или None
        """
        return await self.get(news_id)

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

    async def edit(self, news_id: int, admin_id: int, new_text: str) -> bool:
        """
        Отредактировать новость (статус 'edited').

        Args:
            news_id: ID новости
            admin_id: ID админа
            new_text: Новый текст новости

        Returns:
            True если отредактирована, False если не найдена
        """
        news = await self.get(news_id)
        if news:
            news.text = new_text
            news.moderation_status = 'edited'
            news.admin_id = admin_id
            await self.session.commit()
            return True
        return False

    async def get_by_post(self, original_post_id: int) -> Optional[GeneratedNews]:
        """
        Получить сгенерированную новость по ID оригинального поста.
        (Заглушка, т.к. source_post_ids удалён из модели)

        Args:
            original_post_id: ID оригинального поста

        Returns:
            Новость или None
        """
        # Возвращаем None, т.к. связь с постами больше не хранится
        return None

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
        publisher_channel_id: Optional[int] = None,
        published_at: Optional[datetime] = None
    ) -> bool:
        """
        Отметить новость как опубликованную.

        Args:
            news_id: ID новости
            publisher_channel_id: ID канала публикации (опционально)
            published_at: Время публикации (по умолчанию сейчас)

        Returns:
            True если обновлена, False если не найдена
        """
        news = await self.get(news_id)
        if not news:
            return False

        news.bypass_ara = True
        news.publisher_channel_id = publisher_channel_id
        news.published_at = published_at or datetime.now(timezone.utc)

        await self.session.commit()
        return True

    async def create_news(
        self,
        text: str,
        category: str,
        source_ids: Optional[list[str]] = None,
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
            source_ids: ID исходных новостей с префиксом (["tg_5", "rss_13", "web_10"])
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
            source_ids=json.dumps(source_ids or [], ensure_ascii=False),
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

    async def delete_all(self) -> int:
        """
        Удалить все сгенерированные новости из базы данных.

        Returns:
            Количество удалённых записей
        """
        result = await self.session.execute(
            select(func.count()).select_from(GeneratedNews)
        )
        count = result.scalar() or 0

        await self.session.execute(
            delete(GeneratedNews)
        )
        await self.session.commit()

        return count
