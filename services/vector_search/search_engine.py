"""
Vector Search Engine — высокоуровневый API для поиска похожих событий и новостей.

Оптимизации:
- Кэширование результатов поиска (LRU cache)
- Батчинг для добавления векторов
- Оптимизированные параметры HNSW для ChromaDB
"""

import json
import hashlib
from pathlib import Path
from typing import Optional, Any
from collections import OrderedDict

from services.logging_config import get_logger
from services.vector_search.embeddings import EmbeddingService
from services.vector_search.chroma_client import (
    ChromaVectorStore,
    COLLECTION_EVENTS,
    COLLECTION_NEWS,
    COLLECTION_POSTS,
)

logger = get_logger(__name__)


def _get_settings():
    """Lazy import of settings to avoid circular imports."""
    from config.settings import settings
    return settings


class LRUCache:
    """
    LRU кэш для результатов поиска.

    Attributes:
        capacity: Максимальный размер кэша
    """

    def __init__(self, capacity: int = 1000) -> None:
        """
        Инициализация LRU кэша.

        Args:
            capacity: Максимальное количество записей
        """
        self.capacity = capacity
        self._cache: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        """
        Получить значение из кэша.

        Args:
            key: Ключ

        Returns:
            Значение или None
        """
        if key in self._cache:
            # Перемещаем в конец (свежий)
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, value: Any) -> None:
        """
        Добавить значение в кэш.

        Args:
            key: Ключ
            value: Значение
        """
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value

        # Удаляем старые записи при переполнении
        if len(self._cache) > self.capacity:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        """Очистить кэш."""
        self._cache.clear()


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
        cache_size: int = 500,
    ) -> None:
        """
        Инициализация поискового движка.

        Args:
            embedding_model: Название модели для эмбеддингов
            persist_directory: Путь к хранилищу ChromaDB
            cache_size: Размер LRU кэша для результатов поиска
        """
        self.embeddings = EmbeddingService(model_name=embedding_model)

        persist_dir: Optional[Path] = None
        if persist_directory:
            persist_dir = Path(persist_directory)

        self.vector_store = ChromaVectorStore(
            persist_directory=persist_dir,
            embedding_service=self.embeddings,
        )
        # LRU кэш для результатов поиска (ключ: hash(query+params), значение: результаты)
        self._search_cache = LRUCache(capacity=cache_size)

        logger.info(f"🔍 VectorSearchEngine инициализирован (cache_size={cache_size})")

    # === Добавление данных ===

    async def add_event(
        self,
        id: str,
        text: str,
        event_category: str,
        post_id: int,
        tags: Optional[list[str]] = None,
    ) -> None:
        """
        Добавляет событие в векторный индекс.

        Args:
            id: Уникальный ID события
            text: Текст события (контекст)
            event_category: Категория события
            post_id: ID оригинального поста
            tags: Теги события
        """
        embedding = await self.embeddings.embed(text)

        self._validate_embedding(embedding)

        self.vector_store.add(
            collection_name=COLLECTION_EVENTS,
            id=id,
            text=text,
            embedding=embedding,
            metadata={
                'event_category': event_category,
                'post_id': post_id,
                'tags': json.dumps(tags) if tags else '[]',
            },
        )

    async def add_news(
        self,
        id: str,
        text: str,
        category: str,
        tags: Optional[list[str]] = None,
    ) -> None:
        """
        Добавляет сгенерированную новость в векторный индекс.

        Args:
            id: Уникальный ID новости
            text: Текст новости
            category: Категория
            tags: Теги новости
        """
        embedding = await self.embeddings.embed(text)

        self._validate_embedding(embedding)

        self.vector_store.add(
            collection_name=COLLECTION_NEWS,
            id=id,
            text=text,
            embedding=embedding,
            metadata={
                'category': category,
                'tags': json.dumps(tags) if tags else '[]',
            },
        )

    async def add_post(
        self,
        id: str,
        text: str,
        channel_id: int,
        category: str,
        urgency: Optional[int] = None,
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
        embedding = await self.embeddings.embed(text)

        self._validate_embedding(embedding)

        metadata = {
            'channel_id': channel_id or 0,
            'category': category or '',
        }
        if urgency is not None:
            metadata['urgency'] = urgency

        self.vector_store.add(
            collection_name=COLLECTION_POSTS,
            id=id,
            text=text,
            embedding=embedding,
            metadata=metadata,
        )

    # === Поиск ===

    async def find_similar_events(
        self,
        query_text: str,
        limit: int | None = None,
        category_filter: Optional[str] = None,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Поиск похожих событий по тексту запроса.

        Args:
            query_text: Текст для поиска
            limit: Максимальное количество результатов (по умолчанию из настроек)
            category_filter: Фильтр по категории
            min_score: Минимальный порог сходства (0.0-1.0, по умолчанию из настроек)
        """
        if limit is None:
            limit = _get_settings().vector_search_events_limit
        if min_score is None:
            min_score = _get_settings().vector_search_min_score_events

        # Создаём ключ кэша
        cache_key = self._make_cache_key(
            'events', query_text, limit, category_filter, min_score
        )

        # Проверяем кэш
        cached_result = self._search_cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"✅ Кэш hit для поиска событий: {len(cached_result)} результатов")
            return cached_result

        # Выполняем поиск
        query_embedding = await self.embeddings.embed(query_text)

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

        # Сохраняем в кэш
        self._search_cache.put(cache_key, filtered)

        logger.debug(
            f"🔍 Найдено {len(filtered)} похожих событий (порог: {min_score})"
        )

        return filtered

    def _make_cache_key(
        self,
        collection: str,
        query_text: str,
        limit: int,
        category_filter: Optional[str],
        min_score: float,
    ) -> str:
        """
        Создать ключ кэша для запроса.

        Args:
            collection: Имя коллекции
            query_text: Текст запроса
            limit: Лимит результатов
            category_filter: Фильтр по категории
            min_score: Минимальный порог

        Returns:
            Хэш ключа
        """
        key_data = f"{collection}:{query_text}:{limit}:{category_filter}:{min_score}"
        return hashlib.md5(key_data.encode('utf-8')).hexdigest()

    async def find_similar_posts(
        self,
        query_text: str,
        limit: int | None = None,
        category_filter: Optional[str] = None,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Поиск похожих постов.

        Args:
            query_text: Текст для поиска
            limit: Максимальное количество результатов (по умолчанию из настроек)
            category_filter: Фильтр по категории
            min_score: Минимальный порог сходства (по умолчанию 0.6)
        """
        if limit is None:
            limit = _get_settings().vector_search_posts_limit
        if min_score is None:
            min_score = 0.6

        # Создаём ключ кэша
        cache_key = self._make_cache_key(
            'posts', query_text, limit, category_filter, min_score
        )

        # Проверяем кэш
        cached_result = self._search_cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"✅ Кэш hit для поиска постов: {len(cached_result)} результатов")
            return cached_result

        # Выполняем поиск
        query_embedding = await self.embeddings.embed(query_text)

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

        # Сохраняем в кэш
        self._search_cache.put(cache_key, filtered)

        logger.debug(f"🔍 Найдено {len(filtered)} похожих постов")

        return filtered

    async def find_related_news(
        self,
        query_text: str,
        limit: int | None = None,
        category_filter: Optional[str] = None,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Поиск связанных новостей по тексту.

        Args:
            query_text: Текст для поиска
            limit: Максимальное количество результатов (по умолчанию 5)
            category_filter: Фильтр по категории
            min_score: Минимальный порог сходства (по умолчанию 0.5)
        """
        if limit is None:
            limit = 5
        if min_score is None:
            min_score = 0.5

        # Создаём ключ кэша
        cache_key = self._make_cache_key(
            'news', query_text, limit, category_filter, min_score
        )

        # Проверяем кэш
        cached_result = self._search_cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"✅ Кэш hit для поиска новостей: {len(cached_result)} результатов")
            return cached_result

        # Выполняем поиск
        query_embedding = await self.embeddings.embed(query_text)

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

        # Сохраняем в кэш
        self._search_cache.put(cache_key, filtered)

        logger.debug(f"🔍 Найдено {len(filtered)} связанных новостей")

        return filtered

    def clear_cache(self) -> None:
        """Очистить кэш результатов поиска."""
        self._search_cache.clear()
        logger.debug("🗑️ Кэш векторного поиска очищен")

    def get_cache_stats(self) -> dict[str, int]:
        """
        Получить статистику кэша.

        Returns:
            dict со статистикой кэша
        """
        return {
            'size': len(self._search_cache._cache),
            'capacity': self._search_cache.capacity,
        }

    async def group_posts_to_events(
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
        similar_events = await self.find_similar_events(
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

    def _validate_embedding(self, embedding: list[float]) -> None:
        """Проверить размерность эмбеддинга против ожидаемой от модели."""
        expected = self.embeddings.embedding_dim
        actual = len(embedding)
        if actual != expected:
            logger.error(
                f"❌ Embedding dimension mismatch: expected {expected}, got {actual}"
            )
            raise ValueError(
                f"Embedding dimension mismatch: expected {expected}, got {actual}. "
                "The embedding model may have been changed."
            )

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
