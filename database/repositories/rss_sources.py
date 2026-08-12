"""
RSS Source repository для работы с источниками RSS лент.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from sqlalchemy import select, update, desc, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import RSSSource
from database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class RSSSourceRepository(BaseRepository[RSSSource]):
    """
    Репозиторий для работы с RSS источниками.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RSSSource)

    async def create_source(
        self,
        name: str,
        url: str,
        site_url: Optional[str] = None,
        category: Optional[str] = None,
        description: Optional[str] = None,
        check_interval_minutes: int = 5,
    ) -> RSSSource:
        """
        Создать новый RSS источник.

        Args:
            name: Название источника
            url: URL RSS ленты
            site_url: URL сайта
            category: Категория
            description: Описание
            check_interval_minutes: Интервал проверки (минуты)

        Returns:
            Созданный источник
        """
        source = RSSSource(
            name=name,
            url=url,
            site_url=site_url,
            category=category,
            description=description,
            check_interval_minutes=check_interval_minutes,
            is_active=True,
        )
        self.session.add(source)
        await self.session.commit()
        await self.session.refresh(source)

        logger.info(f"✅ RSS источник создан: {name} ({url})")
        return source

    async def get_active_sources(self) -> List[RSSSource]:
        """
        Получить все активные RSS источники.

        Returns:
            Список активных источников
        """
        result = await self.session.execute(
            select(RSSSource)
            .where(RSSSource.is_active == True)
            .order_by(RSSSource.name)
        )
        return result.scalars().all()

    async def get_sources_due_for_check(self, limit: int = 20) -> List[RSSSource]:
        """
        Получить источники, которые пора проверить.

        Args:
            limit: Максимальное количество источников

        Returns:
            Список источников для проверки
        """
        now = datetime.now(timezone.utc)

        # Получаем все активные источники сначала
        all_sources = await self.get_active_sources()

        # Фильтруем в Python: проверяем каждый источник
        due_sources = []
        for source in all_sources:
            # Если никогда не проверялся или прошло больше интервала
            if source.last_checked is None:
                due_sources.append(source)
            else:
                interval = timedelta(minutes=source.check_interval_minutes or 5)
                if source.last_checked <= now - interval:
                    due_sources.append(source)

        # Сортируем и возвращаем limit
        due_sources.sort(key=lambda s: s.last_checked or datetime.min.replace(tzinfo=timezone.utc))
        return due_sources[:limit]

    async def mark_checked(
        self,
        source_id: int,
        last_modified: Optional[str] = None,
        etag: Optional[str] = None,
    ) -> bool:
        """
        Отметить источник как проверенный.

        Args:
            source_id: ID источника
            last_modified: Last-Modified header
            etag: ETag header

        Returns:
            True если обновлено, False если не найден
        """
        source = await self.get(source_id)
        if not source:
            return False

        source.last_checked = datetime.now(timezone.utc)
        if last_modified:
            source.last_modified = last_modified
        if etag:
            source.etag = etag

        await self.session.commit()
        logger.debug(f"📝 Источник {source.name} отмечен как проверенный")
        return True

    async def update_source(
        self,
        source_id: int,
        name: Optional[str] = None,
        url: Optional[str] = None,
        site_url: Optional[str] = None,
        category: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
        check_interval_minutes: Optional[int] = None,
    ) -> bool:
        """
        Обновить RSS источник.

        Args:
            source_id: ID источника
            name: Новое название
            url: Новый URL
            site_url: Новый URL сайта
            category: Новая категория
            description: Новое описание
            is_active: Активен/не активен
            check_interval_minutes: Новый интервал проверки

        Returns:
            True если обновлено, False если не найден
        """
        source = await self.get(source_id)
        if not source:
            return False

        if name is not None:
            source.name = name
        if url is not None:
            source.url = url
        if site_url is not None:
            source.site_url = site_url
        if category is not None:
            source.category = category
        if description is not None:
            source.description = description
        if is_active is not None:
            source.is_active = is_active
        if check_interval_minutes is not None:
            source.check_interval_minutes = check_interval_minutes

        await self.session.commit()
        logger.info(f"🔄 RSS источник обновлён: {source.name}")
        return True

    async def delete_source(self, source_id: int) -> bool:
        """
        Удалить RSS источник.

        Args:
            source_id: ID источника

        Returns:
            True если удалено, False если не найден
        """
        source = await self.get(source_id)
        if not source:
            return False

        await self.session.delete(source)
        await self.session.commit()

        logger.info(f"🗑️ RSS источник удалён: {source.name}")
        return True

    async def get_by_category(self, category: str) -> List[RSSSource]:
        """
        Получить источники по категории.

        Args:
            category: Категория

        Returns:
            Список источников
        """
        result = await self.session.execute(
            select(RSSSource)
            .where(RSSSource.is_active == True)
            .where(RSSSource.category == category)
            .order_by(RSSSource.name)
        )
        return result.scalars().all()

    async def get_all_categories(self) -> List[str]:
        """
        Получить все категории источников.

        Returns:
            Список категорий
        """
        result = await self.session.execute(
            select(RSSSource.category)
            .where(RSSSource.is_active == True)
            .where(RSSSource.category.isnot(None))
            .distinct()
        )
        return [row[0] for row in result.all()]

    async def count_sources(self) -> int:
        """
        Подсчитать общее количество источников.

        Returns:
            Количество источников
        """
        result = await self.session.execute(
            select(func.count()).select_from(RSSSource)
        )
        return result.scalar() or 0

    async def count_active_sources(self) -> int:
        """
        Подсчитать количество активных источников.

        Returns:
            Количество активных источников
        """
        result = await self.session.execute(
            select(func.count()).select_from(RSSSource).where(RSSSource.is_active == True)
        )
        return result.scalar() or 0
