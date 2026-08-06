"""
Categorizer Agent — первичная классификация новостей.

Задачи:
- Определение категории новости
- Оценка срочности (1-5)
- Очистка текста от рекламы
"""

import logging
import re
import json
from typing import Optional

from services.ai_agent.agents.base import BaseAgent
from services.util import load_prompt

logger = logging.getLogger(__name__)


class CategorizerAgent(BaseAgent):
    """
    Агент для первичной классификации новостей.

    Атрибуты:
        model: Модель для использования
    """

    def __init__(self, model: str = 'qwen2.5:7b') -> None:
        """
        Инициализация категоризатора.

        Args:
            model: Название модели
        """
        system_prompt = load_prompt('categorizer')
        super().__init__(
            model=model,
            message_history_limit=2,
            system_prompt=system_prompt
        )

    async def categorize(
        self,
        text: str,
        channel_title: str = '',
        channel_desc: str = ''
    ) -> dict:
        """
        Классифицирует новость.

        Args:
            text: Текст новости
            channel_title: Название канала
            channel_desc: Описание канала

        Returns:
            dict: {
                'text': str (очищенный текст),
                'category': str,
                'urgency': int (1-5)
            }
        """
        prompt = self._build_prompt(text, channel_title, channel_desc)
        response = await self.send_question(prompt)

        try:
            parsed = self.parse_json_response(response, required_fields=['text', 'category', 'urgency'])
            return {
                'text': parsed.get('text', ''),
                'category': parsed.get('category', 'Другое'),
                'urgency': self._clamp_urgency(parsed.get('urgency', 1))
            }
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка парсинга ответа категоризатора: {e}")
            return {
                'text': text[:500],
                'category': 'Другое',
                'urgency': 1
            }

    def _build_prompt(self, text: str, title: str, desc: str) -> str:
        """Строит промпт для категоризации."""
        return f"""## Название ресурса
{title}

## Описание ресурса
{desc}

## Текст новости
{text}"""

    @staticmethod
    def _clamp_urgency(urgency: int) -> int:
        """Ограничивает срочность диапазоном 1-5."""
        try:
            return min(5, max(1, int(urgency)))
        except (ValueError, TypeError):
            return 1
