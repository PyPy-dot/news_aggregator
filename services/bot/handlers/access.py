"""
Модуль проверки прав доступа.

Централизованная проверка прав администратора для всех хендлеров.
"""

import logging
from typing import Union

from aiogram.types import Message, CallbackQuery

from database.repositories.users import UserRepository
from services.database import get_database_service

logger = logging.getLogger(__name__)


async def check_admin_access(user: Union[Message, CallbackQuery]) -> bool:
    """
    Проверить права администратора.

    Args:
        user: Message или CallbackQuery для проверки

    Returns:
        True если пользователь администратор, False иначе
    """
    telegram_id = user.from_user.id
    username = user.from_user.username or 'N/A'

    logger.debug(f"🔍 Проверка прав для пользователя: ID={telegram_id}, @{username}")

    db_service = get_database_service()
    async with db_service.session_context() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_telegram_id(telegram_id)

        if not db_user:
            logger.warning(f"⚠️ Пользователь не найден в БД: ID={telegram_id}, @{username}")
            # Отправляем ответ только для Message, не для CallbackQuery
            if isinstance(user, Message):
                await user.answer('❌ У вас нет прав для выполнения этого действия')
            return False

        if db_user.role != 'admin':
            logger.warning(
                f"⚠️ Пользователь не администратор: ID={telegram_id}, @{username}, "
                f"role={db_user.role}"
            )
            if isinstance(user, Message):
                await user.answer('❌ У вас нет прав для выполнения этого действия')
            return False

        logger.debug(f"✅ Пользователь имеет права администратора: ID={telegram_id}, @{username}")
        return True


async def is_admin(telegram_id: int) -> bool:
    """
    Проверить, является ли пользователь администратором.

    Args:
        telegram_id: Telegram ID пользователя

    Returns:
        True если администратор, False иначе
    """
    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_telegram_id(telegram_id)
        return db_user is not None and db_user.role == 'admin'
