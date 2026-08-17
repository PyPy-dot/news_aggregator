"""
Web News repository для работы с новостями из Web источников.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from sqlalchemy import select, desc, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import WebNews
from database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class WebNewsRepository(BaseRepository[WebNews]):
    """
    Репозиторий для работы с Web новостями.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, WebNews)

    async def create_news(
        self,
        source_id: int,
        title: str,
        link: str,
        description: Optional[str] = None,
        content: Optional[str] = None,
        author: Optional[str] = None,
        published_at: Optional[datetime] = None,
        image_url: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> WebNews:
        """
        Создать новую Web новость.

        Args:
            source_id: ID источника
            title: Заголовок
            link: Ссылка на новость
            description: Описание/анонс
            content: Полный текст
            author: Автор
            published_at: Дата публикации
            image_url: URL изображения
            category: Категория источника (предварительная)
            tags: Теги

        Returns:
            Созданная новость
        """
        news = WebNews(
            source_id=source_id,
            title=title,
            link=link,
            description=description,
            content=content,
            author=author,
            published_at=published_at,
            image_url=image_url,
            category=category,
            tags=json.dumps(tags, ensure_ascii=False) if tags else None,
            processed=False,
        )
        self.session.add(news)
        await self.session.commit()
        await self.session.refresh(news)

        logger.debug(f"📰 Web новость создана: {title[:50]}...")
        return news

    async def get_unprocessed(self, limit: int = 50) -> List[WebNews]:
        """
        Получить необработанные новости (ещё не прошли категоризацию).

        Args:
            limit: Максимальное количество новостей

        Returns:
            Список необработанных новостей
        """
        result = await self.session.execute(
            select(WebNews)
            .where(WebNews.processed == False)
            .order_by(desc(WebNews.published_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def mark_processed(self, news_id: int, generated_news_id: Optional[int] = None) -> bool:
        """
        Отметить новость как обработанную.

        Args:
            news_id: ID новости
            generated_news_id: ID сгенерированной сводки

        Returns:
            True если обновлено, False если не найдено
        """
        news = await self.get(news_id)
        if not news:
            return False

        news.processed = True
        if generated_news_id:
            news.generated_news_id = generated_news_id

        await self.session.commit()
        logger.debug(f"✅ Web новость отмечена как обработанная: {news.title[:50]}...")
        return True

    async def update_category(
        self,
        news_id: int,
        category: str,
        urgency: Optional[int] = None,
        confidence: Optional[float] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """
        Обновить поля категоризации после обработки CategorizationProcessor.

        Args:
            news_id: ID новости
            category: Категория от AI
            urgency: Срочность (1-5)
            confidence: Уверенность категории
            tags: Теги от AI

        Returns:
            True если обновлено, False если не найдено
        """
        news = await self.get(news_id)
        if not news:
            return False

        news.category = category
        if urgency is not None:
            news.urgency = urgency
        if confidence is not None:
            news.category_confidence = min(1.0, max(0.0, confidence))
        if tags is not None:
            news.tags = json.dumps([tag.lower() for tag in tags], ensure_ascii=False)

        await self.session.commit()
        logger.debug(f"🏷️ Web новость {news_id} категоризована: {category}, urgency={urgency}")
        return True

    async def get_unprocessed_with_category(self, limit: int = 50) -> List[WebNews]:
        """
        Получить необработанные новости, у которых уже есть категория (прошли категоризацию).

        Args:
            limit: Максимальное количество новостей

        Returns:
            Список новостей с установленной категорией
        """
        result = await self.session.execute(
            select(WebNews)
            .where(WebNews.processed == False)
            .where(WebNews.category.isnot(None))
            .order_by(desc(WebNews.published_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def exists_by_link(self, source_id: int, link: str) -> bool:
        """Проверить, существует ли новость с такой ссылкой."""
        result = await self.session.execute(
            select(WebNews.id)
            .where(WebNews.source_id == source_id)
            .where(WebNews.link == link)
        )
        return result.scalar_one_or_none() is not None

    async def get_by_source(self, source_id: int, limit: int = 50) -> List[WebNews]:
        """Получить новости по источнику."""
        result = await self.session.execute(
            select(WebNews)
            .where(WebNews.source_id == source_id)
            .order_by(desc(WebNews.published_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def count_unprocessed(self) -> int:
        """Подсчитать количество необработанных новостей."""
        result = await self.session.execute(
            select(func.count()).select_from(WebNews).where(WebNews.processed == False)
        )
        return result.scalar() or 0
