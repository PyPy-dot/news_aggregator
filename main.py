"""
News Aggregator — главное приложение.

Запускает и управляет жизненным циклом сервисов:
- Admin Bot (aiogram) — бот для управления и модерации
- Listener Bot (Telethon) — мониторинг Telegram каналов
- Scheduler — планировщик обработки новостей

Корректная обработка сигналов и завершение работы.
"""

import asyncio
import logging
import signal
import sys
from typing import Optional

# НАСТРОЙКА ЛОГИРОВАНИЯ ДО ВСЕХ ОСТАЛЬНЫХ ИМПОРТОВ
from services.logging_config import setup_logging, get_logger

setup_logging(
    level=logging.INFO,
    log_to_file=True,
    max_bytes=10 * 1024 * 1024,  # 10 MB
    backup_count=7
)

logger = logging.getLogger(__name__)

# Импорты после настройки логирования
from services.bot.bot import BotService, get_bot_service
from services.listener.bot import ListenerBot
from services.scheduler.scheduler import Scheduler
from services.core.container import init_container, get_container, dispose_container
from services.core.database import dispose_database_service


class Application:
    """
    Главное приложение для управления жизненным циклом сервисов.

    Координирует запуск, работу и корректное завершение всех компонентов.
    """

    def __init__(self) -> None:
        self.container = None
        self.listener: Optional[ListenerBot] = None
        self.scheduler: Optional[Scheduler] = None
        self.bot_service: Optional[BotService] = None

        # Задачи сервисов
        self._bot_task: Optional[asyncio.Task] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._scheduler_task: Optional[asyncio.Task] = None

        # Флаги
        self._running = False
        self._shutdown_triggered = False
        self._shutdown_complete = asyncio.Event()

    async def initialize(self) -> None:
        """Инициализировать приложение."""
        logger.info("🔧 Инициализация приложения...")

        # Инициализация DI контейнера
        self.container = await init_container()
        logger.info("✅ DI контейнер инициализирован")

        # Создаём сервисы
        self.bot_service = get_bot_service()
        self.listener = ListenerBot()
        self.scheduler = Scheduler()

        logger.info("✅ Сервисы созданы")

    async def run(self) -> None:
        """
        Запустить приложение.

        Запускает все сервисы и ждёт сигналов завершения.
        КРИТИЧНО: Боты запускаются последовательно для избежания
        конфликтов при подключении к Telegram.
        """
        if not self.container:
            raise RuntimeError("Application not initialized. Call initialize() first.")

        self._running = True

        # Регистрация обработчиков сигналов
        self._setup_signal_handlers()

        logger.info("🤖 Запуск сервисов...")

        # 1. Сначала запускаем Scheduler (не требует Telegram)
        self._scheduler_task = asyncio.create_task(
            self._run_scheduler(), name="scheduler"
        )
        # Ждём полной инициализации планировщика
        await asyncio.sleep(0.5)

        # 2. Затем Admin Bot (aiogram) — последовательно!
        self._bot_task = asyncio.create_task(self._run_bot(), name="admin_bot")
        # Ждём инициализации бота перед запуском listener
        await asyncio.sleep(1.0)

        # 3. Последний Listener Bot (Telethon)
        self._listener_task = asyncio.create_task(
            self._run_listener(), name="listener_bot"
        )

        logger.info("✅ Все сервисы запущены")
        logger.info("📍 Нажмите Ctrl+C для остановки")

        # Ждём сигнала завершения
        await self._shutdown_complete.wait()
        logger.info("🛑 Сигнал завершения получен")

    async def shutdown(self) -> None:
        """
        Корректное завершение работы.

        КРИТИЧНО: Последовательность остановки важна для избежания
        конфликтов при перезапуске (особенно для aiogram long polling).

        Последовательность:
        1. Останавливаем получение новых событий (ListenerBot)
        2. Останавливаем планировщик (Scheduler)
        3. Останавливаем Admin Bot (закрывает long polling соединение)
        4. Освобождаем ресурсы (DI контейнер, БД)
        """
        if not self._running:
            logger.debug("Приложение уже остановлено")
            return

        logger.info("🛑 Начало корректной остановки...")
        self._running = False

        # 1. Останавливаем ListenerBot (перестаем получать новые сообщения)
        await self._stop_listener()

        # 2. Останавливаем Scheduler (отменяем задачи планировщика)
        await self._stop_scheduler()

        # 3. Останавливаем Admin Bot (критично: закрывает long polling)
        await self._stop_bot()

        # 4. Освобождаем ресурсы
        await self._cleanup_resources()

        logger.info("👋 Приложение полностью остановлено")

    def _setup_signal_handlers(self) -> None:
        """Установить обработчики сигналов."""
        loop = asyncio.get_running_loop()

        if sys.platform != 'win32':
            # Unix-сигналы
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(
                    sig, lambda s=sig: self._handle_signal(s.name)
                )
        else:
            # Windows не поддерживает add_signal_handler
            logger.debug(
                "Windows: обработчики сигналов будут обрабатываться через KeyboardInterrupt"
            )

    def _handle_signal(self, sig_name: str) -> None:
        """Обработчик сигналов завершения."""
        if not self._shutdown_triggered:
            self._shutdown_triggered = True
            logger.info(f"🛑 Получен сигнал {sig_name}, начинаем остановку...")
            asyncio.create_task(self.shutdown())
        else:
            logger.warning(
                f"⚠️ Повторный сигнал {sig_name}! Принудительная остановка..."
            )
            # При повторном сигнале завершаем процесс немедленно
            import os

            os._exit(1)

    async def _run_bot(self) -> None:
        """Запустить Admin Bot."""
        try:
            # Инициализируем бота
            await self.bot_service.initialize()
            logger.info("✅ Admin Bot инициализирован")

            # Запускаем polling (блокирует до отмены)
            await self.bot_service.run_polling()

        except asyncio.CancelledError:
            logger.info("🛑 Admin Bot отменён")
            raise
        except KeyboardInterrupt:
            logger.info("⌨️ Admin Bot получил KeyboardInterrupt")
            raise
        except Exception as e:
            logger.error(f"❌ Admin Bot ошибка: {type(e).__name__}: {e}", exc_info=True)
            raise
        finally:
            # Вызываем shutdown для очистки ресурсов
            await self.bot_service.shutdown()
            logger.info("✅ Admin Bot ресурсы освобождены")

    async def _run_listener(self) -> None:
        """
        Запустить Listener Bot.

        При ошибке инициализации (например, требуется авторизация)
        логгирует ошибку и продолжает работу без ListenerBot.
        """
        try:
            await self.listener.start()
        except asyncio.CancelledError:
            logger.info("🛑 Listener Bot отменён")
            raise
        except KeyboardInterrupt:
            logger.info("⌨️ Listener Bot получил KeyboardInterrupt")
            raise
        except Exception as e:
            logger.error(
                f"❌ Listener Bot ошибка: {type(e).__name__}: {e}", exc_info=True
            )
            logger.warning("⚠️ ListenerBot не запущен. Приложение продолжает работу без мониторинга каналов.")
            # Не пробрасываем ошибку дальше — позволяем приложению работать без ListenerBot
            # Устанавливаем флаг завершения для shutdown_complete
            if not self._shutdown_complete.is_set():
                # Ждём сигнала shutdown от других компонентов
                await asyncio.Event().wait()
        finally:
            await self.listener.stop()
            logger.info("✅ Listener Bot ресурсы освобождены")

    async def _run_scheduler(self) -> None:
        """Запустить Scheduler."""
        try:
            await self.scheduler.start()
        except asyncio.CancelledError:
            logger.info("🛑 Scheduler отменён")
            raise
        except KeyboardInterrupt:
            logger.info("⌨️ Scheduler получил KeyboardInterrupt")
            raise
        except Exception as e:
            logger.error(
                f"❌ Scheduler ошибка: {type(e).__name__}: {e}", exc_info=True
            )
            raise
        finally:
            await self.scheduler.stop()
            logger.info("✅ Scheduler ресурсы освобождены")

    async def _stop_bot(self, timeout: float = 5.0) -> None:
        """Остановить Admin Bot."""
        if not self._bot_task or self._bot_task.done():
            logger.debug("Admin Bot уже остановлен")
            return

        logger.info("⏳ Остановка Admin Bot...")
        self._bot_task.cancel()

        try:
            await asyncio.wait_for(self._bot_task, timeout=timeout)
            logger.info("✅ Admin Bot задача завершена")
        except asyncio.CancelledError:
            logger.info("✅ Admin Bot отменён")
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Admin Bot не ответил за {timeout}с")

    async def _stop_listener(self, timeout: float = 5.0) -> None:
        """Остановить Listener Bot."""
        if not self._listener_task or self._listener_task.done():
            logger.debug("Listener Bot уже остановлен")
            return

        logger.info("⏳ Остановка Listener Bot...")
        self._listener_task.cancel()

        try:
            await asyncio.wait_for(self._listener_task, timeout=timeout)
            logger.info("✅ Listener Bot задача завершена")
        except asyncio.CancelledError:
            logger.info("✅ Listener Bot отменён")
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Listener Bot не ответил за {timeout}с")

    async def _stop_scheduler(self, timeout: float = 5.0) -> None:
        """Остановить Scheduler."""
        if not self._scheduler_task or self._scheduler_task.done():
            logger.debug("Scheduler уже остановлен")
            return

        logger.info("⏳ Остановка Scheduler...")
        self._scheduler_task.cancel()

        try:
            await asyncio.wait_for(self._scheduler_task, timeout=timeout)
            logger.info("✅ Scheduler задача завершена")
        except asyncio.CancelledError:
            logger.info("✅ Scheduler отменён")
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Scheduler не ответил за {timeout}с")

    async def _cleanup_resources(self) -> None:
        """Освободить глобальные ресурсы."""
        # 1. DI контейнер
        try:
            await dispose_container()
            logger.info("✅ DI контейнер остановлен")
        except Exception as e:
            logger.error(f"❌ Ошибка остановки DI контейнера: {e}")

        # 2. Database service
        try:
            await dispose_database_service()
            logger.info("✅ Database service остановлен")
        except Exception as e:
            logger.error(f"❌ Ошибка остановки Database service: {e}")

        # Сигнализируем о завершении
        self._shutdown_complete.set()


async def main():
    """Точка входа приложения."""
    app = Application()

    try:
        # Инициализация
        await app.initialize()

        # Запуск
        await app.run()

    except KeyboardInterrupt:
        logger.info("⌨️ Получен KeyboardInterrupt")
    except Exception as e:
        logger.error(
            f"❌ Критическая ошибка: {type(e).__name__}: {e}", exc_info=True
        )
    finally:
        # Гарантированная очистка
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
