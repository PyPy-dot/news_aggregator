"""
Callback-хендлеры для управления предпочтениями пользователя и подпиской.

Модуль содержит обработчики для:
- Управления категориями и тэгами
- Управления подпиской
- Навигации по меню
"""

import logging
from datetime import datetime, timedelta
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from services.bot.handlers.router import admin
from services.bot.handlers.states import UserPreferencesStates
from database import RepositoryFactory
from database.repositories.users import UserRepository
from services.database import get_database_service
from config.settings import settings

logger = logging.getLogger(__name__)


@admin.callback_query(F.data == 'back_to_menu')
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Вернуться в главное меню."""
    await callback.answer('')

    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        is_admin = user and user.role == 'admin'
        has_subscription = user.has_active_subscription if user else False

    if state is not None:
        await state.clear()

    await callback.message.delete()

    from services.bot.handlers.keyboards import admin_kb, get_user_kb_for_role
    # Для админов показываем админ-меню, для обычных пользователей — пользовательское
    if is_admin:
        keyboard = admin_kb
    else:
        keyboard = get_user_kb_for_role(False, has_subscription)

    await callback.message.answer(
        '👋 Главное меню',
        reply_markup=keyboard
    )


@admin.callback_query(F.data == 'back_to_user_menu')
async def back_to_user_menu_callback(callback: CallbackQuery, state: FSMContext):
    """Вернуться в меню пользователя."""
    from services.bot.handlers.keyboards import get_user_kb_for_role

    # Проверяем роль и подписку пользователя
    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        is_admin = user and user.role == 'admin'
        has_subscription = user.has_active_subscription if user else False

    await callback.answer()
    await state.clear()
    await callback.message.delete()

    keyboard = get_user_kb_for_role(is_admin, has_subscription)

    await callback.message.answer(
        '👋 Главное меню',
        reply_markup=keyboard
    )


@admin.callback_query(F.data.startswith('category_toggle_'))
async def category_toggle_callback(callback: CallbackQuery, state: FSMContext):
    """Переключить категорию в предпочтениях пользователя (мультивыбор)."""
    from services.bot.handlers.keyboards import create_categories_kb

    category_name = callback.data.replace('category_toggle_', '')

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        user_repo = factory.users()
        categories_repo = factory.categories()

        user_prefs = await user_repo.get_preferences(callback.from_user.id)
        user_categories = user_prefs['preferred_categories']

        if category_name in user_categories:
            await user_repo.remove_preferred_category(callback.from_user.id, category_name)
            user_categories.remove(category_name)
            await callback.answer(f'❌ Категория "{category_name}" удалена из предпочтений')
        else:
            await user_repo.add_preferred_category(callback.from_user.id, category_name)
            user_categories.append(category_name)
            await callback.answer(f'✅ Категория "{category_name}" добавлена в предпочтения')

        categories = await categories_repo.get_all_categories(active_only=True)
        categories_data = [{'id': c.id, 'name': c.name} for c in categories]

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

        # Обновляем и текст, и клавиатуру
        try:
            await callback.message.edit_text(
                text,
                parse_mode='HTML',
                reply_markup=create_categories_kb(categories_data, user_categories)
            )
        except Exception as e:
            # Если сообщение слишком старое для редактирования, отправляем новое
            await callback.message.answer(
                text,
                parse_mode='HTML',
                reply_markup=create_categories_kb(categories_data, user_categories)
            )


@admin.callback_query(F.data.startswith('tag_toggle_'))
async def tag_toggle_callback(callback: CallbackQuery, state: FSMContext):
    """Переключить тэг в предпочтениях пользователя (старая версия для совместимости)."""
    from services.bot.handlers.keyboards import create_tags_kb, PREDEFINED_TAGS

    tag_name = callback.data.replace('tag_toggle_', '')

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        user_repo = factory.users()

        user_prefs = await user_repo.get_preferences(callback.from_user.id)
        user_tags = user_prefs['preferred_tags']

        if tag_name in user_tags:
            await user_repo.remove_preferred_tag(callback.from_user.id, tag_name)
            user_tags.remove(tag_name)
            await callback.answer(f'❌ Тэг "{tag_name}" удалён из предпочтений')
        else:
            await user_repo.add_preferred_tag(callback.from_user.id, tag_name)
            user_tags.append(tag_name)
            await callback.answer(f'✅ Тэг "{tag_name}" добавлен в предпочтения')

        await callback.message.edit_reply_markup(
            reply_markup=create_tags_kb(PREDEFINED_TAGS, user_tags)
        )


@admin.callback_query(F.data.startswith('tag_remove_'))
async def tag_remove_callback(callback: CallbackQuery, state: FSMContext):
    """Удалить тэг из предпочтений пользователя."""
    from services.bot.handlers.keyboards import create_user_tags_kb

    tag_name = callback.data.replace('tag_remove_', '')

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        user_repo = factory.users()

        user_prefs = await user_repo.get_preferences(callback.from_user.id)
        user_tags = user_prefs['preferred_tags']

        if tag_name in user_tags:
            await user_repo.remove_preferred_tag(callback.from_user.id, tag_name)
            user_tags.remove(tag_name)
            await callback.answer(f'❌ Тэг "{tag_name}" удалён', show_alert=False)

            if user_tags:
                tags_list = '\n'.join(f'• {tag}' for tag in sorted(user_tags))
                text = (
                    f'🏷️ <b>Ваши тэги</b>\n\n'
                    f'Выбрано тэгов: **{len(user_tags)}**\n\n'
                    f'{tags_list}\n\n'
                    f'<i>Нажмите на тэг, чтобы удалить его.</i>\n'
                    f'<i>Отправьте новые тэги через пробел, чтобы добавить.</i>'
                )
                keyboard = create_user_tags_kb(user_tags)
            else:
                text = (
                    f'🏷️ <b>Тэги новостей</b>\n\n'
                    f'У вас пока нет выбранных тэгов.\n\n'
                    f'<i>Отправьте тэги через пробел, чтобы добавить их.</i>\n'
                    f'<i>Например:</i> <code>Украина экономика инфляция</code>'
                )
                keyboard = create_user_tags_kb([])

            try:
                await callback.message.edit_text(text, parse_mode='HTML', reply_markup=keyboard)
            except Exception as e:
                logger.warning(f"Не удалось отредактировать сообщение с тэгами: {e}")
                await callback.message.answer(text, parse_mode='HTML', reply_markup=keyboard)
        else:
            await callback.answer(f'⚠️ Тэг "{tag_name}" не найден', show_alert=True)


@admin.callback_query(F.data == 'subscription_menu')
async def subscription_menu_callback(callback: CallbackQuery):
    """Показать меню управления подпиской."""
    from services.bot.handlers.keyboards import create_subscription_kb

    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)

        if not user:
            await callback.answer('❌ Пользователь не найден. Нажмите /start', show_alert=True)
            return

        status_text = _format_subscription_status(user)

        await callback.message.edit_text(
            f'💎 **Управление подпиской**\n\n{status_text}',
            reply_markup=create_subscription_kb(user.has_active_subscription),
            parse_mode='Markdown'
        )
        await callback.answer()


@admin.callback_query(F.data == 'subscribe_buy')
async def subscribe_buy_callback(callback: CallbackQuery):
    """
    Оформить подписку (30 дней).

    В зависимости от настроенного платёжного провайдера:
    - Test provider: подписка оформляется мгновенно (бесплатно)
    - Telegram Stars: создаётся инвойс для оплаты
    """
    from services.payment import get_payment_service, PaymentStatus
    from services.bot.handlers.keyboards import create_subscription_kb

    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)

        if not user:
            await callback.answer('❌ Пользователь не найден. Нажмите /start', show_alert=True)
            return

        if user.has_active_subscription:
            await callback.answer('✅ У вас уже есть активная подписка', show_alert=True)
            return

        # Получаем платёжный сервис
        payment_service = get_payment_service()
        provider_name = payment_service.provider_name

        # Если тестовый провайдер — оформляем подписку сразу
        if provider_name == 'test':
            await _process_test_subscription(callback, user_repo)
        else:
            # Создаём платёж для реального провайдера
            await _create_payment_link(callback, payment_service, user_repo)


async def _process_test_subscription(callback: CallbackQuery, user_repo: UserRepository):
    """Обработать подписку в тестовом режиме (бесплатно)."""
    from datetime import datetime, timedelta
    from services.bot.handlers.keyboards import create_subscription_kb

    now = datetime.now()
    ends_at = now + timedelta(days=30)

    await user_repo.update_subscription(
        telegram_id=callback.from_user.id,
        has_subscription=True,
        started_at=now,
        ends_at=ends_at,
    )

    await callback.answer('✅ Подписка оформлена на 30 дней! (тестовый режим)', show_alert=True)

    await callback.message.edit_text(
        f'✅ **Подписка оформлена!**\n\n'
        f'📅 Действует до: **{ends_at.strftime("%d.%m.%Y")}**\n'
        f'⏳ Осталось дней: **30**\n\n'
        '🧪 ТЕСТОВЫЙ РЕЖИМ: подписка оформлена бесплатно.\n\n'
        'Для подключения реальной оплаты используйте Telegram Stars или другой платёжный сервис.',
        parse_mode='Markdown',
        reply_markup=create_subscription_kb(True)
    )

    logger.info(f"✅ Тестовая подписка оформлена: user_id={callback.from_user.id}")


async def _create_payment_link(
    callback: CallbackQuery,
    payment_service,
    user_repo: UserRepository
):
    """Создать ссылку на оплату для реального провайдера."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    user_id = callback.from_user.id
    duration_days = 30
    amount = 99.0  # Рублей

    try:
        # Создаём платёж
        payment_link = await payment_service.create_subscription_payment(
            user_id=user_id,
            duration_days=duration_days,
            amount=amount,
        )

        # Сохраняем payment_id в состоянии для отслеживания
        from aiogram.fsm.context import FSMContext
        state_data = {'payment_id': payment_link.payment_id, 'amount': amount}
        # Note: FSM state management would need proper implementation

        # Создаём клавиатуру с кнопкой оплаты
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text='💳 Оплатить подписку', url=payment_link.url)],
                [InlineKeyboardButton(text='❌ Отмена', callback_data='subscription_menu')],
            ]
        )

        await callback.message.edit_text(
            f'💳 **Оформление подписки**\n\n'
            f'📅 Длительность: **{duration_days} дней**\n'
            f'💰 Стоимость: **{amount}₽**\n\n'
            f'Нажмите кнопку ниже для оплаты.\n\n'
            f'ID платежа: `{payment_link.payment_id}`',
            parse_mode='Markdown',
            reply_markup=keyboard
        )

        await callback.answer('Создан счёт на оплату', show_alert=False)

        logger.info(
            f"💳 Платёж создан: user_id={user_id}, "
            f"payment_id={payment_link.payment_id}, amount={amount}"
        )

    except Exception as e:
        logger.error(f"Ошибка создания платежа: {e}", exc_info=True)
        await callback.answer('❌ Ошибка создания счёта. Попробуйте позже.', show_alert=True)


@admin.callback_query(F.data == 'subscribe_extend')
async def subscribe_extend_callback(callback: CallbackQuery):
    """Продлить подписку (30 дней)."""
    from services.bot.handlers.keyboards import create_subscription_kb

    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)

        if not user:
            await callback.answer('❌ Пользователь не найден', show_alert=True)
            return

        # Нормализуем пустую строку в None
        subscription_ends_at = user.subscription_ends_at
        if subscription_ends_at == '':
            subscription_ends_at = None

        now = datetime.now()
        if subscription_ends_at and subscription_ends_at > now:
            new_ends_at = subscription_ends_at + timedelta(days=30)
        else:
            new_ends_at = now + timedelta(days=30)

        await user_repo.update_subscription(
            telegram_id=callback.from_user.id,
            has_subscription=True,
            started_at=now,
            ends_at=new_ends_at,
        )

    await callback.answer('✅ Подписка продлена на 30 дней!', show_alert=True)

    await callback.message.edit_text(
        f'✅ **Подписка продлена!**\n\n'
        f'📅 Действует до: **{new_ends_at.strftime("%d.%m.%Y")}**\n\n'
        'Спасибо, что остаётесь с нами! 🎉',
        parse_mode='Markdown',
        reply_markup=create_subscription_kb(True)
    )


@admin.callback_query(F.data == 'subscribe_info')
async def subscribe_info_callback(callback: CallbackQuery):
    """Показать информацию о подписке."""
    from database.repositories.users import UserRepository
    from services.database import get_database_service

    await callback.answer()

    # Проверяем, есть ли у пользователя активная подписка
    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)

    # Формируем клавиатуру в зависимости от статуса подписки
    if user and user.has_active_subscription:
        # У пользователя уже есть подписка — кнопки "Оформить" не показываем
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text='🔙 Назад', callback_data='back_to_user_menu')]
            ]
        )
        message_text = (
            '💎 **Премиум подписка**\n\n'
            '✅ **У вас активна подписка!**\n\n'
            'Преимущества подписки:\n\n'
            '📰 **Доступ ко всем новостям**\n'
            '   — Полные версии материалов\n'
            '   — Приоритетная публикация\n\n'
            '🏷️ **Персональные настройки**\n'
            '   — Выбор категорий и тэгов\n'
            '   — Индивидуальная лента\n\n'
            '⚡ **Быстрые уведомления**\n'
            '   — Мгновенные алерты\n'
            '   — Срочные новости первыми\n\n'
            'Ваша подписка активна. Спасибо, что вы с нами! 🎉'
        )
    else:
        # Нет подписки — показываем кнопку оформления
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text='💳 Оформить', callback_data='subscribe_buy')],
                [InlineKeyboardButton(text='🔙 Назад', callback_data='back_to_user_menu')]
            ]
        )
        message_text = (
            '💎 **Премиум подписка**\n\n'
            'Преимущества подписки:\n\n'
            '📰 **Доступ ко всем новостям**\n'
            '   — Полные версии материалов\n'
            '   — Приоритетная публикация\n\n'
            '🏷️ **Персональные настройки**\n'
            '   — Выбор категорий и тэгов\n'
            '   — Индивидуальная лента\n\n'
            '⚡ **Быстрые уведомления**\n'
            '   — Мгновенные алерты\n'
            '   — Срочные новости первыми\n\n'
            '💰 **Стоимость:** 30 дней\n\n'
            'Для оформления нажмите "Оформить подписку"'
        )

    await callback.message.edit_text(
        message_text,
        parse_mode='Markdown',
        reply_markup=keyboard
    )


# =============================================================================
# Вспомогательные функции
# =============================================================================

def _format_subscription_status(user) -> str:
    """Форматировать статус подписки пользователя."""
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

    return status_text
