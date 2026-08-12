"""
Платёжный сервис — модуль для обработки оплат подписок.

Поддерживаемые провайдеры:
- test — тестовый режим (бесплатно, для разработки)
- yookassa — ЮKassa (для продакшена)
- telegram_stars — Telegram Stars (нативная оплата в Telegram)
"""

from services.payment.abstractions import (
    PaymentProvider,
    PaymentLink,
    PaymentData,
    PaymentStatus,
    PaymentError,
)
from services.payment.test_provider import TestPaymentProvider
from services.payment.telegram_stars_provider import TelegramStarsProvider

from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class PaymentService:
    """
    Сервис обработки платежей.

    Делегирует операции конкретному платёжному провайдеру.
    """

    def __init__(self, provider: PaymentProvider) -> None:
        """
        Инициализация сервиса.

        Args:
            provider: Платёжный провайдер
        """
        self._provider = provider
        logger.info(f"✅ PaymentService инициализирован с провайдером: {provider.name}")

    @property
    def provider_name(self) -> str:
        """Получить название текущего провайдера."""
        return self._provider.name

    async def create_subscription_payment(
        self,
        user_id: int,
        duration_days: int = 30,
        amount: float = 99.0,
        currency: str = 'RUB',
    ) -> PaymentLink:
        """
        Создать платёж для оформления подписки.

        Args:
            user_id: Telegram ID пользователя
            duration_days: Длительность подписки в днях
            amount: Сумма
            currency: Валюта

        Returns:
            PaymentLink со ссылкой на оплату
        """
        description = f"Подписка на {duration_days} дней"

        return await self._provider.create_payment(
            user_id=user_id,
            amount=amount,
            description=description,
            metadata={
                'type': 'subscription',
                'duration_days': duration_days,
            }
        )

    async def get_payment_status(self, payment_id: str) -> PaymentData:
        """Получить статус платежа."""
        return await self._provider.get_payment_status(payment_id)

    async def handle_payment_success(self, payment_data: PaymentData) -> bool:
        """
        Обработать успешный платёж — оформить подписку.

        Args:
            payment_data: Данные платежа

        Returns:
            True если подписка оформлена успешно
        """
        if payment_data.status != PaymentStatus.SUCCEEDED:
            logger.warning(f"Попытка оформить подписку для неуспешного платежа: {payment_data.payment_id}")
            return False

        user_id = payment_data.metadata.get('user_id')
        if not user_id:
            logger.error(f"Не указан user_id в метаданных платежа: {payment_data.payment_id}")
            return False

        duration_days = payment_data.metadata.get('duration_days', 30)

        # Оформляем подписку через UserRepository
        from datetime import datetime, timedelta
        from database.repositories.users import UserRepository
        from services.database import get_database_service

        async with get_database_service().session_context() as session:
            user_repo = UserRepository(session)

            now = datetime.now()
            ends_at = now + timedelta(days=duration_days)

            # Если уже есть подписка — продлеваем от текущей даты окончания
            user = await user_repo.get_by_telegram_id(user_id)

            # Нормализуем пустую строку в None
            subscription_ends_at = user.subscription_ends_at if user else None
            if subscription_ends_at == '':
                subscription_ends_at = None

            if user and subscription_ends_at and subscription_ends_at > now:
                ends_at = subscription_ends_at + timedelta(days=duration_days)

            await user_repo.update_subscription(
                telegram_id=user_id,
                has_subscription=True,
                started_at=now,
                ends_at=ends_at,
            )

        logger.info(
            f"✅ Подписка оформлена: user_id={user_id}, "
            f"duration={duration_days} дней, payment_id={payment_data.payment_id}"
        )

        return True

    async def refund(self, payment_id: str, reason: str = '') -> bool:
        """Вернуть платёж."""
        return await self._provider.refund_payment(payment_id, reason=reason)

    async def handle_webhook(self, payload: Dict[str, Any]) -> Optional[PaymentData]:
        """Обработать вебхук от платёжной системы."""
        return await self._provider.handle_webhook(payload)


# Глобальный экземпляр сервиса
_payment_service: Optional[PaymentService] = None


def get_payment_service() -> PaymentService:
    """
    Получить глобальный платёжный сервис.

    Returns:
        PaymentService экземпляр
    """
    global _payment_service
    if _payment_service is None:
        # Используем тестовый провайдер по умолчанию
        # Для продакшена заменить на TelegramStarsProvider() или YooKassaProvider()
        provider = TestPaymentProvider()
        _payment_service = PaymentService(provider)
    return _payment_service


def init_payment_service(
    provider_name: str = 'test',
    bot: Optional[Any] = None,
) -> PaymentService:
    """
    Инициализировать платёжный сервис с указанным провайдером.

    Args:
        provider_name: Название провайдера ('test', 'telegram_stars')
        bot: aiogram Bot экземпляр (требуется для telegram_stars)

    Returns:
        PaymentService экземпляр
    """
    global _payment_service

    providers: Dict[str, PaymentProvider] = {
        'test': TestPaymentProvider(),
        'telegram_stars': TelegramStarsProvider(bot=bot),
    }

    if provider_name not in providers:
        raise ValueError(f"Неизвестный провайдер: {provider_name}. Доступные: {list(providers.keys())}")

    _payment_service = PaymentService(providers[provider_name])
    return _payment_service


def reset_payment_service() -> None:
    """Сбросить сервис (для тестов)."""
    global _payment_service
    _payment_service = None
