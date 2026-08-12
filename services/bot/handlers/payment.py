"""
Payment handlers — обработчики для оплаты подписок.

Обработчики для:
- successful_payment — успешная оплата
- pre_checkout_query — проверка перед оплатой
- invoice — ответы на инвойсы
"""

import logging
from aiogram import F, Router
from aiogram.types import PreCheckoutQuery, Message, LabeledPrice
from aiogram.filters import ExceptionTypeFilter

from services.bot.handlers.router import admin  # Используем тот же роутер

logger = logging.getLogger(__name__)

router = Router(name='payment')


@admin.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    """
    Обработчик pre_checkout_query — проверка перед оплатой.

    Telegram отправляет этот запрос перед тем, как пользователь введёт данные карты.
    """
    from services.payment import get_payment_service

    payment_service = get_payment_service()

    try:
        # Для Telegram Stars используем специальный метод
        if payment_service.provider_name == 'telegram_stars':
            from services.payment.telegram_stars_provider import TelegramStarsProvider
            provider = payment_service._provider
            if isinstance(provider, TelegramStarsProvider):
                await provider.handle_pre_checkout_query(
                    pre_checkout_query_id=pre_checkout_query.id,
                    payload=pre_checkout_query.invoice_payload,
                    user_id=pre_checkout_query.from_user.id,
                )
                return

        # Для других провайдеров просто подтверждаем
        await pre_checkout_query.answer(ok=True)
        logger.info(f"✅ Pre-checkout разрешён: {pre_checkout_query.id}")

    except Exception as e:
        logger.error(f"Ошибка pre-checkout: {e}", exc_info=True)
        await pre_checkout_query.answer(ok=False, error_message="Ошибка оплаты. Попробуйте позже.")


@admin.message(F.successful_payment)
async def process_successful_payment(message: Message):
    """
    Обработчик successful_payment — успешная оплата подписки.

    Оформляет подписку после успешной оплаты.
    """
    from services.payment import get_payment_service, PaymentStatus
    from database import RepositoryFactory
    from database.repositories.users import UserRepository
    from services.database import get_database_service
    from datetime import datetime, timedelta
    import json

    try:
        successful_payment = message.successful_payment

        # Парсим payload из инвойса
        payload = json.loads(successful_payment.invoice_payload)
        payment_id = payload.get('payment_id')
        duration_days = payload.get('duration_days', 30)
        user_id = message.from_user.id

        logger.info(
            f"💰 Успешная оплата: payment_id={payment_id}, "
            f"user_id={user_id}, duration={duration_days} дней"
        )

        # Получаем платёжный сервис
        payment_service = get_payment_service()

        # Если это Telegram Stars, обрабатываем через провайдер
        if payment_service.provider_name == 'telegram_stars':
            from services.payment.telegram_stars_provider import TelegramStarsProvider
            provider = payment_service._provider
            if isinstance(provider, TelegramStarsProvider):
                payment_data = await provider.handle_successful_payment(
                    payment_data={
                        'invoice_payload': successful_payment.invoice_payload,
                        'total_amount': successful_payment.total_amount,
                    },
                    user_id=user_id,
                )

                if payment_data:
                    # Оформляем подписку через сервис
                    await payment_service.handle_payment_success(payment_data)

        # Оформляем подписку
        async with get_database_service().session_context() as session:
            user_repo = UserRepository(session)

            now = datetime.now()

            # Проверяем текущую подписку
            user = await user_repo.get_by_telegram_id(user_id)

            # Нормализуем пустую строку в None
            subscription_ends_at = user.subscription_ends_at if user else None
            if subscription_ends_at == '':
                subscription_ends_at = None

            if user and subscription_ends_at and subscription_ends_at > now:
                # Если уже есть подписка — продлеваем от текущей даты окончания
                ends_at = subscription_ends_at + timedelta(days=duration_days)
            else:
                # Новая подписка
                ends_at = now + timedelta(days=duration_days)

            await user_repo.update_subscription(
                telegram_id=user_id,
                has_subscription=True,
                started_at=now,
                ends_at=ends_at,
            )

        # Отправляем подтверждение пользователю
        await message.answer(
            f"✅ **Подписка оформлена!**\n\n"
            f"📅 Длительность: **{duration_days} дней**\n"
            f"💰 Оплачено: **{successful_payment.total_amount} {successful_payment.currency}**\n"
            f"📅 Действует до: **{ends_at.strftime('%d.%m.%Y')}**\n\n"
            f"Спасибо за покупку! 🎉\n\n"
            f"Теперь у вас есть доступ ко всем функциям бота.",
            parse_mode='Markdown'
        )

        logger.info(f"✅ Подписка оформлена: user_id={user_id}, payment_id={payment_id}")

    except Exception as e:
        logger.error(f"Ошибка обработки успешной оплаты: {e}", exc_info=True)
        await message.answer(
            f"⚠️ Оплата прошла, но возникла ошибка при оформлении подписки.\n\n"
            f"Пожалуйста, обратитесь в поддержку с ID платежа.\n\n"
            f"Детали: {str(e)[:200]}",
            parse_mode='Markdown'
        )


@admin.message(F.text == '💳 Оформить подписку')
async def start_subscription_payment(message: Message):
    """
    Команда для начала оформления подписки.

    Создаёт инвойс для оплаты.
    """
    from services.payment import get_payment_service
    from database import RepositoryFactory
    from database.repositories.users import UserRepository
    from services.database import get_database_service

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        user_repo = factory.users()

        user = await user_repo.get_by_telegram_id(message.from_user.id)

        if not user:
            await message.answer('❌ Пользователь не найден. Нажмите /start')
            return

        if user.has_active_subscription:
            await message.answer(
                '✅ У вас уже есть активная подписка.\n\n'
                'Для продления выберите "Продлить подписку" в меню.'
            )
            return

        # Создаём платёж
        payment_service = get_payment_service()

        try:
            payment_link = await payment_service.create_subscription_payment(
                user_id=message.from_user.id,
                duration_days=30,
                amount=99.0,
            )

            # Для Telegram Stars отправляем инвойс напрямую
            if payment_service.provider_name == 'telegram_stars':
                await _send_stars_invoice(message, payment_link)
            else:
                # Для других провайдеров отправляем ссылку
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text='💳 Оплатить', url=payment_link.url)],
                    ]
                )

                await message.answer(
                    f'💳 **Оформление подписки**\n\n'
                    f'📅 Длительность: **30 дней**\n'
                    f'💰 Стоимость: **99₽**\n\n'
                    f'Нажмите кнопку для оплаты.',
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )

        except Exception as e:
            logger.error(f"Ошибка создания платежа: {e}", exc_info=True)
            await message.answer('❌ Ошибка создания счёта. Попробуйте позже.')


async def _send_stars_invoice(message: Message, payment_link):
    """Отправить инвойс Telegram Stars."""
    from aiogram.types import LabeledPrice

    # Парсим payment_id из payment_link
    # В реальном приложении нужно хранить маппинг payment_id -> параметры
    duration_days = 30
    stars_price = 50  # Цена в звёздах (настраивается)

    await message.answer_invoice(
        title=f"Подписка на {duration_days} дней",
        description="Премиум подписка на новости",
        payload=f'{{"payment_id": "{payment_link.payment_id}", "duration": {duration_days}}}',
        provider_token='',  # Пустой для Stars
        currency='XTR',  # Telegram Stars
        prices=[LabeledPrice(label='Подписка', amount=stars_price)],
        max_tip_amount=0,
        needs_name=False,
        needs_phone_number=False,
        needs_email=False,
        needs_shipping_address=False,
    )
