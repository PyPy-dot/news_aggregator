"""
Обработчики команд Telegram бота.
"""

import logging
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import Message
from aiogram import F

from services.bot.handlers.router import admin
from services.bot.handlers.keyboards import admin_kb, user_kb, ikb1, ikb_trusted, create_subscription_kb
from services.bot.handlers.states import AddChannel, TrustedChannel, UserPreferencesStates
from services.bot.utils import show_last_posts, show_generated_news
from services.bot.handlers import publishers  # noqa: F401
from services.bot.handlers.access import check_admin_access, is_admin

from database import RepositoryFactory
from database.repositories.users import UserRepository
from services.database import get_database_service

logger = logging.getLogger(__name__)


@admin.message(Command('start'))
async def start(message: Message):
    """Команда /start — главное меню и регистрация пользователя."""
    from services.bot.utils import check_and_show_advertisement, send_message_with_retry
    from services.bot.handlers.keyboards import get_user_kb_for_role

    # Регистрируем пользователя в БД
    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)
        await user_repo.get_or_create_user(telegram_id=message.from_user.id)

    # Добавляем информацию о команде /session для админов
    admin_status = await is_admin(message.from_user.id)
    session_help = "\n/session — Проверка сессии Listener Bot" if admin_status else ""

    # Проверяем, является ли пользователь админом
    admin_status = await is_admin(message.from_user.id)

    try:
        if admin_status:
            # Для админов — админ-меню
            await send_message_with_retry(
                message,
                '👋 Привет! Я бот для управления новостями.\n\n'
                '**Админ-панель**\nВыберите действие в меню:',
                reply_markup=admin_kb
            )
        else:
            # Получаем предпочтения пользователя для персонализированного приветствия
            async with get_database_service().session_context() as session:
                factory = RepositoryFactory(session)
                user_repo = factory.users()
                user_prefs = await user_repo.get_preferences(message.from_user.id)
                user_categories = user_prefs['preferred_categories']
                user_tags = user_prefs['preferred_tags']

            # Формируем информацию о подписке
            subscription_info = ""
            if user_categories or user_tags:
                subscription_info = "✅ **Ваши предпочтения:**\n"
                if user_categories:
                    subscription_info += f"   📁 Категории: {', '.join(user_categories[:5])}{'...' if len(user_categories) > 5 else ''}\n"
                if user_tags:
                    subscription_info += f"   🏷️ Тэги: {', '.join(user_tags[:5])}{'...' if len(user_tags) > 5 else ''}\n"
                subscription_info += "\n"
            else:
                subscription_info = (
                    "⚠️ **Вы ещё не настроили предпочтения**\n\n"
                    "Нажмите **📁 Категории** и **🏷️ Тэги**, чтобы выбрать интересующие вас темы.\n"
                    "Новости будут приходить только по выбранным категориям и тэгам.\n\n"
                )

            await send_message_with_retry(
                message,
                f'👋 Привет! Я бот для управления новостями.\n\n'
                f'{subscription_info}'
                f'Выберите действие в меню:',
                reply_markup=user_kb
            )
            # Показываем рекламу (не админу)
            await check_and_show_advertisement(message, message.from_user.id, is_admin=False)
    except TelegramNetworkError as e:
        logger.warning(f"⚠️ Ошибка сети при отправке сообщения: {e} (повторные попытки исчерпаны)")
        # Бот продолжает работать, просто не смог отправить ответ
    except Exception as e:
        logger.error(f"❌ Ошибка в хендлере start: {e}")


@admin.message(Command('get_photo_id'))
async def get_photo(message: Message, state: FSMContext):
    """Команда /get_photo_id — получить ID фото."""
    if not await check_admin_access(message):
        return

    await state.set_state('get_photo_id')
    await message.answer(
        '📸 **Получение ID фото**\n\n'
        'Пришли фото, ID которого нужно получить.\n'
        'Для выхода из режима отправьте /cancel',
        parse_mode='Markdown'
    )


@admin.message(F.text == 'Работа с каналами')
@admin.message(Command('edit_channels'))
async def edit_channels(message: Message, state: FSMContext):
    """Команда /edit_channels — управление каналами."""
    if not await check_admin_access(message):
        return

    await state.set_state(AddChannel.edit_channels)
    await message.answer('Что сделать?', reply_markup=ikb1)




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

    from config.settings import settings
    await show_last_posts(message, limit=settings.repository_default_limit // 10)


@admin.message(Command('generated_news'))
async def generated_news_list(message: Message):
    """Команда /generated_news — показать последние сгенерированные новости."""
    if not await check_admin_access(message):
        return

    from config.settings import settings
    await show_generated_news(message, limit=settings.repository_default_limit // 10)


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
    from services.bot.handlers.keyboards import create_direct_news_description_inline_kb

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
        "Для отмены нажмите /cancel или кнопку ниже",
        reply_markup=create_direct_news_description_inline_kb(),
    )
    await state.set_state(DirectNewsStates.waiting_for_description)


@admin.message(Command('pending_moderation'))
async def pending_moderation(message: Message):
    """Команда /pending_moderation — показать новости на модерации."""
    # Проверяем права администратора
    if not await check_admin_access(message):
        await message.answer('❌ У вас нет прав для просмотра модерации')
        return

    from services.bot.utils import show_pending_moderation
    from config.settings import settings
    await show_pending_moderation(message, limit=settings.repository_default_limit // 5)  # 20 по умолчанию


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


# =============================================================================
# Пользовательское меню (заглушки)
# =============================================================================

@admin.message(F.text == '💎 Подписка')
@admin.message(Command('subscription'))
async def subscription_menu(message: Message):
    """Меню подписки — просмотр статуса и управление."""
    from database.repositories.users import UserRepository
    from services.bot.handlers.keyboards import create_subscription_kb
    from datetime import datetime

    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)

        if not user:
            await message.answer('❌ Пользователь не найден. Нажмите /start')
            return

        # Формируем текст статуса
        if user.has_active_subscription:
            status_text = '✅ **Подписка активна**\n\n'

            # Нормализуем пустую строку в None
            subscription_ends_at = user.subscription_ends_at
            if subscription_ends_at == '':
                subscription_ends_at = None

            if subscription_ends_at:
                days_left = (subscription_ends_at - datetime.now()).days
                if days_left > 0:
                    status_text += f'📅 Действует до: **{subscription_ends_at.strftime("%d.%m.%Y")}**\n'
                    status_text += f'⏳ Осталось дней: **{days_left}**\n'
                else:
                    status_text += '⚠️ Подписка истекла\n'
            else:
                status_text += '♾️ **Бессрочная подписка**\n'
        else:
            status_text = '❌ **Нет активной подписки**\n\n'
            status_text += 'Оформите подписку, чтобы получить доступ ко всем функциям.\n'

        await message.answer(
            f'💎 **Управление подпиской**\n\n'
            f'{status_text}',
            reply_markup=create_subscription_kb(user.has_active_subscription),
            parse_mode='Markdown'
        )


@admin.message(F.text == '📁 Категории')
@admin.message(Command('categories'))
async def categories_menu(message: Message, state: FSMContext):
    """Меню категорий — выбор предпочтительных категорий (мультивыбор)."""
    from database import RepositoryFactory
    from database.repositories.users import UserRepository
    from services.bot.handlers.keyboards import create_categories_kb, create_subscription_kb
    from services.bot.handlers.states import UserPreferencesStates

    # Получаем фабрику и репозитории
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        categories_repo = factory.categories()
        user_repo = factory.users()

        # Получаем пользователя и проверяем подписку
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        has_subscription = user.has_active_subscription if user else False

        # Если подписки нет — перенаправляем на управление подпиской
        if not has_subscription:
            await message.answer(
                "⚠️ <b>Эта функция доступна только подписчикам</b>\n\n"
                "Оформите подписку, чтобы получать новости с учётом ваших предпочтений.\n\n"
                "Подписка даёт доступ к:\n"
                "✅ Персональной ленте новостей\n"
                "✅ Уведомлениям по предпочтениям\n"
                "✅ Доступу к эксклюзивному контенту",
                parse_mode='HTML',
                reply_markup=create_subscription_kb(False)
            )
            return

        # Получаем категории и предпочтения пользователя
        categories = await categories_repo.get_all_categories(active_only=True)
        user_prefs = await user_repo.get_preferences(message.from_user.id)
        user_categories = user_prefs['preferred_categories']

    # Формируем данные для клавиатуры
    categories_data = [{'id': c.id, 'name': c.name} for c in categories]

    # Устанавливаем состояние
    await state.set_state(UserPreferencesStates.viewing_categories)

    # Формируем текст со списком выбранных категорий
    if user_categories:
        categories_list = '\n'.join(f'• {cat}' for cat in sorted(user_categories))
        text = (
            f'📁 <b>Категории новостей</b>\n\n'
            f'Выбрано категорий: **{len(user_categories)}**\n\n'
            f'{categories_list}\n\n'
            f'<i>Нажмите на категорию, чтобы добавить или удалить её.</i>'
        )
    else:
        text = (
            f'📁 <b>Категории новостей</b>\n\n'
            f'У вас пока нет выбранных категорий.\n\n'
            f'<i>Нажмите на категорию ниже, чтобы добавить её.</i>'
        )

    await message.answer(
        text,
        parse_mode='HTML',
        reply_markup=create_categories_kb(categories_data, user_categories)
    )


@admin.message(F.text == '🏷️ Тэги')
@admin.message(Command('tags'))
async def tags_menu(message: Message, state: FSMContext):
    """Меню тэгов — управление предпочтительными тэгами."""
    from database.repositories.users import UserRepository
    from services.bot.handlers.keyboards import create_user_tags_kb, create_subscription_kb
    from services.bot.handlers.states import UserPreferencesStates

    # Получаем пользователя и проверяем подписку
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        user_repo = factory.users()
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        has_subscription = user.has_active_subscription if user else False

        # Если подписки нет — перенаправляем на управление подпиской
        if not has_subscription:
            await message.answer(
                "⚠️ <b>Эта функция доступна только подписчикам</b>\n\n"
                "Оформите подписку, чтобы получать новости с учётом ваших предпочтений.\n\n"
                "Подписка даёт доступ к:\n"
                "✅ Персональной ленте новостей\n"
                "✅ Уведомлениям по предпочтениям\n"
                "✅ Доступу к эксклюзивному контенту",
                parse_mode='HTML',
                reply_markup=create_subscription_kb(False)
            )
            return

        user_prefs = await user_repo.get_preferences(message.from_user.id)
        user_tags = user_prefs['preferred_tags']

    # Устанавливаем состояние
    await state.set_state(UserPreferencesStates.viewing_tags)

    # Формируем текст со списком тэгов
    if user_tags:
        tags_list = '\n'.join(f'• {tag}' for tag in sorted(user_tags))
        text = (
            f'🏷️ <b>Ваши тэги</b>\n\n'
            f'Выбрано тэгов: **{len(user_tags)}**\n\n'
            f'{tags_list}\n\n'
            f'<i>Нажмите на тэг, чтобы удалить его.</i>\n'
            f'<i>Отправьте новые тэги через пробел, чтобы добавить.</i>'
        )
    else:
        text = (
            f'🏷️ <b>Тэги новостей</b>\n\n'
            f'У вас пока нет выбранных тэгов.\n\n'
            f'<i>Отправьте тэги через пробел, чтобы добавить их.</i>\n'
            f'<i>Например:</i> <code>Украина экономика инфляция</code>'
        )

    # Создаём клавиатуру с тэгами пользователя
    keyboard = create_user_tags_kb(user_tags)

    await message.answer(
        text,
        parse_mode='HTML',
        reply_markup=keyboard
    )


@admin.message(UserPreferencesStates.viewing_tags, F.text)
async def process_tags_input(message: Message, state: FSMContext):
    """
    Обработка ввода тэгов пользователем.

    Тэги вводятся через пробел и сохраняются в БД.
    """
    from database.repositories.users import UserRepository
    from services.bot.handlers.keyboards import create_user_tags_kb
    from services.bot.handlers.states import UserPreferencesStates

    # Получаем тэги из сообщения (разделяем по пробелам)
    input_text = message.text.strip()
    new_tags = [tag.strip() for tag in input_text.split() if tag.strip()]

    if not new_tags:
        await message.answer(
            '⚠️ <b>Нет тэгов для добавления</b>\n\n'
            'Отправьте тэги через пробел. Например:\n'
            '<code>Украина экономика инфляция</code>',
            parse_mode='HTML'
        )
        return

    # Получаем текущие тэги пользователя и добавляем новые
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        user_repo = factory.users()
        user_prefs = await user_repo.get_preferences(message.from_user.id)
        current_tags = user_prefs['preferred_tags']

        # Добавляем новые тэги (без дубликатов)
        updated_tags = list(dict.fromkeys(current_tags + new_tags))  # Сохраняем порядок, убираем дубликаты

        # Сохраняем в БД
        await user_repo.update_preferences(
            telegram_id=message.from_user.id,
            preferred_tags=updated_tags,
        )

    # Формируем ответ
    added_tags = [tag for tag in new_tags if tag not in current_tags]
    skipped_tags = [tag for tag in new_tags if tag in current_tags]

    response_text = f'✅ <b>Тэги добавлены</b>\n\n'
    if added_tags:
        response_text += f'Добавлено: **{", ".join(added_tags)}**\n'
    if skipped_tags:
        response_text += f'Уже были: **{", ".join(skipped_tags)}**\n'
    response_text += f'\nВсего тэгов: **{len(updated_tags)}**'

    # Создаём клавиатуру с обновлёнными тэгами
    keyboard = create_user_tags_kb(updated_tags)

    await message.answer(
        response_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )


# =============================================================================
# Очистка базы данных
# =============================================================================

@admin.message(Command('cleanup'))
async def cleanup_database(message: Message):
    """
    Команда /cleanup — очистка базы данных от записей.

    Удаляет все записи из таблиц: posts, generated_news, events, publishers.
    Таблицы users и channels НЕ очищаются.
    """
    if not await check_admin_access(message):
        await message.answer('❌ У вас нет прав для этой команды')
        return

    from services.bot.handlers.keyboards import cleanup_confirm_kb

    await message.answer(
        '⚠️ **Очистка базы данных**\n\n'
        'Вы собираетесь удалить ВСЕ записи из следующих таблиц:\n'
        '• 📝 Посты (posts)\n'
        '• 📰 Сгенерированные новости (generated_news)\n'
        '• 📚 События (events)\n'
        '• 📢 Каналы публикации (publishers)\n\n'
        '❗️ Таблицы **users** и **channels** НЕ будут очищены.\n\n'
        'Вы уверены?',
        reply_markup=cleanup_confirm_kb,
        parse_mode='Markdown'
    )


@admin.message(Command('unsubscribe'))
@admin.message(F.text == '❌ Отписаться')
async def unsubscribe_command(message: Message):
    """
    Отписаться от новостей — сброс предпочтений и отписка.
    Редактирует исходное сообщение меню, убирая кнопку отписки.
    """
    from database.repositories.users import UserRepository
    from services.bot.handlers.keyboards import get_user_kb_for_role, user_kb
    from services.bot.handlers.access import is_admin

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        user_repo = factory.users()

        user = await user_repo.get_by_telegram_id(message.from_user.id)

        if not user:
            await message.answer(
                '❌ Вы не найдены в базе данных.\n\n'
                'Возможно, вы ещё не оформили подписку.',
                reply_markup=user_kb
            )
            return

        # Сбрасываем предпочтения и отписку
        await user_repo.clear_preferences(message.from_user.id)
        await user_repo.update_subscription(
            telegram_id=message.from_user.id,
            has_subscription=False,
            started_at=None,
            ends_at=None,
        )

    # Получаем клавиатуру БЕЗ кнопки отписки (has_subscription=False)
    is_admin_user = user.role == 'admin'
    keyboard_after_unsubscribe = get_user_kb_for_role(is_admin_user, has_subscription=False)

    # Редактируем исходное сообщение меню
    try:
        await message.edit_text(
            '✅ <b>Вы успешно отписались от новостей!</b>\n\n'
            'Ваши предпочтения сброшены:\n'
            '• ❌ Категории очищены\n'
            '• ❌ Тэги удалены\n'
            '• ❌ Подписка отключена\n\n'
            'Вы всегда можете подписаться снова через меню /subscription',
            parse_mode='HTML',
            reply_markup=keyboard_after_unsubscribe
        )
    except Exception as e:
        # Если не удалось отредактировать (например, сообщение слишком старое),
        # отправляем новое сообщение
        logger.debug(f"Не удалось отредактировать сообщение: {e}")
        await message.answer(
            '✅ <b>Вы успешно отписались от новостей!</b>\n\n'
            'Ваши предпочтения сброшены:\n'
            '• ❌ Категории очищены\n'
            '• ❌ Тэги удалены\n'
            '• ❌ Подписка отключена\n\n'
            'Вы всегда можете подписаться снова через меню /subscription',
            parse_mode='HTML',
            reply_markup=keyboard_after_unsubscribe
        )

    logger.info(f"📤 Пользователь ID={message.from_user.id} отписался от новостей")


@admin.message(F.text == '👤 Меню пользователя')
async def switch_to_user_menu(message: Message):
    """
    Переключиться на пользовательское меню (для админов).
    """
    from services.bot.handlers.keyboards import get_user_kb_for_role
    from services.bot.handlers.access import is_admin

    # Проверяем является ли пользователь админом и его подписку
    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        is_admin_user = user and user.role == 'admin'
        has_subscription = user.has_active_subscription if user else False

    # Получаем клавиатуру с учётом роли и подписки
    keyboard = get_user_kb_for_role(is_admin_user, has_subscription)

    await message.answer(
        '👤 <b>Переключено в меню пользователя</b>\n\n'
        'Теперь вы видите меню обычного пользователя.\n'
        'Для возврата в админ-меню нажмите /admin',
        parse_mode='HTML',
        reply_markup=keyboard
    )


@admin.message(Command('admin'))
@admin.message(F.text == '🔙 Меню админа')
async def switch_to_admin_menu(message: Message):
    """
    Переключиться на админ-меню (для админов).
    """
    from services.bot.handlers.keyboards import admin_kb
    from services.bot.handlers.access import is_admin

    # Проверяем права администратора
    if not await is_admin(message.from_user.id):
        await message.answer('❌ У вас нет прав администратора')
        return

    await message.answer(
        '🔙 <b>Возврат в меню администратора</b>',
        parse_mode='HTML',
        reply_markup=admin_kb
    )


@admin.message(Command('metrics'))
async def show_metrics(message: Message):
    """
    Команда /metrics — показать метрики системы (для админов).

    Показывает:
    - Размер очередей
    - Активные задачи
    - Статистику векторного поиска
    - Health status
    """
    # Проверяем права администратора
    if not await check_admin_access(message):
        await message.answer('❌ У вас нет прав администратора')
        return

    from services.monitoring import get_health_status, update_queue_size, update_active_tasks

    # Получаем health status
    health = get_health_status()

    # Формируем сообщение с метриками
    metrics_text = (
        '📊 <b>Метрики системы</b>\n\n'
        f'<b>Статус:</b> {health["status"]}\n'
        f'<b>Время:</b> {health["timestamp"]:.0f}\n\n'
        'ℹ️ Полные метрики доступны на /metrics endpoint'
    )

    await message.answer(metrics_text, parse_mode='HTML')


@admin.message(Command('session'))
async def cmd_session(message: Message):
    """
    Команда /session — проверка состояния сессии Listener Bot.
    
    Доступна только администраторам.
    """
    from services.bot.utils import send_message_with_retry
    
    # Проверяем, админ ли пользователь
    if not await check_admin_access(message):
        return
    
    session_name = 'userbot'
    session_file = f"{session_name}.session"
    
    import os
    from datetime import datetime
    
    # Проверяем существование файла
    if not os.path.exists(session_file):
        text = (
            "📊 **Статус сессии Listener Bot**\n\n"
            "❌ Сессия не найдена\n\n"
            "Требуется авторизация. Запустите бота заново."
        )
        await send_message_with_retry(message, text, parse_mode='Markdown')
        return
    
    # Получаем информацию о файле
    mtime = os.path.getmtime(session_file)
    last_modified = datetime.fromtimestamp(mtime)
    age = datetime.now() - last_modified
    
    # Определяем статус
    if age.days == 0:
        status = "✅ Свежая (сегодня)"
    elif age.days < 7:
        status = f"✅ Активная ({age.days} дн.)"
    elif age.days < 30:
        status = f"⚠️ Устарела ({age.days} дн.)"
    else:
        status = f"❌ Очень старая ({age.days} дн.)"
    
    text = (
        f"📊 **Статус сессии Listener Bot**\n\n"
        f"📁 Файл: `{session_file}`\n"
        f"🕒 Последняя активность: {last_modified.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📅 Возраст: {age.days} дн.\n"
        f"🔹 Статус: {status}\n\n"
        f"_Для обновления сессии используйте команду /auth или перезапустите бота_"
    )
    
    await send_message_with_retry(message, text, parse_mode='Markdown')
