"""
Category repository для работы с категориями новостей.
"""

from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import NewsCategory
from database.repositories.base import BaseRepository


class CategoryRepository(BaseRepository[NewsCategory]):
    """
    Репозиторий для работы с категориями новостей.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, NewsCategory)

    async def get_all_categories(self, active_only: bool = True) -> List[NewsCategory]:
        """
        Получить все категории.

        Args:
            active_only: Если True, вернуть только активные категории

        Returns:
            Список категорий
        """
        query = select(NewsCategory).order_by(NewsCategory.name)
        if active_only:
            query = query.where(NewsCategory.is_active == True)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> Optional[NewsCategory]:
        """
        Получить категорию по названию.

        Args:
            name: Название категории

        Returns:
            Категория или None
        """
        result = await self.session.execute(
            select(NewsCategory).where(NewsCategory.name == name)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, category_id: int) -> Optional[NewsCategory]:
        """
        Получить категорию по ID.

        Args:
            category_id: ID категории

        Returns:
            Категория или None
        """
        return await self.get(category_id)

    async def activate(self, category_id: int) -> bool:
        """
        Активировать категорию.

        Args:
            category_id: ID категории

        Returns:
            True если активирована, False если не найдена
        """
        category = await self.get(category_id)
        if category:
            category.is_active = True
            await self.session.commit()
            return True
        return False

    async def deactivate(self, category_id: int) -> bool:
        """
        Деактивировать категорию.

        Args:
            category_id: ID категории

        Returns:
            True если деактивирована, False если не найдена
        """
        category = await self.get(category_id)
        if category:
            category.is_active = False
            await self.session.commit()
            return True
        return False

    async def get_active_categories_names(self) -> List[str]:
        """
        Получить названия активных категорий.

        Returns:
            Список названий категорий
        """
        result = await self.session.execute(
            select(NewsCategory.name)
            .where(NewsCategory.is_active == True)
            .order_by(NewsCategory.name)
        )
        return list(result.scalars().all())
