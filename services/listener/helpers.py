"""
Helper functions для ListenerBot.

Эти функции предоставляют удобный интерфейс для работы с репозиториями.
Используют RepositoryFactory для соблюдения паттерна Repository.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Optional

from database import RepositoryFactory
from services.core.database import get_database_service
from services.vector_search import VectorSearchEngine

logger = logging.getLogger(__name__)

# Глобальный экземпляр поискового движка (ленивая инициализация)
_vector_search_engine: Optional[VectorSearchEngine] = None


def get_vector_search_engine() -> VectorSearchEngine:
    """Получает или создаёт поисковый движок."""
    global _vector_search_engine
    if _vector_search_engine is None:
        _vector_search_engine = VectorSearchEngine()
    return _vector_search_engine


async def get_channel_full(channel_id: int):
    """
    Получить полную информацию о канале.

    Args:
        channel_id: ID канала в Telegram

    Returns:
        Объект Channel или None
    """
    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        return await factory.channels().get_by_telegram_id(channel_id)


async def add_tg_post(
    channel_id: int,
    text: str,
    category: str,
    urgency: int,
    rate: Optional[int] = None,
    source_trust_rating: float = 0.5,
    tags: str = ''
) -> int:
    """
    Создать новый пост в Telegram.

    Args:
        channel_id: ID канала в Telegram
        text: Текст поста
        category: Категория
        urgency: Срочность (1-5)
        rate: Рейтинг новости
        source_trust_rating: Рейтинг доверия источника
        tags: Теги

    Returns:
        ID созданного поста
    """
    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        post = await factory.posts().create_post(
            channel_id=channel_id,
            text=text,
            category=category,
            urgency=urgency,
            rate=rate,
            source_trust_rating=source_trust_rating,
            tags=tags
        )
        return post.id


async def update_channel_trust_rating(channel_id: int) -> bool:
    """
    Обновить рейтинг доверия канала.

    Args:
        channel_id: ID канала в Telegram

    Returns:
        True если обновлён, False если не найден
    """
    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        return await factory.channels().update_trust_rating(channel_id)


async def calculate_news_rate(channel, urgency: int) -> int:
    """
    Рассчитать рейтинг новости на основе доверия канала и срочности.

    Args:
        channel: Объект канала
        urgency: Срочность (1-5)

    Returns:
        Рейтинг новости (0-100)
    """
    if channel is None:
        return 50

    # Базовый рейтинг от доверия канала (0-50)
    trust_component = int(channel.trust_rating * 50)

    # Компонент срочности (0-50)
    urgency_component = int((urgency / 5) * 50)

    return trust_component + urgency_component


async def add_event_context(
    post_id: int,
    context_data: dict,
    event_category: str,
    tags: list,
    summary: str
) -> int:
    """
    Создать контекст события.

    Args:
        post_id: ID оригинального поста
        context_data: Данные контекста
        event_category: Категория события
        tags: Список тегов
        summary: Выжимка для векторного поиска

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
            summary=summary
        )
        return event.id


async def add_generated_news(
    source_post_ids: list[int],
    text: str,
    category: str,
    tags: list[str],
    source_event_ids: Optional[list[int]] = None,
    moderation_status: str = 'pending'
) -> int:
    """
    Создать сгенерированную новость.

    Args:
        source_post_ids: ID исходных постов
        text: Текст новости
        category: Категория
        tags: Теги новости
        source_event_ids: ID событий
        moderation_status: Статус модерации

    Returns:
        ID созданной новости
    """
    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        news = await factory.news().create_news(
            text=text,
            category=category,
            source_post_ids=source_post_ids,
            source_event_ids=source_event_ids,
            tags=tags,
            moderation_status=moderation_status
        )
        return news.id


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
        search_engine = get_vector_search_engine()
        results = await search_engine.find_similar_events(
            query_text=text,
            category_filter=category,
            limit=limit,
            min_score=min_score,
        )
        logger.debug(f"🔍 Найдено {len(results)} похожих событий для '{text[:50]}...'")
        return results
    except Exception as e:
        logger.error(f"Ошибка векторного поиска событий: {e}")
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
        search_engine = get_vector_search_engine()
        results = await search_engine.find_similar_posts(
            query_text=text,
            category_filter=category,
            limit=limit,
            min_score=min_score,
        )
        logger.debug(f"🔍 Найдено {len(results)} похожих постов для '{text[:50]}...'")
        return results
    except Exception as e:
        logger.error(f"Ошибка векторного поиска постов: {e}")
        return []


async def update_post_category_confidence(post_id: int, confidence: float) -> bool:
    """
    Обновить оценку уверенности категории поста.

    Args:
        post_id: ID поста
        confidence: Уверенность (0.0-1.0)

    Returns:
        True если обновлена, False если не найден
    """
    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        return await factory.posts().update_category_confidence(post_id, confidence)


async def add_channel_tag(channel_id: int, tag: str) -> bool:
    """
    Добавить тег каналу.

    Args:
        channel_id: ID канала в Telegram
        tag: Тег для добавления

    Returns:
        True если добавлен, False если не найден
    """
    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        return await factory.channels().add_tag(channel_id, tag)


async def mark_post_analyzed(post_id: int, generated_news_id: Optional[int] = None) -> bool:
    """
    Отметить пост как обработанный Аналитиком.

    Args:
        post_id: ID поста
        generated_news_id: ID сгенерированной новости

    Returns:
        True если обновлён, False если не найден
    """
    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        return await factory.posts().mark_analyzed(post_id, generated_news_id)


async def add_event_to_vector_index(
    event_id: int,
    post_id: int,
    context_data: dict,
    event_category: str,
    summary: str,
    tags: list[str],
) -> None:
    """
    Добавить событие в векторный индекс.

    Args:
        event_id: ID события
        post_id: ID оригинального поста
        context_data: Данные контекста
        event_category: Категория события
        summary: Краткая выжимка
        tags: Теги события
    """
    try:
        search_engine = get_vector_search_engine()

        # Формируем текст для поиска
        search_text = f"{summary} {json.dumps(context_data, ensure_ascii=False)}".strip()

        await search_engine.add_event(
            id=f"event_{event_id}",
            text=search_text,
            event_category=event_category,
            post_id=post_id,
            summary=summary,
            tags=tags,
        )
        logger.info(f"📦 Событие ID={event_id} добавлено в векторный индекс")
    except Exception as e:
        logger.error(f"Ошибка добавления события в векторный индекс: {e}")


async def add_news_to_vector_index(
    news_id: int,
    text: str,
    category: str,
    source_post_ids: list[int],
    tags: list[str],
) -> None:
    """
    Добавить сгенерированную новость в векторный индекс.

    Args:
        news_id: ID новости
        text: Текст новости
        category: Категория
        source_post_ids: ID исходных постов
        tags: Теги новости
    """
    try:
        search_engine = get_vector_search_engine()

        await search_engine.add_news(
            id=f"news_{news_id}",
            text=text,
            category=category,
            source_post_ids=source_post_ids,
            tags=tags,
        )
        logger.info(f"📦 Новость ID={news_id} добавлена в векторный индекс")
    except Exception as e:
        logger.error(f"Ошибка добавления новости в векторный индекс: {e}")
