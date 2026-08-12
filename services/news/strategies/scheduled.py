"""
Стратегия обработки плановых новостей (1-3).

ВАЖНО: Analyst НЕ запускается здесь — он уже сработал на этапе категоризации.
Плановая обработка (через планировщик) запустит Analyst только если пост
не был проанализирован (checked_at=false и category_confidence=None).
"""

import logging
from typing import Any

from services.news.strategies.base import NewsProcessingStrategy

logger = logging.getLogger(__name__)


class ScheduledNewsStrategy(NewsProcessingStrategy):
    """
    Стратегия для плановых новостей.

    Сохраняет событие для обработки планировщиком.
    Analyst НЕ запускается — пост уже проанализирован при категоризации.
    """

    @property
    def name(self) -> str:
        return 'scheduled'

    async def process(self, post_id: int, **kwargs: Any) -> None:
        """
        Обработать плановую новость.

        Args:
            post_id: ID поста
            **kwargs: text, category, urgency
        """
        text = kwargs.get('text', '')
        category = kwargs.get('category', 'Другое')
        urgency = kwargs.get('urgency', 1)

        logger.info(f"📝 Плановая новость: ID={post_id}, срочность={urgency}")

        # Analyst НЕ запускается — пост уже проанализирован при категоризации
        # category и category_confidence уже установлены CategorizationProcessor

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

        event_id = await self.events_repo.create_event(
            post_id=post_id,
            context_data=context_data,
            event_category=category,
            tags=[],  # Тэги будут добавлены Analyst при плановой обработке если нужно
        )

        logger.info(f"📝 Событие ID={event_id} создано (ожидает планировщика)")
