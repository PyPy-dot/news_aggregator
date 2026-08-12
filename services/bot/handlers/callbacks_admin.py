"""
Callback-хендлеры для административных задач.

Модуль содержит обработчики для:
- Очистки базы данных
- Других административных функций
"""

import logging
from aiogram import F
from aiogram.types import CallbackQuery

from services.bot.handlers.router import admin
from database import RepositoryFactory
from services.database import get_database_service
from database.repositories.users import UserRepository

logger = logging.getLogger(__name__)


async def _check_admin_access(callback: CallbackQuery) -> bool:
    """Проверить права администратора. Возвращает True если доступ разрешён."""
    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user or user.role != 'admin':
            await callback.answer('❌ У вас нет прав для этого действия', show_alert=True)
            return False
        return True


@admin.callback_query(F.data == 'cleanup_confirm')
async def cleanup_confirm_callback(callback: CallbackQuery):
    """
    Подтверждение очистки базы данных.

    Удаляет все записи из таблиц: posts, generated_news, events, publishers.
    """
    if not await _check_admin_access(callback):
        return

    await callback.answer('⏳ Очистка базы данных...')

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)

        posts_count = await factory.posts().delete_all()
        news_count = await factory.news().delete_all()
        events_count = await factory.events().delete_all()
        publishers_count = await factory.publishers().delete_all()

    total = posts_count + news_count + events_count + publishers_count

    await callback.message.answer(
        f'✅ **База данных очищена!**\n\n'
        f'Удалено записей: **{total}**\n\n'
        f'📝 Посты: {posts_count}\n'
        f'📰 Сгенерированные новости: {news_count}\n'
        f'📚 События: {events_count}\n'
        f'📢 Каналы публикации: {publishers_count}\n\n'
        f'Таблицы **users** и **channels** сохранены.',
        parse_mode='Markdown'
    )

    logger.info(
        f"🗑️ База данных очищена: {total} записей "
        f"(posts={posts_count}, news={news_count}, events={events_count}, publishers={publishers_count})"
    )


@admin.callback_query(F.data == 'cleanup_cancel')
async def cleanup_cancel_callback(callback: CallbackQuery):
    """Отмена очистки базы данных."""
    if not await _check_admin_access(callback):
        return

    await callback.answer('❌ Очистка отменена')

    await callback.message.answer(
        '❌ **Очистка базы данных отменена**\n\n'
        'Все данные сохранены.'
    )
