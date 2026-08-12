"""
Абстракции платёжного сервиса.

Позволяет легко переключаться между платёжными системами:
- ЮKassa
- CloudPayments
- Robokassa
- Telegram Stars (нативная оплата в Telegram)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum


class PaymentStatus(Enum):
    """Статус платежа."""
    PENDING = 'pending'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    REFUNDED = 'refunded'


@dataclass
class PaymentData:
    """Данные платежа."""
    payment_id: str  # ID платежа в платёжной системе
    user_id: int  # Telegram ID пользователя
    amount: float  # Сумма
    currency: str  # Валюта (RUB, USD, ...)
    description: str  # Описание
    status: PaymentStatus  # Статус
    metadata: Dict[str, Any]  # Дополнительные данные


@dataclass
class PaymentLink:
    """Ссылка на оплату."""
    payment_id: str  # ID платежа для отслеживания
    url: str  # URL для оплаты
    expires_at: Optional[str] = None  # Время истечения (ISO 8601)


class PaymentProvider(ABC):
    """
    Абстрактный базовый класс для платёжных провайдеров.

    Определяет интерфейс для всех реализаций.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Название платёжной системы."""
        pass

    @abstractmethod
    async def create_payment(
        self,
        user_id: int,
        amount: float,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentLink:
        """
        Создать платёж.

        Args:
            user_id: ID пользователя
            amount: Сумма платежа
            description: Описание
            metadata: Дополнительные данные

        Returns:
            PaymentLink со ссылкой на оплату
        """
        pass

    @abstractmethod
    async def get_payment_status(self, payment_id: str) -> PaymentData:
        """
        Получить статус платежа.

        Args:
            payment_id: ID платежа

        Returns:
            PaymentData со статусом
        """
        pass

    @abstractmethod
    async def refund_payment(
        self,
        payment_id: str,
        amount: Optional[float] = None,
        reason: str = '',
    ) -> bool:
        """
        Вернуть платёж.

        Args:
            payment_id: ID платежа
            amount: Сумма возврата (None = полный)
            reason: Причина

        Returns:
            True если возврат успешен
        """
        pass

    @abstractmethod
    async def handle_webhook(self, payload: Dict[str, Any]) -> Optional[PaymentData]:
        """
        Обработать вебхук от платёжной системы.

        Args:
            payload: Данные вебхука

        Returns:
            PaymentData если это статус платежа, иначе None
        """
        pass


class PaymentError(Exception):
    """Ошибка платёжного сервиса."""
    pass
