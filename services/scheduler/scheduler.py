"""
Планировщик задач для обработки новостей и событий.

Логика работы:
1. Новости со срочностью 4-5 обрабатываются немедленно (обходят АРА)
2. Новости со срочностью 1-3 обрабатываются планировщиком 2 раза в сутки:
   - Утром в 09:00 МСК
   - Вечером в 21:00 МСК
3. События обрабатываются раз в 48 часов
"""

import asyncio
import logging
from datetime import datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

from database import RepositoryFactory
from services.news.orchestrator import NewsOrchestrator
from services.core.database import get_database_service
from config.settings import settings

logger = logging.getLogger(__name__)

# Часовой пояс Москвы
MSK_TZ = ZoneInfo('Europe/Moscow')

# Время запусков планировщика (время Москвы) — из конфига
MORNING_RUN = time(settings.morning_hour, 0)
EVENING_RUN = time(settings.evening_hour, 0)


class Scheduler:
    """
    Планировщик задач для обработки новостей и событий.

    Делегирует обработку новостей NewsOrchestrator.
    """

    def __init__(self) -> None:
        """Инициализация планировщика."""
        self._db_service = get_database_service()
        self._session = None
        self.repo_factory = None

        # Координатор будет создан при запуске
        self.orchestrator: Optional[NewsOrchestrator] = None

        # Задачи планировщика
        self._morning_task: Optional[asyncio.Task] = None
        self._evening_task: Optional[asyncio.Task] = None
        self._event_task: Optional[asyncio.Task] = None

        self._running = False
        self._initialized = False

    async def _init_components(self) -> None:
        """Инициализировать компоненты (ленивая инициализация)."""
        if self._initialized:
            return

        self._session = await self._db_service.create_session()
        self.repo_factory = RepositoryFactory(self._session)
        self.orchestrator = NewsOrchestrator(
            repo_factory=self.repo_factory,
            model=settings.agent_model,
        )
        self._initialized = True
        logger.info("✅ Scheduler компоненты инициализированы")

    async def start(self) -> None:
        """
        Запуск планировщика.

        Создаёт задачи для утренней, вечерней обработки и обработки событий.
        """
        # Инициализируем компоненты
        await self._init_components()

        self._running = True
        logger.info("🕐 Планировщик запущен")

        # Запускаем фоновые задачи
        self._morning_task = asyncio.create_task(self._run_morning_scheduler())
        self._evening_task = asyncio.create_task(self._run_evening_scheduler())
        self._event_task = asyncio.create_task(self._run_event_processor())

        # Запускаем шину событий через orchestrator
        await self.orchestrator.start_event_bus()

        logger.info("✅ Все задачи планировщика запущены")

    async def stop(self) -> None:
        """
        Корректная остановка планировщика.

        Последовательность:
        1. Останавливаем флаг работы
        2. Отменяем все задачи
        3. Останавливаем оркестратор
        4. Закрываем сессию БД
        """
        logger.info("🛑 Остановка планировщика...")

        self._running = False

        # 1. Отменяем задачи
        tasks_to_cancel = [
            (self._morning_task, "Утренняя задача"),
            (self._evening_task, "Вечерняя задача"),
            (self._event_task, "Задача событий"),
        ]

        for task, name in tasks_to_cancel:
            if task and not task.done():
                logger.info(f"⏳ Отмена: {name}...")
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=3.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

        # 2. Останавливаем оркестратор
        if self.orchestrator:
            logger.info("⏳ Остановка NewsOrchestrator...")
            await self.orchestrator.stop()

        # 3. Закрываем сессию БД
        if self._session:
            try:
                await self._session.close()
                logger.debug("✅ Сессия БД закрыта")
            except Exception as e:
                logger.error(f"❌ Ошибка закрытия сессии БД: {e}")
            self._session = None

        self._initialized = False
        logger.info("👋 Планировщик полностью остановлен")

    async def _run_morning_scheduler(self) -> None:
        """Запуск утренней обработки новостей (09:00 МСК)."""
        while self._running:
            now = datetime.now(MSK_TZ)
            target_time = now.replace(
                hour=MORNING_RUN.hour,
                minute=MORNING_RUN.minute,
                second=0,
                microsecond=0
            )

            if now >= target_time:
                target_time = target_time.replace(day=target_time.day + 1)

            sleep_seconds = (target_time - now).total_seconds()
            logger.info(
                f"🌅 Утренняя обработка запланирована через "
                f"{sleep_seconds/3600:.1f} ч (в {MORNING_RUN})"
            )

            await asyncio.sleep(sleep_seconds)

            if self._running:
                logger.info("🌅 Запуск утренней обработки новостей")
                await self._process_pending_news()

    async def _run_evening_scheduler(self) -> None:
        """Запуск вечерней обработки новостей (21:00 МСК)."""
        while self._running:
            now = datetime.now(MSK_TZ)
            target_time = now.replace(
                hour=EVENING_RUN.hour,
                minute=EVENING_RUN.minute,
                second=0,
                microsecond=0
            )

            if now >= target_time:
                target_time = target_time.replace(day=target_time.day + 1)

            sleep_seconds = (target_time - now).total_seconds()
            logger.info(
                f"🌆 Вечерняя обработка запланирована через "
                f"{sleep_seconds/3600:.1f} ч (в {EVENING_RUN})"
            )

            await asyncio.sleep(sleep_seconds)

            if self._running:
                logger.info("🌆 Запуск вечерней обработки новостей")
                await self._process_pending_news()

    async def _run_event_processor(self) -> None:
        """Обработка событий раз в 48 часов."""
        while self._running:
            # Интервал из конфига (48 часов по умолчанию)
            await asyncio.sleep(settings.event_processing_interval_seconds)

            if self._running:
                logger.info("🔄 Запуск обработки событий")
                # TODO: Реализовать обработку событий через orchestrator

    async def _process_pending_news(self) -> None:
        """
        Обработка новостей, ожидающих генерации.
        Делегирует обработку NewsOrchestrator.
        """
        try:
            # Делегируем обработку orchestrator
            processed_count = await self.orchestrator.process_pending_news_batch(hours=48)

            if processed_count == 0:
                logger.info("📭 Нет новостей для обработки")
            else:
                logger.info(f"✅ Обработано {processed_count} новостей")

        except Exception as e:
            logger.error(f"Ошибка в _process_pending_news: {e}")
