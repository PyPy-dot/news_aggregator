"""
Editor Agent — генерация новостей в журналистском стиле.

Задачи:
- Генерация текста новости (200-400 слов)
- Заголовок (до 80 символов)
- Саммари (1 предложение)
- Тэги новости (3-5 штук)
"""

import logging
from typing import Optional

from services.ai_agent.agents.base import BaseAgent
from services.util import load_prompt

logger = logging.getLogger(__name__)


class EditorAgent(BaseAgent):
    """
    Агент-редактор для генерации новостей.

    Атрибуты:
        model: Модель для использования
    """

    def __init__(self, model: str = 'qwen2.5:7b') -> None:
        """
        Инициализация редактора.

        Args:
            model: Название модели
        """
        system_prompt = load_prompt('editor')
        super().__init__(
            model=model,
            message_history_limit=3,
            system_prompt=system_prompt
        )

    async def generate_news(
        self,
        post_text: str,
        analysis: dict,
        event_context: Optional[dict] = None
    ) -> dict:
        """
        Генерирует новость в журналистском стиле.

        Args:
            post_text: Оригинальный текст поста
            analysis: Результат анализа от AnalystAgent
            event_context: Контекст события (если есть)

        Returns:
            dict: {
                'title': str,
                'text': str,
                'summary': str,
                'news_tags': list[str]
            }
        """
        prompt = self._build_prompt(post_text, analysis, event_context)
        response = await self.send_question(prompt)

        try:
            parsed = self.parse_json_response(
                response,
                required_fields=['title', 'text', 'summary']
            )

            return {
                'title': parsed.get('title', '')[:80],
                'text': parsed.get('text', ''),
                'summary': parsed.get('summary', ''),
                'news_tags': parsed.get('news_tags', [])
            }
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка парсинга ответа редактора: {e}")
            return {
                'title': analysis.get('category', 'Новость')[:80],
                'text': post_text[:500],
                'summary': post_text[:100],
                'news_tags': analysis.get('post_tags', [])[:5]
            }

    def _build_prompt(
        self,
        post_text: str,
        analysis: dict,
        event_context: Optional[dict]
    ) -> str:
        """Строит промпт для редактора."""
        context_str = ""
        if event_context:
            context_str = f"""
### Контекст события
- Участники: {', '.join(event_context.get('participants', []) or ['не указано'])}
- Описание: {event_context.get('event_description', 'не указано')}
- Место: {event_context.get('location') or 'не указано'}
- Последствия: {', '.join(event_context.get('consequences', []) or ['не указано'])}
- Ключевые факты: {', '.join(event_context.get('key_facts', []) or ['не указано'])}
"""

        return f"""Ты — редактор новостного агентства. Твоя задача — создать профессиональную новость.

## Входные данные

### Оригинальный пост
{post_text}

### Результат анализа
- Категория: {analysis.get('category', 'не указано')}
- Уверенность: {analysis.get('confidence', 0.5)}
- Это продолжение события: {'да' if analysis.get('is_continuation') else 'нет'}
- Тэги поста: {', '.join(analysis.get('post_tags', [])[:5])}
{context_str}

## Твои задачи

1. **Напиши новость** в журналистском стиле (200-400 слов)
   - Перевёрнутая пирамида (важное → детали → контекст)
   - Нейтральный тон, без эмодзи
   - Удали рекламные вставки

2. **Придумай заголовок** (до 80 символов, без кликбейта)

3. **Напиши саммари** (1 предложение — суть новости)

4. **Добавь 3-5 тэгов** новости

## Формат вывода

Строго JSON без markdown:
{{
    "title": "Краткий информативный заголовок",
    "text": "Полный текст новости с абзацами",
    "summary": "Одно предложение — суть",
    "news_tags": ["тег1", "тег2", "тег3"]
}}"""
