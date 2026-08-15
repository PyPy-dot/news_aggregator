"""
RSS News repository для работы с новостями из RSS.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, desc, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import RSSNews
from database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class RSSNewsRepository(BaseRepository[RSSNews]):
    """
    Репозиторий для работы с RSS новостями.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RSSNews)

    async def create_news(
        self,
        source_id: int,
        title: str,
        link: str,
        description: Optional[str] = None,
        content: Optional[str] = None,
        author: Optional[str] = None,
        published_at: Optional[datetime] = None,
        guid: Optional[str] = None,
        image_url: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> RSSNews:
        """
        Создать новую RSS новость.

        Args:
            source_id: ID источника
            title: Заголовок
            link: Ссылка на новость
            description: Описание/анонс
            content: Полный текст
            author: Автор
            published_at: Дата публикации
            guid: Уникальный ID (GUID)
            image_url: URL изображения
            category: Категория
            tags: Теги

        Returns:
            Созданная новость
        """
        news = RSSNews(
            source_id=source_id,
            title=title,
            link=link,
            description=description,
            content=content,
            author=author,
            published_at=published_at,
            guid=guid,
            image_url=image_url,
            category=category,
            tags=json.dumps(tags, ensure_ascii=False) if tags else None,
            processed=False,
        )
        self.session.add(news)
        await self.session.commit()
        await self.session.refresh(news)

        logger.debug(f"📰 RSS новость создана: {title[:50]}...")
        return news

    async def get_unprocessed(self, limit: int = 50) -> List[RSSNews]:
        """
        Получить необработанные новости.

        Args:
            limit: Максимальное количество новостей

        Returns:
            Список необработанных новостей
        """
        result = await self.session.execute(
            select(RSSNews)
            .where(RSSNews.processed == False)
            .order_by(desc(RSSNews.published_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def mark_processed(self, news_id: int, post_id: Optional[int] = None) -> bool:
        """
        Отметить новость как обработанную.

        Args:
            news_id: ID новости
            post_id: ID связанного поста

        Returns:
            True если обновлено, False если не найдено
        """
        news = await self.get(news_id)
        if not news:
            return False

        news.processed = True
        if post_id:
            news.post_id = post_id

        await self.session.commit()
        logger.debug(f"✅ RSS новость отмечена как обработанная: {news.title[:50]}...")
        return True

    async def exists_by_guid(self, source_id: int, guid: str) -> bool:
        """
        Проверить, существует ли новость с таким GUID.

        Args:
            source_id: ID источника
            guid: Уникальный ID новости

        Returns:
            True если существует, False иначе
        """
        result = await self.session.execute(
            select(RSSNews.id)
            .where(RSSNews.source_id == source_id)
            .where(RSSNews.guid == guid)
        )
        return result.scalar_one_or_none() is not None

    async def exists_by_link(self, source_id: int, link: str) -> bool:
        """
        Проверить, существует ли новость с такой ссылкой.

        Args:
            source_id: ID источника
            link: Ссылка на новость

        Returns:
            True если существует, False иначе
        """
        result = await self.session.execute(
            select(RSSNews.id)
            .where(RSSNews.source_id == source_id)
            .where(RSSNews.link == link)
        )
        return result.scalar_one_or_none() is not None

    async def get_by_source(self, source_id: int, limit: int = 50) -> List[RSSNews]:
        """
        Получить новости по источнику.

        Args:
            source_id: ID источника
            limit: Максимальное количество новостей

        Returns:
            Список новостей
        """
        result = await self.session.execute(
            select(RSSNews)
            .where(RSSNews.source_id == source_id)
            .order_by(desc(RSSNews.published_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_recent_news(self, hours: int = 24, limit: int = 100) -> List[RSSNews]:
        """
        Получить недавние новости.

        Args:
            hours: За сколько часов
            limit: Максимальное количество новостей

        Returns:
            Список новостей
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.session.execute(
            select(RSSNews)
            .where(RSSNews.published_at >= cutoff)
            .order_by(desc(RSSNews.published_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def count_unprocessed(self) -> int:
        """
        Подсчитать количество необработанных новостей.

        Returns:
            Количество необработанных новостей
        """
        result = await self.session.execute(
            select(func.count()).select_from(RSSNews).where(RSSNews.processed == False)
        )
        return result.scalar() or 0

    async def delete_old_news(self, days: int = 30) -> int:
        """
        Удалить старые новости.

        Args:
            days: Удалять новости старше N дней

        Returns:
            Количество удалённых новостей
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.session.execute(
            delete(RSSNews)
            .where(RSSNews.published_at < cutoff)
            .where(RSSNews.processed == True)
        )
        await self.session.commit()

        deleted_count = result.rowcount
        if deleted_count > 0:
            logger.info(f"🗑️ Удалено {deleted_count} старых RSS новостей")

        return deleted_count
