"""
Тестовый платёжный провайдер.

Используется для разработки и тестирования.
Создаёт "платежи" без реального списания средств.
"""

from services.payment.abstractions import (
    PaymentProvider,
    PaymentLink,
    PaymentData,
    PaymentStatus,
)
from typing import Optional, Dict, Any
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class TestPaymentProvider(PaymentProvider):
    """Тестовый провайдер для разработки."""

    @property
    def name(self) -> str:
        return 'test'

    # Хранилище платежей в памяти
    _payments: Dict[str, PaymentData] = {}

    async def create_payment(
        self,
        user_id: int,
        amount: float,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentLink:
        """
        Создать тестовый платёж.

        В тестовом режиме платёж автоматически считается успешным.
        """
        payment_id = f"test_{user_id}_{int(datetime.now().timestamp())}"

        # Создаём данные платежа
        payment_data = PaymentData(
            payment_id=payment_id,
            user_id=user_id,
            amount=amount,
            currency='RUB',
            description=description,
            status=PaymentStatus.SUCCEEDED,  # Автоматически успешен
            metadata={
                **(metadata or {}),
                'user_id': user_id,
            }
        )

        # Сохраняем в "базу"
        self._payments[payment_id] = payment_data

        logger.info(
            f"🧪 [TEST] Платёж создан: {payment_id}, "
            f"user={user_id}, amount={amount}, status=SUCCESS"
        )

        # Возвращаем "ссылку" (в тестовом режиме это просто заглушка)
        return PaymentLink(
            payment_id=payment_id,
            url=f"https://test.payment/confirm/{payment_id}",
            expires_at=None,
        )

    async def get_payment_status(self, payment_id: str) -> PaymentData:
        """Получить статус платежа."""
        if payment_id not in self._payments:
            raise ValueError(f"Платёж не найден: {payment_id}")

        return self._payments[payment_id]

    async def refund_payment(
        self,
        payment_id: str,
        amount: Optional[float] = None,
        reason: str = '',
    ) -> bool:
        """Вернуть тестовый платёж."""
        if payment_id not in self._payments:
            return False

        self._payments[payment_id] = self._payments[payment_id].__class__(
            **self._payments[payment_id].__dict__,
            status=PaymentStatus.REFUNDED
        )

        logger.info(f"🧪 [TEST] Платёж возвращён: {payment_id}, reason={reason}")
        return True

    async def handle_webhook(self, payload: Dict[str, Any]) -> Optional[PaymentData]:
        """Вебхуки не поддерживаются в тестовом режиме."""
        logger.debug("🧪 [TEST] Вебхук получен (игнорируется)")
        return None
