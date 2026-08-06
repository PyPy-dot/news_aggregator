from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from services.bot.handlers.keyboards import admin_kb, user_kb, choose_chat_kb, ikb_trusted
from services.bot.handlers.router import admin
from services.bot.handlers.states import AddChannel, DeleteChannel, TrustedChannel

from database.repositories.users import UserRepository
from database.models import async_session


async def check_admin_access(callback: CallbackQuery) -> bool:
    """Проверить права администратора. Возвращает True если доступ разрешён."""
    async with async_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user or user.role != 'admin':
            await callback.answer('❌ У вас нет прав для этого действия', show_alert=True)
            return False
        return True


@admin.callback_query(F.data == 'add_channel')
async def add_channel(callback: CallbackQuery, state: FSMContext):
    if not await check_admin_access(callback):
        return

    await callback.answer('')
    await callback.message.delete()
    await state.set_state(AddChannel.add_channel)
    await callback.message.answer('Нажми кнопку и выбери чат:', reply_markup=choose_chat_kb)


@admin.callback_query(F.data == 'delete_channel')
async def delete_channel(callback: CallbackQuery, state: FSMContext):
    if not await check_admin_access(callback):
        return

    await callback.answer('')
    await callback.message.delete()
    await state.set_state(DeleteChannel.delete_channel)
    await callback.message.answer('Нажми кнопку и выбери чат:', reply_markup=choose_chat_kb)


@admin.callback_query(F.data == 'make_trusted')
async def make_trusted(callback: CallbackQuery, state: FSMContext):
    if not await check_admin_access(callback):
        return

    await callback.answer('')
    await callback.message.delete()
    await state.set_state(TrustedChannel.select_channel)
    await callback.message.answer(
        'Выберите канал, чтобы сделать его доверенным (новости будут иметь рейтинг 100):',
        reply_markup=choose_chat_kb
    )


@admin.callback_query(F.data == 'remove_trusted')
async def remove_trusted(callback: CallbackQuery, state: FSMContext):
    if not await check_admin_access(callback):
        return

    await callback.answer('')
    await callback.message.delete()
    await state.set_state(TrustedChannel.select_channel)
    await callback.message.answer(
        'Выберите канал, чтобы снять с него доверие:',
        reply_markup=choose_chat_kb
    )


@admin.callback_query(F.data == 'back_to_menu')
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer('')

    # Проверяем роль для показа правильного меню
    async with async_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        is_admin = user and user.role == 'admin'

    if state is not None:
        await state.clear()

    await callback.message.delete()
    await callback.message.answer(
        '👋 Главное меню',
        reply_markup=admin_kb if is_admin else user_kb
    )
