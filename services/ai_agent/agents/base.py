"""
Base Agent для работы с LLM через Ollama.
"""

import logging
import re
import json
from typing import Optional, Any

from ollama import AsyncClient, ResponseError

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Базовый класс для всех AI агентов.

    Attributes:
        model: Название модели (например, 'qwen2.5:7b')
        message_history_limit: Максимальное количество сообщений в истории
        system_prompt: Системный промпт агента
    """

    def __init__(
        self,
        model: str = 'qwen2.5:7b',
        message_history_limit: int = 5,
        system_prompt: Optional[str] = None,
        base_url: str = 'http://localhost:11434',
    ) -> None:
        """
        Инициализация базового агента.

        Args:
            model: Название модели
            message_history_limit: Лимит истории сообщений
            system_prompt: Системный промпт (загружается из файла)
            base_url: URL Ollama API
        """
        self.model = model
        self.client = AsyncClient(base_url)
        self._context_len = message_history_limit
        self._system_prompt = system_prompt
        self.message_list = self._init_message_list()

    def _init_message_list(self) -> list[dict]:
        """Инициализирует список сообщений с системным промптом."""
        if self._system_prompt:
            return [{'role': 'system', 'content': self._system_prompt}]
        return []

    async def send_message_list(self) -> str:
        """
        Отправляет текущую историю сообщений в LLM.

        Returns:
            Ответ от модели
        """
        try:
            completion = await self.client.chat(
                model=self.model,
                messages=self.message_list
            )
            message = completion.message
            self.message_list.append({
                'role': message.role,
                'content': message.content
            })
            return message.content
        except ResponseError as e:
            logger.error(f"Ollama API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщений: {e}")
            raise

    async def send_question(self, message_text: str) -> str:
        """
        Отправляет вопрос в LLM и возвращает ответ.

        Args:
            message_text: Текст вопроса

        Returns:
            Ответ от модели
        """
        if len(self.message_list) >= self._context_len:
            self.clear_message_list()

        self.message_list.append({
            'role': 'user',
            'content': message_text
        })
        logger.debug(f"Отправка вопроса в AI (длина истории: {len(self.message_list)})")

        return await self.send_message_list()

    def clear_message_list(self):
        """
        Очищает историю сообщений, сохраняя системный промпт.
        """
        has_system = bool(self.message_list) and self.message_list[0]['role'] == 'system'
        system = [self.message_list[0]] if has_system else []
        rest = self.message_list[1:] if has_system else self.message_list

        tail_len = max(self._context_len - len(system), 0)
        self.message_list = system + rest[-tail_len:] if tail_len else system

        logger.debug(f"История очищена, осталось сообщений: {len(self.message_list)}")

    def reset(self):
        """Полный сброс истории сообщений."""
        self.message_list = self._init_message_list()
        logger.info("История сообщений полностью сброшена")

    @staticmethod
    def parse_json_response(response: str, required_fields: Optional[list[str]] = None) -> dict[str, Any]:
        """
        Парсит JSON ответ от модели.

        Args:
            response: Строка с ответом
            required_fields: Список обязательных полей

        Returns:
            Распарсенный JSON

        Raises:
            ValueError: Если JSON не распарсился или нет обязательных полей
        """
        cleaned = response.strip()

        # Удаляем markdown обёртки
        cleaned = re.sub(r'^```json\s*', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'^```\s*', '', cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()
        cleaned = re.sub(r'^json\s*\n', '', cleaned, flags=re.IGNORECASE)

        # Пытаемся найти JSON в тексте
        json_match = re.search(r'\{[^{}]*\}', cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group()

        try:
            parsed = json.loads(cleaned)

            if required_fields:
                missing = [f for f in required_fields if f not in parsed]
                if missing:
                    logger.warning(f"Отсутствуют обязательные поля: {missing}")

            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}\nОтвет: {response[:200]}")
            raise ValueError(f"Не удалось распарсить JSON: {e}")
