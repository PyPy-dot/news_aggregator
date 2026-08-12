"""
Publisher Service — публикация новостей в Telegram каналы.

Использует aiogram Bot для отправки постов в каналы публикации.
"""

import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)


class PublisherService:
    """
    Сервис для публикации новостей в Telegram каналы.

    Attributes:
        _bot: aiogram Bot для отправки сообщений
    """

    def __init__(self, bot: Optional[Bot] = None) -> None:
        """
        Инициализация сервиса публикации.

        Args:
            bot: aiogram Bot экземпляр для отправки
        """
        self._bot = bot

    @property
    def bot(self) -> Optional[Bot]:
        """Получить бота."""
        return self._bot

    async def publish_to_channel(
        self,
        channel_id: int,
        text: str,
        parse_mode: str = 'HTML'
    ) -> bool:
        """
        Опубликовать сообщение в Telegram канал.

        Args:
            channel_id: Telegram ID канала (может быть отрицательным для супергрупп)
            text: Текст сообщения
            parse_mode: Режим парсинга ('HTML' или 'Markdown')

        Returns:
            True если опубликовано успешно, False иначе
        """
        if not self._bot:
            logger.error("❌ PublisherService: Bot не инициализирован")
            return False

        try:
            # Для каналов/супергрупп ID обычно отрицательный и начинается с -100
            # Если передан положительный ID, конвертируем в формат супергруппы
            if channel_id > 0:
                # Преобразуем в формат ID супергруппы
                target_id = -1000000000000 + channel_id
            else:
                target_id = channel_id

            await self._bot.send_message(
                chat_id=target_id,
                text=text,
                parse_mode=parse_mode
            )

            logger.info(f"✅ Опубликовано в канал ID={channel_id} (target={target_id})")
            return True

        except TelegramAPIError as e:
            logger.error(
                f"❌ Ошибка Telegram API при публикации в канал ID={channel_id}: {e}"
            )
            return False
        except Exception as e:
            logger.error(
                f"❌ Неожиданная ошибка при публикации в канал ID={channel_id}: {e}",
                exc_info=True
            )
            return False
