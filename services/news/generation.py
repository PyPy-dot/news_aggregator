"""
News Generation Service — генерация новостей через AI агентов.

Инкапсулирует логику вызова EditorAgent и ArchivistAgent.
"""

import logging
import json
from typing import Optional, Dict, Any, List

from database.repositories.posts import PostRepository
from database.repositories.events import EventRepository
from database.repositories.news import NewsRepository
from database.repositories.channels import ChannelRepository
from services.ai_agent.agents import EditorAgent, ArchivistAgent
from services.news.helpers import add_generated_news
from services.telegram.notification import NotificationService

logger = logging.getLogger(__name__)


def _extract_event_ids(similar_events: List[Dict[str, Any]]) -> List[str]:
    """Извлечь ID событий из списка похожих событий."""
    return [
        event.get('id') for event in similar_events
        if event.get('id')
    ]


class NewsGenerationService:
    """
    Сервис для генерации новостей через AI агентов.

    Координирует:
    - Вызов EditorAgent для генерации текста
    - Вызов ArchivistAgent для создания контекста
    - Сохранение новости в БД
    - Уведомление админов о модерации

    Attributes:
        posts_repo: Репозиторий постов
        events_repo: Репозиторий событий
        news_repo: Репозиторий новостей
        channels_repo: Репозиторий каналов
        notification_service: Сервис уведомлений
    """

    def __init__(
        self,
        posts_repo: PostRepository,
        events_repo: EventRepository,
        news_repo: NewsRepository,
        channels_repo: ChannelRepository,
        notification_service: Optional[NotificationService] = None,
    ) -> None:
        """
        Инициализация сервиса.

        Args:
            posts_repo: Репозиторий постов
            events_repo: Репозиторий событий
            news_repo: Репозиторий новостей
            channels_repo: Репозиторий каналов
            notification_service: Сервис уведомлений
        """
        self.posts_repo = posts_repo
        self.events_repo = events_repo
        self.news_repo = news_repo
        self.channels_repo = channels_repo
        self.notification_service = notification_service

    async def generate_news(
        self,
        post_id: int,
        post_text: str,
        post_category: str,
        post_tags: List[str],
        post_category_confidence: float,
        similar_events: List[Dict[str, Any]],
        similar_posts: List[Dict[str, Any]],
    ) -> Optional[int]:
        """
        Сгенерировать новость из поста.

        Алгоритм:
        1. Вызов EditorAgent для генерации текста
        2. Сохранение новости в БД
        3. Уведомление админов о модерации
        4. Вызов ArchivistAgent для создания контекста
        5. Сохранение контекста события

        Args:
            post_id: ID оригинального поста
            post_text: Текст поста
            post_category: Категория
            post_tags: Теги поста
            post_category_confidence: Уверенность категории
            similar_events: Похожие события из векторного поиска
            similar_posts: Похожие посты из векторного поиска

        Returns:
            ID сгенерированной новости или None при ошибке
        """
        try:
            # 1. Генерация через EditorAgent
            news_result = await self._generate_content(
                editor=EditorAgent(),
                post_text=post_text,
                similar_events=similar_events,
                post_category=post_category,
                post_category_confidence=post_category_confidence,
                post_tags=post_tags,
            )

            logger.info(
                f"📝 Новость сгенерирована: {len(news_result.get('text', ''))} символов"
            )

            # 2. Сохранение в БД
            source_event_ids = _extract_event_ids(similar_events[:3])
            news_id = await self._save_news(
                news_result, post_category, source_event_ids
            )

            logger.info(f"✅ Новость ID={news_id} сохранена в БД")

            # 3. Уведомление админов
            await self._notify_moderation(
                news_id=news_id,
                post_id=post_id,
                news_text=news_result.get('text', ''),
                category=post_category,
            )

            # 4-5. Создание и сохранение контекста
            await self._create_and_save_context(
                archivist=ArchivistAgent(),
                post_text=post_text,
                generated_news=news_result,
                post_category=post_category,
                post_tags=post_tags,
                post_id=post_id,
            )

            logger.info(f"📚 Архивариус создал контекст события")

            return news_id

        except Exception as e:
            logger.error(f"Ошибка генерации новости: {e}", exc_info=True)
            return None

    async def _generate_content(
        self,
        editor: EditorAgent,
        post_text: str,
        similar_events: List[Dict[str, Any]],
        post_category: str,
        post_category_confidence: float,
        post_tags: List[str],
    ):
        """Сгенерировать контент новости через EditorAgent."""
        # Формируем контекст из событий
        event_contexts = [
            json.loads(event.get('metadata', {}).get('context_data', '{}'))
            for event in similar_events
            if isinstance(event.get('metadata', {}).get('context_data'), (str, dict))
        ]

        return await editor.generate_news(
            post_text=post_text,
            analysis={
                'category': post_category,
                'confidence': post_category_confidence,
                'post_tags': post_tags,
            },
            event_context=event_contexts[0] if event_contexts else {}
        )

    async def _save_news(self, news_result: dict, category: str, source_event_ids: list):
        """Сохранить новость в БД."""
        return await add_generated_news(
            text=news_result.get('text', ''),
            category=category,
            tags=news_result.get('news_tags', []),
            source_event_ids=source_event_ids,
            moderation_status='pending'
        )

    async def _create_and_save_context(
        self,
        archivist: ArchivistAgent,
        post_text: str,
        generated_news: dict,
        post_category: str,
        post_tags: List[str],
        post_id: int,
    ):
        """Создать контекст события через ArchivistAgent и сохранить."""
        context_result = await archivist.create_context(
            post_text=post_text,
            generated_news=generated_news,
            analysis={
                'category': post_category,
                'post_tags': post_tags,
            }
        )

        await self.events_repo.create_event(
            post_id=post_id,
            context_data=context_result['context_data'],
            event_category=post_category,
            tags=context_result['tags'],
        )

    async def _notify_moderation(
        self,
        news_id: int,
        post_id: int,
        news_text: str,
        category: str,
    ) -> None:
        """
        Уведомить админов о новости на модерации.

        Args:
            news_id: ID новости
            post_id: ID оригинального поста
            news_text: Текст новости
            category: Категория
        """
        if not self.notification_service:
            return

        # Получаем информацию о канале для названия
        try:
            post = await self.posts_repo.get(post_id)
            if post:
                channel = await self.channels_repo.get_by_telegram_id(post.channel_id)
                channel_title = channel.title if channel else f"Post ID={post_id}"
            else:
                channel_title = f"Post ID={post_id}"
        except Exception as e:
            logger.warning(f"Не удалось получить информацию о канале: {e}")
            channel_title = f"Post ID={post_id}"

        await self.notification_service.notify_pending_news(
            post_id=news_id,
            text=news_text[:500],
            category=category,
            channel_title=channel_title,
        )

        logger.info(f"📬 Отправлено уведомление о новости ID={news_id} на модерации")
