"""
Base Agent для работы с LLM через fallback-провайдер.

Поддерживает:
- Ollama (локальные модели)
- OpenAI API (GPT-4, GPT-4o-mini)
- Anthropic API (Claude 3/4)
- Автоматический fallback при недоступности основного провайдера

Работает через единую очередь задач (AgentTaskQueue).
"""

import logging
import re
import json
import time
import asyncio
from typing import Optional, Any, Callable, Coroutine
from functools import wraps

from config.settings import settings

logger = logging.getLogger(__name__)


def queued(priority: 'TaskPriority' = None):
    """
    Декоратор для выполнения метода агента через очередь.

    Args:
        priority: Приоритет задачи (по умолчанию NORMAL)

    Usage:
        @queued(priority=TaskPriority.HIGH)
        async def categorize(self, text: str) -> dict:
            ...
    """
    from services.ai_agent.agent_queue import TaskPriority, get_agent_queue

    if priority is None:
        priority = TaskPriority.NORMAL

    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Получаем очередь
            queue = get_agent_queue()

            # Если очередь не запущена, выполняем напрямую
            if not queue._running:
                logger.debug(f"⚠️ Очередь не запущена, выполняем {func.__name__} напрямую")
                return await func(self, *args, **kwargs)

            # Добавляем задачу в очередь
            task_id = await queue.add_task(
                self.__class__.__name__,  # agent_name
                func.__name__,            # method_name
                func,                     # method
                self,                     # self (instance)
                *args,                    # остальные аргументы
                priority=priority,
                **kwargs,
            )
            logger.debug(f"📋 Задача {task_id} добавлена в очередь")

            # Ждём выполнения задачи (находим результат в истории)
            while True:
                history = queue.get_history()
                for task in reversed(history):
                    if task.task_id == task_id:
                        if task.status.value >= 3:  # COMPLETED, FAILED, RETRY
                            if task.result is not None:
                                return task.result
                            elif task.error:
                                raise task.error
                await asyncio.sleep(0.1)

        return wrapper
    return decorator


class BaseAgent:
    """
    Базовый класс для всех AI агентов.

    Использует LLM провайдер с поддержкой fallback:
    - Ollama (локально)
    - OpenAI API
    - Anthropic API

    Attributes:
        model: Название модели (например, 'qwen2.5:7b' или 'gpt-4o-mini')
        message_history_limit: Максимальное количество сообщений в истории
        system_prompt: Системный промпт агента
        llm_provider: LLM провайдер (FallbackLLMProvider или конкретный)
    """

    def __init__(
        self,
        model: Optional[str] = None,
        message_history_limit: Optional[int] = None,
        system_prompt: Optional[str] = None,
        llm_provider: Optional[Any] = None,
    ) -> None:
        """
        Инициализация базового агента.

        Args:
            model: Название модели (по умолчанию из конфига)
            message_history_limit: Лимит истории сообщений (по умолчанию из конфига)
            system_prompt: Системный промпт (загружается из файла)
            llm_provider: LLM провайдер (по умолчанию создаётся fallback из настроек)
        """
        self.model = model or settings.agent_model
        self._context_len = message_history_limit or settings.agent_message_history_limit
        self._system_prompt = system_prompt
        self.message_list = self._init_message_list()

        # LLM провайдер (fallback по умолчанию)
        if llm_provider is not None:
            self.llm_provider = llm_provider
        else:
            from services.core.llm_provider import get_llm_provider
            self.llm_provider = get_llm_provider()

        logger.debug(f"✅ AI агент инициализирован: модель={self.model}, провайдер={self.llm_provider.name}")

    def _init_message_list(self) -> list[dict]:
        """Инициализирует список сообщений с системным промптом."""
        if self._system_prompt:
            return [{'role': 'system', 'content': self._system_prompt}]
        return []

    async def send_message_list(self) -> str:
        """
        Отправляет текущую историю сообщений в LLM с retry/fallback логикой.

        Returns:
            Ответ от модели
        """
        from services.core.llm_provider import LLMMessage, LLMProviderError

        # Преобразуем сообщения в формат LLMMessage
        messages = [
            LLMMessage(role=msg['role'], content=msg['content'])
            for msg in self.message_list
        ]

        try:
            response = await self.llm_provider.chat(
                messages=messages,
                model=self.model,
                temperature=0.7,
            )

            # Добавляем ответ в историю
            self.message_list.append({
                'role': 'assistant',
                'content': response.content
            })

            # Логируем если был использован fallback
            if response.is_fallback:
                logger.warning(
                    f"🔄 Fallback сработал для агента {self.__class__.__name__}: "
                    f"использован {response.provider} вместо основного"
                )

            logger.debug(
                f"✅ LLM ответ получен ({response.provider}, "
                f"latency={response.latency_ms}ms, "
                f"tokens={response.usage.get('total_tokens', 'N/A') if response.usage else 'N/A'})"
            )

            return response.content

        except LLMProviderError as e:
            logger.error(f"❌ LLM ошибка после всех попыток fallback: {e}")
            raise

        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при отправке в LLM: {type(e).__name__}: {e}")
            raise

    async def send_question(self, message_text: str, use_cache: bool = True) -> str:
        """
        Отправляет вопрос в LLM и возвращает ответ.

        Args:
            message_text: Текст вопроса
            use_cache: Использовать ли кэш (по умолчанию True)

        Returns:
            Ответ от модели
        """
        # Проверяем кэш
        if use_cache:
            from services.ai_agent.cache import get_llm_cache
            cache = get_llm_cache()

            # Ключ кэша: полный промпт (системный + пользовательский)
            cache_prompt = self._get_cache_prompt(message_text)
            cached_response = await cache.get(cache_prompt, self.model)

            if cached_response is not None:
                logger.info(f"🔄 Кэш hit для запроса (экономия ~2-5с)")
                return cached_response

        if len(self.message_list) >= self._context_len:
            self.clear_message_list()

        self.message_list.append({
            'role': 'user',
            'content': message_text
        })
        logger.debug(f"Отправка вопроса в AI (длина истории: {len(self.message_list)})")

        response = await self.send_message_list()

        # Сохраняем в кэш
        if use_cache:
            from services.ai_agent.cache import get_llm_cache
            cache = get_llm_cache()
            await cache.set(cache_prompt, response, self.model)
            logger.debug(f"💾 Запрос сохранён в кэш (TTL=24ч)")

        return response

    def _get_cache_prompt(self, message_text: str) -> str:
        """
        Создать полный промпт для кэширования.

        Args:
            message_text: Текст пользовательского вопроса

        Returns:
            Полный промпт (системный + пользовательский)
        """
        # Включаем системный промпт для точного匹配
        if self._system_prompt:
            return f"{self._system_prompt}|||{message_text}"
        return message_text

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

    def get_provider_stats(self) -> dict:
        """
        Получить статистику LLM провайдера.

        Returns:
            Dict со статистикой провайдера
        """
        from services.core.llm_provider import FallbackLLMProvider

        if isinstance(self.llm_provider, FallbackLLMProvider):
            return {
                name: {
                    'total': stats.total_requests,
                    'success': stats.successful_requests,
                    'failed': stats.failed_requests,
                    'fallbacks': stats.fallback_count,
                    'avg_latency_ms': round(stats.avg_latency_ms, 2),
                    'healthy': stats.is_healthy,
                    'last_error': stats.last_error,
                }
                for name, stats in self.llm_provider.get_all_stats().items()
            }
        else:
            stats = self.llm_provider.get_stats()
            return {
                self.llm_provider.name: {
                    'total': stats.total_requests,
                    'success': stats.successful_requests,
                    'failed': stats.failed_requests,
                    'avg_latency_ms': round(stats.avg_latency_ms, 2),
                    'healthy': stats.is_healthy,
                }
            }

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
