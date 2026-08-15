"""
Telegram Stars Payment Provider.

Нативная оплата в Telegram через звёзды (Stars).
1 звезда ≈ 1.5-2 рубля (курс устанавливается Telegram).

Для подключения:
1. Настроить бота в @BotFather
2. Включить платежи в настройках бота
3. Использовать метод sendInvoice для выставления счёта
"""

from services.payment.abstractions import (
    PaymentProvider,
    PaymentLink,
    PaymentData,
    PaymentStatus,
    PaymentError,
)
from typing import Optional, Dict, Any
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class StarsProduct:
    """Товар для оплаты звёздами."""
    title: str
    description: str
    price_stars: int  # Цена в звёздах


class TelegramStarsProvider(PaymentProvider):
    """
    Платёжный провайдер Telegram Stars.

    Использует нативный механизм оплаты Telegram через инвойсы.
    """

    # Тарифы в звёздах (примерные, можно настроить)
    PRICE_STARS_PER_MONTH = 50  # ~75-100 рублей за месяц

    def __init__(self, bot: Optional[Any] = None) -> None:
        """
        Инициализация провайдера.

        Args:
            bot: aiogram Bot экземпляр для отправки инвойсов
        """
        self._bot = bot

    @property
    def name(self) -> str:
        return 'telegram_stars'

    @property
    def bot(self) -> Optional[Any]:
        """Получить экземпляр бота."""
        return self._bot

    def _get_stars_price(self, duration_days: int) -> int:
        """Рассчитать цену в звёздах на основе длительности."""
        months = max(1, duration_days // 30)
        return months * self.PRICE_STARS_PER_MONTH

    async def create_payment(
        self,
        user_id: int,
        amount: float,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentLink:
        """
        Создать инвойс для оплаты звёздами.

        Args:
            user_id: Telegram ID пользователя
            amount: Сумма в рублях (конвертируется в звёзды)
            description: Описание
            metadata: Дополнительные данные

        Returns:
            PaymentLink с ссылкой на оплату
        """
        if not self._bot:
            raise PaymentError("Бот не инициализирован")

        duration_days = (metadata or {}).get('duration_days', 30)
        stars_price = self._get_stars_price(duration_days)

        payment_id = f"stars_{user_id}_{duration_days}"

        # Создаём инвойс через Telegram Bot API
        try:
            from aiogram.types import LabeledPrice

            # Формируем цены
            prices = [
                LabeledPrice(
                    label=description,
                    amount=stars_price  # В звёздах
                )
            ]

            # Генерируем payload для отслеживания
            import json
            payload_data = {
                'user_id': user_id,
                'duration_days': duration_days,
                'payment_id': payment_id,
            }
            payload = json.dumps(payload_data)

            # Создаём ссылку на инвойс
            # Для отправки используем sendInvoice, для ссылки — createInvoiceLink
            invoice_link = await self._bot.create_invoice_link(
                title=f"Подписка ({duration_days} дней)",
                description=description,
                payload=payload,
                provider_token='',  # Пустой для Telegram Stars
                currency='XTR',  # Telegram Stars
                prices=prices,
                max_tip_amount=0,  # Без чаевых
                needs_name=False,
                needs_phone_number=False,
                needs_email=False,
                needs_shipping_address=False,
            )

            logger.info(
                f"⭐ Инвойс создан: {payment_id}, "
                f"user={user_id}, stars={stars_price}"
            )

            return PaymentLink(
                payment_id=payment_id,
                url=invoice_link,
                expires_at=None,
            )

        except Exception as e:
            logger.error(f"Ошибка создания инвойса: {e}")
            raise PaymentError(f"Не удалось создать инвойс: {e}")

    async def get_payment_status(self, payment_id: str) -> PaymentData:
        """
        Получить статус платежа.

        В Telegram Stars статус определяется через успешную оплату инвойса.
        """
        # В Stars мы не можем проверить статус до оплаты
        # Статус становится известен только после pre_checkout_query или successful_payment
        raise NotImplementedError(
            "Статус платежа в Telegram Stars проверяется через вебхуки"
        )

    async def refund_payment(
        self,
        payment_id: str,
        amount: Optional[float] = None,
        reason: str = '',
    ) -> bool:
        """
        Вернуть платёж.

        Telegram Stars не поддерживает автоматические возвраты.
        Требуется ручное вмешательство через @BotFather.
        """
        logger.warning(
            f"Возврат в Telegram Stars не поддерживается автоматически. "
            f"payment_id={payment_id}, reason={reason}"
        )
        return False

    async def handle_pre_checkout_query(
        self,
        pre_checkout_query_id: str,
        payload: str,
        user_id: int,
    ) -> bool:
        """
        Обработать запрос на проверку оплаты (pre_checkout_query).

        Args:
            pre_checkout_query_id: ID запроса
            payload: Payload из инвойса
            user_id: ID пользователя

        Returns:
            True если оплата разрешена
        """
        try:
            # Разрешаем оплату
            await self._bot.answer_pre_checkout_query(
                pre_checkout_query_id=pre_checkout_query_id,
                ok=True,
            )
            logger.info(f"✅ Pre-checkout разрешён: {pre_checkout_query_id}")
            return True

        except Exception as e:
            logger.error(f"Ошибка pre-checkout: {e}")
            return False

    async def handle_successful_payment(
        self,
        payment_data: Dict[str, Any],
        user_id: int,
    ) -> Optional[PaymentData]:
        """
        Обработать успешный платёж (successful_payment).

        Args:
            payment_data: Данные платежа из Telegram
            user_id: ID пользователя

        Returns:
            PaymentData если платёж успешен
        """
        import json

        try:
            # Парсим payload
            payload = json.loads(payment_data.get('invoice_payload', '{}'))
            payment_id = payload.get('payment_id', f'stars_{user_id}')
            duration_days = payload.get('duration_days', 30)
            stars_paid = payment_data.get('total_amount', 0)

            logger.info(
                f"✅ Успешная оплата: {payment_id}, "
                f"user={user_id}, stars={stars_paid}"
            )

            return PaymentData(
                payment_id=payment_id,
                user_id=user_id,
                amount=stars_paid,  # В звёздах
                currency='XTR',
                description=f"Подписка на {duration_days} дней",
                status=PaymentStatus.SUCCEEDED,
                metadata={
                    'duration_days': duration_days,
                    'stars_paid': stars_paid,
                }
            )

        except Exception as e:
            logger.error(f"Ошибка обработки успешного платежа: {e}")
            return None

    async def handle_webhook(self, payload: Dict[str, Any]) -> Optional[PaymentData]:
        """Вебхуки обрабатываются через handle_successful_payment."""
        return None
