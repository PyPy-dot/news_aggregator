"""
Base repository для работы с базой данных.
"""

from typing import Generic, TypeVar
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.models import Base

ModelType = TypeVar('ModelType', bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Базовый класс для всех репозиториев.

    Args:
        session: SQLAlchemy async session
        model: Модель SQLAlchemy для работы
    """

    def __init__(self, session: AsyncSession, model: type[ModelType]) -> None:
        self.session = session
        self.model = model

    async def get(self, id: int) -> ModelType | None:
        """
        Получить запись по ID.

        Args:
            id: ID записи

        Returns:
            Модель или None
        """
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[ModelType]:
        """
        Получить все записи с пагинацией.

        Args:
            limit: Максимальное количество записей
            offset: Смещение

        Returns:
            Список моделей
        """
        result = await self.session.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return result.scalars().all()

    async def create(self, data: dict) -> ModelType:
        """
        Создать новую запись.

        Args:
            data: Данные для создания

        Returns:
            Созданная модель
        """
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: int, data: dict) -> ModelType | None:
        """
        Обновить запись по ID.

        Args:
            id: ID записи
            data: Данные для обновления

        Returns:
            Обновлённая модель или None
        """
        instance = await self.get(id)
        if instance:
            for key, value in data.items():
                setattr(instance, key, value)
            await self.session.commit()
            await self.session.refresh(instance)
        return instance

    async def delete(self, id: int) -> bool:
        """
        Удалить запись по ID.

        Args:
            id: ID записи

        Returns:
            True если удалено, False если не найдено
        """
        instance = await self.get(id)
        if instance:
            await self.session.delete(instance)
            await self.session.commit()
            return True
        return False
