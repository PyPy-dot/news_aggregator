"""
Event repository для работы с событиями.
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import select, update, desc, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import EventContext
from database.repositories.base import BaseRepository


class EventRepository(BaseRepository[EventContext]):
    """
    Репозиторий для работы с событиями.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, EventContext)

    async def get_for_scheduler(self, hours: int = 48) -> list[EventContext]:
        """
        Получить события для обработки планировщиком.

        Args:
            hours: За сколько часов искать события

        Returns:
            Список событий
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.session.execute(
            select(EventContext)
            .where(
                (EventContext.last_processed_at.is_(None)) |
                (EventContext.last_processed_at < cutoff_time)
            )
            .order_by(desc(EventContext.created_at))
        )
        return result.scalars().all()

    async def mark_processed(self, event_id: int) -> bool:
        """
        Отметить событие как обработанное планировщиком.

        Args:
            event_id: ID события

        Returns:
            True если обновлено, False если не найдено
        """
        event = await self.get(event_id)
        if event:
            event.last_processed_at = datetime.now(timezone.utc)
            await self.session.commit()
            return True
        return False

    async def create_event(
        self,
        post_id: int,
        context_data: dict,
        event_category: str,
        tags: Optional[list[str]] = None,
    ) -> EventContext:
        """
        Создать новое событие (case-insensitive tags).

        Args:
            post_id: ID оригинального поста
            context_data: Данные контекста
            event_category: Категория события
            tags: Список тегов

        Returns:
            Созданное событие
        """
        event = EventContext(
            post_id=post_id,
            context_data=json.dumps(context_data, ensure_ascii=False),
            event_category=event_category,
            # Нормализация тэгов к нижнему регистру
            tags=json.dumps(
                [tag.lower() for tag in tags] if tags else [],
                ensure_ascii=False
            ),
            created_at=datetime.now(timezone.utc)
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def update_event(
        self,
        event_id: int,
        context_data: Optional[dict] = None,
        tags: Optional[list[str]] = None,
    ) -> bool:
        """
        Обновить событие (case-insensitive tags).

        Args:
            event_id: ID события
            context_data: Новые данные контекста
            tags: Новые теги

        Returns:
            True если обновлено, False если не найдено
        """
        event = await self.get(event_id)
        if event:
            if context_data is not None:
                event.context_data = json.dumps(context_data, ensure_ascii=False)
            if tags is not None:
                # Нормализация тэгов к нижнему регистру
                event.tags = json.dumps(
                    [tag.lower() for tag in tags], ensure_ascii=False
                )
            await self.session.commit()
            return True
        return False

    async def get_by_post(self, post_id: int) -> list[EventContext]:
        """
        Получить события по ID поста.

        Args:
            post_id: ID поста

        Returns:
            Список событий
        """
        result = await self.session.execute(
            select(EventContext)
            .where(EventContext.post_id == post_id)
            .order_by(desc(EventContext.created_at))
        )
        return result.scalars().all()

    async def get_context(self, event_id: int) -> Optional[dict]:
        """
        Получить контекст события по ID.

        Args:
            event_id: ID события

        Returns:
            Словарь с контекстом или None
        """
        event = await self.get(event_id)
        if event:
            return json.loads(event.context_data)
        return None

    async def delete_all(self) -> int:
        """
        Удалить все события из базы данных.

        Returns:
            Количество удалённых записей
        """
        result = await self.session.execute(
            select(func.count()).select_from(EventContext)
        )
        count = result.scalar() or 0

        await self.session.execute(
            delete(EventContext)
        )
        await self.session.commit()

        return count
