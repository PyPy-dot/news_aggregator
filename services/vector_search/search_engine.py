"""
Vector Search Engine — высокоуровневый API для поиска похожих событий и новостей.
"""

import logging
from typing import Optional, Any

from services.logging_config import get_logger
from services.vector_search.embeddings import EmbeddingService
from services.vector_search.chroma_client import (
    ChromaVectorStore,
    COLLECTION_EVENTS,
    COLLECTION_NEWS,
    COLLECTION_POSTS,
)

logger = get_logger(__name__)


class VectorSearchEngine:
    """
    Высокоуровневый движок для поиска похожих событий и новостей.

    Комбинирует EmbeddingService и ChromaVectorStore для:
    - Поиска похожих событий по тексту
    - Поиска связанных новостей
    - Кластеризации постов по событиям

    Пример использования:
        search_engine = VectorSearchEngine()

        # Поиск похожих событий
        similar = search_engine.find_similar_events("Землетрясение в Турции")

        # Добавление нового события
        search_engine.add_event(
            id="event_123",
            text="Землетрясение магнитудой 7.8...",
            event_category="disaster",
            post_id=456,
        )
    """

    def __init__(
        self,
        embedding_model: str = 'paraphrase-multilingual-MiniLM-L12-v2',
        persist_directory: Optional[str] = None,
    ) -> None:
        """
        Инициализация поискового движка.

        Args:
            embedding_model: Название модели для эмбеддингов
            persist_directory: Путь к хранилищу ChromaDB
        """
        self.embeddings = EmbeddingService(model_name=embedding_model)
        self.vector_store = ChromaVectorStore(
            persist_directory=None if persist_directory is None else None  # Используется по умолчанию
        )

        logger.info("🔍 VectorSearchEngine инициализирован")

    # === Добавление данных ===

    def add_event(
        self,
        id: str,
        text: str,
        event_category: str,
        post_id: int,
        summary: str = '',
        tags: Optional[list[str]] = None,
    ) -> None:
        """
        Добавляет событие в векторный индекс.

        Args:
            id: Уникальный ID события
            text: Текст события (контекст)
            event_category: Категория события
            post_id: ID оригинального поста
            summary: Краткая выжимка
            tags: Теги события
        """
        # Создаём объединённый текст для лучшего поиска
        search_text = f"{summary} {text}".strip()

        embedding = self.embeddings.embed(search_text)

        self.vector_store.add(
            collection_name=COLLECTION_EVENTS,
            id=id,
            text=search_text,
            embedding=embedding,
            metadata={
                'event_category': event_category,
                'post_id': post_id,
                'tags': json.dumps(tags) if tags else '[]',
                'type': 'event',
            },
        )

    def add_news(
        self,
        id: str,
        text: str,
        category: str,
        source_post_ids: list[int],
        tags: Optional[list[str]] = None,
    ) -> None:
        """
        Добавляет сгенерированную новость в векторный индекс.

        Args:
            id: Уникальный ID новости
            text: Текст новости
            category: Категория
            source_post_ids: ID исходных постов
            tags: Теги новости
        """
        import json
        embedding = self.embeddings.embed(text)

        self.vector_store.add(
            collection_name=COLLECTION_NEWS,
            id=id,
            text=text,
            embedding=embedding,
            metadata={
                'category': category,
                'source_post_ids': json.dumps(source_post_ids),
                'tags': json.dumps(tags) if tags else '[]',
                'type': 'news',
            },
        )

    def add_post(
        self,
        id: str,
        text: str,
        channel_id: int,
        category: str,
        urgency: int,
    ) -> None:
        """
        Добавляет пост в векторный индекс.

        Args:
            id: Уникальный ID поста
            text: Текст поста
            channel_id: ID канала
            category: Категория
            urgency: Срочность (1-5)
        """
        embedding = self.embeddings.embed(text)

        self.vector_store.add(
            collection_name=COLLECTION_POSTS,
            id=id,
            text=text,
            embedding=embedding,
            metadata={
                'channel_id': channel_id,
                'category': category,
                'urgency': urgency,
                'type': 'post',
            },
        )

    # === Поиск ===

    def find_similar_events(
        self,
        query_text: str,
        limit: int = 5,
        category_filter: Optional[str] = None,
        min_score: float = 0.7,
    ) -> list[dict[str, Any]]:
        """
        Поиск похожих событий по тексту запроса.

        Args:
            query_text: Текст для поиска
            limit: Максимальное количество результатов
            category_filter: Фильтр по категории
            min_score: Минимальный порог сходства (0.0-1.0)

        Returns:
            Список похожих событий с score
        """
        query_embedding = self.embeddings.embed(query_text)

        filter_metadata = None
        if category_filter:
            filter_metadata = {'event_category': category_filter}

        results = self.vector_store.search(
            collection_name=COLLECTION_EVENTS,
            query_embedding=query_embedding,
            limit=limit,
            filter_metadata=filter_metadata,
        )

        # Фильтруем по порогу сходства
        filtered = [r for r in results if r['score'] >= min_score]

        logger.debug(
            f"🔍 Найдено {len(filtered)} похожих событий (порог: {min_score})"
        )

        return filtered

    def find_similar_posts(
        self,
        query_text: str,
        limit: int = 10,
        category_filter: Optional[str] = None,
        min_score: float = 0.6,
    ) -> list[dict[str, Any]]:
        """
        Поиск похожих постов.

        Args:
            query_text: Текст для поиска
            limit: Максимальное количество результатов
            category_filter: Фильтр по категории
            min_score: Минимальный порог сходства

        Returns:
            Список похожих постов с score
        """
        query_embedding = self.embeddings.embed(query_text)

        filter_metadata = None
        if category_filter:
            filter_metadata = {'category': category_filter}

        results = self.vector_store.search(
            collection_name=COLLECTION_POSTS,
            query_embedding=query_embedding,
            limit=limit,
            filter_metadata=filter_metadata,
        )

        filtered = [r for r in results if r['score'] >= min_score]

        logger.debug(f"🔍 Найдено {len(filtered)} похожих постов")

        return filtered

    def find_related_news(
        self,
        query_text: str,
        limit: int = 5,
        category_filter: Optional[str] = None,
        min_score: float = 0.5,
    ) -> list[dict[str, Any]]:
        """
        Поиск связанных новостей по тексту.

        Args:
            query_text: Текст для поиска
            limit: Максимальное количество результатов
            category_filter: Фильтр по категории
            min_score: Минимальный порог сходства

        Returns:
            Список связанных новостей с score
        """
        query_embedding = self.embeddings.embed(query_text)

        filter_metadata = None
        if category_filter:
            filter_metadata = {'category': category_filter}

        results = self.vector_store.search(
            collection_name=COLLECTION_NEWS,
            query_embedding=query_embedding,
            limit=limit,
            filter_metadata=filter_metadata,
        )

        filtered = [r for r in results if r['score'] >= min_score]

        logger.debug(f"🔍 Найдено {len(filtered)} связанных новостей")

        return filtered

    def group_posts_to_events(
        self,
        post_text: str,
        post_category: str,
        min_score: float = 0.75,
    ) -> Optional[dict[str, Any]]:
        """
        Определяет, к какому существующему событию относится пост.

        Args:
            post_text: Текст поста
            post_category: Категория поста
            min_score: Минимальный порог сходства

        Returns:
            Найденное событие или None
        """
        similar_events = self.find_similar_events(
            query_text=post_text,
            category_filter=post_category,
            limit=1,
            min_score=min_score,
        )

        if similar_events:
            logger.info(
                f"✅ Пост относится к событию ID={similar_events[0]['id']} "
                f"(score={similar_events[0]['score']:.2f})"
            )
            return similar_events[0]

        logger.debug("🆕 Пост не относится к существующим событиям")
        return None

    # === Статистика ===

    def get_stats(self) -> dict[str, int]:
        """
        Возвращает статистику по коллекциям.

        Returns:
            dict с количеством векторов в каждой коллекции
        """
        return {
            'events': self.vector_store.count(COLLECTION_EVENTS),
            'news': self.vector_store.count(COLLECTION_NEWS),
            'posts': self.vector_store.count(COLLECTION_POSTS),
        }

    def log_stats(self) -> None:
        """Логирует текущую статистику."""
        stats = self.get_stats()
        total = sum(stats.values())
        logger.info(
            f"📊 Векторный индекс: {total} векторов "
            f"(events: {stats['events']}, news: {stats['news']}, "
            f"posts: {stats['posts']})"
        )


# Импортируем json для сериализации
import json
