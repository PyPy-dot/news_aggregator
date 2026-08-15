"""
Service Manager — глобальный менеджер управления сервисами.

Позволяет запускать и останавливать сервисы из веб-админки:
- BotService (Admin Bot)
- ListenerBot (мониторинг каналов)
- Scheduler (планировщик задач)

ВАЖНО: Web Admin и БД не управляются через этот менеджер —
они запускаются/останавливаются отдельно.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ServiceState(Enum):
    """Состояние сервиса."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"


class ServiceManager:
    """
    Глобальный менеджер сервисов.

    Предоставляет API для запуска/остановки сервисов из веб-админки.
    """

    _instance: Optional['ServiceManager'] = None
    _initialized: bool = False

    def __new__(cls) -> 'ServiceManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # Состояния сервисов - по умолчанию все остановлено
        self._states: Dict[str, ServiceState] = {
            "bot": ServiceState.STOPPED,
            "listener": ServiceState.STOPPED,
            "scheduler": ServiceState.STOPPED,
        }

        # Ссылки на сервисы (устанавливаются из main.py)
        self._bot_service = None
        self._listener = None
        self._scheduler = None

        # Задачи сервисов (для внутреннего использования)
        self._bot_task: Optional[asyncio.Task] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._scheduler_task: Optional[asyncio.Task] = None

        # Флаги для отслеживания состояния задач
        self._bot_should_run = False
        self._listener_should_run = False
        self._scheduler_should_run = False

        # Блокировка для потокобезопасности
        self._lock = asyncio.Lock()

        logger.info("✅ ServiceManager инициализирован")
        logger.info("📍 Сервисы остановлены - нажмите 'Старт' в консоли для запуска")

    def set_services(
        self,
        bot_service=None,
        listener=None,
        scheduler=None,
        bot_task=None,
        listener_task=None,
        scheduler_task=None
    ):
        """Установить ссылки на сервисы и их задачи (вызывается из main.py)."""
        self._bot_service = bot_service
        self._listener = listener
        self._scheduler = scheduler
        self._bot_task = bot_task
        self._listener_task = listener_task
        self._scheduler_task = scheduler_task

        logger.info("✅ Сервисы зарегистрированы в ServiceManager:")
        logger.info(f"   • bot_service: {type(bot_service).__name__}")
        logger.info(f"   • listener: {type(listener).__name__ if listener else None}")
        logger.info(f"   • scheduler: {type(scheduler).__name__ if scheduler else None}")
        logger.info(f"   • bot_task: {bot_task.get_name() if bot_task else None}")
        logger.info(f"   • listener_task: {listener_task.get_name() if listener_task else None}")
        logger.info(f"   • scheduler_task: {scheduler_task.get_name() if scheduler_task else None}")

    def get_state(self, service: str) -> ServiceState:
        """Получить состояние сервиса."""
        return self._states.get(service, ServiceState.STOPPED)

    def is_running(self, service: str) -> bool:
        """Проверить, запущен ли сервис."""
        return self._states.get(service) == ServiceState.RUNNING

    def get_all_states(self) -> Dict[str, bool]:
        """Получить состояния всех сервисов (для API)."""
        return {
            "bot": self.is_running("bot"),
            "listener": self.is_running("listener"),
            "scheduler": self.is_running("scheduler"),
        }

    async def start_service(self, service: str) -> Dict[str, Any]:
        """
        Запустить сервис.

        Returns:
            Dict с результатом: {"success": bool, "message": str}
        """
        async with self._lock:
            if service not in self._states:
                return {"success": False, "error": f"Неизвестный сервис: {service}"}

            if self.is_running(service):
                return {"success": True, "message": f"Сервис {service} уже запущен"}

            logger.info(f"🚀 Запуск сервиса: {service}")
            self._states[service] = ServiceState.STARTING

            try:
                if service == "scheduler":
                    await self._start_scheduler()
                elif service == "bot":
                    await self._start_bot()
                elif service == "listener":
                    await self._start_listener()

                self._states[service] = ServiceState.RUNNING
                logger.info(f"✅ Сервис {service} запущен")
                return {"success": True, "message": f"{service} запущен"}

            except Exception as e:
                self._states[service] = ServiceState.STOPPED
                logger.error(f"❌ Ошибка запуска {service}: {e}", exc_info=True)
                return {"success": False, "error": str(e)}

    async def stop_service(self, service: str) -> Dict[str, Any]:
        """
        Остановить сервис.

        Returns:
            Dict с результатом: {"success": bool, "message": str}
        """
        async with self._lock:
            if service not in self._states:
                return {"success": False, "error": f"Неизвестный сервис: {service}"}

            if not self.is_running(service):
                return {"success": True, "message": f"Сервис {service} уже остановлен"}

            logger.info(f"🛑 Остановка сервиса: {service}")
            self._states[service] = ServiceState.STOPPING

            try:
                if service == "scheduler":
                    await self._stop_scheduler()
                elif service == "bot":
                    await self._stop_bot()
                elif service == "listener":
                    await self._stop_listener()

                self._states[service] = ServiceState.STOPPED
                logger.info(f"✅ Сервис {service} остановлен")
                return {"success": True, "message": f"{service} остановлен"}

            except Exception as e:
                self._states[service] = ServiceState.STOPPED
                logger.error(f"❌ Ошибка остановки {service}: {e}", exc_info=True)
                return {"success": False, "error": str(e)}

    async def restart_service(self, service: str) -> Dict[str, Any]:
        """Перезапустить сервис."""
        await self.stop_service(service)

        if service == "bot":
            # Для бота: ждём пока старый task полностью завершится (dp.start_polling
            # делает retry с sleep после CancelledError — задача может жить
            # дольше чем timeout). После этого даём Telegram время освободить
            # сессию getUpdates на сервере.
            if self._bot_task and not self._bot_task.done():
                logger.info("⏳ Ожидание полного завершения задачи бота...")
                try:
                    await asyncio.wait_for(self._bot_task, timeout=15.0)
                except asyncio.TimeoutError:
                    logger.warning("⚠️ Задача бота не завершилась за 15 сек, форсирую")
                except asyncio.CancelledError:
                    pass

            # Дополнительная пауза чтобы Telegram сервер отпустил сессию
            logger.info("⏳ Пауза перед запуском нового polling (Telegram session cleanup)...")
            await asyncio.sleep(5)

        return await self.start_service(service)

    async def start_all(self) -> Dict[str, Any]:
        """Запустить все сервисы."""
        logger.info("🚀 Запуск всех сервисов...")
        results = []

        # Запускаем в порядке: scheduler -> bot -> listener
        for service in ["scheduler", "bot", "listener"]:
            result = await self.start_service(service)
            results.append(result)

        all_success = all(r.get("success", False) for r in results)
        return {
            "success": all_success,
            "results": dict(zip(["scheduler", "bot", "listener"], results))
        }

    async def stop_all(self) -> Dict[str, Any]:
        """Остановить все сервисы."""
        logger.info("🛑 Остановка всех сервисов...")
        results = []

        # Останавливаем в обратном порядке: listener -> bot -> scheduler
        for service in ["listener", "bot", "scheduler"]:
            result = await self.stop_service(service)
            results.append(result)

        all_success = all(r.get("success", False) for r in results)
        return {
            "success": all_success,
            "results": dict(zip(["listener", "bot", "scheduler"], results))
        }

    # Внутренние методы запуска/остановки

    async def _start_scheduler(self):
        """Запустить Scheduler."""
        if self._scheduler is None:
            raise RuntimeError("Scheduler не создан")

        # Инициализируем scheduler если ещё не инициализирован
        if not hasattr(self._scheduler, '_initialized') or not self._scheduler._initialized:
            await self._scheduler.start()  # Это инициализирует компоненты
            self._scheduler._initialized = True

        self._scheduler_should_run = True

        # Создаём новую задачу для запуска scheduler
        async def run_scheduler():
            try:
                await self._scheduler.start()
                await self._scheduler.wait()
            except asyncio.CancelledError:
                logger.info("🛑 Scheduler задача отменена")
            except Exception as e:
                logger.error(f"❌ Scheduler ошибка: {e}", exc_info=True)

        self._scheduler_task = asyncio.create_task(
            run_scheduler(),
            name="scheduler_manager"
        )
        logger.info("🕐 Scheduler запущен")

    async def _stop_scheduler(self):
        """Остановить Scheduler."""
        self._scheduler_should_run = False

        if self._scheduler:
            await self._scheduler.stop()
            logger.info("🛑 Scheduler остановлен")

    async def _start_bot(self):
        """Запустить BotService."""
        if self._bot_service is None:
            raise RuntimeError("BotService не инициализирован")

        # 1. Если бот не инициализирован — инициализируем (lazy, с подключением к Telegram)
        if self._bot_service.bot is None:
            logger.info("🔄 Инициализация бота (первый запуск / после рестарта)...")
            await self._bot_service.initialize()
            logger.info("✅ Бот инициализирован")

        # 2. Регистрируем BotService в глобальной ссылке (для get_bot_instance_async)
        from services.bot.bot import set_bot_service_ref, set_bot_ready_event

        set_bot_service_ref(self._bot_service)
        logger.info("✅ BotService зарегистрирован (глобальная ссылка)")

        # 3. Регистрируем Bot и NotificationService в DI контейнере
        # _global_container — глобальная переменная из main.py; достаем через sys.modules
        # чтобы избежать циклического импорта
        import sys
        main_mod = sys.modules.get('main')
        _global_container = getattr(main_mod, '_global_container', None) if main_mod else None

        if _global_container and self._bot_service.bot:
            _global_container.register_instance_by_name('Bot', self._bot_service.bot)
            logger.info("✅ Bot зарегистрирован в DI контейнере")

        if _global_container and self._bot_service._notification_service:
            _global_container.register_instance_by_name(
                'NotificationService', self._bot_service._notification_service
            )
            logger.info("✅ NotificationService зарегистрирован в DI контейнере")

        # 4. Сигнализируем о готовности
        _bot_ready = asyncio.Event()
        set_bot_ready_event(_bot_ready)
        _bot_ready.set()
        logger.info("🚩 Бот готов, событие _bot_ready установлено")

        self._bot_should_run = True

        # 5. Запускаем polling в новой задаче
        async def run_bot():
            try:
                await self._bot_service.run_polling()
            except asyncio.CancelledError:
                logger.info("🛑 Bot задача отменена")
            except Exception as e:
                logger.error(f"❌ Bot ошибка: {e}", exc_info=True)

        self._bot_task = asyncio.create_task(
            run_bot(),
            name="bot_manager"
        )
        logger.info("🤖 Bot запущен")

    async def _stop_bot(self):
        """Остановить BotService."""
        self._bot_should_run = False

        logger.info("🛑 Остановка BotService...")

        # 0. Сигнализируем Dispatcher'у остановить polling (GRACEFUL shutdown).
        #    dp.stop_polling() устанавливает _stop_signal → asyncio.wait()
        #    завершается → pending polling tasks отменяются → finally блок
        #    закрывает сессии. Это КРИТИЧНО для избежания TelegramConflictError.
        try:
            from services.bot.bot import dp
            if dp._running_lock.locked():
                logger.info("   Сигнал остановки polling (dp.stop_polling)...")
                await dp.stop_polling()
                logger.info("   ✅ Polling остановлен через dp.stop_polling()")
        except RuntimeError:
            # Polling не запущен (ещё не старттовал или уже остановлен)
            logger.debug("   Polling не запущен, dp.stop_polling() пропущен")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка dp.stop_polling(): {e}")

        # 1. Отменяем задачу — если dp.stop_polling() не сработал
        if self._bot_task and not self._bot_task.done():
            logger.info("   Отмена задачи бота...")
            self._bot_task.cancel()
            try:
                await asyncio.wait_for(self._bot_task, timeout=5.0)
                logger.info("   ✅ Задача отменена")
            except asyncio.CancelledError:
                logger.info("   ✅ Задача отменена (CancelledError)")
            except asyncio.TimeoutError:
                logger.warning("   ⚠️ Задача не ответила за 5 сек")

        # 2. Вызываем shutdown() для закрытия сессии бота и освобождения соединений
        if self._bot_service:
            try:
                logger.info("   Вызов bot_service.shutdown()...")
                await self._bot_service.shutdown()
                logger.info("   ✅ shutdown() завершён")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при shutdown(): {e}")

        # 3. Дополнительное принудительное закрытие на всякий случай
        if self._bot_service:
            try:
                await self._bot_service.force_close()
                logger.info("   ✅ force_close() завершён")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при force_close(): {e}")

        logger.info("🛑 Bot остановлен")

    async def _start_listener(self):
        """Запустить ListenerBot."""
        if self._listener is None:
            raise RuntimeError("ListenerBot не инициализирован")

        self._listener_should_run = True

        # Запускаем в новой задаче
        async def run_listener():
            try:
                await self._listener.start()
                # Listener работает пока не отменят
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                logger.info("🛑 Listener задача отменена")
            except Exception as e:
                logger.error(f"❌ Listener ошибка: {e}", exc_info=True)
            finally:
                if self._listener:
                    await self._listener.stop()

        try:
            self._listener_task = asyncio.create_task(
                run_listener(),
                name="listener_manager"
            )
            logger.info("👂 Listener запущен")
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Listener: {e}")
            raise

    async def _stop_listener(self):
        """Остановить ListenerBot."""
        self._listener_should_run = False

        if self._listener:
            try:
                # Отменяем задачу, если она есть
                if self._listener_task and not self._listener_task.done():
                    self._listener_task.cancel()
                    try:
                        await asyncio.wait_for(self._listener_task, timeout=5.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass

                # Останавливаем клиент
                await self._listener.stop()
                logger.info("🛑 Listener остановлен")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки Listener: {e}")
                raise


# Глобальный экземпляр
def get_service_manager() -> ServiceManager:
    """Получить экземпляр ServiceManager."""
    return ServiceManager()
