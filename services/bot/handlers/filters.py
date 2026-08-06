"""
Фильтры для проверки прав администратора.

Используют проверку роли пользователя в базе данных.
"""

from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery

from database.models import async_session
from database.repositories.users import UserRepository


class AdminM(Filter):
    """
    Фильтр для сообщений — проверяет, является ли пользователь администратором.
    """

    async def __call__(self, message: Message) -> bool:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(message.from_user.id)
            return user is not None and user.role == 'admin'


class AdminQ(Filter):
    """
    Фильтр для callback-запросов — проверяет, является ли пользователь администратором.
    """

    async def __call__(self, callback: CallbackQuery) -> bool:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(callback.from_user.id)
            return user is not None and user.role == 'admin'
