"""
Хендлеры для управления каналами публикации (Publisher).

Только администраторы могут управлять каналами публикации.
"""

import logging
from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from services.database import get_database_service
from database import RepositoryFactory
from services.bot.handlers.keyboards import (
    publishers_menu_kb,
    publishers_list_view_kb,
    create_publisher_action_kb,
    create_publishers_choice_kb,
    add_publisher_kb,
    kb2,
    create_categories_select_kb,
)
from services.bot.handlers.states import PublisherStates

from services.bot.handlers.access import check_admin_access

logger = logging.getLogger(__name__)

router = Router()


# === Команда /publishers ===
@router.message(F.text == '📢 Каналы публикации')
async def cmd_publishers(message: Message):
    """Показать меню управления каналами публикации."""
    if not await check_admin_access(message):
        return

    await message.answer(
        "📢 **Управление каналами публикации**\n\n"
        "Здесь вы можете добавлять и управлять Telegram-каналами, "
        "в которые будут публиковаться новости.\n\n"
        "Выберите действие:",
        reply_markup=publishers_menu_kb,
    )


# === Список каналов публикации (reply kb кнопка) ===
@router.message(F.text == '📋 Список каналов')
async def list_publishers(message: Message):
    """Показать список всех каналов публикации с кнопками управления."""
    if not await check_admin_access(message):
        return

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        publishers = await factory.publishers().get_all(active_only=False)

    if not publishers:
        await message.answer(
            "📭 Пока нет добавленных каналов публикации.\n\n"
            "Используйте кнопку '➕ Добавить канал', чтобы добавить первый.",
            reply_markup=publishers_menu_kb,
        )
        return

    text = "📢 **Каналы публикации:**\n\n"

    # Создаём inline-клавиатуру с кнопками для каждого канала
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    inline_buttons = []

    for pub in publishers:
        status = "✅ Активен" if pub.is_active else "❌ Отключён"
        category_text = f"Категория: {pub.category}" if pub.category else "Категория: не указана"
        text += (
            f"🔹 **{pub.title}**\n"
            f"   ID: `{pub.channel_id}`\n"
            f"   Статус: {status}\n"
            f"   {category_text}\n"
            f"   Описание: {pub.description[:50] if pub.description else 'Нет'}\n\n"
        )

        # Добавляем кнопку удаления с названием канала
        # Обрезаем название если слишком длинное (max 30 символов для кнопки)
        short_title = pub.title[:28] + '...' if len(pub.title) > 30 else pub.title
        inline_buttons.append([
            InlineKeyboardButton(
                text=f'🗑️ Удалить: {short_title}',
                callback_data=f'delete_publisher_{pub.id}'
            )
        ])

    # Добавляем кнопку "Назад"
    inline_buttons.append([
        InlineKeyboardButton(text='🔙 Назад', callback_data='back_to_publishers_menu')
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons)

    await message.answer(text, reply_markup=keyboard)


# === Добавить канал публикации (через reply KB) ===
@router.message(F.text == '➕ Добавить канал')
async def add_publisher_start(message: Message, state: FSMContext):
    """Начать процесс добавления канала публикации через выбор канала."""
    if not await check_admin_access(message):
        return

    await state.set_state(PublisherStates.waiting_for_channel)
    await message.answer(
        "➕ **Добавление канала публикации**\n\n"
        "Нажмите кнопку ниже и выберите канал, в который хотите публиковать новости.\n"
        "Бот автоматически получит название и описание канала.\n\n"
        "Для отмены нажмите /cancel",
        reply_markup=add_publisher_kb,
    )


@router.message(StateFilter(PublisherStates.waiting_for_channel), F.chat_shared)
async def handle_channel_shared(message: Message, state: FSMContext):
    """Обработка выбранного канала через chat_shared — переход к выбору категории."""
    # Проверка прав не требуется — состояние устанавливается только после проверки

    chat = message.chat_shared

    if not chat or not chat.chat_id:
        await message.answer("❌ Не удалось получить информацию о канале.")
        await state.clear()
        return

    channel_id = chat.chat_id
    title = chat.title or f"Канал {channel_id}"
    # ChatShared не имеет description, используем пустую строку
    description = ""

    # === ПРОВЕРКА НА ДУБЛИКАТ (до выбора категории) ===
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        existing = await factory.publishers().get_by_telegram_id(channel_id)

        if existing:
            logger.warning(f"⚠️ Канал уже существует: {existing.title}")
            await message.answer(
                f"⚠️ **Канал уже существует!**\n\n"
                f"📢 Канал с ID `{channel_id}` уже добавлен:\n"
                f"• Название: {existing.title}\n"
                f"• Категория: {existing.category or 'не указана'}\n\n"
                "Если нужно обновить категорию, сначала удалите старый канал.",
                reply_markup=publishers_menu_kb,
            )
            await state.clear()
            return

    # Сохраняем временные данные в состоянии
    await state.update_data(
        channel_id=channel_id,
        title=title,
        description=description,
    )

    # Получаем категории из БД для выбора
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        categories_repo = factory.categories()
        categories = await categories_repo.get_all_categories(active_only=True)

    if not categories:
        # Если категорий нет, сохраняем канал без категории
        await save_publisher_without_category(
            message=message,
            state=state,
            channel_id=channel_id,
            title=title,
            description=description,
        )
        return

    categories_names = [cat.name for cat in categories]
    keyboard = create_categories_select_kb(categories_names)

    await state.set_state(PublisherStates.waiting_for_category)
    await message.answer(
        "📁 **Выберите категорию канала**\n\n"
        f"Канал: **{title}**\n\n"
        "Нажмите на категорию, чтобы назначить её этому каналу.\n"
        "Это поможет фильтровать новости по категориям.\n\n"
        "Для отмены нажмите '❌ Отмена'",
        reply_markup=keyboard,
    )


async def save_publisher_without_category(
    message: Message,
    state: FSMContext,
    channel_id: int,
    title: str,
    description: str,
):
    """
    Сохранить канал без категории (если категорий нет в БД).

    Примечание: Проверка на дубликат уже выполнена в handle_channel_shared.
    """
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        publisher = await factory.publishers().create(
            channel_id=channel_id,
            title=title,
            description=description,
            category=None,
        )

    await message.answer(
        f"✅ **Канал добавлен!**\n\n"
        f"📢 Название: {title}\n"
        f"🆔 ID: `{channel_id}`\n"
        f"📝 Описание: {description[:100] if description else 'Нет'}\n"
        f"📁 Категория: не указана\n\n"
        "Теперь вы можете выбирать этот канал для публикации новостей.",
        reply_markup=publishers_menu_kb,
    )

    await state.clear()


@router.callback_query(F.data.startswith('publisher_category_'))
async def handle_category_selected(callback: CallbackQuery, state: FSMContext):
    """Обработка выбранной категории — сохранение канала в БД."""
    if not await check_admin_access(callback):
        return

    # Извлекаем название категории
    category_name = callback.data.replace('publisher_category_', '')

    # Получаем сохранённые данные канала
    data = await state.get_data()
    channel_id = data.get('channel_id')
    title = data.get('title')
    description = data.get('description')

    if not channel_id or not title:
        await callback.answer("❌ Ошибка: данные канала не найдены", show_alert=True)
        await state.clear()
        return

    # Проверяем, существует ли уже канал с таким ID
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        existing = await factory.publishers().get_by_telegram_id(channel_id)

        if existing:
            await callback.answer('⚠️ Канал уже существует', show_alert=True)
            await callback.message.answer(
                f"⚠️ **Канал уже существует!**\n\n"
                f"📢 Канал с ID `{channel_id}` уже добавлен:\n"
                f"• Название: {existing.title}\n"
                f"• Категория: {existing.category or 'не указана'}\n\n"
                "Если нужно обновить категорию, сначала удалите старый канал.",
                reply_markup=publishers_menu_kb,
            )
            await state.clear()
            return

        # Сохраняем канал с категорией в БД
        publisher = await factory.publishers().create(
            channel_id=channel_id,
            title=title,
            description=description,
            category=category_name,
        )

    await callback.message.answer(
        f"✅ **Канал добавлен!**\n\n"
        f"📢 Название: {title}\n"
        f"🆔 ID: `{channel_id}`\n"
        f"📁 Категория: **{category_name}**\n"
        f"📝 Описание: {description[:100] if description else 'Нет'}\n\n"
        "Теперь вы можете выбирать этот канал для публикации новостей.",
        reply_markup=publishers_menu_kb,
    )
    logger.info(f"✅ Добавлен канал публикации: {title} (категория: {category_name})")

    await callback.answer()
    await state.clear()


@router.callback_query(F.data == 'cancel_add_publisher')
async def cancel_add_publisher(callback: CallbackQuery, state: FSMContext):
    """Отмена добавления канала."""
    if not await check_admin_access(callback):
        return

    await state.clear()
    await callback.message.answer(
        "❌ Добавление канала отменено.",
        reply_markup=publishers_menu_kb,
    )
    await callback.answer()


@router.message(StateFilter(PublisherStates.waiting_for_channel), ~F.chat_shared)
async def handle_other_input(message: Message, state: FSMContext):
    """Обработка другого ввода (не chat_shared)."""
    if not await check_admin_access(message):
        return

    # Проверяем, не нажата ли кнопка "Назад"
    if message.text in ('🔙 Назад', '🔙 Назад в меню каналов'):
        await state.clear()
        await message.answer(
            "🔙 Возврат в меню управления каналами.",
            reply_markup=publishers_menu_kb,
        )
        return

    await message.answer(
        "⚠️ Пожалуйста, нажмите кнопку '➕ Выбрать канал для публикации' и выберите канал.\n\n"
        "Для отмены нажмите /cancel",
        reply_markup=add_publisher_kb,
    )


# === Выбор канала для действия ===
@router.callback_query(F.data.startswith('publisher_'))
async def cb_publisher_action(callback: CallbackQuery):
    """Показать действия для выбранного publisher."""
    if not await check_admin_access(callback):
        return

    await callback.answer()

    publisher_id = int(callback.data.split('_')[1])

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        publisher = await factory.publishers().get_by_id(publisher_id)

    if not publisher:
        await callback.message.answer("❌ Канал не найден.")
        return

    status = "✅ Активен" if publisher.is_active else "❌ Отключён"
    category_text = f"Категория: {publisher.category}" if publisher.category else "Категория: не указана"

    await callback.message.answer(
        f"📢 **{publisher.title}**\n\n"
        f"ID: `{publisher.channel_id}`\n"
        f"Статус: {status}\n"
        f"{category_text}\n"
        f"Описание: {publisher.description[:100] if publisher.description else 'Нет'}\n\n"
        "Выберите действие:",
        reply_markup=create_publisher_action_kb(publisher_id),
    )


# === Активация/деактивация ===
@router.callback_query(F.data.startswith('activate_publisher_'))
@router.callback_query(F.data.startswith('deactivate_publisher_'))
async def cb_toggle_publisher(callback: CallbackQuery):
    """
    Активировать или деактивировать канал публикации.

    Обработчик для callback вида 'activate_publisher_<id>' или 'deactivate_publisher_<id>'.
    """
    if not await check_admin_access(callback):
        return

    await callback.answer()

    # Извлекаем ID publisher и действие из callback
    try:
        parts = callback.data.split('_')
        action = parts[0]  # 'activate' или 'deactivate'
        publisher_id = int(parts[-1])
    except (ValueError, IndexError):
        await callback.message.answer("❌ Неверный формат команды.", reply_markup=publishers_list_view_kb)
        return

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        publisher = await factory.publishers().get_by_id(publisher_id)

        if not publisher:
            await callback.message.answer("❌ Канал не найден.", reply_markup=publishers_list_view_kb)
            return

        # Устанавливаем новое состояние
        new_status = action == 'activate'
        publisher.is_active = new_status
        await session.commit()

        status_text = "✅ Активирован" if new_status else "❌ Деактивирован"

    await callback.message.answer(
        f"📢 **Канал {status_text}**\n\n"
        f"🔹 {publisher.title}\n"
        f"🆔 ID: `{publisher.channel_id}`\n\n"
        f"Теперь канал {'будет' if new_status else 'не будет'} получать новости для публикации.",
        reply_markup=publishers_list_view_kb,
    )
    logger.info(f"Publisher ID={publisher_id} ({publisher.title}) {'активирован' if new_status else 'деактивирован'}")


# === Удаление канала публикации ===
@router.callback_query(F.data.startswith('delete_publisher_'))
async def cb_delete_publisher(callback: CallbackQuery):
    """
    Удалить канал публикации.

    Обработчик для callback вида 'delete_publisher_<id>'.
    """
    if not await check_admin_access(callback):
        return

    # Извлекаем ID publisher
    try:
        publisher_id = int(callback.data.split('_')[-1])
    except (ValueError, IndexError):
        await callback.answer("❌ Неверный формат ID", show_alert=True)
        return

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        publisher = await factory.publishers().get_by_id(publisher_id)

        if not publisher:
            await callback.answer("❌ Канал не найден", show_alert=True)
            return

        # Получаем название для лога
        publisher_title = publisher.title

        # Удаляем канал
        await factory.publishers().delete(publisher_id)
        await session.commit()

    await callback.answer(f"✅ Канал '{publisher_title}' удалён", show_alert=False)

    # Обновляем сообщение со списком каналов
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        publishers = await factory.publishers().get_all(active_only=False)

    if not publishers:
        await callback.message.edit_text(
            "📢 **Каналы публикации**\n\n"
            "📭 Пока нет добавленных каналов.\n\n"
            "Используйте кнопку '➕ Добавить канал', чтобы добавить первый.",
        )
        return

    text = "📢 **Каналы публикации:**\n\n"
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    inline_buttons = []

    for pub in publishers:
        status = "✅ Активен" if pub.is_active else "❌ Отключён"
        category_text = f"Категория: {pub.category}" if pub.category else "Категория: не указана"
        text += (
            f"🔹 **{pub.title}**\n"
            f"   ID: `{pub.channel_id}`\n"
            f"   Статус: {status}\n"
            f"   {category_text}\n"
            f"   Описание: {pub.description[:50] if pub.description else 'Нет'}\n\n"
        )
        # Добавляем кнопку удаления с названием канала
        short_title = pub.title[:28] + '...' if len(pub.title) > 30 else pub.title
        inline_buttons.append([
            InlineKeyboardButton(
                text=f'🗑️ Удалить: {short_title}',
                callback_data=f'delete_publisher_{pub.id}'
            )
        ])

    inline_buttons.append([
        InlineKeyboardButton(text='🔙 Назад', callback_data='back_to_publishers_menu')
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons)

    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard
        )
    except Exception as e:
        # Если не удалось отредактировать, отправляем новое сообщение
        logger.warning(f"Не удалось обновить сообщение со списком каналов: {e}")
        await callback.message.answer(text, reply_markup=keyboard)

    logger.info(f"🗑️ Удалён канал публикации ID={publisher_id} ({publisher_title})")


# === Назад в меню publisher'ов из списка ===
@router.callback_query(F.data == 'back_to_publishers_menu')
async def cb_back_to_publishers_menu(callback: CallbackQuery):
    """Вернуться в меню publisher'ов из списка каналов."""
    if not await check_admin_access(callback):
        return

    await callback.answer()
    await callback.message.answer(
        "📢 **Управление каналами публикации**\n\n"
        "Выберите действие:",
        reply_markup=publishers_menu_kb,
    )


# === Публикация в выбранный канал ===
@router.callback_query(F.data.startswith('publish_to_'))
async def cb_publish_to_channel(callback: CallbackQuery):
    """
    Опубликовать новость в выбранный канал.

    Обработчик для callback вида 'publish_to_<publisher_id>'.
    """
    if not await check_admin_access(callback):
        return

    await callback.answer()

    # Извлекаем ID publisher из callback
    try:
        publisher_id = int(callback.data.split('_')[-1])
    except (ValueError, IndexError):
        await callback.message.answer("❌ Неверный формат канала.")
        return

    # Получаем контекст из состояния (news_id, который нужно опубликовать)
    # Для этого нужно будет сохранить news_id в state при одобрении
    # Пока заглушка - в реальной реализации нужно брать из state или context

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        publisher = await factory.publishers().get_by_id(publisher_id)

    if not publisher:
        await callback.message.answer("❌ Канал не найден.")
        return

    # Здесь будет логика публикации через Telethon
    # Пока просто показываем подтверждение
    await callback.message.answer(
        f"✅ **Публикация в канал**\n\n"
        f"📢 {publisher.title}\n"
        f"🆔 ID: `{publisher.channel_id}`\n\n"
        f"Новость будет опубликована в ближайшее время."
    )

    # Помечаем новость как опубликованную
    # await news_repo.mark_published(news_id, publisher_id)


@router.callback_query(F.data == 'cancel_publish')
async def cb_cancel_publish(callback: CallbackQuery):
    """Отменить публикацию."""
    if not await check_admin_access(callback):
        return

    await callback.answer()
    await callback.message.answer("❌ Публикация отменена.", reply_markup=publishers_list_view_kb)


# === Назад в главное меню ===
@router.message(F.text == '🔙 Назад в главное меню')
async def back_to_main_menu_from_publishers(message: Message, state: FSMContext):
    """Вернуться в главное меню из меню publisher'ов."""
    from services.bot.handlers.keyboards import kb1

    await state.clear()
    await message.answer(
        "🔙 Возврат в главное меню.",
        reply_markup=kb1,
    )


@router.message(F.text == '🔙 Назад')
async def back_to_previous_from_publishers(message: Message, state: FSMContext):
    """Вернуться назад из текущего состояния publisher'ов."""
    from services.bot.handlers.keyboards import publishers_menu_kb, add_publisher_kb

    current_state = await state.get_state()

    # Если в состоянии добавления канала (waiting_for_channel) — вернуться в главное меню publishers
    if current_state == PublisherStates.waiting_for_channel.state:
        # Очищаем состояние и возвращаемся в меню
        await state.clear()
        await message.answer(
            "🔙 Возврат в меню управления каналами.",
            reply_markup=publishers_menu_kb,
        )
        return

    # Если в состоянии выбора категории — тоже вернуться в меню
    if current_state == PublisherStates.waiting_for_category.state:
        await state.clear()
        await message.answer(
            "🔙 Возврат в меню управления каналами.",
            reply_markup=publishers_menu_kb,
        )
        return

    # Если в других состояниях — вернуться в меню publisher'ов
    await state.clear()
    await message.answer(
        "🔙 Возврат в меню управления каналами.",
        reply_markup=publishers_menu_kb,
    )
