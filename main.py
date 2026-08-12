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
from services.bot.bot import BotService
from services.listener.bot import ListenerBot
from services.scheduler.scheduler import Scheduler
from services.core.container import Container
from services.core.database import dispose_database_service
from services.ai_agent.agent_queue import start_agent_queue, stop_agent_queue, is_redis_queue

# Глобальная ссылка на контейнер и приложение для helper функций (get_bot_instance и др.)
_global_container: Optional[Container] = None
app: Optional['Application'] = None  # type: ignore[name-defined]


class Application:
    """
    Главное приложение для управления жизненным циклом сервисов.

    Координирует запуск, работу и корректное завершение всех компонентов.
    """

    def __init__(self) -> None:
        self.container: Optional[Container] = None
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

        # События готовности сервисов
        self._scheduler_ready = asyncio.Event()
        self._bot_ready = asyncio.Event()
        self._listener_ready = asyncio.Event()

    async def initialize(self) -> None:
        """Инициализировать приложение."""
        logger.info("🔧 Инициализация приложения...")

        # Логирование конфигурации базы данных
        from config.settings import settings
        logger.info(f"📊 Конфигурация БД:")
        logger.info(f"   Тип: {settings.database_url_resolved.split('+')[0] if '+' in settings.database_url_resolved else 'sqlite'}")
        logger.info(f"   URL: {self._mask_db_url(settings.database_url_resolved)}")
        logger.info(f"   Пул: size={settings.db_pool_size}, overflow={settings.db_max_overflow}")

        # Создаём DI контейнер явно (без глобального singleton)
        self.container = Container()
        await self.container.init()

        # Исправление некорректных datetime полей в БД (пустые строки → NULL)
        await self._fix_corrupted_datetime_fields()

        # Создаём и инициализируем сервисы в правильном порядке
        # 1. Сначала BotService — он создаёт NotificationService
        self.bot_service = BotService()
        await self.bot_service.initialize()

        # ВАЖНО: Сначала регистрируем ВСЕ сервисы, потом сигнализируем о готовности!
        logger.info("🔍 Регистрация сервисов...")
        logger.info(f"   bot_service.bot exists: {self.bot_service.bot is not None}")
        logger.info(f"   bot_service._notification_service exists: {self.bot_service._notification_service is not None}")

        # 1. Регистрируем BotService в глобальной переменной для get_bot_instance_async
        from services.bot.bot import set_bot_service_ref
        set_bot_service_ref(self.bot_service)

        # 2. Регистрируем Bot и NotificationService в контейнере
        if self.bot_service.bot:
            self.container.register_instance_by_name('Bot', self.bot_service.bot)
            logger.info("✅ Bot зарегистрирован в контейнере")
        else:
            logger.error("❌ Bot НЕ зарегистрирован: bot_service.bot = None")

        if self.bot_service._notification_service:
            self.container.register_instance_by_name(
                'NotificationService', self.bot_service._notification_service
            )
            logger.info("✅ NotificationService зарегистрирован в контейнере")
        else:
            logger.error("❌ NotificationService НЕ зарегистрирован")

        # 3. Сохраняем контейнер для других helper функций
        global _global_container
        _global_container = self.container
        logger.info("✅ Контейнер сохранён (_global_container установлен)")

        # 4. Регистрируем событие готовности в системе (ДО установки!)
        from services.bot.bot import set_bot_ready_event
        set_bot_ready_event(self._bot_ready)

        # 5. ТЕПЕРЬ сигнализируем о готовности - ВСЁ зарегистрировано
        self._bot_ready.set()
        logger.info("🚩 ГОТОВО: бот зарегистрирован, событие _bot_ready установлено")
        logger.info(f"✅ Контейнер сохранён для helper функций (_global_container={id(_global_container)})")

        # 2. Теперь ListenerBot и Scheduler могут использовать контейнер
        self.listener = ListenerBot(self.container)
        self.scheduler = Scheduler(self.container)

        # 3. Инициализируем очередь задач (Redis или локальную)
        self._agent_queue_started = False
        if is_redis_queue():
            logger.info("🔧 Инициализация Redis очереди задач...")
        else:
            logger.info("🔧 Инициализация локальной очереди задач...")

        logger.debug("✅ Сервисы созданы и инициализированы")

    def _mask_db_url(self, url: str) -> str:
        """Замаскировать пароль в URL БД для логирования."""
        if '://' not in url:
            return url
        prefix, rest = url.split('://', 1)
        if '@' not in rest:
            return url
        host_part = rest.split('@', 1)[1]
        return f"{prefix}://***:***@{host_part}"

        logger.debug("✅ Сервисы созданы и инициализированы")

    async def _fix_corrupted_datetime_fields(self) -> None:
        """
        Исправить записи с пустыми строками в datetime полях.

        Проблема: некоторые записи имеют '' вместо NULL в полях
        subscription_started_at и subscription_ends_at, что вызывает
        ошибку при чтении: "Invalid isoformat string: ''"
        """
        try:
            from database.repositories.users import UserRepository
            from services.core.database import get_database_service

            db_service = get_database_service()
            # session_context() сам инициализирует engine при необходимости
            async with db_service.session_context() as session:
                user_repo = UserRepository(session)
                fixed_count = await user_repo.fix_empty_datetime_fields()
                if fixed_count > 0:
                    logger.info(f"🔧 Исправлено {fixed_count} записей с некорректными datetime полями")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось исправить datetime поля: {e}")

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

        # 1. Сначала запускаем очередь задач (если Redis)
        if is_redis_queue():
            logger.info("🚀 Запуск Redis очереди задач...")
            await start_agent_queue(num_workers=2)
            self._agent_queue_started = True
            logger.info("✅ Redis очередь запущена (2 воркера)")

        # 2. Теперь запускаем Scheduler (не требует Telegram)
        self._scheduler_task = asyncio.create_task(
            self._run_scheduler(), name="scheduler"
        )
        # Ждём готовности планировщика
        await asyncio.wait_for(self._scheduler_ready.wait(), timeout=10.0)

        # 2. Затем Admin Bot (aiogram) — запускаем polling
        self._bot_task = asyncio.create_task(self._run_bot(), name="admin_bot")

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

        # 1. Останавливаем очередь задач (если Redis)
        if self._agent_queue_started:
            logger.info("🛑 Остановка очереди задач...")
            await stop_agent_queue()
            logger.info("✅ Очередь задач остановлена")

        # 2. Останавливаем ListenerBot (перестаем получать новые сообщения)
        await self._stop_listener()

        # 3. Останавливаем Scheduler (отменяем задачи планировщика)
        await self._stop_scheduler()

        # 4. Останавливаем Admin Bot (критично: закрывает long polling)
        await self._stop_bot()

        # 5. Освобождаем ресурсы
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
        """
        Запустить Admin Bot (polling).

        При ошибке в соседних задачах (ListenerBot) продолжает работу.
        """
        try:
            # Бот уже инициализирован в initialize(), запускаем polling
            logger.info("🤖 Запуск Admin Bot polling...")

            # Проверяем, что бот инициализирован
            if self.bot_service and self.bot_service.bot:
                logger.info("✅ Bot экземпляр готов перед запуском polling")
            else:
                logger.error("❌ Bot экземпляр НЕ готов перед запуском polling!")

            # Запускаем polling (блокирует до отмены)
            # Событие _bot_ready уже установлено в initialize()
            await self.bot_service.run_polling()

        except asyncio.CancelledError:
            logger.info("🛑 Admin Bot отменён")
        except KeyboardInterrupt:
            logger.info("⌨️ Admin Bot получил KeyboardInterrupt")
        except Exception as e:
            logger.error(f"❌ Admin Bot ошибка: {type(e).__name__}: {e}", exc_info=True)
        finally:
            # Вызываем shutdown для очистки ресурсов
            # Принудительно закрываем коннектор, чтобы избежать утечки
            if self.bot_service:
                await self.bot_service.force_close()
            await self.bot_service.shutdown()
            logger.info("✅ Admin Bot ресурсы освобождены")

    async def _run_listener(self) -> None:
        """
        Запустить Listener Bot.

        При ошибке инициализации (например, требуется авторизация)
        логгирует ошибку и продолжает работу без ListenerBot.
        """
        from config.settings import settings

        # Проверяем, не отключён ли ListenerBot
        if getattr(settings, 'disable_listener_bot', False):
            logger.info("ℹ️ ListenerBot отключён (DISABLE_LISTENER_BOT=true)")
            self._listener_ready.set()  # Сигнализируем "готовность"
            await self._shutdown_complete.wait()  # Ждём завершения
            return

        try:
            await self.listener.start()
            # Сигнализируем о готовности после успешной инициализации
            self._listener_ready.set()
            logger.info("👂 Listener Bot слушает события...")
        except asyncio.CancelledError:
            logger.info("🛑 Listener Bot отменён")
            raise
        except KeyboardInterrupt:
            logger.info("⌨️ Listener Bot получил KeyboardInterrupt")
            raise
        except Exception as e:
            # Специальная обработка FloodWaitError с понятным сообщением
            error_msg = str(e)
            if 'FloodWaitError' in type(e).__name__ or 'wait of' in error_msg:
                # Пытаемся извлечь время ожидания
                import re
                match = re.search(r'wait of (\d+) seconds', error_msg)
                if match:
                    wait_seconds = int(match.group(1))
                    wait_hours = wait_seconds / 3600
                    wait_days = wait_hours / 24

                    if wait_days >= 1:
                        wait_msg = f"{wait_days:.1f} дн. ({wait_hours:.1f} ч.)"
                    elif wait_hours >= 1:
                        wait_msg = f"{wait_hours:.1f} ч. ({int(wait_seconds)} сек.)"
                    else:
                        wait_msg = f"{int(wait_seconds)} сек."

                    logger.error(
                        f"🚫 Telegram ограничивает запросы авторизации!\n"
                        f"   Время ожидания: {wait_msg}\n"
                        f"   Решение: Используйте другой номер телефона или подождите\n"
                        f"   (ListenerBot не будет работать до окончания блокировки)"
                    )
                else:
                    logger.error(f"❌ Listener Bot ошибка: {type(e).__name__}: {e}", exc_info=False)
            else:
                logger.error(f"❌ Listener Bot ошибка: {type(e).__name__}: {e}", exc_info=False)

            logger.warning("⚠️ ListenerBot не запущен. Приложение продолжает работу без мониторинга каналов.")
            # Сигнализируем, что listener не сможет работать (для продолжения запуска)
            if not self._listener_ready.is_set():
                self._listener_ready.set()
            # Освобождаем ресурсы listener
            try:
                await self.listener.stop()
            except Exception:
                pass
            # Ждём сигнала shutdown от других компонентов
            await self._shutdown_complete.wait()

    async def _run_scheduler(self) -> None:
        """Запустить Scheduler."""
        try:
            # Сигнализируем о готовности ДО запуска long-running операций
            # Это критично для избежания timeout при запуске приложения
            if not self._scheduler_ready.is_set():
                self._scheduler_ready.set()

            # Запускаем планировщик (создаёт фоновые задачи)
            await self.scheduler.start()

            # Ждём пока планировщик работает (блокируем до отмены)
            await self.scheduler.wait()

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
            # Сигнализируем об ошибке инициализации
            if not self._scheduler_ready.is_set():
                self._scheduler_ready.set()
            raise
        finally:
            await self.scheduler.stop()
            logger.info("✅ Scheduler ресурсы освобождены")

    async def _stop_bot(self, timeout: float = 10.0) -> None:
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
            # Принудительно закрываем сессию бота
            if self.bot_service and self.bot_service.bot:
                try:
                    await self.bot_service.bot.session.close()
                except Exception:
                    pass

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
        # 1. DI контейнер (явный экземпляр)
        if self.container:
            try:
                await self.container.dispose()
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
    global app
    app = Application()

    try:
        # Инициализация
        await app.initialize()

        # Запуск
        await app.run()

    except KeyboardInterrupt:
        logger.info("⌨️ Получен KeyboardInterrupt")
    except RuntimeError as e:
        # Специальная обработка ошибок инициализации
        error_msg = str(e)
        if "инициализировать бота" in error_msg or "Telegram" in error_msg:
            logger.error(f"❌ Ошибка подключения к Telegram: {e}")
            logger.warning(
                "⚠️ Приложение не может работать без бота. Проверьте:\n"
                "  1. TELEGRAM_BOT_TOKEN в .env\n"
                "  2. Соединение с интернетом\n"
                "  3. Telegram не заблокирован (используйте прокси если нужно)\n"
                "  4. Токен бота действителен (проверьте в @BotFather)"
            )
        else:
            logger.error(f"❌ Ошибка запуска: {type(e).__name__}: {e}", exc_info=True)
    except Exception as e:
        logger.error(
            f"❌ Критическая ошибка: {type(e).__name__}: {e}", exc_info=True
        )
    finally:
        # Гарантированная очистка
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
