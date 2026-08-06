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
import json
from datetime import datetime, timezone, time
from zoneinfo import ZoneInfo

from database import RepositoryFactory, async_session
from services.ai_agent.agents import (
    AnalystAgent,
    EditorAgent,
    ArchivistAgent,
)
from services.ai_agent.routers import EventBus
from services.ai_agent.events import Event, EventType

logger = logging.getLogger(__name__)

# Часовой пояс Москвы
MSK_TZ = ZoneInfo('Europe/Moscow')

# Время запусков планировщика (время Москвы)
MORNING_RUN = time(9, 0)  # 09:00 МСК
EVENING_RUN = time(21, 0)  # 21:00 МСК


class Scheduler:
    """
    Планировщик задач для обработки новостей и событий.

    Attributes:
        repo_factory: Фабрика репозиториев
        analyst: Агент-аналитик
        editor: Агент-редактор
        archivist: Агент-архивариус
        event_bus: Шина событий
    """

    def __init__(self) -> None:
        """Инициализация планировщика."""
        self._session = async_session()
        self.repo_factory = RepositoryFactory(self._session)

        # Агенты АРА
        self.analyst = AnalystAgent(model='qwen2.5:7b')
        self.editor = EditorAgent(model='qwen2.5:7b')
        self.archivist = ArchivistAgent(model='qwen2.5:7b')

        self.event_bus = EventBus(max_concurrency=2)
        self._running = False

    async def start(self) -> None:
        """Запуск планировщика."""
        self._running = True
        logger.info("🕐 Планировщик запущен")

        # Запускаем фоновые задачи
        asyncio.create_task(self._run_morning_scheduler())
        asyncio.create_task(self._run_evening_scheduler())
        asyncio.create_task(self._run_event_processor())

        # Запускаем шину событий
        await self.event_bus.run()

    async def stop(self) -> None:
        """Остановка планировщика."""
        self._running = False
        logger.info("🛑 Планировщик остановлен")

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
            # 48 часов = 172800 секунд
            await asyncio.sleep(172800)

            if self._running:
                logger.info("🔄 Запуск обработки событий")
                await self._process_events()

    async def _process_pending_news(self) -> None:
        """
        Обработка новостей, ожидающих генерации.
        Использует PostRepository для получения необработанных постов.
        """
        try:
            posts_repo = self.repo_factory.posts()
            events_repo = self.repo_factory.events()

            # Получаем посты, которые ещё не были обработаны
            unanalyzed_posts = await posts_repo.get_unanalyzed(hours=48)

            # Фильтруем посты, которые уже были проанализированы
            posts_to_process = []
            for post in unanalyzed_posts:
                if not await posts_repo.is_analyzed(post.id):
                    posts_to_process.append(post)

            if not posts_to_process:
                logger.info("📭 Нет новостей для обработки (все уже проанализированы)")
                return

            logger.info(f"📊 Найдено {len(posts_to_process)} новостей для обработки")

            for post in posts_to_process:
                try:
                    # Получаем контекст события для этого поста
                    contexts = await events_repo.get_by_post(post.id)
                    context = contexts[0] if contexts else {}

                    # Emit событие генерации новости
                    await self.event_bus.emit(Event(
                        type=EventType.GENERATE_NEWS,
                        payload={
                            'post_id': post.id,
                            'event_id': contexts[0].id if contexts else None,
                            'event_context': context,
                            'category': post.category,
                            'urgency': int(post.urgency) if post.urgency else 1,
                            'scheduled': True,
                            'from_scheduler': True
                        }
                    ))

                    logger.info(
                        f"✅ Пост ID={post.id} отправлен на генерацию "
                        f"(категория: {post.category})"
                    )

                except Exception as e:
                    logger.error(f"Ошибка обработки поста ID={post.id}: {e}")

        except Exception as e:
            logger.error(f"Ошибка в _process_pending_news: {e}")

    async def _process_events(self) -> None:
        """
        Обработка событий: генерация сводных новостей.
        Собирает несколько постов одного события и создаёт сводку.
        """
        try:
            events_repo = self.repo_factory.events()

            # Получаем все необработанные события
            events = await events_repo.get_for_scheduler(hours=48)

            if not events:
                logger.info("📭 Нет событий для обработки")
                return

            # Группируем события по категориям
            from collections import defaultdict
            grouped = defaultdict(list)
            for event in events:
                grouped[event.event_category].append(event)

            logger.info(
                f"📊 Найдено {len(events)} событий в {len(grouped)} категориях"
            )

            # Обрабатываем каждую группу
            for category, cat_events in grouped.items():
                logger.info(
                    f"📰 Обработка категории '{category}': "
                    f"{len(cat_events)} событий"
                )

                # Пока просто отправляем каждое событие отдельно
                # TODO: Здесь будет логика группировки событий в сводную новость
                for event in cat_events:
                    context = json.loads(event.context_data)

                    await self.event_bus.emit(Event(
                        type=EventType.GENERATE_NEWS,
                        payload={
                            'post_id': event.post_id,
                            'event_id': event.id,
                            'event_context': context,
                            'category': category,
                            'scheduled': True
                        }
                    ))

                    await events_repo.mark_processed(event.id)

        except Exception as e:
            logger.error(f"Ошибка в _process_events: {e}")

    async def process_urgent_news(
        self,
        post_id: int,
        text: str,
        category: str,
        urgency: int
    ) -> None:
        """
        Немедленная обработка срочной новости (срочность 4-5).
        Обходит планировщик, запускает АРА немедленно.

        Args:
            post_id: ID поста
            text: Текст поста
            category: Категория
            urgency: Срочность (4 или 5)
        """
        logger.info(
            f"⚡ Срочная новость! Срочность {urgency}, категория {category}"
        )

        try:
            # Emit событие создания контекста (срочно)
            await self.event_bus.emit(Event(
                type=EventType.CREATE_CONTEXT,
                payload={
                    'post_id': post_id,
                    'text': text,
                    'category': category,
                    'urgency': urgency,
                    'urgent': True
                }
            ))

            logger.info(f"✅ Срочная новость ID={post_id} отправлена на обработку")

        except Exception as e:
            logger.error(f"Ошибка обработки срочной новости: {e}")
