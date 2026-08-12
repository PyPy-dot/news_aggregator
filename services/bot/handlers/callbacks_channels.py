"""
Callback-хендлеры для управления каналами.

Модуль содержит обработчики для:
- Добавления каналов
- Удаления каналов
- Управления доверенными источниками
"""

import logging
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from services.bot.handlers.keyboards import ikb1
from services.bot.handlers.router import admin
from services.bot.handlers.states import AddChannel, DeleteChannel, TrustedChannel
from database import RepositoryFactory
from services.database import get_database_service
from database.repositories.users import UserRepository

logger = logging.getLogger(__name__)


async def check_admin_access(callback: CallbackQuery) -> bool:
    """Проверить права администратора. Возвращает True если доступ разрешён."""
    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user or user.role != 'admin':
            await callback.answer('❌ У вас нет прав для этого действия', show_alert=True)
            return False
        return True


@admin.callback_query(F.data == 'add_channel')
async def add_channel(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки добавления канала."""
    if not await check_admin_access(callback):
        return

    await callback.answer('')
    await callback.message.delete()
    await state.set_state(AddChannel.add_channel)

    from services.bot.handlers.keyboards import choose_chat_kb
    await callback.message.answer('Нажми кнопку и выбери чат:', reply_markup=choose_chat_kb)


@admin.callback_query(F.data == 'delete_channel')
async def delete_channel(callback: CallbackQuery, state: FSMContext):
    """Показать список каналов из БД для удаления."""
    if not await check_admin_access(callback):
        return

    await callback.answer('')
    await callback.message.delete()

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        channels = await factory.channels().get_all_channels()

    if not channels:
        await callback.message.answer(
            '📭 В базе данных нет каналов для удаления.\n\n'
            'Сначала добавьте каналы через "Работа с каналами" → "Добавить".',
            reply_markup=ikb1
        )
        await state.clear()
        return

    buttons = _build_channels_keyboard(channels, prefix='delete_channel_')
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await state.set_state(DeleteChannel.delete_channel)
    await callback.message.answer(
        '🗑️ **Удаление канала**\n\n'
        'Выберите канал из списка, чтобы удалить его из базы данных:\n\n'
        f'Всего каналов в БД: **{len(channels)}**',
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


@admin.callback_query(F.data.startswith('delete_channel_'))
async def confirm_delete_channel(callback: CallbackQuery, state: FSMContext):
    """Подтверждение удаления канала."""
    if not await check_admin_access(callback):
        return

    channel_id = _extract_channel_id(callback.data, 'delete_channel_')
    if channel_id is None:
        await callback.answer('❌ Неверный формат ID канала', show_alert=True)
        return

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        channels_repo = factory.channels()
        channel = await channels_repo.get_by_telegram_id(channel_id)

        if not channel:
            await callback.answer('❌ Канал не найден в БД', show_alert=True)
            return

        is_success = await channels_repo.delete_channel(channel_id)

        if is_success:
            await callback.answer(f'✅ Канал "{channel.title}" удалён', show_alert=False)
            await callback.message.edit_text(
                f'✅ **Канал удалён**\n\n'
                f'📢 {channel.title}\n'
                f'ID: `{channel_id}`\n\n'
                'Выберите действие:',
                reply_markup=ikb1,
                parse_mode='Markdown'
            )
            logger.info(f'🗑️ Удалён канал ID={channel_id} ({channel.title})')
        else:
            await callback.answer('❌ Ошибка при удалении канала', show_alert=True)


@admin.callback_query(F.data == 'trusted_channels_menu')
async def trusted_channels_menu(callback: CallbackQuery, state: FSMContext):
    """Показать меню управления доверенными источниками."""
    if not await check_admin_access(callback):
        return

    await callback.answer('')
    await callback.message.delete()

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        channels = await factory.channels().get_all_channels()

    if not channels:
        await callback.message.answer(
            '📭 В базе данных нет каналов.\n\n'
            'Сначала добавьте каналы через "Работа с каналами" → "Добавить".',
            reply_markup=ikb1
        )
        await state.clear()
        return

    buttons = _build_trusted_keyboard(channels)
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await state.set_state(TrustedChannel.select_channel)
    await callback.message.answer(
        '✅ **Доверенные источники**\n\n'
        'Нажмите на канал, чтобы сделать его доверенным или снять доверие.\n\n'
        '✅ — доверенный источник (новости имеют рейтинг 100)\n'
        '⬜ — обычный источник\n\n'
        f'Всего каналов в БД: **{len(channels)}**',
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


@admin.callback_query(F.data.startswith('toggle_trusted_'))
async def toggle_trusted_channel(callback: CallbackQuery, state: FSMContext):
    """Переключить статус доверенного источника (быстрый способ)."""
    if not await check_admin_access(callback):
        return

    channel_id = _extract_channel_id(callback.data, 'toggle_trusted_')
    if channel_id is None:
        await callback.answer('❌ Неверный формат ID канала', show_alert=True)
        return

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        channels_repo = factory.channels()
        channel = await channels_repo.get_by_telegram_id(channel_id)

        if not channel:
            await callback.answer('❌ Канал не найден в БД', show_alert=True)
            return

        new_status = not channel.is_trusted
        await channels_repo.set_trusted(channel_id, new_status)

        status_text = '✅ доверенным' if new_status else '❌ обычным'
        action = 'назначен доверенным источником' if new_status else 'снят статус доверенного'
        logger.info(f"✅ Канал '{channel.title}' (ID={channel_id}) {action} админом ID={callback.from_user.id}")
        await callback.answer(f'Канал "{channel.title}" назначен {status_text}', show_alert=False)

        channels = await channels_repo.get_all_channels()
        buttons = _build_trusted_keyboard(channels)
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        try:
            await callback.message.edit_text(
                '✅ **Доверенные источники**\n\n'
                'Нажмите на канал, чтобы переключить статус.\n\n'
                '✅ — доверенный источник\n'
                '⬜ — обычный источник',
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Не удалось обновить сообщение: {e}")


@admin.callback_query(F.data == 'make_trusted')
async def make_trusted(callback: CallbackQuery, state: FSMContext):
    """Показать каналы из БД для назначения доверенными."""
    if not await check_admin_access(callback):
        return

    await callback.answer('')
    await callback.message.delete()

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        channels = await factory.channels().get_all_channels()

    if not channels:
        await callback.message.answer(
            '📭 В базе данных нет каналов.',
            reply_markup=ikb1
        )
        await state.clear()
        return

    buttons = _build_make_trusted_keyboard(channels)
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await state.set_state(TrustedChannel.select_channel)
    await callback.message.answer(
        'Выберите канал, чтобы сделать его доверенным (новости будут иметь рейтинг 100):',
        reply_markup=keyboard
    )


@admin.callback_query(F.data == 'remove_trusted')
async def remove_trusted(callback: CallbackQuery, state: FSMContext):
    """Показать каналы из БД для снятия доверия."""
    if not await check_admin_access(callback):
        return

    await callback.answer('')
    await callback.message.delete()

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        channels = await factory.channels().get_all_channels()

    if not channels:
        await callback.message.answer(
            '📭 В базе данных нет каналов.',
            reply_markup=ikb1
        )
        await state.clear()
        return

    buttons = _build_remove_trusted_keyboard(channels)
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await state.set_state(TrustedChannel.select_channel)
    await callback.message.answer(
        'Выберите канал, чтобы снять с него доверие:',
        reply_markup=keyboard
    )


@admin.callback_query(F.data.startswith('make_trusted_'))
async def confirm_make_trusted(callback: CallbackQuery, state: FSMContext):
    """Назначить канал доверенным источником."""
    if not await check_admin_access(callback):
        return

    channel_id = _extract_channel_id(callback.data, 'make_trusted_')
    if channel_id is None:
        await callback.answer('❌ Неверный формат ID канала', show_alert=True)
        return

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        channels_repo = factory.channels()
        channel = await channels_repo.get_by_telegram_id(channel_id)

        if not channel:
            await callback.answer('❌ Канал не найден в БД', show_alert=True)
            return

        await channels_repo.set_trusted(channel_id, True)
        await callback.answer(f'✅ Канал "{channel.title}" назначен доверенным источником', show_alert=False)

        channels = await channels_repo.get_all_channels()
        buttons = _build_trusted_keyboard(channels)
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        try:
            await callback.message.edit_text(
                '✅ **Доверенные источники**\n\n'
                f'Канал "{channel.title}" назначен доверенным.\n\n'
                'Нажмите на канал, чтобы переключить статус.\n\n'
                '✅ — доверенный источник\n'
                '⬜ — обычный источник',
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Не удалось обновить сообщение: {e}")


@admin.callback_query(F.data.startswith('remove_trusted_'))
async def confirm_remove_trusted(callback: CallbackQuery, state: FSMContext):
    """Снять доверие с канала."""
    if not await check_admin_access(callback):
        return

    channel_id = _extract_channel_id(callback.data, 'remove_trusted_')
    if channel_id is None:
        await callback.answer('❌ Неверный формат ID канала', show_alert=True)
        return

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        channels_repo = factory.channels()
        channel = await channels_repo.get_by_telegram_id(channel_id)

        if not channel:
            await callback.answer('❌ Канал не найден в БД', show_alert=True)
            return

        await channels_repo.set_trusted(channel_id, False)
        await callback.answer(f'❌ Канал "{channel.title}" больше не доверенный источник', show_alert=False)

        channels = await channels_repo.get_all_channels()
        buttons = _build_trusted_keyboard(channels)
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        try:
            await callback.message.edit_text(
                '✅ **Доверенные источники**\n\n'
                f'Канал "{channel.title}" больше не доверенный.\n\n'
                'Нажмите на канал, чтобы переключить статус.\n\n'
                '✅ — доверенный источник\n'
                '⬜ — обычный источник',
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Не удалось обновить сообщение: {e}")


# =============================================================================
# Вспомогательные функции
# =============================================================================

def _extract_channel_id(callback_data: str, prefix: str) -> int | None:
    """Извлечь ID канала из callback_data."""
    try:
        return int(callback_data.replace(prefix, ''))
    except ValueError:
        return None


def _build_channels_keyboard(channels: list, prefix: str = '') -> list:
    """Построить клавиатуру с каналами."""
    buttons = []
    row = []

    for channel in channels:
        if prefix == 'delete_channel_':
            text = f'🗑️ {channel.title}'
        else:
            text = channel.title

        row.append(
            InlineKeyboardButton(
                text=text,
                callback_data=f'{prefix}{channel.channel_id}'
            )
        )

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text='🔙 Назад к каналам', callback_data='back_to_channels_menu')])
    return buttons


def _build_trusted_keyboard(channels: list) -> list:
    """Построить клавиатуру доверенных источников."""
    buttons = []
    row = []

    for channel in channels:
        trusted_mark = '✅' if channel.is_trusted else '⬜'
        row.append(
            InlineKeyboardButton(
                text=f'{trusted_mark} {channel.title}',
                callback_data=f'toggle_trusted_{channel.channel_id}'
            )
        )

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text='🔙 Назад к каналам', callback_data='back_to_channels_menu')])
    return buttons


def _build_make_trusted_keyboard(channels: list) -> list:
    """Построить клавиатуру для назначения доверенными."""
    buttons = []
    row = []

    for channel in channels:
        row.append(
            InlineKeyboardButton(
                text=f'✅ {channel.title}',
                callback_data=f'make_trusted_{channel.channel_id}'
            )
        )

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text='🔙 Назад к каналам', callback_data='back_to_channels_menu')])
    return buttons


def _build_remove_trusted_keyboard(channels: list) -> list:
    """Построить клавиатуру для снятия доверия."""
    buttons = []
    row = []

    for channel in channels:
        row.append(
            InlineKeyboardButton(
                text=f'❌ {channel.title}',
                callback_data=f'remove_trusted_{channel.channel_id}'
            )
        )

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text='🔙 Назад к каналам', callback_data='back_to_channels_menu')])
    return buttons

@admin.callback_query(F.data == 'back_to_channels_menu')
async def back_to_channels_menu(callback: CallbackQuery, state: FSMContext):
    """Вернуться в меню работы с каналами (не в главное меню)."""
    if not await check_admin_access(callback):
        return

    await callback.answer('')
    await callback.message.delete()

    # Показываем меню работы с каналами
    await callback.message.answer(
        '📢 **Работа с каналами**\n\n'
        'Выберите действие:',
        reply_markup=ikb1,
        parse_mode='Markdown'
    )
