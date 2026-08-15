"""
Vector Search Routers — обработчики событий для векторного поиска.

Интегрируют AI агентов с векторным поиском через EventBus.
"""


from services.ai_agent.events import EventType, Event
from services.ai_agent.routers import EventBus
from services.news.helpers import (
    add_event_context,
    add_event_to_vector_index,
    add_news_to_vector_index,
    find_similar_events,
)
from services.logging_config import get_logger

logger = get_logger(__name__)


def register_vector_search_handlers(event_bus: EventBus) -> None:
    """
    Регистрирует обработчики событий для векторного поиска.

    Args:
        event_bus: Шина событий для регистрации хендлеров
    """

    @event_bus.on(EventType.CREATE_CONTEXT)
    async def handle_create_context(event: Event) -> None:
        """
        Обработчик создания контекста события.
        После создания контекста добавляет событие в векторный индекс.
        """
        payload = event.payload
        post_id = payload.get('post_id')
        context_data = payload.get('context_data', {})
        event_category = payload.get('category', 'other')
        tags = payload.get('tags', [])

        # Создаём контекст в БД
        event_id = await add_event_context(
            post_id=post_id,
            context_data=context_data,
            event_category=event_category,
            tags=tags,
        )

        # Добавляем в векторный индекс
        if event_id:
            await add_event_to_vector_index(
                event_id=event_id,
                post_id=post_id,
                context_data=context_data,
                event_category=event_category,
                tags=tags,
            )
            logger.info(f"✅ Событие ID={event_id} создано и добавлено в векторный индекс")

    @event_bus.on(EventType.GENERATE_NEWS)
    async def handle_generate_news(event: Event) -> None:
        """
        Обработчик генерации новости.
        После генерации добавляет новость в векторный индекс и отправляет уведомление админам.
        """
        from services.news.helpers import add_generated_news
        from services.ai_agent.agents import EditorAgent
        from services.telegram.notification import NotificationService
        from database.repositories.posts import PostRepository
        from database.repositories.channels import ChannelRepository
        from services.database import get_database_service

        payload = event.payload
        post_id = payload.get('post_id')
        event_context = payload.get('event_context', {})
        category = payload.get('category', 'other')

        # Генерируем новость через EditorAgent
        editor = EditorAgent()
        news_result = await editor.generate(
            post_text=payload.get('text', ''),
            context=event_context,
            analysis=payload.get('analysis', {}),
        )

        # Сохраняем новость в БД
        source_event_ids = [payload.get('event_id')] if payload.get('event_id') else []

        news_id = await add_generated_news(
            text=news_result.get('text', ''),
            category=category,
            tags=news_result.get('tags', []),
            source_event_ids=source_event_ids,
            moderation_status='pending',
        )

        # Добавляем в векторный индекс
        if news_id:
            await add_news_to_vector_index(
                news_id=news_id,
                text=news_result.get('text', ''),
                category=category,
                tags=news_result.get('tags', []),
            )
            logger.info(f"✅ Новость ID={news_id} сгенерирована и добавлена в векторный индекс")

            # Отправляем уведомление админам о новости на модерации
            # Получаем пост и канал для получения информации
            if post_id:
                async with get_database_service().session_context() as session:
                    posts_repo = PostRepository(session)
                    channels_repo = ChannelRepository(session)

                    post = await posts_repo.get(post_id)
                    if post:
                        channel = await channels_repo.get_by_telegram_id(post.channel_id)
                        channel_title = channel.title if channel else 'Неизвестно'

                        notification_service = NotificationService()
                        await notification_service.notify_pending_news(
                            post_id=news_id,  # ID сгенерированной новости
                            text=news_result.get('text', '')[:500],
                            category=category,
                            channel_title=channel_title,
                        )
                        logger.info(f"📬 Отправлено уведомление о новости ID={news_id} на модерации")

    @event_bus.on(EventType.NEW_NEWS)
    async def handle_new_news(event: Event) -> None:
        """
        Обработчик новой новости.
        Проверяет, относится ли пост к существующему событию.
        """
        payload = event.payload
        text = payload.get('text', '')
        category = payload.get('category', 'other')

        # Ищем похожие события
        similar = await find_similar_events(
            text=text,
            category=category,
            limit=1,
            min_score=0.75,
        )

        if similar:
            logger.info(
                f"🔗 Новость относится к событию ID={similar[0]['id']} "
                f"(score={similar[0]['score']:.2f})"
            )
            payload['related_event_id'] = similar[0]['id']
            payload['is_continuation'] = True
        else:
            logger.debug("🆕 Новое событие (аналогов не найдено)")
            payload['is_continuation'] = False

    logger.info("✅ Обработчики векторного поиска зарегистрированы")
