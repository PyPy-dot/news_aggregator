"""
NewsClassifier — классификация новостей.

Определяет категорию, срочность и фильтрует рекламу.
"""

import logging
import re
import json
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """
    Результат классификации.

    Attributes:
        text: Очищенный текст новости
        category: Категория новости
        urgency: Уровень срочности (1-5)
        is_advertisement: Флаг рекламы
        confidence: Уверенность классификации (0.0-1.0)
    """
    text: str
    category: str
    urgency: int
    is_advertisement: bool = False
    confidence: float = 0.0


class NewsClassifier:
    """
    Классификатор новостей.

    Парсит ответы AI и извлекает структурированные данные.
    """

    def __init__(self) -> None:
        """Инициализация классификатора."""

    def parse_ai_response(self, response: str) -> ClassificationResult:
        """
        Распарсить ответ AI.

        Args:
            response: Строка с ответом от модели

        Returns:
            ClassificationResult с извлечёнными данными

        Raises:
            ValueError: Если не удалось распарсить JSON
        """
        cleaned = self._clean_response(response)
        parsed = self._parse_json(cleaned)

        # Проверяем на рекламу
        is_ad = parsed.get('category', '').lower() == 'реклама'

        # Нормализуем срочность
        urgency_raw = parsed.get('urgency', 1)
        try:
            urgency = min(5, max(1, int(urgency_raw)))
        except (ValueError, TypeError):
            urgency = 1

        return ClassificationResult(
            text=parsed.get('text', response[:500]),
            category=parsed.get('category', 'Другое'),
            urgency=urgency,
            is_advertisement=is_ad,
            confidence=parsed.get('confidence', 0.0)
        )

    def _clean_response(self, response: str) -> str:
        """
        Очистить ответ от markdown обёрток.

        Args:
            response: Исходный ответ

        Returns:
            Очищенная строка
        """
        cleaned = response.strip()

        # Удаляем markdown code blocks
        cleaned = re.sub(r'^```json\s*', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'^```\s*', '', cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()

        # Удаляем "json" в начале
        cleaned = re.sub(r'^json\s*\n', '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        return cleaned

    def _parse_json(self, text: str) -> dict:
        """
        Распарсить JSON из текста.

        Args:
            text: Текст с JSON

        Returns:
            Распарсенный dict

        Raises:
            ValueError: Если JSON не распарсился
        """
        # Пытаемся найти JSON в тексте
        json_match = re.search(
            r'\{[^{}]*"text"[^{}]*"category"[^{}]*"urgency"[^{}]*\}',
            text,
            re.DOTALL
        )

        if json_match:
            text = json_match.group()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            # Возвращаем дефолтный результат
            return {
                'text': text[:500],
                'category': 'Другое',
                'urgency': 1
            }
