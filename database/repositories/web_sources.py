"""
Web Sources repository для работы с Web источниками.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import WebSource
from database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class WebSourceRepository(BaseRepository[WebSource]):
    """
    Репозиторий для работы с Web источниками.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, WebSource)

    async def create_source(
        self,
        name: str,
        url: str,
        parser_config: str,
        category: Optional[str] = None,
        description: Optional[str] = None,
        check_interval_minutes: int = 60,
    ) -> WebSource:
        """
        Создать новый Web источник.

        Args:
            name: Название источника
            url: URL сайта
            parser_config: JSON конфигурация парсера
            category: Категория
            description: Описание
            check_interval_minutes: Интервал проверки в минутах

        Returns:
            Созданный источник
        """
        source = WebSource(
            name=name,
            url=url,
            parser_config=parser_config,
            category=category,
            description=description,
            check_interval_minutes=check_interval_minutes,
            is_active=True,
        )
        self.session.add(source)
        await self.session.commit()
        await self.session.refresh(source)

        logger.info(f"✅ Web источник создан: {name}")
        return source

    async def get_active(self, limit: int = 50) -> List[WebSource]:
        """Получить все активные источники."""
        result = await self.session.execute(
            select(WebSource)
            .where(WebSource.is_active == True)
            .order_by(desc(WebSource.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_sources_due_for_check(self, limit: int = 50) -> List[WebSource]:
        """
        Получить источники, которые пора проверить.

        Args:
            limit: Максимальное количество источников

        Returns:
            Список источников для проверки
        """
        now = datetime.now(timezone.utc)

        # Получаем все активные источники
        all_sources = await self.get_active(limit=limit)

        # Фильтруем в Python: проверяем каждый источник
        due = []
        for source in all_sources:
            if source.last_checked is None:
                due.append(source)
            elif source.last_checked < now - timedelta(minutes=source.check_interval_minutes):
                due.append(source)

        return due[:limit]

    async def mark_checked(self, source_id: int) -> bool:
        """Отметить источник как проверенный."""
        source = await self.get(source_id)
        if not source:
            return False

        source.last_checked = datetime.now(timezone.utc)
        await self.session.commit()
        return True

    async def toggle_active(self, source_id: int) -> bool:
        """Переключить активность источника."""
        source = await self.get(source_id)
        if not source:
            return False

        source.is_active = not source.is_active
        await self.session.commit()
        logger.info(f"{'✅' if source.is_active else '⛔'} Источник {source.name} {'активирован' if source.is_active else 'деактивирован'}")
        return True

    async def get_by_url(self, url: str) -> WebSource | None:
        """Получить источник по URL."""
        result = await self.session.execute(
            select(WebSource).where(WebSource.url == url)
        )
        return result.scalar_one_or_none()

    async def delete_source(self, source_id: int) -> bool:
        """Удалить источник."""
        source = await self.get(source_id)
        if not source:
            return False

        await self.session.delete(source)
        await self.session.commit()
        logger.info(f"🗑️ Источник {source.name} удалён")
        return True
