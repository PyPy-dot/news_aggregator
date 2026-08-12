"""
Хендлеры для управления подпиской (Telegram Stars).

Интеграция с Telegram Payments для покупки подписки.
"""

import logging
from datetime import datetime, timedelta
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

from services.bot.handlers.router import admin
from services.bot.handlers.keyboards import user_kb, get_user_kb_for_role
from services.bot.handlers.states import UserPreferencesStates
from services.bot.handlers.access import is_admin

from database import RepositoryFactory
from database.repositories.users import UserRepository
from services.database import get_database_service

logger = logging.getLogger(__name__)

# Тарифы подписки (в звёздах Telegram)
SUBSCRIPTION_TARIFFS = {
    '1_month': {
        'name': '1 месяц',
        'stars': 99,
        'duration_days': 30,
    },
    '3_months': {
        'name': '3 месяца',
        'stars': 249,
        'duration_days': 90,
    },
    '12_months': {
        'name': '12 месяцев',
        'stars': 799,
        'duration_days': 365,
    },
}


@admin.message(Command('subscription'))
@admin.message(F.text == '💎 Подписка')
async def subscription_menu(message: Message):
    """
    Показать меню с тарифами подписки.
    """
    from services.bot.handlers.keyboards import create_subscription_tariffs_kb

    # Проверяем текущий статус подписки пользователя
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        user_repo = factory.users()
        user = await user_repo.get_by_telegram_id(message.from_user.id)

    if user and user.has_subscription:
        # Нормализуем пустую строку в None
        subscription_ends_at = user.subscription_ends_at
        if subscription_ends_at == '':
            subscription_ends_at = None

        if subscription_ends_at:
            ends_at = subscription_ends_at
            days_left = (ends_at - datetime.now()).days
            status = f"📅 Подписка активна до {ends_at.strftime('%d.%m.%Y')} ({days_left} дн.)"
        else:
            status = "♾️ Подписка активна (бессрочно)"
    else:
        status = "❌ Подписка не оформлена"

    await message.answer(
        f"💎 <b>Подписка на новости</b>\n\n"
        f"Ваш статус: {status}\n\n"
        f"<b>Тарифы:</b>\n"
        f"• 1 месяц — 99 ⭐️\n"
        f"• 3 месяца — 249 ⭐️ (выгода 23%)\n"
        f"• 12 месяцев — 799 ⭐️ (выгода 33%)\n\n"
        f"Подписка даёт доступ к:\n"
        f"✅ Персональной ленте новостей\n"
        f"✅ Уведомлениям по предпочтениям\n"
        f"✅ Доступу к эксклюзивному контенту\n\n"
        f"Выберите тариф для оплаты:",
        parse_mode='HTML',
        reply_markup=create_subscription_tariffs_kb()
    )


def create_subscription_tariffs_kb() -> 'InlineKeyboardMarkup':
    """Создать клавиатуру с тарифами подписки."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    buttons = []
    for tariff_id, tariff in SUBSCRIPTION_TARIFFS.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"{tariff['name']} — {tariff['stars']} ⭐️",
                callback_data=f'subscription_pay_{tariff_id}'
            )
        ])

    buttons.append([
        InlineKeyboardButton(text='🔙 Назад в меню', callback_data='back_to_user_menu')
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@admin.callback_query(F.data.startswith('subscription_pay_'))
async def subscription_pay_callback(callback: CallbackQuery):
    """
    Обработка выбора тарифа — выставление счёта.
    """
    tariff_id = callback.data.replace('subscription_pay_', '')

    if tariff_id not in SUBSCRIPTION_TARIFFS:
        await callback.answer('❌ Неверный тариф', show_alert=True)
        return

    tariff = SUBSCRIPTION_TARIFFS[tariff_id]

    # Проверяем, не админ ли пользователь (админам подписка не нужна)
    if await is_admin(callback.from_user.id):
        await callback.answer(
            'ℹ️ Администраторам подписка доступна бесплатно',
            show_alert=True
        )
        return

    await callback.answer()

    # Создаём счёт через Telegram Stars
    # Для Stars используется валюта "XTR" и цена в звёздах
    await callback.message.answer_invoice(
        title=f"Подписка на новости ({tariff['name']})",
        description=f"Доступ к персональной ленте новостей на {tariff['duration_days']} дн.",
        prices=[
            LabeledPrice(label=f"{tariff['name']}", amount=tariff['stars'])
        ],
        provider_token='',  # Для Stars не требуется
        payload=f'subscription_{tariff_id}_{callback.from_user.id}',
        currency='XTR',  # Telegram Stars
        is_flexible=False,
    )


@admin.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: PreCheckoutQuery):
    """
    Обработка pre-checkout query — подтверждаем оплату.
    """
    # Проверяем payload
    payload = pre_checkout_query.invoice_payload
    if not payload.startswith('subscription_'):
        await pre_checkout_query.answer(ok=False, error_message='❌ Неверный тип оплаты')
        return

    # Подтверждаем
    await pre_checkout_query.answer(ok=True)
    logger.info(f"✅ Pre-checkout подтверждён для {pre_checkout_query.from_user.id}")


@admin.message(F.successful_payment)
async def successful_payment_handler(message: Message, state: FSMContext):
    """
    Обработка успешной оплаты подписки.
    """
    payment = message.successful_payment

    # Парсим payload
    # Формат: subscription_<tariff_id>_<user_id>
    payload_parts = payment.invoice_payload.split('_')
    if len(payload_parts) < 3:
        await message.answer('❌ Ошибка обработки платежа. Обратитесь к администратору.')
        return

    tariff_id = payload_parts[1]

    if tariff_id not in SUBSCRIPTION_TARIFFS:
        await message.answer('❌ Неверный тариф. Обратитесь к администратору.')
        return

    tariff = SUBSCRIPTION_TARIFFS[tariff_id]
    stars_paid = payment.total_amount  # Количество звёзд

    # Обновляем подписку пользователя
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        user_repo = factory.users()

        user = await user_repo.get_by_telegram_id(message.from_user.id)
        if not user:
            # Создаём нового пользователя
            user = await user_repo.create_user(
                telegram_id=message.from_user.id,
                role='user'
            )

        # Рассчитываем дату окончания
        now = datetime.now()

        # Нормализуем subscription_ends_at (пустая строка → None)
        subscription_ends_at = user.subscription_ends_at
        if subscription_ends_at == '':
            subscription_ends_at = None

        if user.has_subscription and subscription_ends_at and subscription_ends_at > now:
            # Если подписка уже активна, продлеваем от текущей даты окончания
            starts_at = subscription_ends_at
        else:
            starts_at = now

        ends_at = starts_at + timedelta(days=tariff['duration_days'])

        # Обновляем подписку
        await user_repo.update_subscription(
            telegram_id=message.from_user.id,
            has_subscription=True,
            started_at=starts_at,
            ends_at=ends_at,
        )

    # Получаем клавиатуру с учётом роли пользователя и подписки
    is_admin_user = await is_admin(message.from_user.id)
    keyboard = get_user_kb_for_role(is_admin_user, has_subscription=True)

    await message.answer(
        f"✅ <b>Подписка оформлена!</b>\n\n"
        f"Тариф: {tariff['name']}\n"
        f"Оплачено: {stars_paid} ⭐️\n"
        f"Действует до: {ends_at.strftime('%d.%m.%Y')}\n\n"
        f"Теперь вы получаете:\n"
        f"✅ Персональную ленту новостей\n"
        f"✅ Уведомления по вашим предпочтениям\n\n"
        f"Настройте предпочтения в меню /categories и /tags",
        parse_mode='HTML',
        reply_markup=keyboard
    )

    logger.info(
        f"💎 Подписка оформлена: user={message.from_user.id}, "
        f"tariff={tariff_id}, stars={stars_paid}, ends={ends_at}"
    )


@admin.callback_query(F.data == 'back_to_user_menu')
async def back_to_user_menu_from_subscription(callback: CallbackQuery, state: FSMContext):
    """Вернуться в главное меню пользователя из меню подписки."""
    await callback.answer()
    await state.clear()

    await callback.message.delete()

    # Получаем клавиатуру с учётом роли и подписки пользователя
    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        is_admin_user = user and user.role == 'admin'
        has_subscription = user.has_active_subscription if user else False

    keyboard = get_user_kb_for_role(is_admin_user, has_subscription)

    await callback.message.answer(
        '👋 Главное меню',
        reply_markup=keyboard
    )
