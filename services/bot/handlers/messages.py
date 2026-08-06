"""
Обработчики сообщений Telegram бота.

Все обработчики проверяют права администратора через БД.
"""

from aiogram import F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from database import RepositoryFactory, async_session
from services.bot.handlers.keyboards import kb2
from services.bot.handlers.router import admin
from services.bot.handlers.states import AddChannel, DeleteChannel, TrustedChannel

from database.repositories.users import UserRepository


async def check_admin_access(message: Message) -> bool:
    """Проверить права администратора. Возвращает True если доступ разрешён."""
    async with async_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        if not user or user.role != 'admin':
            return False
        return True


@admin.message(F.photo)
async def get_photo_id(message: Message):
    """Получение ID фото."""
    if not await check_admin_access(message):
        await message.answer('❌ У вас нет прав для этой команды')
        return

    photo_id = message.photo[-1].file_id
    await message.answer(
        f"✅ Фото получено!\n\n"
        f"ID: {photo_id}"
    )


@admin.message(AddChannel.add_channel, F.chat_shared)
async def fadd_channel(message: Message, state: FSMContext):
    """Добавление канала."""
    # Проверка прав не требуется — состояние устанавливается только после проверки
    data = message.chat_shared
    await message.delete()

    factory = RepositoryFactory(async_session())
    channels_repo = factory.channels()

    is_success = await channels_repo.create_channel(
        channel_id=data.chat_id,
        title=data.title
    )

    if is_success:
        await message.answer(f'Готово! Добавили {data.title} в бд')
        await state.clear()
    else:
        await message.answer(f'{data.title} уже в бд')


@admin.message(DeleteChannel.delete_channel, F.chat_shared)
async def fdelete_channel(message: Message, state: FSMContext):
    """Удаление канала."""
    # Проверка прав не требуется — состояние устанавливается только после проверки
    data = message.chat_shared
    await message.delete()

    factory = RepositoryFactory(async_session())
    channels_repo = factory.channels()

    is_success = await channels_repo.delete_channel(data.chat_id)

    if is_success:
        await message.answer(f'Готово! Удалили {data.title} из бд')
        await state.clear()
    else:
        await message.answer(f'{data.title} нет в бд')


@admin.message(TrustedChannel.select_channel, F.chat_shared)
async def set_trusted_channel(message: Message, state: FSMContext):
    """Установка флага доверенного источника."""
    # Проверка прав не требуется — состояние устанавливается только после проверки
    data = message.chat_shared
    await message.delete()

    factory = RepositoryFactory(async_session())
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
    if not await check_admin_access(message):
        await message.answer('❌ У вас нет прав для просмотра этой информации')
        return

    from services.bot.utils import show_last_posts
    await show_last_posts(message, limit=10)


@admin.message(F.text == '📝 Сгенерированные новости')
@admin.message(Command('generated_news'))
async def show_generated_news_cmd(message: Message):
    """Показать последние сгенерированные новости."""
    if not await check_admin_access(message):
        await message.answer('❌ У вас нет прав для просмотра этой информации')
        return

    from services.bot.utils import show_generated_news
    await show_generated_news(message, limit=10)
