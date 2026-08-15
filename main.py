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
from services.logging_config import setup_logging

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
from services.web_admin.service import WebAdminService

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
        self.web_admin_service: Optional[WebAdminService] = None

        # Задачи сервисов
        self._bot_task: Optional[asyncio.Task] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._scheduler_task: Optional[asyncio.Task] = None
        self._web_admin_task: Optional[asyncio.Task] = None

        # Флаги
        self._running = False
        self._shutdown_triggered = False
        self._shutdown_complete = asyncio.Event()

        # События готовности сервисов
        self._scheduler_ready = asyncio.Event()
        self._bot_ready = asyncio.Event()
        self._listener_ready = asyncio.Event()
        self._web_admin_ready = asyncio.Event()

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

        # Создаём сервисы (без инициализации бота!)
        # BotService инициализируется lazy через ServiceManager._start_bot()
        self.bot_service = BotService()
        self.listener = ListenerBot(self.container)
        self.scheduler = Scheduler(self.container)

        # Сохраняем контейнер для helper функций
        global _global_container
        _global_container = self.container
        logger.info("✅ Контейнер сохранён (_global_container установлен)")

        # Очередь задач
        self._agent_queue_started = False
        if is_redis_queue():
            logger.info("🔧 Инициализация Redis очереди задач...")
        else:
            logger.info("🔧 Инициализация локальной очереди задач...")

        logger.debug("✅ Сервисы созданы (бот не инициализирован — будет lazy через ServiceManager)")

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

        Запускает Web Admin и регистрирует сервисы в ServiceManager.
        Бот, Listener и Scheduler запускаются lazy через консоль админки.
        """
        if not self.container:
            raise RuntimeError("Application not initialized. Call initialize() first.")

        self._running = True

        # Регистрация обработчиков сигналов
        self._setup_signal_handlers()

        logger.info("🤖 Инициализация сервисов...")

        # 1. Инициализируем очередь задач (если Redis)
        if is_redis_queue():
            logger.info("🔧 Инициализация Redis очереди задач...")
            await start_agent_queue(num_workers=2)
            self._agent_queue_started = True
            logger.info("✅ Redis очередь инициализирована (2 воркера)")
        else:
            logger.info("✅ Локальная очередь задач инициализирована")

        # 2. Запускаем Web Admin (не требует Telegram, работает всегда)
        self.web_admin_service = WebAdminService(host="0.0.0.0", port=8001)
        self._web_admin_task = asyncio.create_task(
            self._run_web_admin(), name="web_admin"
        )
        # Ждём готовности Web Admin
        await asyncio.wait_for(self._web_admin_ready.wait(), timeout=10.0)

        # 3. Регистрируем сервисы в ServiceManager (для управления из веб-админки)
        # Сервисы НЕ запускаются автоматически - только через консоль
        try:
            from services.service_manager import get_service_manager
            service_manager = get_service_manager()

            # Создаём сервисы но не запускаем их
            self._scheduler_task = None
            self._bot_task = None
            self._listener_task = None

            service_manager.set_services(
                bot_service=self.bot_service,
                listener=self.listener,
                scheduler=self.scheduler,
                bot_task=self._bot_task,
                listener_task=self._listener_task,
                scheduler_task=self._scheduler_task
            )
            logger.info("✅ Сервисы зарегистрированы в ServiceManager")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось зарегистрировать сервисы в ServiceManager: {e}")

        logger.info("✅ Сервисы инициализированы (ожидают запуска)")
        logger.info("📍 Откройте консоль для запуска сервисов")
        logger.info("🌐 Web Admin панель: http://localhost:8001/console")

        # Ждём сигнала завершения (сервисы запускаются через консоль)
        await self._shutdown_complete.wait()
        logger.info("🛑 Сигнал завершения получен")

    async def shutdown(self) -> None:
        """
        Корректное завершение работы.

        КРИТИЧНО: Последовательность остановки важна для избежания
        конфликтов при перезапуске (особенно для aiogram long polling).

        Последовательность:
        1. Останавливаем сервисы через ServiceManager
        2. Останавливаем очередь задач (если Redis)
        3. Останавливаем Web Admin
        4. Освобождаем ресурсы (DI контейнер, БД)
        """
        if not self._running:
            logger.debug("Приложение уже остановлено")
            return

        logger.info("🛑 Начало корректной остановки...")
        self._running = False

        # 1. Останавливаем сервисы через ServiceManager
        try:
            from services.service_manager import get_service_manager
            service_manager = get_service_manager()
            await service_manager.stop_all()
            logger.info("✅ Сервисы остановлены через ServiceManager")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось остановить сервисы через ServiceManager: {e}")
            # Пробуем остановить напрямую
            await self._stop_listener()
            await self._stop_scheduler()
            await self._stop_bot()

        # 2. Останавливаем очередь задач (если Redis)
        if self._agent_queue_started:
            logger.info("🛑 Остановка очереди задач...")
            await stop_agent_queue()
            logger.info("✅ Очередь задач остановлена")

        # 3. Останавливаем Web Admin
        await self._stop_web_admin()

        # 4. Освобождаем ресурсы
        try:
            await self._cleanup_resources()
        except Exception as e:
            # Логгируем но не прерываем завершение
            logger.warning(f"⚠️ Предупреждение при очистке ресурсов: {e}")

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

    async def _run_web_admin(self) -> None:
        """
        Запустить Web Admin сервер.

        Работает параллельно с остальными сервисами.
        """
        try:
            logger.info("🌐 Запуск Web Admin сервера...")

            # Сигнализируем о готовности
            if not self._web_admin_ready.is_set():
                self._web_admin_ready.set()

            # Запускаем сервис (блокирует до отмены)
            await self.web_admin_service.start()

        except asyncio.CancelledError:
            logger.info("🛑 Web Admin отменён")
            raise
        except KeyboardInterrupt:
            logger.info("⌨️ Web Admin получил KeyboardInterrupt")
            raise
        except Exception as e:
            logger.error(
                f"❌ Web Admin ошибка: {type(e).__name__}: {e}", exc_info=True
            )
            # Сигнализируем об ошибке инициализации
            if not self._web_admin_ready.is_set():
                self._web_admin_ready.set()
            raise

    async def _stop_web_admin(self, timeout: float = 5.0) -> None:
        """Остановить Web Admin сервер."""
        if not self._web_admin_task or self._web_admin_task.done():
            logger.debug("Web Admin уже остановлен")
            return

        logger.info("⏳ Остановка Web Admin...")
        self._web_admin_task.cancel()

        try:
            await asyncio.wait_for(self._web_admin_task, timeout=timeout)
            logger.info("✅ Web Admin задача завершена")
        except asyncio.CancelledError:
            logger.info("✅ Web Admin отменён")
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Web Admin не ответил за {timeout}с")

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
        import warnings

        # 1. DI контейнер (явный экземпляр)
        if self.container:
            try:
                await self.container.dispose()
                logger.info("✅ DI контейнер остановлен")
            except Exception as e:
                logger.debug(f"Предупреждение при остановке DI контейнера: {e}")

        # 2. Database service (подавляем предупреждения SQLAlchemy о greenlet)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            warnings.simplefilter("ignore", category=Warning)
            try:
                await dispose_database_service()
                logger.info("✅ Database service остановлен")
            except Exception as e:
                logger.debug(f"Предупреждение при остановке Database service: {e}")

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

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("⌨️ Получен сигнал остановки (Ctrl+C)")
        logger.info("🛑 Корректное завершение работы...")
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
        logger.info("🔄 Завершение работы приложения...")
        await app.shutdown()
        logger.info("✅ Приложение завершено")


if __name__ == "__main__":
    # Подавляем предупреждения SQLAlchemy при завершении (greenlet termination)
    import warnings
    warnings.filterwarnings(
        'ignore',
        message='.*garbage collector is trying to clean up non-checked-in connection.*',
        category=Warning,
        module='sqlalchemy'
    )
    warnings.filterwarnings(
        'ignore',
        message='.*greenlet is being finalized.*',
        category=RuntimeWarning,
        module='sqlalchemy'
    )

    asyncio.run(main())
