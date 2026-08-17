"""
Helpers для News Aggregator.

Эти функции предоставляют удобный интерфейс для работы с репозиториями
и векторным поиском. Используются в orchestrator и strategies.

Примечание: Для нового кода рекомендуется использовать VectorSearchService
через DI контейнер вместо этих helper функций.
"""

import logging
import json
from typing import Optional

from database import RepositoryFactory
from services.database import get_database_service
from services.vector_search import VectorSearchEngine

logger = logging.getLogger(__name__)


async def find_similar_events(
    text: str,
    category: str,
    limit: int = 5,
    min_score: float = 0.7
) -> list:
    """
    Найти похожие события с помощью векторного поиска.

    Args:
        text: Текст для поиска
        category: Категория
        limit: Максимальное количество результатов
        min_score: Минимальный порог сходства (0.0-1.0)

    Returns:
        Список похожих событий с metadata
    """
    try:
        # Используем глобальный экземпляр для обратной совместимости
        search_engine = VectorSearchEngine()
        results = await search_engine.find_similar_events(
            query_text=text,
            category_filter=category,
            limit=limit,
            min_score=min_score,
        )
        logger.debug(f"🔍 Найдено {len(results)} похожих событий для '{text[:50]}...'")
        return results
    except Exception as e:
        # Векторный поиск — опциональная функция, ошибка не критична
        logger.debug(f"⚠️ Векторный поиск событий не выполнен: {e}")
        return []


async def find_similar_posts(
    text: str,
    category: str,
    limit: int = 10,
    min_score: float = 0.6
) -> list:
    """
    Найти похожие посты с помощью векторного поиска.

    Args:
        text: Текст для поиска
        category: Категория
        limit: Максимальное количество результатов
        min_score: Минимальный порог сходства (0.0-1.0)

    Returns:
        Список похожих постов с metadata
    """
    try:
        # Используем глобальный экземпляр для обратной совместимости
        search_engine = VectorSearchEngine()
        results = await search_engine.find_similar_posts(
            query_text=text,
            category_filter=category,
            limit=limit,
            min_score=min_score,
        )
        logger.debug(f"🔍 Найдено {len(results)} похожих постов для '{text[:50]}...'")
        return results
    except Exception as e:
        # Векторный поиск — опциональная функция, ошибка не критична
        logger.debug(f"⚠️ Векторный поиск постов не выполнен: {e}")
        return []


async def add_generated_news(
    text: str,
    category: str,
    tags: list[str],
    source_ids: Optional[list[str]] = None,
    source_event_ids: Optional[list[int]] = None,
    moderation_status: str = 'pending',
    publisher_channel_id: Optional[int] = None,
    index_in_vector_search: bool = True,
) -> int:
    """
    Создать сгенерированную новость.

    Args:
        text: Текст новости
        category: Категория
        tags: Теги новости
        source_ids: ID исходных новостей с префиксом (["tg_5", "rss_13", "web_10"])
        source_event_ids: ID событий
        moderation_status: Статус модерации
        publisher_channel_id: ID канала публикации (опционально)
        index_in_vector_search: Добавить в векторный индекс

    Returns:
        ID созданной новости
    """
    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        news = await factory.news().create_news(
            text=text,
            category=category,
            source_ids=source_ids,
            source_event_ids=source_event_ids,
            tags=tags,
            moderation_status=moderation_status,
            publisher_channel_id=publisher_channel_id,
        )
        news_id = news.id

        # Индексация в векторный поиск
        if index_in_vector_search:
            await add_news_to_vector_index(
                news_id=news_id,
                text=text,
                category=category,
                tags=tags,
            )

        return news_id


async def add_event_context(
    post_id: int,
    context_data: dict,
    event_category: str,
    tags: list,
) -> int:
    """
    Создать контекст события.

    Args:
        post_id: ID оригинального поста
        context_data: Данные контекста
        event_category: Категория события
        tags: Список тегов

    Returns:
        ID созданного события
    """
    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        event = await factory.events().create_event(
            post_id=post_id,
            context_data=context_data,
            event_category=event_category,
            tags=tags,
        )
        return event.id


async def add_event_to_vector_index(
    event_id: int,
    post_id: int,
    context_data: dict,
    event_category: str,
    tags: list[str],
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
        # Используем глобальный экземпляр для обратной совместимости
        search_engine = VectorSearchEngine()

        # Формируем текст для поиска из контекста
        search_text = json.dumps(context_data, ensure_ascii=False)

        await search_engine.add_event(
            id=f"event_{event_id}",
            text=search_text,
            event_category=event_category,
            post_id=post_id,
            tags=tags,
        )
        logger.info(f"📦 Событие ID={event_id} добавлено в векторный индекс")
    except Exception as e:
        logger.error(f"Ошибка добавления события в векторный индекс: {e}")


async def add_news_to_vector_index(
    news_id: int,
    text: str,
    category: str,
    tags: list[str],
) -> None:
    """
    Добавить сгенерированную новость в векторный индекс.

    Args:
        news_id: ID новости
        text: Текст новости
        category: Категория
        tags: Теги новости
    """
    try:
        search_engine = VectorSearchEngine()

        await search_engine.add_news(
            id=f"news_{news_id}",
            text=text,
            category=category,
            tags=tags,
        )
        logger.info(f"📦 Новость ID={news_id} добавлена в векторный индекс")
    except Exception as e:
        logger.error(f"Ошибка добавления новости в векторный индекс: {e}")


async def add_post_to_vector_index(
    post_id: int,
    text: str,
    channel_id: int,
    category: str,
    urgency: int = 1,
) -> None:
    """
    Добавить пост в векторный индекс.

    Args:
        post_id: ID поста
        text: Текст поста (можно enriched: text + category + tags)
        channel_id: ID канала
        category: Категория
        urgency: Срочность (1-5)
    """
    try:
        search_engine = VectorSearchEngine()

        await search_engine.add_post(
            id=f"post_{post_id}",
            text=text,
            channel_id=channel_id,
            category=category,
            urgency=urgency,
        )
        logger.info(f"📦 Пост ID={post_id} добавлен в векторный индекс")
    except Exception as e:
        logger.error(f"Ошибка добавления поста в векторный индекс: {e}")


async def add_rss_to_vector_index(
    rss_id: int,
    text: str,
    category: str,
    tags: list[str],
) -> None:
    """Добавить RSS новость в векторный индекс."""
    try:
        search_engine = VectorSearchEngine()

        await search_engine.add_news(
            id=f"rss_{rss_id}",
            text=text,
            category=category,
            tags=tags,
        )
        logger.info(f"📦 RSS ID={rss_id} добавлена в векторный индекс")
    except Exception as e:
        logger.error(f"Ошибка добавления RSS в векторный индекс: {e}")


async def add_web_to_vector_index(
    web_id: int,
    text: str,
    category: str,
    tags: list[str],
) -> None:
    """Добавить Web новость в векторный индекс."""
    try:
        search_engine = VectorSearchEngine()

        await search_engine.add_news(
            id=f"web_{web_id}",
            text=text,
            category=category,
            tags=tags,
        )
        logger.info(f"📦 Web ID={web_id} добавлена в векторный индекс")
    except Exception as e:
        logger.error(f"Ошибка добавления Web в векторный индекс: {e}")
