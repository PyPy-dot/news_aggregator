"""
Хендлеры для управления каналами публикации (Publisher).

Только администраторы могут управлять каналами публикации.
"""

import logging
from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from database import async_session, RepositoryFactory
from services.bot.handlers.keyboards import (
    publishers_menu_kb,
    publishers_list_view_kb,
    create_publisher_action_kb,
    create_publishers_choice_kb,
    add_publisher_kb,
    kb2,
)
from services.bot.handlers.states import PublisherStates

from database.repositories.users import UserRepository

logger = logging.getLogger(__name__)

router = Router()


async def check_admin_access(message: Message | CallbackQuery) -> bool:
    """Проверить права администратора. Возвращает True если доступ разрешён."""
    user_id = message.from_user.id if hasattr(message, 'from_user') else message.from_user.id

    async with async_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(user_id)
        if not user or user.role != 'admin':
            await (
                message.answer('❌ У вас нет прав для управления каналами публикации')
                if isinstance(message, Message)
                else message.answer('❌ У вас нет прав для этого действия', show_alert=True)
            )
            return False
        return True


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
    """Показать список всех каналов публикации."""
    if not await check_admin_access(message):
        return

    async with async_session() as session:
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
    for pub in publishers:
        status = "✅ Активен" if pub.is_active else "❌ Отключён"
        text += (
            f"🔹 **{pub.title}**\n"
            f"   ID: `{pub.channel_id}`\n"
            f"   Статус: {status}\n"
            f"   Описание: {pub.description[:50] if pub.description else 'Нет'}\n\n"
        )

    await message.answer(text, reply_markup=publishers_list_view_kb)


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
    """Обработка выбранного канала через chat_shared."""
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

    # Сохраняем в БД
    async with async_session() as session:
        factory = RepositoryFactory(session)
        publisher = await factory.publishers().create(
            channel_id=channel_id,
            title=title,
            description=description,
        )

    if publisher:
        await message.answer(
            f"✅ **Канал добавлен!**\n\n"
            f"📢 Название: {title}\n"
            f"🆔 ID: `{channel_id}`\n"
            f"📝 Описание: {description[:100] if description else 'Нет'}\n\n"
            "Теперь вы можете выбирать этот канал для публикации новостей.",
            reply_markup=publishers_menu_kb,
        )
    else:
        await message.answer(
            f"⚠️ Канал с ID `{channel_id}` уже был добавлен ранее.",
            reply_markup=publishers_menu_kb,
        )

    await state.clear()


@router.message(StateFilter(PublisherStates.waiting_for_channel))
async def handle_other_input(message: Message, state: FSMContext):
    """Обработка другого ввода (не chat_shared)."""
    if not await check_admin_access(message):
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

    async with async_session() as session:
        factory = RepositoryFactory(session)
        publisher = await factory.publishers().get_by_id(publisher_id)

    if not publisher:
        await callback.message.answer("❌ Канал не найден.")
        return

    status = "✅ Активен" if publisher.is_active else "❌ Отключён"
    await callback.message.answer(
        f"📢 **{publisher.title}**\n\n"
        f"ID: `{publisher.channel_id}`\n"
        f"Статус: {status}\n"
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

    async with async_session() as session:
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


# === Удаление ===
@router.callback_query(F.data == 'delete_publisher')
async def cb_delete_publisher(callback: CallbackQuery):
    """Удалить канал публикации."""
    if not await check_admin_access(callback):
        return

    await callback.answer()
    await callback.message.answer("⚠️ Функция в разработке.")


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

    async with async_session() as session:
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
    await callback.message.answer("❌ Публикация отменена.", reply_markup=publishers_list_kb)


# === Назад в главное меню ===
@router.message(F.text == '🔙 Назад в главное меню')
@router.message(F.text == '🔙 Назад')
async def back_to_menu_from_publishers(message: Message):
    """Вернуться в главное меню из меню publisher'ов."""
    from services.bot.handlers.keyboards import kb1

    await message.answer(
        "🔙 Возврат в главное меню.",
        reply_markup=kb1,
    )
