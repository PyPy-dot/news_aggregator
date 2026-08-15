"""
Обработчики сообщений Telegram бота.

Все обработчики проверяют права администратора через БД.
"""

import json
import logging

from aiogram import F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from services.database import get_database_service
from database import RepositoryFactory
from services.bot.handlers.keyboards import ikb1
from services.bot.handlers.router import admin
from services.bot.handlers.states import AddChannel, DeleteChannel, TrustedChannel, EditNewsStates
from services.bot.handlers.access import check_admin_access

logger = logging.getLogger(__name__)


@admin.message(F.photo)
async def get_photo_id(message: Message, state: FSMContext):
    """Получение ID фото (не работает во время прямой генерации новостей)."""
    if not await check_admin_access(message):
        await message.answer('❌ У вас нет прав для этой команды')
        return

    # Проверяем, не находится ли пользователь в режиме прямой генерации
    current_state = await state.get_state()
    if current_state == 'DirectNewsStates:waiting_for_description':
        # Пропускаем сообщение — оно будет обработано в direct_news.py
        return

    # Проверяем, не была ли только что вызвана команда /get_photo_id
    if current_state == 'get_photo_id':
        photo_id = message.photo[-1].file_id
        await message.answer(
            f"✅ Фото получено!\n\n"
            f"ID: <code>{photo_id}</code>\n\n"
            f"Для выхода из режима отправьте /cancel",
            parse_mode='HTML'
        )
        return

    # Обычный режим — просто показываем ID
    photo_id = message.photo[-1].file_id
    await message.answer(
        f"✅ Фото получено!\n\n"
        f"ID: {photo_id}"
    )


@admin.message(AddChannel.add_channel, F.chat_shared)
async def fadd_channel(message: Message, state: FSMContext):
    """Добавление канала с описанием."""
    # Проверяем права администратора
    if not await check_admin_access(message):
        await message.answer('❌ У вас нет прав для этой команды')
        return

    data = message.chat_shared
    await message.delete()

    # Извлекаем описание (может быть None)
    description = data.description if hasattr(data, 'description') and data.description else ''

    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        channels_repo = factory.channels()

        is_success = await channels_repo.create_channel(
            channel_id=data.chat_id,
            title=data.title,
            description=description
        )

    if is_success:
        desc_text = f'\n📝 Описание: {description[:100]}{"..." if len(description) > 100 else ""}' if description else ''
        await message.answer(f'Готово! Добавили {data.title} в бд{desc_text}')
        await state.clear()
        # Показываем меню работы с каналами
        from services.bot.handlers.keyboards import ikb1
        await message.answer('📢 **Работа с каналами**\n\nВыберите действие:', reply_markup=ikb1, parse_mode='Markdown')
    else:
        await message.answer(f'{data.title} уже в бд')


@admin.message(DeleteChannel.delete_channel, F.chat_shared)
async def fdelete_channel(message: Message, state: FSMContext):
    """Удаление канала."""
    # Проверяем права администратора
    if not await check_admin_access(message):
        await message.answer('❌ У вас нет прав для этой команды')
        return

    data = message.chat_shared
    await message.delete()

    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        channels_repo = factory.channels()

        is_success = await channels_repo.delete_channel(data.chat_id)

    if is_success:
        await message.answer(f'Готово! Удалили {data.title} из бд')
        await state.clear()
    else:
        await message.answer(f'{data.title} нет в бд')


@admin.message(AddChannel.add_channel, F.text == '🔙 Назад')
@admin.message(DeleteChannel.delete_channel, F.text == '🔙 Назад')
@admin.message(TrustedChannel.select_channel, F.text == '🔙 Назад')
async def back_from_channel_menu(message: Message, state: FSMContext):
    """Вернуться в меню управления каналами."""
    if not await check_admin_access(message):
        return

    await state.clear()
    await message.answer(
        '🔙 Возврат в меню управления каналами.\n\n'
        'Выберите действие:',
        reply_markup=ikb1
    )


@admin.message(TrustedChannel.select_channel, F.chat_shared)
async def set_trusted_channel(message: Message, state: FSMContext):
    """Установка флага доверенного источника."""
    # Проверяем права администратора
    if not await check_admin_access(message):
        await message.answer('❌ У вас нет прав для этой команды')
        return

    data = message.chat_shared
    await message.delete()

    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        channels_repo = factory.channels()

        is_success = await channels_repo.set_trusted(data.chat_id, True)

    if is_success:
        await message.answer(
            f'✅ Канал "{data.title}" теперь доверенный!\n'
            f'Все новости будут иметь рейтинг 100.'
        )
    else:
        await message.answer(f'❌ Канал "{data.title}" не найден в бд')

    await state.clear()


@admin.message(F.text == '📬 Последние посты')
@admin.message(Command('last_posts'))
async def show_last_posts_cmd(message: Message):
    """Показать последние посты."""
    # Сначала проверяем права — ДО любого ответа
    if not await check_admin_access(message):
        return

    from services.bot.utils import show_last_posts
    from config.settings import settings
    await show_last_posts(message, limit=settings.repository_default_limit // 10)  # 10 по умолчанию


@admin.message(F.text == '📝 Сгенерированные новости')
@admin.message(Command('generated_news'))
async def show_generated_news_cmd(message: Message):
    """Показать последние сгенерированные новости."""
    # Сначала проверяем права — ДО любого ответа
    if not await check_admin_access(message):
        return

    from services.bot.utils import show_generated_news
    from config.settings import settings
    await show_generated_news(message, limit=settings.repository_default_limit // 10)  # 10 по умолчанию


@admin.message(EditNewsStates.waiting_for_text)
async def handle_edit_news_text(message: Message, state: FSMContext):
    """
    Обработчик нового текста для редактирования новости.

    Args:
        message: Сообщение с новым текстом
        state: FSM состояние
    """
    # Проверяем права администратора
    if not await check_admin_access(message):
        await message.answer('❌ У вас нет прав для этой команды')
        return

    new_text = message.text

    # Получаем данные из состояния
    data = await state.get_data()
    news_id = data.get('news_id')
    admin_telegram_id = data.get('admin_telegram_id')

    if not news_id:
        await message.answer('❌ Ошибка: ID новости не найден. Начните редактирование заново.')
        await state.clear()
        return

    async with get_database_service().session_context() as session:
        from database.repositories.news import NewsRepository
        from database.repositories.channels import ChannelRepository
        from database.repositories.publishers import PublisherRepository

        news_repo = NewsRepository(session)
        channels_repo = ChannelRepository(session)

        # Получаем новость
        news = await news_repo.get(news_id)
        if not news:
            await message.answer(f'❌ Новость ID={news_id} не найдена')
            await state.clear()
            return

        # Используем метод edit() для обновления новости
        await news_repo.edit(news_id, admin_telegram_id, new_text)

        # Добавляем тэг "редактирован_админом"
        news.tags = json.dumps(['редактирован_админом'], ensure_ascii=False)

        # Снижаем рейтинг канала на 5% (0.05)
        if news.publisher_channel_id:
            publishers_repo = PublisherRepository(session)
            publisher = await publishers_repo.get(news.publisher_channel_id)
            if publisher:
                await channels_repo.decrease_trust_rating(publisher.channel_id, amount=0.05)

        await session.commit()

    await message.answer(
        f'✅ **Новость ID={news_id} отредактирована и опубликована!**\n\n'
        f'Тэг: "редактирован_админом"\n'
        f'Рейтинг канала снижен на 5%'
    )
    await state.clear()

    logger.info(f"✏️ Новость ID={news_id} отредактирована админом ID={admin_telegram_id}")
