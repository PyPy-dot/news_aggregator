"""
Модуль проверки прав доступа.

Централизованная проверка прав администратора для всех хендлеров.
"""

import logging
from typing import Union

from aiogram.types import Message, CallbackQuery

from database import async_session
from database.repositories.users import UserRepository

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

    async with async_session() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_telegram_id(telegram_id)

        if not db_user or db_user.role != 'admin':
            await _send_no_access_response(user)
            return False

        return True


async def _send_no_access_response(user: Union[Message, CallbackQuery]) -> None:
    """
    Отправить ответ об отсутствии прав.

    Args:
        user: Message или CallbackQuery для ответа
    """
    if isinstance(user, Message):
        await user.answer('❌ У вас нет прав для выполнения этого действия')
    elif isinstance(user, CallbackQuery):
        await user.answer('❌ У вас нет прав для этого действия', show_alert=True)


async def is_admin(telegram_id: int) -> bool:
    """
    Проверить, является ли пользователь администратором.

    Args:
        telegram_id: Telegram ID пользователя

    Returns:
        True если администратор, False иначе
    """
    async with async_session() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_telegram_id(telegram_id)
        return db_user is not None and db_user.role == 'admin'
