"""
Платёжный модуль для обработки оплат подписок.

Поддерживаемые провайдеры:
- test — тестовый режим (бесплатно, для разработки)
- telegram_stars — Telegram Stars (нативная оплата в Telegram)

Пример использования:
    from services.payment import get_payment_service

    payment_service = get_payment_service()
    payment_link = await payment_service.create_subscription_payment(
        user_id=user_id,
        duration_days=30,
        amount=99.0,
    )
    # Отправить payment_link.url пользователю
"""

from services.payment.abstractions import (
    PaymentProvider,
    PaymentLink,
    PaymentData,
    PaymentStatus,
    PaymentError,
)
from services.payment.service import (
    PaymentService,
    get_payment_service,
    init_payment_service,
    reset_payment_service,
)

__all__ = [
    # Абстракции
    'PaymentProvider',
    'PaymentLink',
    'PaymentData',
    'PaymentStatus',
    'PaymentError',
    # Сервис
    'PaymentService',
    'get_payment_service',
    'init_payment_service',
    'reset_payment_service',
]
