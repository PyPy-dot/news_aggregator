"""
Publisher Repository — работа с каналами для публикации.
"""

import logging
from typing import Optional

from sqlalchemy import select, update, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.repositories.base import BaseRepository
from database.models import Publisher

logger = logging.getLogger(__name__)


class PublisherRepository(BaseRepository):
    """
    Репозиторий для работы с таблицей Publisher.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Publisher)

    async def get_all(self, active_only: bool = True) -> list[Publisher]:
        """
        Получить все каналы публикации.

        Args:
            active_only: Если True, вернуть только активные

        Returns:
            Список Publisher
        """
        query = select(Publisher)
        if active_only:
            query = query.where(Publisher.is_active == True)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, publisher_id: int) -> Optional[Publisher]:
        """Получить канал по ID."""
        query = select(Publisher).where(Publisher.id == publisher_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[Publisher]:
        """Получить канал по ID в Telegram."""
        query = select(Publisher).where(Publisher.channel_id == telegram_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(
        self,
        channel_id: int,
        title: str,
        description: str = '',
        category: Optional[str] = None,
    ) -> Publisher:
        """
        Создать канал публикации.

        Args:
            channel_id: ID канала в Telegram
            title: Название канала
            description: Описание канала
            category: Категория канала

        Returns:
            Созданный Publisher
        """
        # Проверяем, существует ли уже
        existing = await self.get_by_telegram_id(channel_id)
        if existing:
            logger.warning(f"Publisher с channel_id={channel_id} уже существует")
            return existing

        publisher = Publisher(
            channel_id=channel_id,
            title=title,
            description=description,
            category=category,
            is_active=True,
        )

        self.session.add(publisher)
        await self.session.commit()
        await self.session.refresh(publisher)

        logger.info(f"✅ Создан publisher: {title} (ID={channel_id})")
        return publisher

    async def update(
        self,
        publisher_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        """
        Обновить информацию о канале.

        Returns:
            True если обновлён, False если не найден
        """
        publisher = await self.get_by_id(publisher_id)
        if not publisher:
            return False

        if title is not None:
            publisher.title = title
        if description is not None:
            publisher.description = description
        if category is not None:
            publisher.category = category
        if is_active is not None:
            publisher.is_active = is_active

        await self.session.commit()
        logger.info(f"🔄 Обновлён publisher ID={publisher_id}")
        return True

    async def deactivate(self, publisher_id: int) -> bool:
        """Деактивировать канал публикации."""
        return await self.update(publisher_id, is_active=False)

    async def delete(self, publisher_id: int) -> bool:
        """Удалить канал публикации."""
        publisher = await self.get_by_id(publisher_id)
        if not publisher:
            return False

        await self.session.delete(publisher)
        await self.session.commit()
        logger.info(f"🗑️ Удалён publisher ID={publisher_id}")
        return True

    async def delete_all(self) -> int:
        """
        Удалить все каналы публикации из базы данных.

        Returns:
            Количество удалённых записей
        """
        result = await self.session.execute(
            select(func.count()).select_from(Publisher)
        )
        count = result.scalar() or 0

        await self.session.execute(
            delete(Publisher)
        )
        await self.session.commit()

        return count
