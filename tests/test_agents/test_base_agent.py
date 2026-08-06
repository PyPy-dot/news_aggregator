"""
Tests for BaseAgent.

Запуск:
    pytest tests/test_agents/test_base_agent.py -v
"""

import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock

from services.ai_agent.agents.base import BaseAgent


class TestBaseAgent:
    """Тесты для базового класса агента."""

    def test_init_with_system_prompt(self):
        """Тест инициализации с системным промптом."""
        system_prompt = "Ты — полезный ассистент"
        agent = BaseAgent(
            model='qwen2.5:7b',
            system_prompt=system_prompt,
            message_history_limit=5
        )

        assert agent.model == 'qwen2.5:7b'
        assert agent._context_len == 5
        assert len(agent.message_list) == 1
        assert agent.message_list[0]['role'] == 'system'
        assert agent.message_list[0]['content'] == system_prompt

    def test_init_without_system_prompt(self):
        """Тест инициализации без системного промпта."""
        agent = BaseAgent(
            model='qwen2.5:7b',
            message_history_limit=3
        )

        assert agent.model == 'qwen2.5:7b'
        assert agent._context_len == 3
        assert len(agent.message_list) == 0

    def test_init_message_list_with_prompt(self):
        """Тест создания списка сообщений с промптом."""
        system_prompt = "System prompt"
        agent = BaseAgent(system_prompt=system_prompt)

        messages = agent._init_message_list()

        assert len(messages) == 1
        assert messages[0]['role'] == 'system'
        assert messages[0]['content'] == system_prompt

    def test_init_message_list_without_prompt(self):
        """Тест создания списка сообщений без промпта."""
        agent = BaseAgent()

        messages = agent._init_message_list()

        assert len(messages) == 0

    def test_clear_message_list_preserves_system(self):
        """Тест очистки истории с сохранением системного промпта."""
        agent = BaseAgent(system_prompt="System", message_history_limit=3)

        # Добавляем сообщения
        agent.message_list.append({'role': 'user', 'content': 'Hello'})
        agent.message_list.append({'role': 'assistant', 'content': 'Hi'})
        agent.message_list.append({'role': 'user', 'content': 'How are you?'})

        assert len(agent.message_list) == 4

        # Очищаем
        agent.clear_message_list()

        # Должен остаться только системный промпт
        assert len(agent.message_list) == 1
        assert agent.message_list[0]['role'] == 'system'

    def test_clear_message_list_without_system(self):
        """Тест очистки истории без системного промпта."""
        agent = BaseAgent(message_history_limit=3)

        # Добавляем сообщения
        for i in range(5):
            agent.message_list.append({'role': 'user', 'content': f'Message {i}'})

        assert len(agent.message_list) == 5

        # Очищаем
        agent.clear_message_list()

        # Должно остаться 2 последних сообщения (limit=3, но одно уже добавлено)
        assert len(agent.message_list) == 2

    def test_reset(self):
        """Тест полного сброса истории."""
        agent = BaseAgent(system_prompt="System", message_history_limit=3)

        # Добавляем сообщения
        agent.message_list.append({'role': 'user', 'content': 'Hello'})
        agent.message_list.append({'role': 'assistant', 'content': 'Hi'})

        assert len(agent.message_list) == 3

        # Сбрасываем
        agent.reset()

        # Должен остаться только системный промпт
        assert len(agent.message_list) == 1
        assert agent.message_list[0]['role'] == 'system'

    def test_parse_json_response_simple(self):
        """Тест парсинга простого JSON."""
        response = '{"key": "value", "number": 42}'

        result = BaseAgent.parse_json_response(response)

        assert result['key'] == 'value'
        assert result['number'] == 42

    def test_parse_json_response_with_markdown(self):
        """Тест парсинга JSON с markdown обёрткой."""
        response = '''```json
{"key": "value"}
```'''

        result = BaseAgent.parse_json_response(response)

        assert result['key'] == 'value'

    def test_parse_json_response_with_prefix(self):
        """Тест парсинга JSON с префиксом."""
        response = '''json
{"key": "value"}'''

        result = BaseAgent.parse_json_response(response)

        assert result['key'] == 'value'

    def test_parse_json_response_required_fields(self):
        """Тест парсинга с проверкой обязательных полей."""
        response = '{"key": "value"}'

        # Есть требуемое поле
        result = BaseAgent.parse_json_response(response, required_fields=['key'])
        assert result['key'] == 'value'

    def test_parse_json_response_missing_fields(self):
        """Тест парсинга с отсутствующими требуемыми полями."""
        response = '{"key": "value"}'

        # Нет требуемого поля
        result = BaseAgent.parse_json_response(response, required_fields=['missing'])

        assert result['key'] == 'value'
        assert 'missing' not in result

    def test_parse_json_response_invalid(self):
        """Тест парсинга невалидного JSON."""
        response = '{invalid json}'

        with pytest.raises(ValueError, match="Не удалось распарсить JSON"):
            BaseAgent.parse_json_response(response)

    @pytest.mark.asyncio
    async def test_send_question(self):
        """Тест отправки вопроса."""
        with patch('services.ai_agent.agents.base.AsyncClient') as MockClient:
            # Настраиваем мок
            mock_client = AsyncMock()
            MockClient.return_value = mock_client

            mock_response = MagicMock()
            mock_response.message.role = 'assistant'
            mock_response.message.content = 'Ответ'
            mock_client.chat = AsyncMock(return_value=mock_response)

            agent = BaseAgent(model='test-model')

            # Отправляем вопрос
            response = await agent.send_question('Вопрос')

            assert response == 'Ответ'
            assert mock_client.chat.called
            assert len(agent.message_list) == 2  # system + user + assistant
