"""
Editor Agent — генерация новостей в журналистском стиле.

Задачи:
- Генерация текста новости (200-400 слов)
- Заголовок (до 80 символов)
- Саммари (1 предложение)
- Тэги новости (3-5 штук)
"""

import json
import logging
from typing import Optional

from services.ai_agent.agents.base import BaseAgent, queued
from services.ai_agent.agent_queue import TaskPriority
from services.util import load_prompt

logger = logging.getLogger(__name__)


class DirectNewsEditorAgent(BaseAgent):
    """
    Агент-редактор для прямой генерации SMM-постов по описанию админа.

    Использует промпт direct_news_generator.txt для создания ярких,
    цепляющих постов в стиле Telegram-каналов.
    """

    def __init__(self, model: str = 'qwen2.5:7b') -> None:
        """
        Инициализация редактора для прямой генерации.

        Args:
            model: Название модели
        """
        system_prompt = load_prompt('direct_news_generator')
        super().__init__(
            model=model,
            message_history_limit=2,
            system_prompt=system_prompt
        )

    @queued(priority=TaskPriority.HIGH)
    async def generate_from_description(
        self,
        description: str,
    ) -> dict:
        """
        Генерирует SMM-пост из описания админа.

        Args:
            description: Описание от админа (тема, детали, призыв к действию)

        Returns:
            dict: {
                'title': str (с эмодзи),
                'text': str (с форматированием и эмодзи),
                'summary': str,
                'news_tags': list[str]
            }
        """
        prompt = f"""Ты — SMM-редактор Telegram-канала. Создай яркий пост на основе описания:

{description}

⚠️ КРИТИЧНО: Верни ТОЛЬКО JSON без какого-либо текста до или после.

Формат JSON (строго следуй):
{{
    "title": "🔥 Цепляющий заголовок с эмодзи (до 60 символов)",
    "text": "Текст поста с **жирным текстом** и эмодзи\\n\\nРаздели на абзацы",
    "summary": "Одно предложение — суть предложения или анонса",
    "news_tags": ["акция", "скидки", "промокод"]
}}

Требования к контенту:
- Эмодзи: 2-4 штуки (🔥💰🎁⚡📅✅)
- **Жирный текст** для важных цифр, сроков, выгод
- Заголовок: цепляющий, с эмодзи, до 60 символов
- Текст: 100-300 слов, разбит на абзацы
- Тэги: 3-5 ключевых слов

Начни ответ сразу с {{ и закончи }}"""

        response = await self.send_question(prompt)

        try:
            parsed = self.parse_json_response(
                response,
                required_fields=['title', 'text', 'summary']
            )

            return {
                'title': parsed.get('title', '')[:60],
                'text': parsed.get('text', ''),
                'summary': parsed.get('summary', ''),
                'news_tags': parsed.get('news_tags', [])[:5]
            }
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка парсинга ответа редактора (прямая генерация): {e}")
            logger.warning(f"Raw response: {response[:200]}")
            # Fallback — возвращаем описание как есть
            return {
                'title': '📢 Анонс',
                'text': description[:500],
                'summary': description[:100],
                'news_tags': ['анонс', 'новость']
            }


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

    @queued(priority=TaskPriority.NORMAL)
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
