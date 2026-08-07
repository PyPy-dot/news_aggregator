"""
News Orchestrator — единый координатор для обработки новостей.

Централизует логику обработки новостей, устраняя дублирование между:
- ListenerBot (срочные новости)
- Scheduler (плановые новости)

Поддерживает стратегии:
- UrgentNewsStrategy — срочная обработка (4-5)
- ScheduledNewsStrategy — плановая обработка (1-3)
- TrustedSourceStrategy — доверенные источники (без модерации)

Корректное управление жизненным циклом шины событий.
"""

import logging
from typing import Optional, Dict, Any
from enum import Enum

from database import RepositoryFactory
from database.repositories.posts import PostRepository
from database.repositories.events import EventRepository
from database.repositories.news import NewsRepository
from database.repositories.publishers import PublisherRepository
from services.ai_agent.agents import (
    AnalystAgent,
    EditorAgent,
    ArchivistAgent,
)
from services.ai_agent.routers import EventBus
from services.ai_agent.events import Event, EventType
from services.ai_agent.vector_routers import register_vector_search_handlers
from services.telegram.notification import NotificationService
from config.settings import settings

logger = logging.getLogger(__name__)


class NewsPriority(Enum):
    """Приоритет обработки новости."""
    URGENT = 'urgent'           # Срочность 4-5
    SCHEDULED = 'scheduled'     # Срочность 1-3
    TRUSTED = 'trusted'         # Доверенный источник


class NewsOrchestrator:
    """
    Координатор обработки новостей.

    Attributes:
        repo_factory: Фабрика репозиториев
        analyst: Агент-аналитик
        editor: Агент-редактор
        archivist: Агент-архивариус
        event_bus: Шина событий
        notification_service: Сервис уведомлений
    """

    def __init__(
        self,
        repo_factory: RepositoryFactory,
        model: Optional[str] = None,
        notification_service: Optional[NotificationService] = None,
    ) -> None:
        """
        Инициализация координатора.

        Args:
            repo_factory: Фабрика репозиториев
            model: Модель для агентов (по умолчанию из конфига)
            notification_service: Сервис уведомлений
        """
        self.repo_factory = repo_factory
        self.model = model or settings.agent_model

        # Инициализация агентов
        self.analyst = AnalystAgent(model=self.model)
        self.editor = EditorAgent(model=self.model)
        self.archivist = ArchivistAgent(model=self.model)

        # Инициализация шины событий
        self.event_bus = EventBus(max_concurrency=3)
        register_vector_search_handlers(self.event_bus)

        # Сервис уведомлений
        self.notification_service = notification_service or NotificationService()

        # Флаги
        self._event_handlers_registered = False
        self._running = False

    async def process_news(
        self,
        post_id: int,
        text: str,
        category: str,
        urgency: int,
        channel_id: int,
        is_trusted_source: bool = False,
    ) -> None:
        """
        Обработать новость.

        Args:
            post_id: ID поста
            text: Текст новости
            category: Категория
            urgency: Срочность (1-5)
            channel_id: ID канала
            is_trusted_source: Флаг доверенного источника
        """
        if not self._running:
            logger.warning("⚠️ NewsOrchestrator не запущен, новость не обработана")
            return

        # Определяем приоритет
        if is_trusted_source and urgency >= 4:
            priority = NewsPriority.TRUSTED
        elif urgency >= 4:
            priority = NewsPriority.URGENT
        else:
            priority = NewsPriority.SCHEDULED

        logger.info(
            f"📰 Обработка новости ID={post_id}, приоритет={priority.value}, "
            f"срочность={urgency}, доверенный={is_trusted_source}"
        )

        # Обработка в зависимости от приоритета
        if priority == NewsPriority.TRUSTED:
            await self._handle_trusted_news(post_id, channel_id)
        elif priority == NewsPriority.URGENT:
            await self._handle_urgent_news(post_id, text, category, urgency)
        else:
            await self._handle_scheduled_news(post_id, text, category, urgency)

    async def _handle_trusted_news(self, post_id: int, channel_id: int) -> None:
        """
        Обработать новость от доверенного источника.

        Публикует напрямую без модерации и АРА.

        Args:
            post_id: ID поста
            channel_id: ID канала
        """
        logger.info(f"✅ ДОВЕРЕННЫЙ ИСТОЧНИК! Публикация без модерации (пост ID={post_id})")

        posts_repo = self.repo_factory.posts()
        publishers_repo = self.repo_factory.publishers()

        # Получаем publisher по умолчанию (первый активный)
        publishers = await publishers_repo.get_all(active_only=True)
        publisher_id = publishers[0].id if publishers else None

        # Помечаем пост как опубликованный напрямую
        await posts_repo.mark_direct_publish(
            post_id=post_id,
            publisher_channel_id=publisher_id
        )

        logger.info(f"🚀 Пост ID={post_id} помечен как опубликованный напрямую")

    async def _handle_urgent_news(
        self,
        post_id: int,
        text: str,
        category: str,
        urgency: int
    ) -> None:
        """
        Обработать срочную новость.

        Запускает АРА немедленно, затем уведомляет админа.

        Args:
            post_id: ID поста
            text: Текст новости
            category: Категория
            urgency: Срочность
        """
        logger.info(f"⚡ Срочная новость! Срочность {urgency}, категория {category}")

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

        # Emit событие генерации новости
        await self.event_bus.emit(Event(
            type=EventType.GENERATE_NEWS,
            payload={
                'post_id': post_id,
                'text': text,
                'category': category,
                'urgency': urgency,
                'urgent': True,
                'already_approved': False  # Требует модерации
            }
        ))

        logger.info(f"✅ Срочная новость ID={post_id} отправлена на обработку")

    async def _handle_scheduled_news(
        self,
        post_id: int,
        text: str,
        category: str,
        urgency: int
    ) -> None:
        """
        Обработать плановую новость.

        Сохраняет событие для обработки планировщиком.

        Args:
            post_id: ID поста
            text: Текст новости
            category: Категория
            urgency: Срочность
        """
        logger.info(f"📝 Плановая новость: срочность {urgency}, категория {category}")

        events_repo = self.repo_factory.events()

        # Создаём контекст события для планировщика
        context_data = {
            'event_description': text[:200],
            'participants': [],
            'location': None,
            'timestamp': None,
            'cause': None,
            'consequences': [],
            'related_topics': [category],
            'key_facts': []
        }

        event_id = await events_repo.create_event(
            post_id=post_id,
            context_data=context_data,
            event_category=category,
            tags=[],
            summary=text[:100]
        )

        logger.info(f"📝 Событие ID={event_id} создано (ожидает планировщика)")

    async def process_pending_news_batch(self, hours: int = 48) -> int:
        """
        Обработать пакет новостей, ожидающих обработки.

        Используется планировщиком для плановой обработки.

        Args:
            hours: За сколько часов искать новости

        Returns:
            Количество обработанных новостей
        """
        if not self._running:
            logger.warning("⚠️ NewsOrchestrator не запущен, обработка отменена")
            return 0

        posts_repo = self.repo_factory.posts()
        events_repo = self.repo_factory.events()

        # Получаем посты, которые ещё не были обработаны
        unanalyzed_posts = await posts_repo.get_unanalyzed(hours=hours)

        # Фильтруем посты, которые уже были проанализированы
        posts_to_process = []
        for post in unanalyzed_posts:
            if not await posts_repo.is_analyzed(post.id):
                posts_to_process.append(post)

        if not posts_to_process:
            logger.info("📭 Нет новостей для обработки (все уже проанализированы)")
            return 0

        logger.info(f"📊 Найдено {len(posts_to_process)} новостей для обработки")

        processed_count = 0
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
                processed_count += 1

            except Exception as e:
                logger.error(f"Ошибка обработки поста ID={post.id}: {e}")

        return processed_count

    async def start_event_bus(self) -> None:
        """Запустить шину событий."""
        logger.info("🚀 Запуск шины событий...")
        self._running = True
        await self.event_bus.run()

    async def stop(self) -> None:
        """
        Остановить координатор.

        Последовательность:
        1. Останавливаем флаг работы
        2. Останавливаем шину событий
        """
        if not self._running:
            logger.debug("NewsOrchestrator уже остановлен")
            return

        logger.info("🛑 Остановка NewsOrchestrator...")
        self._running = False

        # Шина событий будет остановлена отдельно в Scheduler/ListenerBot
