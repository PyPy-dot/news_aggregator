"""
Утилиты для Telegram бота.
"""

import logging
import json
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database import RepositoryFactory, async_session

logger = logging.getLogger(__name__)


async def get_repository_factory() -> RepositoryFactory:
    """Получить фабрику репозиториев."""
    return RepositoryFactory(async_session())


async def show_last_posts(message: Message, limit: int = 10) -> None:
    """
    Показать последние посты.

    Args:
        message: Сообщение для ответа
        limit: Максимальное количество постов
    """
    factory = await get_repository_factory()
    posts_repo = factory.posts()
    news_repo = factory.news()

    posts = await posts_repo.get_all(limit=limit)

    if not posts:
        await message.answer('📭 Постов пока нет')
        return

    text = '📰 **Последние посты:**\n\n'
    for post in posts:
        confidence_emoji = (
            '✓' if post.category_confidence > 0.7
            else '⚠️' if post.category_confidence > 0.4
            else '❓'
        )

        # Проверяем, есть ли сгенерированная новость
        generated = await news_repo.get_by_post(post.id)
        generated_mark = '📝' if generated else ''

        text += (
            f'{generated_mark} **ID={post.id}** | {post.category} | '
            f'срочность {post.urgency} | рейтинг {post.rate}\n'
            f'   {confidence_emoji} Уверенность: {post.category_confidence:.2f}\n'
            f'   Текст: {post.text[:100]}...\n\n'
        )

    await message.answer(text)


async def show_generated_news(message: Message, limit: int = 10) -> None:
    """
    Показать последние сгенерированные новости.

    Args:
        message: Сообщение для ответа
        limit: Максимальное количество новостей
    """
    factory = await get_repository_factory()
    news_repo = factory.news()
    events_repo = factory.events()

    news_items = await news_repo.get_recent(limit=limit)

    if not news_items:
        await message.answer('📭 Сгенерированных новостей пока нет')
        return

    text = '📝 **Последние сгенерированные новости:**\n\n'
    for news in news_items:
        # Получаем контекст события
        context = None
        if news.source_event_ids:
            import json
            event_ids = json.loads(news.source_event_ids)
            if event_ids:
                context = await events_repo.get_context(event_ids[0])

        text += f'**ID={news.id}** (оригинальный пост ID={news.source_post_ids})\n'
        if context:
            event_desc = context.get('event_description', 'не указано')
            text += f'   📌 Контекст: {event_desc[:100]}...\n'
        text += f'   Текст: {news.text[:200]}...\n\n'

    await message.answer(text)


async def show_pending_moderation(message: Message, limit: int = 20) -> None:
    """
    Показать новости, ожидающие модерации.

    Args:
        message: Сообщение для ответа
        limit: Максимальное количество новостей
    """
    factory = await get_repository_factory()
    news_repo = factory.news()

    pending = await news_repo.get_pending(limit=limit)

    if not pending:
        await message.answer('✅ Нет новостей, ожидающих модерации')
        return

    text = '⏳ **Новости на модерации:**\n\n'
    for news in pending:
        text += (
            f'**ID={news.id}** | {news.category}\n'
            f'Текст: {news.text[:150]}...\n'
            f'Теги: {news.tags}\n\n'
        )

    await message.answer(text)


async def approve_news_by_id(
    message: Message,
    news_id: int,
    admin_telegram_id: int,
    with_channel_choice: bool = True,
) -> None:
    """
    Одобрить новость по ID.

    Args:
        message: Сообщение для ответа
        news_id: ID новости
        admin_telegram_id: Telegram ID админа
        with_channel_choice: Показать ли выбор канала для публикации
    """
    from database.repositories.users import UserRepository

    factory = await get_repository_factory()
    news_repo = factory.news()
    publishers_repo = factory.publishers()
    user_repo = factory.users()

    # Получаем пользователя из БД
    user = await user_repo.get_by_telegram_id(admin_telegram_id)
    if not user or user.role != 'admin':
        await message.answer('❌ У вас нет прав администратора')
        return

    # Получаем новость
    news = await news_repo.get_by_id(news_id)
    if not news:
        await message.answer(f'❌ Новость ID={news_id} не найдена')
        return

    # Получаем активные каналы публикации
    publishers = await publishers_repo.get_all(active_only=True)

    if with_channel_choice and publishers:
        # Показываем выбор канала
        publishers_data = [
            {'id': p.id, 'title': p.title, 'channel_id': p.channel_id}
            for p in publishers
        ]
        keyboard = create_publishers_choice_kb(publishers_data)

        await message.answer(
            f'✅ **Новость ID={news_id} одобрена!**\n\n'
            f'📝 Текст: {news.text[:200]}...\n\n'
            f'Выберите канал для публикации:',
            reply_markup=keyboard,
        )
    else:
        # Одобрение без выбора канала (старая логика)
        if await news_repo.approve(news_id, admin_telegram_id):
            await message.answer(f'✅ Новость ID={news_id} одобрена')
        else:
            await message.answer(f'❌ Новость ID={news_id} не найдена')


def create_publishers_choice_kb(publishers: list[dict]) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру с выбором канала для публикации.

    Args:
        publishers: Список dict с publisher'ами [{'id': 1, 'title': 'Channel'}, ...]

    Returns:
        InlineKeyboardMarkup с кнопками выбора
    """
    buttons = []
    for pub in publishers:
        buttons.append([
            InlineKeyboardButton(
                text=f"📢 {pub['title']}",
                callback_data=f"publish_to_{pub['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_publish')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def reject_news_by_id(
    message: Message,
    news_id: int,
    admin_telegram_id: int,
) -> None:
    """
    Отклонить новость по ID.

    Args:
        message: Сообщение для ответа
        news_id: ID новости
        admin_telegram_id: Telegram ID админа
    """
    from database.repositories.users import UserRepository

    factory = await get_repository_factory()
    news_repo = factory.news()
    user_repo = factory.users()

    # Проверяем права администратора
    user = await user_repo.get_by_telegram_id(admin_telegram_id)
    if not user or user.role != 'admin':
        await message.answer('❌ У вас нет прав администратора')
        return

    if await news_repo.reject(news_id, admin_telegram_id):
        await message.answer(f'❌ Новость ID={news_id} отклонена')
    else:
        await message.answer(f'❌ Новость ID={news_id} не найдена')
