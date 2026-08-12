"""
Tests for NewsClassifier.
"""

import pytest
from services.categorization.classifier import NewsClassifier, ClassificationResult


class TestNewsClassifier:
    """Тесты для классификатора новостей."""

    def setup_method(self):
        """Настройка перед каждым тестом."""
        self.classifier = NewsClassifier()

    def test_parse_valid_json_response(self):
        """Тест парсинга валидного JSON ответа."""
        response = '''```json
        {
            "text": "Землетрясение магнитудой 7.8",
            "category": "Происшествия",
            "urgency": 5,
            "confidence": 0.95
        }
        ```'''

        result = self.classifier.parse_ai_response(response)

        assert isinstance(result, ClassificationResult)
        assert result.text == "Землетрясение магнитудой 7.8"
        assert result.category == "Происшествия"
        assert result.urgency == 5
        assert result.confidence == 0.95
        assert result.is_advertisement is False

    def test_parse_plain_json(self):
        """Тест парсинга JSON без markdown обёртки."""
        response = '{"text": "Тест", "category": "Политика", "urgency": 3}'

        result = self.classifier.parse_ai_response(response)

        assert result.text == "Тест"
        assert result.category == "Политика"
        assert result.urgency == 3

    def test_parse_advertisement(self):
        """Тест определения рекламы."""
        response = '''{
            "text": "Купите наш товар",
            "category": "Реклама",
            "urgency": 1
        }'''

        result = self.classifier.parse_ai_response(response)

        assert result.is_advertisement is True
        assert result.category == "Реклама"

    def test_parse_invalid_json_fallback(self):
        """Тест fallback при невалидном JSON."""
        response = "Это не JSON ответ"

        result = self.classifier.parse_ai_response(response)

        assert result.text == "Это не JSON ответ"
        assert result.category == "Другое"
        assert result.urgency == 1

    def test_parse_urgency_bounds(self):
        """Тест ограничения срочности (1-5)."""
        # Срочность > 5
        response = '{"text": "Тест", "category": "Тест", "urgency": 10}'
        result = self.classifier.parse_ai_response(response)
        assert result.urgency == 5

        # Срочность < 1
        response = '{"text": "Тест", "category": "Тест", "urgency": 0}'
        result = self.classifier.parse_ai_response(response)
        assert result.urgency == 1

        # Срочность не число
        response = '{"text": "Тест", "category": "Тест", "urgency": "высокая"}'
        result = self.classifier.parse_ai_response(response)
        assert result.urgency == 1

    def test_clean_response_markdown(self):
        """Тест очистки markdown обёрток."""
        # С ```json
        response = '```json\n{"text": "Тест"}\n```'
        cleaned = self.classifier._clean_response(response)
        assert '```' not in cleaned

        # С ```
        response = '```\n{"text": "Тест"}\n```'
        cleaned = self.classifier._clean_response(response)
        assert '```' not in cleaned

        # С "json" в начале
        response = 'json\n{"text": "Тест"}'
        cleaned = self.classifier._clean_response(response)
        assert not cleaned.startswith('json')

    def test_parse_json_from_text(self):
        """Тест извлечения JSON из текста."""
        response = '''
        Вот мой ответ:
        {"text": "Извлечённый текст", "category": "Тест", "urgency": 2}
        Конец ответа.
        '''

        result = self.classifier._parse_json(response)

        assert result['text'] == "Извлечённый текст"
        assert result['category'] == "Тест"
        assert result['urgency'] == 2
