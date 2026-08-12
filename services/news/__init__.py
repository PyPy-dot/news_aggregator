"""
News services package.

Модули для обработки новостей:
- orchestrator: Координация обработки новостей
- generation: Генерация новостей через AI агентов
- context: Управление контекстом событий
- moderation: Уведомления о модерации
- helpers: Helper-функции для работы с новостями
"""

from services.news.orchestrator import NewsOrchestrator
from services.news.generation import NewsGenerationService
from services.news.context import EventContextService
from services.news.moderation import ModerationNotificationService
from services.news.helpers import (
    find_similar_events,
    find_similar_posts,
    add_generated_news,
    add_event_context,
)

__all__ = [
    'NewsOrchestrator',
    'NewsGenerationService',
    'EventContextService',
    'ModerationNotificationService',
    'find_similar_events',
    'find_similar_posts',
    'add_generated_news',
    'add_event_context',
]
