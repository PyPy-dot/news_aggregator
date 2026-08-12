"""
Стратегия обработки срочных новостей (4-5).

Запускает полный цикл АРА (Analyst → Editor → Archivist) немедленно.
"""

import logging
from typing import Any

from services.news.strategies.base import NewsProcessingStrategy
from services.ai_agent.events import Event, EventType
from services.ai_agent.agents import AnalystAgent
from services.news.helpers import find_similar_events, find_similar_posts

logger = logging.getLogger(__name__)


class UrgentNewsStrategy(NewsProcessingStrategy):
    """
    Стратегия для срочных новостей.

    Запускает полный цикл АРА (Analyst → Editor → Archivist) немедленно.
    Отправляет уведомление админам на модерацию.
    """

    @property
    def name(self) -> str:
        return 'urgent'

    async def process(self, post_id: int, **kwargs: Any) -> None:
        """
        Обработать срочную новость.

        Args:
            post_id: ID поста
            **kwargs: text, category, urgency
        """
        text = kwargs.get('text', '')
        category = kwargs.get('category', 'Другое')
        urgency = kwargs.get('urgency', 5)

        logger.info(f"⚡ Срочная новость! ID={post_id}, срочность={urgency}")

        # === ЗАПУСКАЕМ ANALYST ===
        analyst = AnalystAgent()

        # Ищем похожие события и посты для контекста (быстрый поиск)
        similar_events = await find_similar_events(
            text=text,
            category=category,
            limit=3,  # Меньше для скорости
            min_score=0.7
        )
        similar_posts = await find_similar_posts(
            text=text,
            category=category,
            limit=5,  # Меньше для скорости
            min_score=0.6
        )

        # Анализируем новость
        analysis = await analyst.analyze(
            post_text=text,
            similar_events=similar_events,
            similar_posts=similar_posts,
            preliminary_category=category
        )

        logger.info(
            f"🔍 Analyst: категория={analysis['category']}, "
            f"уверенность={analysis['confidence']:.2f}, "
            f"тэгов={len(analysis['post_tags'])}"
        )

        # Обновляем пост с результатами анализа
        await self.posts_repo.update_category_confidence(
            post_id, analysis['confidence']
        )

        # Добавляем тэги к посту
        if analysis['post_tags']:
            await self.posts_repo.update_post_tags(post_id, analysis['post_tags'])

        # === СОЗДАЁМ КОНТЕКСТ СОБЫТИЯ ===
        context_data = {
            'event_description': text[:200],
            'participants': analysis.get('participants', []),
            'location': analysis.get('location'),
            'timestamp': analysis.get('timestamp'),
            'cause': analysis.get('cause'),
            'consequences': analysis.get('consequences', []),
            'related_topics': [analysis['category']],
            'key_facts': analysis.get('key_facts', [])
        }

        event_id = await self.events_repo.create_event(
            post_id=post_id,
            context_data=context_data,
            event_category=analysis['category'],
            tags=analysis['post_tags'],
        )

        logger.info(f"📝 Событие ID={event_id} создано")

        # === ОТПРАВЛЯЕМ НА ГЕНЕРАЦИЮ НОВОСТИ ===
        await self.event_bus.emit(Event(
            type=EventType.GENERATE_NEWS,
            payload={
                'post_id': post_id,
                'event_id': event_id,
                'text': text,
                'category': analysis['category'],
                'urgency': urgency,
                'urgent': True,
                'already_approved': False,
                # Передаём результаты анализа для Editor
                'analysis': {
                    'is_continuation': analysis.get('is_continuation', False),
                    'related_event_id': analysis.get('related_event_id'),
                    'post_tags': analysis.get('post_tags', []),
                },
                'event_context': context_data
            }
        ))

        logger.info(f"✅ Срочная новость ID={post_id} отправлена на обработку")
