"""
Тесты для Payment Service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.payment.service import PaymentService
from services.payment.test_provider import TestPaymentProvider
from services.payment.abstractions import PaymentLink, PaymentData, PaymentStatus


class TestTestPaymentProvider:
    """Тесты для TestPaymentProvider."""

    @pytest.mark.asyncio
    async def test_create_payment(self):
        """Проверка создания платежа в тестовом провайдере."""
        provider = TestPaymentProvider()

        link = await provider.create_payment(
            user_id=12345,
            amount=99.0,
            description='Тестовая оплата',
        )

        assert link is not None
        assert link.payment_id.startswith('test_')

    @pytest.mark.asyncio
    async def test_get_payment_status(self):
        """Проверка получения статуса платежа."""
        provider = TestPaymentProvider()

        # Сначала создадим платёж
        link = await provider.create_payment(
            user_id=12345,
            amount=99.0,
            description='Тест',
        )

        # Теперь получим статус (возвращает PaymentData)
        payment_data = await provider.get_payment_status(link.payment_id)

        assert payment_data.status == PaymentStatus.SUCCEEDED
