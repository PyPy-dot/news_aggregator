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

from services.core.database import get_database_service
import services.bot.handlers.router as r

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


# ВАЖНО: НЕ регистрируем on_shutdown_db!
# БД живёт дольше чем бот - она используется веб-админкой и другими сервисами.
# При остановке бота НЕ утилизируем БД, иначе при перезапуске
# будет ошибка "DatabaseService not initialized".

dp.startup.register(on_startup_db)


# Глобальный обработчик ошибок для всех хендлеров
@dp.errors()
async def errors_handler(event: Exception, **kwargs):
    """
    Глобальный обработчик ошибок.

    Args:
        event: Исключение (обёрнуто в UpdateEvent)
        **kwargs: Дополнительные данные от middleware
    """
    from aiogram.exceptions import TelegramNetworkError, TelegramAPIError

    # Извлекаем исключение из события
    error = event.exception if hasattr(event, 'exception') else event

    if isinstance(error, TelegramNetworkError):
        logger.warning(f"⚠️ Ошибка сети Telegram: {error}")
        return True  # Поглощаем ошибку
    elif isinstance(error, TelegramAPIError):
        logger.error(f"❌ Ошибка Telegram API: {error}")
        return True  # Поглощаем ошибку
    else:
        logger.error(f"❌ Неожиданная ошибка: {type(error).__name__}: {error}", exc_info=True)
        return True  # Поглощаем ошибку


class BotService:
    """
    Сервис для управления жизненным циклом бота.

    Инкапсулирует создание, запуск и корректное завершение бота.
    """

    def __init__(self) -> None:
        self.bot: Optional[Bot] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
        self._notification_service = None
        self._running = False
        self._last_error: Optional[str] = None

    async def initialize(self) -> Bot:
        """
        Инициализировать бота и сессию.

        Returns:
            Инициализированный Bot экземпляр

        Raises:
            RuntimeError: Если не удалось подключиться после нескольких попыток
        """
        import asyncio
        from aiogram.exceptions import TelegramNetworkError

        # Увеличиваем таймауты для Telegram API
        timeout = aiohttp.ClientTimeout(
            total=300,
            connect=120,
            sock_connect=120,
            sock_read=120
        )

        # Закрываем старый connector если остался от предыдущего запуска
        await self._close_connector()

        # Создаём connector с IPv4 для стабильности
        self._connector = aiohttp.TCPConnector(
            ssl=False,
            family=socket.AF_INET,
            limit=100,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )

        # Создаём aiohttp ClientSession
        self._session = aiohttp.ClientSession(
            connector=self._connector,
            timeout=timeout,
            connector_owner=False,  # Коннектор закрываем отдельно, не через сессию
        )

        # Создаём AiohttpSession и передаём ей aiohttp сессию
        session = AiohttpSession()
        session._session = self._session

        # Создаём бота
        from config.settings import settings
        self.bot = Bot(token=settings.bot_token, session=session)

        # Попытки удалить webhook с retry логикой
        max_retries = 5
        retry_delay = 2.0  # секунды

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"🔌 Попытка {attempt}/{max_retries}: удаление webhook...")
                await self.bot.delete_webhook(drop_pending_updates=True)
                logger.info("✅ Webhook удалён, pending updates сброшены")
                break  # Успех
            except TelegramNetworkError as e:
                if attempt < max_retries:
                    wait_time = retry_delay * attempt  # Экспоненциальная задержка
                    logger.warning(
                        f"⚠️ Попытка {attempt} не удалась: {type(e).__name__}: {e}. "
                        f"Ждём {wait_time}с перед следующей попыткой..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"❌ Не удалось удалить webhook после {max_retries} попыток. "
                        f"Проверьте соединение с Telegram и токен бота."
                    )
                    # Закрываем сессию перед выбросом исключения
                    await self._session.close()
                    raise RuntimeError(
                        f"Не удалось инициализировать бота: {e}. "
                        f"Возможные причины: нет интернета, Telegram заблокирован, неверный токен"
                    ) from e
            except Exception as e:
                logger.error(f"❌ Ошибка при удалении webhook: {type(e).__name__}: {e}")
                await self._session.close()
                raise

        # Создаём NotificationService
        from services.telegram.notification import NotificationService
        self._notification_service = NotificationService(bot=self.bot)

        logger.info("✅ Admin Bot инициализирован с увеличенными таймаутами")
        logger.info("✅ Webhook удалён, pending updates сброшены")
        logger.info("✅ NotificationService создан")

        return self.bot

    async def run_polling(self) -> None:
        """
        Запустить polling.

        Блокирует до отмены или ошибки.
        """
        if self.bot is None:
            raise RuntimeError("Bot not initialized. Call initialize() first.")

        self._running = True
        self._last_error = None

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

    def is_alive(self) -> bool:
        """Проверить, действительно ли бот работает (polling активен)."""
        if not self._running or self.bot is None:
            return False
        # dp._running_lock захвачен = polling запущен
        try:
            return dp._running_lock.locked()
        except Exception:
            return False

    async def _close_connector(self) -> None:
        """Безопасно закрыть TCPConnector, если он остался от предыдущего запуска."""
        if self._connector and not self._connector.closed:
            try:
                await self._connector.close()
                logger.debug("✅ TCPConnector закрыт")
            except Exception as e:
                logger.debug(f"⚠️ Ошибка закрытия TCPConnector: {e}")
        self._connector = None

    async def force_close(self) -> None:
        """
        Принудительно закрыть соединения бота.

        Используется при аварийном завершении для немедленного
        освобождения long polling соединения.
        """
        logger.debug("🔒 Принудительное закрытие соединений бота...")

        # Закрываем aiohttp сессию (даже если бота нет — это спасает
        # от "Unclosed client session" при аварийном завершении)
        if self._session:
            try:
                await self._session.close()
                logger.debug("✅ aiohttp сессия закрыта (force)")
            except Exception as e:
                logger.debug(f"⚠️ Ошибка закрытия aiohttp сессии (force): {e}")
            self._session = None

        # Закрываем коннектор отдельно
        await self._close_connector()

        # Закрываем сессию бота (принудительно)
        if self.bot:
            try:
                await self.bot.session.close()
                logger.debug("✅ Сессия бота закрыта (force)")
            except Exception as e:
                logger.debug(f"⚠️ Ошибка закрытия сессии бота (force): {e}")

    async def shutdown(self) -> None:
        """
        Корректно завершить работу бота и освободить ресурсы.

        Последовательность:
        1. Закрываем сессию бота (освобождает long polling соединение)
        2. Закрываем бота (с защитой от Telegram Flood control)
        3. Закрываем aiohttp сессию
        4. Вызываем shutdown Dispatcher'а (очищает внутренние очереди)
        """
        if not self.bot:
            # Бота нет, но сессия может быть — закрываем её, чтобы избежать
            # "Unclosed client session" при аварийном завершении процесса.
            if self._session:
                try:
                    await self._session.close()
                except Exception:
                    pass
                self._session = None
            await self._close_connector()
            logger.debug("Bot не инициализирован, shutdown пропускается")
            return

        logger.info("🛑 Shutdown Admin Bot...")

        # 1. Закрываем сессию бота (критично для освобождения long polling)
        try:
            await self.bot.session.close()
            logger.debug("✅ Сессия бота закрыта")
        except Exception as e:
            logger.debug(f"⚠️ Ошибка закрытия сессии бота: {e}")

        # 2. Закрываем бота — с защитой от Telegram Flood control.
        #    Telegram rate-limits метод close(): «Too Many Requests: retry after N».
        #    Игнорируем — бот и так остановлен, это косметический call.
        try:
            await self.bot.close()
            logger.debug("✅ Бот закрыт")
        except Exception as e:
            error_str = str(e).lower()
            if 'flood' in error_str or 'too many requests' in error_str:
                logger.warning(
                    f"⚠️ Telegram Flood control на close() — пропущено: {e}"
                )
            else:
                logger.debug(f"⚠️ Ошибка закрытия бота: {e}")

        # 3. Закрываем aiohttp сессию
        if self._session:
            try:
                await self._session.close()
                logger.debug("✅ aiohttp сессия закрыта")
            except Exception as e:
                logger.debug(f"⚠️ Ошибка закрытия aiohttp сессии: {e}")
            self._session = None

        # 3.1 Закрываем TCPConnector отдельно — иначе при рестарте
        # старый коннектор остаётся с активными TCP-соединениями
        # и GC жалуется "Unclosed connector".
        await self._close_connector()

        # 4. Очищаем состояние Dispatcher'а — он глобальный singleton,
        #    и при рестарте должен быть чистым (иначе стартовое событие
        #    и внутренние очереди могут конфликтовать)
        try:
            await dp.shutdown(self.bot)
            logger.debug("✅ Dispatcher shutdown завершён")
        except Exception as e:
            logger.debug(f"⚠️ Ошибка shutdown Dispatcher'а: {e}")

        self.bot = None
        logger.info("✅ Admin Bot полностью остановлен")


# =============================================================================
# Helper функции для получения бота handler'ами
# =============================================================================

# Глобальное событие готовности бота
_bot_ready_event: Optional[asyncio.Event] = None
# Глобальная ссылка на BotService
_bot_service_ref: Optional[BotService] = None


def set_bot_ready_event(event: asyncio.Event) -> None:
    """Установить событие готовности бота."""
    global _bot_ready_event
    _bot_ready_event = event
    logger.info("✅ Событие готовности бота установлено")


def set_bot_service_ref(bot_service: BotService) -> None:
    """Установить глобальную ссылку на BotService."""
    global _bot_service_ref
    _bot_service_ref = bot_service
    logger.info(f"✅ BotService зарегистрирован (ссылка: {id(bot_service)})")


async def get_bot_instance_async(wait: bool = True, timeout: float = 10.0) -> Optional[Bot]:
    """
    Асинхронно получить экземпляр бота для handler'ов.

    Args:
        wait: Если True, ждать готовности бота
        timeout: Максимальное время ожидания (секунды)

    Returns:
        Bot экземпляр или None
    """
    logger.debug(f"🔍 get_bot_instance_async вызван (wait={wait}, timeout={timeout})")
    logger.debug(f"   _bot_service_ref: {_bot_service_ref}")
    logger.debug(f"   _bot_service_ref.bot: {_bot_service_ref.bot if _bot_service_ref else None}")

    # Если BotService не зарегистрирован — ждём
    if _bot_service_ref is None:
        if wait:
            logger.debug("⏳ BotService не зарегистрирован (бот не запущен через ServiceManager), ожидаю...")
            await asyncio.sleep(min(timeout, 1.0))
        if _bot_service_ref is None:
            # Бот не запущен — это не ошибка, а легитимное состояние
            # (сервисы стартуют лениво через консоль админки)
            logger.debug("BotService не зарегистрирован — бот не запущен через консоль")
            return None

    # Проверяем, есть ли бот
    if _bot_service_ref.bot:
        logger.debug("Bot найден в _bot_service_ref")
        return _bot_service_ref.bot

    # Бота нет, но BotService есть — ждём инициализации
    if wait:
        logger.debug("⏳ Bot не инициализирован, ожидаю...")
        max_attempts = int(timeout * 2)
        for attempt in range(max_attempts):
            if _bot_service_ref.bot:
                logger.info(f"✅ Bot инициализирован после {attempt + 1} попыток")
                return _bot_service_ref.bot
            await asyncio.sleep(0.5)

    logger.debug("Bot не инициализирован после ожидания")
    return None


def get_bot_instance(wait: bool = True, timeout: float = 10.0) -> Optional[Bot]:
    """
    Синхронная обёртка для get_bot_instance_async.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            task = loop.create_task(get_bot_instance_async(wait, timeout))
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = asyncio.run_coroutine_threadsafe(task, loop)
                return future.result(timeout=timeout + 2)
        else:
            return loop.run_until_complete(get_bot_instance_async(wait, timeout))
    except Exception as e:
        logger.error(f"❌ Ошибка получения бота: {type(e).__name__}: {e}")
        return None


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
