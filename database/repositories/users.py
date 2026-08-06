"""
User repository для работы с пользователями.
"""

import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User
from database.repositories.base import BaseRepository
from services.util import encrypt_user_id, decrypt_user_id, hash_user_id_for_lookup, get_encryption_key


class UserRepository(BaseRepository[User]):
    """
    Репозиторий для работы с пользователями.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """
        Найти пользователя по Telegram ID.

        Args:
            telegram_id: ID пользователя в Telegram

        Returns:
            Пользователь или None
        """
        user_hash = hash_user_id_for_lookup(telegram_id)
        result = await self.session.execute(
            select(User).where(User.user_id_hash == user_hash)
        )
        return result.scalar_one_or_none()

    async def create_user(
        self,
        telegram_id: int,
        role: str = 'user',
        preferred_tags: list[str] | None = None,
        preferred_categories: list[str] | None = None,
    ) -> User:
        """
        Создать нового пользователя.

        Args:
            telegram_id: ID пользователя в Telegram
            role: Роль пользователя ('user' или 'admin')
            preferred_tags: Предпочтительные теги
            preferred_categories: Предпочтительные категории

        Returns:
            Созданный пользователь
        """
        encrypted_id = encrypt_user_id(telegram_id)
        user_hash = hash_user_id_for_lookup(telegram_id)

        # Проверяем, существует ли уже пользователь
        existing = await self.get_by_telegram_id(telegram_id)
        if existing:
            return existing

        now = datetime.now(timezone.utc)

        user = User(
            user_id_encrypted=encrypted_id,
            user_id_hash=user_hash,
            role=role,
            created_at=now,
            has_subscription=(role == 'admin'),  # Admin получает подписку
            subscription_started_at=now if role == 'admin' else None,
            subscription_ends_at=None if role == 'admin' else None,  # NULL = бессрочно для admin
            preferred_tags=json.dumps(preferred_tags or []),
            preferred_categories=json.dumps(preferred_categories or []),
        )

        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_or_create_user(
        self,
        telegram_id: int,
        preferred_tags: list[str] | None = None,
        preferred_categories: list[str] | None = None,
    ) -> User:
        """
        Получить пользователя или создать нового.

        Args:
            telegram_id: ID пользователя в Telegram
            preferred_tags: Предпочтительные теги (для нового пользователя)
            preferred_categories: Предпочтительные категории (для нового пользователя)

        Returns:
            Существующий или newly созданный пользователь
        """
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            return user

        return await self.create_user(
            telegram_id,
            preferred_tags=preferred_tags,
            preferred_categories=preferred_categories,
        )

    async def update_subscription(
        self,
        telegram_id: int,
        has_subscription: bool,
        started_at: datetime | None = None,
        ends_at: datetime | None = None,
    ) -> bool:
        """
        Обновить подписку пользователя.

        Args:
            telegram_id: ID пользователя в Telegram
            has_subscription: Флаг наличия подписки
            started_at: Дата начала подписки
            ends_at: Дата окончания подписки (None = бессрочно)

        Returns:
            True если обновлено, False если пользователь не найден
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False

        user.has_subscription = has_subscription
        user.subscription_started_at = started_at
        user.subscription_ends_at = ends_at

        await self.session.commit()
        await self.session.refresh(user)
        return True

    async def update_preferences(
        self,
        telegram_id: int,
        preferred_tags: list[str] | None = None,
        preferred_categories: list[str] | None = None,
    ) -> bool:
        """
        Обновить предпочтения пользователя.

        Args:
            telegram_id: ID пользователя в Telegram
            preferred_tags: Предпочтительные теги
            preferred_categories: Предпочтительные категории

        Returns:
            True если обновлено, False если пользователь не найден
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False

        if preferred_tags is not None:
            user.preferred_tags = json.dumps(preferred_tags)

        if preferred_categories is not None:
            user.preferred_categories = json.dumps(preferred_categories)

        await self.session.commit()
        await self.session.refresh(user)
        return True

    async def get_admins(self) -> list[User]:
        """
        Получить всех администраторов.

        Returns:
            Список пользователей с ролью admin
        """
        result = await self.session.execute(
            select(User).where(User.role == 'admin')
        )
        return result.scalars().all()

    async def is_admin(self, telegram_id: int) -> bool:
        """
        Проверить, является ли пользователь администратором.

        Args:
            telegram_id: ID пользователя в Telegram

        Returns:
            True если администратор, False иначе
        """
        user = await self.get_by_telegram_id(telegram_id)
        return user is not None and user.role == 'admin'

    async def has_active_subscription(self, telegram_id: int) -> bool:
        """
        Проверить, есть ли у пользователя активная подписка.

        Args:
            telegram_id: ID пользователя в Telegram

        Returns:
            True если подписка активна, False иначе
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False
        return user.has_active_subscription

    def get_user_telegram_id(self, user: User) -> int:
        """
        Расшифровать Telegram ID пользователя.

        Args:
            user: Пользователь

        Returns:
            Telegram ID
        """
        return decrypt_user_id(user.user_id_encrypted)
