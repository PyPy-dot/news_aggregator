"""
Event Context Service — управление контекстом событий.

Инкапсулирует логику создания, обновления и поиска контекстов событий.
"""

import logging
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from database.repositories.events import EventRepository
from database.repositories.posts import PostRepository
from services.news.helpers import add_event_to_vector_index

if TYPE_CHECKING:
    from services.vector_search.service import VectorSearchService

logger = logging.getLogger(__name__)


class EventContextService:
    """
    Сервис для управления контекстом событий.

    Предоставляет методы для:
    - Поиска похожих событий
    - Поиска похожих постов
    - Создания нового контекста события
    - Обновления существующего контекста
    - Добавления в векторный индекс

    Attributes:
        events_repo: Репозиторий событий
        posts_repo: Репозиторий постов
        vector_search_service: Сервис векторного поиска (опционально)
    """

    def __init__(
        self,
        events_repo: EventRepository,
        posts_repo: PostRepository,
        vector_search_service: Optional['VectorSearchService'] = None,
    ) -> None:
        """
        Инициализация сервиса.

        Args:
            events_repo: Репозиторий событий
            posts_repo: Репозиторий постов
            vector_search_service: Сервис векторного поиска (опционально)
        """
        self.events_repo = events_repo
        self.posts_repo = posts_repo
        self.vector_search_service = vector_search_service

    async def find_similar(
        self,
        text: str,
        category: str,
        events_limit: int = 5,
        events_min_score: float = 0.7,
        posts_limit: int = 10,
        posts_min_score: float = 0.6,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Найти похожие события и посты.

        Args:
            text: Текст для поиска
            category: Категория
            events_limit: Лимит похожих событий
            events_min_score: Минимальный порог для событий
            posts_limit: Лимит похожих постов
            posts_min_score: Минимальный порог для постов

        Returns:
            Dict с ключами 'events' и 'posts'
        """
        # Используем VectorSearchService если доступен
        if self.vector_search_service:
            similar_events = await self.vector_search_service.find_similar_events(
                text=text,
                category=category,
                limit=events_limit,
                min_score=events_min_score,
            )
            similar_posts = await self.vector_search_service.find_similar_posts(
                text=text,
                category=category,
                limit=posts_limit,
                min_score=posts_min_score,
            )
        else:
            # Fallback на глобальные функции
            from services.news.helpers import find_similar_events, find_similar_posts
            similar_events = await find_similar_events(
                text=text,
                category=category,
                limit=events_limit,
                min_score=events_min_score,
            )
            similar_posts = await find_similar_posts(
                text=text,
                category=category,
                limit=posts_limit,
                min_score=posts_min_score,
            )

        logger.info(
            f"🔍 Найдено {len(similar_events)} похожих событий, "
            f"{len(similar_posts)} похожих постов"
        )

        return {
            'events': similar_events,
            'posts': similar_posts,
        }

    async def create_context(
        self,
        post_id: int,
        context_data: Dict[str, Any],
        event_category: str,
        tags: List[str],
        add_to_vector_index: bool = True,
    ) -> int:
        """
        Создать контекст события.

        Args:
            post_id: ID оригинального поста
            context_data: Данные контекста
            event_category: Категория события
            tags: Теги события
            add_to_vector_index: Добавить в векторный индекс

        Returns:
            ID созданного события
        """
        event_id = await self.events_repo.create_event(
            post_id=post_id,
            context_data=context_data,
            event_category=event_category,
            tags=tags,
        )

        logger.info(f"📝 Событие ID={event_id} создано")

        # Добавляем в векторный индекс
        if add_to_vector_index:
            await self._add_to_vector_index(
                event_id=event_id,
                post_id=post_id,
                context_data=context_data,
                event_category=event_category,
                tags=tags,
            )

        return event_id

    async def get_or_create_context(
        self,
        post_id: int,
        text: str,
        category: str,
        min_score: float = 0.75,
    ) -> tuple[Optional[Dict[str, Any]], bool]:
        """
        Получить существующий контекст или создать новый.

        Args:
            post_id: ID поста
            text: Текст поста
            category: Категория
            min_score: Минимальный порог сходства

        Returns:
            Tuple[контекст или None, True если создан новый]
        """
        # Ищем похожие события через VectorSearchService если доступен
        if self.vector_search_service:
            similar = await self.vector_search_service.find_similar_events(
                text=text,
                category=category,
                limit=1,
                min_score=min_score,
            )
        else:
            # Fallback на глобальные функции
            from services.news.helpers import find_similar_events
            similar = await find_similar_events(
                text=text,
                category=category,
                limit=1,
                min_score=min_score,
            )

        if similar:
            # Нашли похожее событие — используем его контекст
            event_data = similar[0]
            logger.info(
                f"🔗 Пост относится к событию ID={event_data.get('id')} "
                f"(score={event_data.get('score', 0):.2f})"
            )
            return event_data, False

        # Новый контекст будет создан вызывающим кодом
        logger.debug("🆕 Новое событие (аналогов не найдено)")
        return None, True

    async def _add_to_vector_index(
        self,
        event_id: int,
        post_id: int,
        context_data: Dict[str, Any],
        event_category: str,
        tags: List[str],
    ) -> None:
        """
        Добавить событие в векторный индекс.

        Args:
            event_id: ID события
            post_id: ID оригинального поста
            context_data: Данные контекста
            event_category: Категория события
            tags: Теги события
        """
        try:
            await add_event_to_vector_index(
                event_id=event_id,
                post_id=post_id,
                context_data=context_data,
                event_category=event_category,
                tags=tags,
            )
        except Exception as e:
            logger.error(f"Ошибка добавления в векторный индекс: {e}")

    def build_initial_context(
        self,
        text: str,
        category: str,
        participants: Optional[List[str]] = None,
        location: Optional[str] = None,
        timestamp: Optional[str] = None,
        cause: Optional[str] = None,
        consequences: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Построить начальный контекст события.

        Args:
            text: Текст события
            category: Категория
            participants: Участники
            location: Местоположение
            timestamp: Время
            cause: Причина
            consequences: Последствия

        Returns:
            Dict с данными контекста
        """
        return {
            'event_description': text[:200],
            'participants': participants or [],
            'location': location,
            'timestamp': timestamp,
            'cause': cause,
            'consequences': consequences or [],
            'related_topics': [category],
            'key_facts': [],
        }
