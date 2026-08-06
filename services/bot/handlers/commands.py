"""
Обработчики команд Telegram бота.
"""

from services.bot.handlers.router import admin
from services.bot.handlers.keyboards import admin_kb, user_kb, ikb1, ikb_trusted
from services.bot.handlers.states import AddChannel, TrustedChannel
from services.bot.utils import show_last_posts, show_generated_news
from services.bot.handlers import publishers  # noqa: F401
from services.bot.handlers.access import check_admin_access, is_admin
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import Message
from aiogram import F

from database.repositories.users import UserRepository
from database.models import async_session


@admin.message(Command('start'))
async def start(message: Message):
    """Команда /start — главное меню и регистрация пользователя."""
    # Регистрируем пользователя в БД
    async with async_session() as session:
        user_repo = UserRepository(session)
        await user_repo.get_or_create_user(telegram_id=message.from_user.id)

    # Проверяем, является ли пользователь админом
    admin_status = await is_admin(message.from_user.id)

    if admin_status:
        await message.answer(
            '👋 Привет! Я бот для управления новостями.\n\n'
            '**Админ-панель**\nВыберите действие в меню:',
            reply_markup=admin_kb
        )
    else:
        await message.answer(
            '👋 Привет! Я бот для управления новостями.\n\n'
            'Выберите действие в меню:',
            reply_markup=user_kb
        )


@admin.message(Command('get_photo_id'))
async def get_photo(message: Message):
    """Команда /get_photo_id — получить ID фото."""
    if not await check_admin_access(message):
        return

    await message.answer('Пришли фото, id которого нужно получить')


@admin.message(F.text == 'Работа с каналами')
@admin.message(Command('edit_channels'))
async def edit_channels(message: Message, state: FSMContext):
    """Команда /edit_channels — управление каналами."""
    if not await check_admin_access(message):
        return

    await state.set_state(AddChannel.edit_channels)
    await message.answer('Что сделать?', reply_markup=ikb1)


@admin.message(F.text == 'Доверенные источники')
@admin.message(Command('trusted_channels'))
async def trusted_channels(message: Message, state: FSMContext):
    """Команда /trusted_channels — управление доверенными источниками."""
    if not await check_admin_access(message):
        return

    await state.set_state(TrustedChannel.select_channel)
    await message.answer(
        'Выберите канал и назначьте его доверенным или снимите доверие:',
        reply_markup=ikb_trusted
    )


@admin.message(F.text == 'Работа с сайтами')
@admin.message(Command('edit_sites'))
async def edit_sites(message: Message):
    """Команда /edit_sites — работа с сайтами (не реализовано)."""
    if not await check_admin_access(message):
        return

    await message.answer('Пока не реализовано')


@admin.message(Command('gen_news_by_id'))
async def gen_news_by_id(message: Message):
    """Команда /gen_news_by_id — генерация новости по ID поста."""
    if not await check_admin_access(message):
        return

    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer('Использование: /gen_news_by_id <ID_поста>')
            return

        post_id = int(parts[1])
        await message.answer(
            f'Генерация новости для поста ID={post_id} (в разработке)'
        )

    except ValueError:
        await message.answer('Неверный формат ID. Используйте число.')


@admin.message(Command('last_posts'))
async def last_posts(message: Message):
    """Команда /last_posts — показать последние посты."""
    if not await check_admin_access(message):
        return

    await show_last_posts(message, limit=10)


@admin.message(Command('generated_news'))
async def generated_news_list(message: Message):
    """Команда /generated_news — показать последние сгенерированные новости."""
    if not await check_admin_access(message):
        return

    await show_generated_news(message, limit=10)


@admin.message(Command('publishers'))
async def publishers_menu(message: Message):
    """Команда /publishers — управление каналами публикации."""
    if not await check_admin_access(message):
        return

    from services.bot.handlers.publishers import cmd_publishers
    await cmd_publishers(message)


@admin.message(F.text == '✍️ Прямая генерация новости')
@admin.message(Command('direct_news'))
async def direct_news_menu(message: Message, state: FSMContext):
    """Команда /direct_news — прямая генерация новости админом."""
    if not await check_admin_access(message):
        return

    from services.bot.handlers.states import DirectNewsStates
    from aiogram.types import ReplyKeyboardRemove

    await state.clear()
    await message.answer(
        "✍️ **Прямая генерация новости — Этап 1**\n\n"
        "**Введите описание новости**\n\n"
        "Отправьте текст, который нужно преобразовать в новость.\n"
        "Это может быть:\n"
        "- Анонс мероприятия\n"
        "- Рекламный материал\n"
        "- Краткая сводка\n"
        "- Любая другая информация\n\n"
        "📎 **Фото/видео:** Если нужно прикрепить медиа, отправьте его вместе с текстом.\n\n"
        "Для отмены нажмите /cancel",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(DirectNewsStates.waiting_for_description)


@admin.message(Command('pending_moderation'))
async def pending_moderation(message: Message):
    """Команда /pending_moderation — показать новости на модерации."""
    # Проверяем права администратора
    async with async_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        if not user or user.role != 'admin':
            await message.answer('❌ У вас нет прав для просмотра модерации')
            return

    from services.bot.utils import show_pending_moderation
    await show_pending_moderation(message, limit=20)


@admin.message(Command('approve_news'))
async def approve_news(message: Message):
    """Команда /approve_news <ID> — одобрить новость."""
    from services.bot.utils import approve_news_by_id

    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer('Использование: /approve_news <ID_новости>')
            return

        news_id = int(parts[1])

        if not await check_admin_access(message):
            return

        await approve_news_by_id(message, news_id, message.from_user.id)

    except ValueError:
        await message.answer('Неверный формат ID. Используйте число.')


@admin.message(Command('reject_news'))
async def reject_news(message: Message):
    """Команда /reject_news <ID> — отклонить новость."""
    from services.bot.utils import reject_news_by_id

    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer('Использование: /reject_news <ID_новости>')
            return

        news_id = int(parts[1])

        if not await check_admin_access(message):
            return

        await reject_news_by_id(message, news_id, message.from_user.id)

    except ValueError:
        await message.answer('Неверный формат ID. Используйте число.')
