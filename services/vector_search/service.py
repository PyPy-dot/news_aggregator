"""
Vector Search Service — сервис для поиска похожих событий и постов.

Инкапсулирует VectorSearchEngine и предоставляет удобный интерфейс
для использования через DI контейнер.
"""

import logging
import json
from typing import Optional, Dict, Any, List

from services.vector_search.search_engine import VectorSearchEngine

logger = logging.getLogger(__name__)


class VectorSearchService:
    """
    Сервис векторного поиска.

    Предоставляет методы для:
    - Поиска похожих событий
    - Поиска похожих постов
    - Поиска связанных новостей
    - Добавления событий/новостей/постов в индекс
    - Группировки постов по событиям

    Attributes:
        search_engine: Основной движок векторного поиска
    """

    def __init__(
        self,
        embedding_model: str = 'paraphrase-multilingual-MiniLM-L12-v2',
        persist_directory: str | None = None,
        cache_size: int = 500,
    ) -> None:
        """
        Инициализация сервиса.

        Args:
            embedding_model: Модель для эмбеддингов
            persist_directory: Путь к хранилищу ChromaDB (если None — по умолчанию ./vector_store)
            cache_size: Размер LRU кэша
        """
        self.search_engine = VectorSearchEngine(
            embedding_model=embedding_model,
            persist_directory=persist_directory,
            cache_size=cache_size,
        )
        logger.info("🔍 VectorSearchService инициализирован")

    async def find_similar_events(
        self,
        text: str,
        category: str,
        limit: int = 5,
        min_score: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """
        Найти похожие события.

        Args:
            text: Текст для поиска
            category: Категория для фильтрации
            limit: Лимит результатов
            min_score: Минимальный порог сходства

        Returns:
            Список похожих событий с metadata
        """
        try:
            results = await self.search_engine.find_similar_events(
                query_text=text,
                category_filter=category,
                limit=limit,
                min_score=min_score,
            )
            logger.debug(
                f"🔍 Найдено {len(results)} похожих событий для '{text[:50]}...'"
            )
            return results
        except Exception as e:
            logger.warning(f"⚠️ Векторный поиск событий не выполнен: {e}")
            return []

    async def find_similar_posts(
        self,
        text: str,
        category: str,
        limit: int = 10,
        min_score: float = 0.6,
    ) -> List[Dict[str, Any]]:
        """
        Найти похожие посты.

        Args:
            text: Текст для поиска
            category: Категория для фильтрации
            limit: Лимит результатов
            min_score: Минимальный порог сходства

        Returns:
            Список похожих постов с metadata
        """
        try:
            results = await self.search_engine.find_similar_posts(
                query_text=text,
                category_filter=category,
                limit=limit,
                min_score=min_score,
            )
            logger.debug(
                f"🔍 Найдено {len(results)} похожих постов для '{text[:50]}...'"
            )
            return results
        except Exception as e:
            logger.warning(f"⚠️ Векторный поиск постов не выполнен: {e}")
            return []

    async def find_related_news(
        self,
        text: str,
        category: str,
        limit: int = 5,
        min_score: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Найти связанные новости.

        Args:
            text: Текст для поиска
            category: Категория для фильтрации
            limit: Лимит результатов
            min_score: Минимальный порог сходства

        Returns:
            Список связанных новостей с metadata
        """
        try:
            results = await self.search_engine.find_related_news(
                query_text=text,
                category_filter=category,
                limit=limit,
                min_score=min_score,
            )
            logger.debug(
                f"🔍 Найдено {len(results)} связанных новостей для '{text[:50]}...'"
            )
            return results
        except Exception as e:
            logger.warning(f"⚠️ Векторный поиск новостей не выполнен: {e}")
            return []

    async def add_event(
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
            # Формируем текст для поиска из контекста
            search_text = json.dumps(context_data, ensure_ascii=False)

            await self.search_engine.add_event(
                id=f"event_{event_id}",
                text=search_text,
                event_category=event_category,
                post_id=post_id,
                tags=tags,
            )
            logger.info(f"📦 Событие ID={event_id} добавлено в векторный индекс")
        except Exception as e:
            logger.error(f"Ошибка добавления события в векторный индекс: {e}")
            raise

    async def add_news(
        self,
        news_id: int,
        text: str,
        category: str,
        tags: List[str],
    ) -> None:
        """
        Добавить новость в векторный индекс.

        Args:
            news_id: ID новости
            text: Текст новости
            category: Категория
            tags: Теги новости
        """
        try:
            await self.search_engine.add_news(
                id=f"news_{news_id}",
                text=text,
                category=category,
                tags=tags,
            )
            logger.info(f"📦 Новость ID={news_id} добавлена в векторный индекс")
        except Exception as e:
            logger.error(f"Ошибка добавления новости в векторный индекс: {e}")
            raise

    async def add_post(
        self,
        post_id: int,
        text: str,
        channel_id: int,
        category: str,
        urgency: int,
    ) -> None:
        """
        Добавить пост в векторный индекс.

        Args:
            post_id: ID поста
            text: Текст поста
            channel_id: ID канала
            category: Категория
            urgency: Срочность (1-5)
        """
        try:
            await self.search_engine.add_post(
                id=f"post_{post_id}",
                text=text,
                channel_id=channel_id,
                category=category,
                urgency=urgency,
            )
            logger.info(f"📦 Пост ID={post_id} добавлен в векторный индекс")
        except Exception as e:
            logger.error(f"Ошибка добавления поста в векторный индекс: {e}")
            raise

    async def group_posts_to_events(
        self,
        post_text: str,
        post_category: str,
        min_score: float = 0.75,
    ) -> Optional[Dict[str, Any]]:
        """
        Определить, к какому событию относится пост.

        Args:
            post_text: Текст поста
            post_category: Категория поста
            min_score: Минимальный порог сходства

        Returns:
            Найденное событие или None
        """
        result = await self.search_engine.group_posts_to_events(
            post_text=post_text,
            post_category=post_category,
            min_score=min_score,
        )
        if result:
            logger.info(
                f"✅ Пост относится к событию (score={result.get('score', 0):.2f})"
            )
        else:
            logger.debug("🆕 Пост не относится к существующим событиям")
        return result

    def clear_cache(self) -> None:
        """Очистить кэш векторного поиска."""
        self.search_engine.clear_cache()
        logger.debug("🗑️ Кэш векторного поиска очищен")

    def get_stats(self) -> Dict[str, int]:
        """
        Получить статистику векторного индекса.

        Returns:
            Dict со статистикой по коллекциям
        """
        return self.search_engine.get_stats()

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Получить статистику кэша.

        Returns:
            Dict со статистикой кэша
        """
        return self.search_engine.get_cache_stats()

    def log_stats(self) -> None:
        """Логировать статистику векторного индекса."""
        self.search_engine.log_stats()
