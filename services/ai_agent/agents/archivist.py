"""
Archivist Agent — структурирование контекста событий.

Задачи:
- Выжимка для векторного поиска (50-100 слов)
- Обновление контекста события
- Связь с другими событиями
- Тэги события (5-10 штук)
"""

import logging
import json
from typing import Optional

from services.ai_agent.agents.base import BaseAgent, queued
from services.ai_agent.agent_queue import TaskPriority
from services.util import load_prompt

logger = logging.getLogger(__name__)


class ArchivistAgent(BaseAgent):
    """
    Агент-архивариус для создания контекста событий.

    Атрибуты:
        model: Модель для использования
    """

    def __init__(self, model: str = 'qwen2.5:7b') -> None:
        """
        Инициализация архивариуса.

        Args:
            model: Название модели
        """
        system_prompt = load_prompt('archivist')
        super().__init__(
            model=model,
            message_history_limit=3,
            system_prompt=system_prompt
        )

    @queued(priority=TaskPriority.LOW)
    async def create_context(
        self,
        post_text: str,
        generated_news: dict,
        analysis: dict,
        existing_context: Optional[dict] = None
    ) -> dict:
        """
        Создаёт или обновляет контекст события.

        Args:
            post_text: Оригинальный текст поста
            generated_news: Результат работы EditorAgent
            analysis: Результат анализа от AnalystAgent
            existing_context: Существующий контекст (если обновление)

        Returns:
            dict: {
                'context_data': dict,
                'embedding_text': str,
                'tags': list[str],
                'related_event_ids': list[int]
            }
        """
        prompt = self._build_prompt(
            post_text,
            generated_news,
            analysis,
            existing_context
        )
        response = await self.send_question(prompt)

        try:
            parsed = self.parse_json_response(response)

            return {
                'context_data': {
                    'participants': parsed.get('participants', []),
                    'event_description': parsed.get('event_description', ''),
                    'location': parsed.get('location'),
                    'timestamp': parsed.get('timestamp'),
                    'cause': parsed.get('cause'),
                    'consequences': parsed.get('consequences', []),
                    'related_topics': parsed.get('related_topics', []),
                    'key_facts': parsed.get('key_facts', [])
                },
                'embedding_text': parsed.get('embedding_text', ''),
                'tags': parsed.get('event_tags', []),
                'related_event_ids': parsed.get('related_event_ids', [])
            }
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка парсинга ответа архивариуса: {e}")
            return {
                'context_data': {
                    'event_description': generated_news.get('summary', post_text[:200]),
                    'participants': [],
                    'location': None,
                    'timestamp': None,
                    'cause': None,
                    'consequences': [],
                    'related_topics': [analysis.get('category', 'не указано')],
                    'key_facts': []
                },
                'embedding_text': post_text[:500],
                'tags': analysis.get('post_tags', [])[:5],
                'related_event_ids': []
            }

    def _build_prompt(
        self,
        post_text: str,
        generated_news: dict,
        analysis: dict,
        existing_context: Optional[dict]
    ) -> str:
        """Строит промпт для архивариуса."""
        existing_str = ""
        if existing_context:
            existing_str = f"""
### Существующий контекст события
{json.dumps(existing_context, ensure_ascii=False)[:500]}...
"""

        return f"""Ты — архивариус новостной базы знаний. Твоя задача — структурировать событие для будущего поиска.

## Входные данные

### Оригинальный пост
{post_text}

### Сгенерированная новость
- Заголовок: {generated_news.get('title', 'не указано')}
- Саммари: {generated_news.get('summary', 'не указано')}

### Анализ
- Категория: {analysis.get('category', 'не указано')}
- Тэги поста: {', '.join(analysis.get('post_tags', [])[:5])}
- Это продолжение: {'да' if analysis.get('is_continuation') else 'нет'}
{existing_str}

## Твои задачи

1. **Создай выжимку для векторного поиска** (50-100 слов)
   - Кто, что, где, когда, почему
   - Ключевые факты и цифры

2. **Структурируй контекст события**:
   - participants: список участников
   - event_description: краткое описание
   - location: место (или null)
   - timestamp: время (или null)
   - cause: причина (или null)
   - consequences: последствия
   - related_topics: связанные темы
   - key_facts: ключевые факты цифрами

3. **Добавь 5-10 тэгов** события (для поиска)

4. **Укажи связи** с другими событиями (если есть)

## Формат вывода

Строго JSON без markdown:
{{
    "embedding_text": "текст для создания эмбеддинга",
    "event_description": "описание события",
    "participants": ["участник1", "участник2"],
    "location": "Киев",
    "timestamp": "2026-08-06 10:00",
    "cause": "Запуск БПЛА",
    "consequences": ["Объявлена тревога"],
    "related_topics": ["БПЛА", "ПВО"],
    "key_facts": ["10 БПЛА сбито"],
    "event_tags": ["тег1", "тег2"],
    "related_event_ids": [1, 2]
}}"""
