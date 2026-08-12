"""
Telegram Connection Service — подключение и авторизация в Telegram.

Изолирует логику подключения от ListenerBot.
"""

import logging
from typing import Optional, List

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from config.settings import settings

logger = logging.getLogger(__name__)


class TelegramConnectionService:
    """
    Сервис для подключения и авторизации в Telegram.

    Attributes:
        client: Telethon клиент
        is_connected: Флаг подключения
    """

    def __init__(
        self,
        session_name: str = 'userbot',
        connection_retries: int = 10,
        retry_delay: int = 5,
        timeout: int = 30,
    ) -> None:
        """
        Инициализация сервиса подключения.

        Args:
            session_name: Имя сессии
            connection_retries: Количество попыток подключения
            retry_delay: Задержка между попытками
            timeout: Таймаут подключения
        """
        self.client = TelegramClient(
            session_name,
            api_id=settings.api_id,
            api_hash=settings.api_hash,
            connection_retries=connection_retries,
            retry_delay=retry_delay,
            timeout=timeout,
            use_ipv6=False
        )
        self.is_connected = False

    async def connect(self) -> bool:
        """
        Подключиться к Telegram.

        Returns:
            True если подключено, False иначе
        """
        try:
            logger.info("🔌 Подключение к Telegram...")
            await self.client.connect()
            self.is_connected = True
            logger.info("✅ Подключение успешно")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return False

    async def disconnect(self) -> None:
        """Отключиться от Telegram."""
        if self.is_connected:
            await self.client.disconnect()
            self.is_connected = False
            logger.info("👋 Отключено от Telegram")

    async def is_authorized(self) -> bool:
        """
        Проверить авторизацию.

        Returns:
            True если авторизован, False иначе
        """
        return await self.client.is_user_authorized()

    async def authorize(self) -> bool:
        """
        Пройти авторизацию.

        Returns:
            True если авторизован, False иначе
        """
        if not self.is_connected:
            await self.connect()

        if await self.is_authorized():
            return True

        logger.warning("⚠️ Требуется авторизация! Введите код из Telegram.")

        try:
            await self.client.send_code_request(settings.phone_number)
            code = input('Enter the code: ')

            try:
                await self.client.sign_in(settings.phone_number, code)
            except SessionPasswordNeededError:
                password = input('Password: ')
                await self.client.sign_in(password=password)

            logger.info("✅ Авторизация успешна")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка авторизации: {e}")
            return False

    async def get_me(self) -> Optional[dict]:
        """
        Получить информацию о текущем пользователе.

        Returns:
            dict с информацией или None
        """
        try:
            me = await self.client.get_me()
            return {
                'id': me.id,
                'username': me.username,
                'first_name': me.first_name,
                'last_name': me.last_name,
            }
        except Exception as e:
            logger.error(f"Ошибка получения информации о пользователе: {e}")
            return None

    def add_event_handler(self, handler, event) -> None:
        """
        Добавить обработчик событий.

        Args:
            handler: Функция-обработчик
            event: Тип события
        """
        self.client.add_event_handler(handler, event)

    def remove_event_handler(self, handler) -> None:
        """
        Удалить обработчик событий.

        Args:
            handler: Функция-обработчик
        """
        self.client.remove_event_handler(handler)

    async def get_dialogs(self) -> List:
        """
        Получить список диалогов.

        Returns:
            Список диалогов
        """
        return await self.client.get_dialogs()
