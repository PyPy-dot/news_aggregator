"""
Analyst Agent — анализ новостей и извлечение метаданных.

Задачи:
- Оценка категории + confidence (0.0-1.0)
- Определение: продолжение события или новое
- Извлечение тэгов (5-10 штук)
"""

import json
import logging
from typing import Optional

from services.ai_agent.agents.base import BaseAgent, queued
from services.ai_agent.agent_queue import TaskPriority
from services.util import load_prompt

logger = logging.getLogger(__name__)


class AnalystAgent(BaseAgent):
    """
    Агент-аналитик для классификации и тэгирования.

    Атрибуты:
        model: Модель для использования
    """

    def __init__(self, model: str = 'qwen2.5:7b') -> None:
        """
        Инициализация аналитика.

        Args:
            model: Название модели
        """
        system_prompt = load_prompt('analyst')
        super().__init__(
            model=model,
            message_history_limit=3,
            system_prompt=system_prompt
        )

    @queued(priority=TaskPriority.NORMAL)
    async def analyze(
        self,
        post_text: str,
        similar_events: Optional[list[dict]] = None,
        similar_posts: Optional[list] = None,
        preliminary_category: str = 'Другое'
    ) -> dict:
        """
        Анализирует пост и возвращает структурированные данные.

        Args:
            post_text: Текст поста
            similar_events: Похожие события из БД
            similar_posts: Похожие посты из БД
            preliminary_category: Предварительная категория

        Returns:
            dict: {
                'category': str,
                'confidence': float (0.0-1.0),
                'is_continuation': bool,
                'related_event_id': int | None,
                'post_tags': list[str]
            }
        """
        prompt = self._build_prompt(
            post_text,
            similar_events or [],
            similar_posts or [],
            preliminary_category
        )
        response = await self.send_question(prompt)

        try:
            parsed = self.parse_json_response(
                response,
                required_fields=['category', 'confidence', 'is_continuation']
            )

            return {
                'category': parsed.get('category', preliminary_category),
                'confidence': self._clamp_confidence(parsed.get('confidence', 0.5)),
                'is_continuation': parsed.get('is_continuation', False),
                'related_event_id': parsed.get('related_event_id'),
                'post_tags': parsed.get('post_tags', [])
            }
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка парсинга ответа аналитика: {e}")
            return {
                'category': preliminary_category,
                'confidence': 0.5,
                'is_continuation': False,
                'related_event_id': None,
                'post_tags': []
            }

    def _build_prompt(
        self,
        post_text: str,
        similar_events: list[dict],
        similar_posts: list,
        preliminary_category: str
    ) -> str:
        """Строит промпт для аналитика."""
        events_str = "\n".join([
            f"- {e.get('event_description', 'не указано')}"
            for e in similar_events[:5]
        ]) if similar_events else "Нет похожих событий"

        posts_str = "\n".join([
            f"- {p.text[:100]}..." if hasattr(p, 'text') else f"- {p[:100]}..."
            for p in similar_posts[:10]
        ]) if similar_posts else "Нет похожих постов"

        return f"""Ты — медиа-аналитик. Твоя задача — классифицировать и тегировать новость.

## Входные данные

### Оригинальный пост
{post_text}

### Категория от категорайзера
{preliminary_category}

### Похожие события (из базы)
{events_str}

### Похожие посты (из базы)
{posts_str}

## Твои задачи

1. **Подтверди или отклони категорию** (уверенность 0.0-1.0)
2. **Определи**: это продолжение существующего события или новое?
   - Если продолжение → укажи related_event_id
   - Если новое → is_continuation=false
3. **Извлеки 5-10 тэгов** (ключевые слова для поиска: имена, локации, организации)

## Формат вывода

Строго JSON без markdown:
{{
    "category": "Политика",
    "confidence": 0.85,
    "is_continuation": true,
    "related_event_id": 42,
    "post_tags": ["Зеленский", "США", "помощь", "Киев"]
}}"""

    @staticmethod
    def _clamp_confidence(confidence: float) -> float:
        """Ограничивает confidence диапазоном 0.0-1.0."""
        try:
            return min(1.0, max(0.0, float(confidence)))
        except (ValueError, TypeError):
            return 0.5
