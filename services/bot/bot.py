"""
Admin Bot — Telegram бот для управления и модерации.

Использует aiogram 3.x с polling режимом.
Корректная инициализация и завершение ресурсов.
"""

import asyncio
import logging
import socket
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

import services.bot.config as conf
import services.bot.handlers.router as r
from services.core.database import get_database_service

logger = logging.getLogger(__name__)

# Прокси для обхода блокировок (раскомментируйте при необходимости)
# PROXY_URL = "http://proxy:port"  # или "socks5://user:pass@proxy:port"
PROXY_URL = None  # Без прокси

# Глобальные переменные (инициализируются в on_startup)
bot: Optional[Bot] = None
dp = Dispatcher()

dp.include_routers(r.admin)


async def on_startup_db():
    """Инициализация базы данных при старте бота."""
    db_service = get_database_service()
    await db_service.init_db()


async def on_shutdown_db():
    """Очистка ресурсов БД при остановке бота."""
    db_service = get_database_service()
    await db_service.dispose()


dp.startup.register(on_startup_db)
dp.shutdown.register(on_shutdown_db)


# Глобальный обработчик ошибок для всех хендлеров
@dp.errors()
async def errors_handler(event, data):
    """Глобальный обработчик ошибок."""
    from aiogram.exceptions import TelegramNetworkError, TelegramAPIError

    error = event.exception
    if isinstance(error, TelegramNetworkError):
        logger.warning(f"⚠️ Ошибка сети Telegram: {error}")
        return True
    elif isinstance(error, TelegramAPIError):
        logger.error(f"❌ Ошибка Telegram API: {error}")
        return True
    else:
        logger.error(f"❌ Неожиданная ошибка: {error}", exc_info=True)
        return True


class BotService:
    """
    Сервис для управления жизненным циклом бота.

    Инкапсулирует создание, запуск и корректное завершение бота.
    """

    def __init__(self) -> None:
        self.bot: Optional[Bot] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False

    async def initialize(self) -> Bot:
        """
        Инициализировать бота и сессию.

        Returns:
            Инициализированный Bot экземпляр
        """
        # Увеличиваем таймауты для Telegram API
        timeout = aiohttp.ClientTimeout(
            total=300,
            connect=120,
            sock_connect=120,
            sock_read=120
        )

        # Создаём connector с IPv4 для стабильности
        connector = aiohttp.TCPConnector(
            ssl=False,
            family=socket.AF_INET,
            limit=100,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )

        # Создаём aiohttp ClientSession
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            connector_owner=True,
        )

        # Создаём AiohttpSession и передаём ей aiohttp сессию
        session = AiohttpSession()
        session._session = self._session

        # Создаём бота
        self.bot = Bot(token=conf.BOT_TOKEN, session=session)

        # Устанавливаем бота в NotificationService
        from services.telegram.notification import set_global_bot
        set_global_bot(self.bot)

        # Удаляем webhook и сбрасываем pending updates
        await self.bot.delete_webhook(drop_pending_updates=True)

        logger.info("✅ Admin Bot инициализирован с увеличенными таймаутами")
        logger.info("✅ Webhook удалён, pending updates сброшены")

        return self.bot

    async def run_polling(self) -> None:
        """
        Запустить polling.

        Блокирует до отмены или ошибки.
        """
        if self.bot is None:
            raise RuntimeError("Bot not initialized. Call initialize() first.")

        self._running = True

        try:
            await dp.start_polling(
                self.bot,
                allowed_updates=[
                    'message',
                    'channel_post',
                    'edited_channel_post',
                    'callback_query',
                ],
            )
        except asyncio.CancelledError:
            logger.info("🛑 Admin Bot получил сигнал отмены")
            raise
        except KeyboardInterrupt:
            logger.info("⌨️ Admin Bot получил KeyboardInterrupt")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка polling: {type(e).__name__}: {e}")
            raise
        finally:
            self._running = False
            logger.info("🛑 Admin Bot polling остановлен")

    async def shutdown(self) -> None:
        """
        Корректно завершить работу бота и освободить ресурсы.

        Последовательность:
        1. Останавливаем polling (если запущен)
        2. Закрываем сессию бота (освобождает long polling соединение)
        3. Закрываем бота
        4. Закрываем aiohttp сессию
        """
        if not self.bot:
            logger.debug("Bot не инициализирован, shutdown пропускается")
            return

        logger.info("🛑 Shutdown Admin Bot...")

        # 1. Снимаем с глобального контекста
        from services.telegram.notification import set_global_bot
        set_global_bot(None)

        # 2. Закрываем сессию бота (критично для освобождения long polling)
        try:
            await self.bot.session.close()
            logger.debug("✅ Сессия бота закрыта")
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия сессии бота: {e}")

        # 3. Закрываем бота
        try:
            await self.bot.close()
            logger.debug("✅ Бот закрыт")
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия бота: {e}")

        # 4. Закрываем aiohttp сессию
        if self._session:
            try:
                await self._session.close()
                logger.debug("✅ aiohttp сессия закрыта")
            except Exception as e:
                logger.error(f"❌ Ошибка закрытия aiohttp сессии: {e}")
            self._session = None

        self.bot = None
        logger.info("✅ Admin Bot полностью остановлен")


# Глобальный сервис бота (singleton)
_bot_service: Optional[BotService] = None


def get_bot_service() -> BotService:
    """Получить сервис бота (singleton)."""
    global _bot_service
    if _bot_service is None:
        _bot_service = BotService()
    return _bot_service


def get_bot() -> Optional[Bot]:
    """Получить текущего бота (для обратной совместимости)."""
    service = get_bot_service()
    return service.bot


async def on_startup():
    """
    Запуск бота (точка входа из main.py).

    Инициализирует сервис и запускает polling.
    """
    service = get_bot_service()

    # Инициализируем бота
    await service.initialize()

    # Запускаем polling (блокирует до отмены)
    await service.run_polling()


async def on_shutdown():
    """
    Завершение работы бота (вызывается из main.py).
    """
    service = get_bot_service()
    await service.shutdown()
