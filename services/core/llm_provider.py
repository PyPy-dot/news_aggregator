"""
LLM Provider — абстракция для работы с LLM провайдерами.

Поддерживает:
- Ollama (локальные модели)
- OpenAI API (GPT-4, GPT-4o-mini, и др.)
- Anthropic API (Claude 3/4)
- Fallback-цепочка с автоматическим переключением при ошибках
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Sequence
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Lazy import settings (avoid circular imports)
_settings = None


def _get_settings():
    """Lazy load settings to avoid circular imports."""
    global _settings
    if _settings is None:
        from config.settings import settings
        _settings = settings
    return _settings


class ProviderType(Enum):
    """Типы LLM провайдеров."""
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    FALLBACK = "fallback"


@dataclass
class LLMMessage:
    """Сообщение для LLM."""
    role: str  # 'system', 'user', 'assistant'
    content: str


@dataclass
class LLMResponse:
    """Ответ от LLM."""
    content: str
    model: str
    provider: str = "unknown"
    usage: Optional[Dict[str, int]] = None  # {prompt_tokens, completion_tokens, total_tokens}
    latency_ms: int = 0
    is_fallback: bool = False


@dataclass
class ProviderStats:
    """Статистика провайдера."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    fallback_count: int = 0
    avg_latency_ms: float = 0.0
    last_error: Optional[str] = None
    last_check: Optional[float] = None
    is_healthy: bool = True


class LLMProvider(ABC):
    """
    Абстрактный базовый класс для LLM провайдеров.

    Определяет интерфейс для всех провайдеров.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Название провайдера."""

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        """Тип провайдера."""

    @abstractmethod
    async def chat(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Отправить запрос к LLM.

        Args:
            messages: Список сообщений
            model: Модель для использования
            temperature: Температура генерации
            max_tokens: Максимум токенов в ответе

        Returns:
            Ответ от модели
        """

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Проверить доступность провайдера.

        Returns:
            True если провайдер доступен
        """

    def get_stats(self) -> ProviderStats:
        """Получить статистику провайдера."""
        return ProviderStats()


class LLMProviderError(Exception):
    """Ошибка LLM провайдера."""
    def __init__(self, message: str, provider: str = "unknown"):
        super().__init__(message)
        self.provider = provider
        self.message = message


class OllamaProvider(LLMProvider):
    """
    Провайдер для работы с Ollama.

    Поддерживает локальные модели через Ollama API.
    Встроенный circuit breaker защищает от каскадных сбоев.
    """

    def __init__(
        self,
        base_url: str = 'http://localhost:11434',
        default_model: str = 'qwen2.5:7b',
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        timeout: float = 120.0,  # Увеличено с 60 до 120 секунд для медленных моделей
        request_timeout: float = 90.0,  # Таймаут одного запроса (секунды)
    ) -> None:
        self.base_url = base_url
        self.default_model = default_model
        self._client = None
        self._stats = ProviderStats()
        self._request_timeout = request_timeout

        # Circuit breaker для защиты от каскадных сбоев
        from services.core.circuit_breaker import CircuitBreaker
        self._circuit_breaker = CircuitBreaker(
            name=f"ollama:{base_url}",
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            timeout=timeout,
            expected_exceptions=(Exception,),  # Любые ошибки считаем проблемами
        )

    @property
    def name(self) -> str:
        return 'ollama'

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OLLAMA

    @property
    def client(self):
        """Ленивая инициализация клиента с увеличенными таймаутами."""
        if self._client is None:
            from ollama import AsyncClient
            # Увеличенные таймауты для стабильности при медленном соединении
            self._client = AsyncClient(
                host=self.base_url,
                timeout=self._request_timeout,  # 90 секунд вместо default
            )
        return self._client

    async def chat(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        max_retries: int = 3,
        base_delay: float = 2.0,
    ) -> LLMResponse:
        """
        Отправить запрос к Ollama через circuit breaker с retry-логикой.

        Args:
            max_retries: Максимальное количество повторных попыток
            base_delay: Базовая задержка между попытками (секунды)
        """
        import time
        from ollama import ResponseError

        model = model or self.default_model

        async def _do_chat():
            self._stats.total_requests += 1
            start_time = time.time()

            ollama_messages = [
                {'role': msg.role, 'content': msg.content}
                for msg in messages
            ]

            completion = await self.client.chat(
                model=model,
                messages=ollama_messages,
                options={
                    'temperature': temperature,
                    'num_predict': max_tokens or 2048,
                }
            )

            latency_ms = int((time.time() - start_time) * 1000)
            self._stats.successful_requests += 1
            self._stats.avg_latency_ms = (
                (self._stats.avg_latency_ms * (self._stats.successful_requests - 1) + latency_ms)
                / self._stats.successful_requests
            )

            return LLMResponse(
                content=completion.message.content,
                model=model,
                provider='ollama',
                usage={
                    'prompt_tokens': completion.prompt_eval_count or 0,
                    'completion_tokens': completion.eval_count or 0,
                    'total_tokens': (completion.prompt_eval_count or 0) + (completion.eval_count or 0),
                },
                latency_ms=latency_ms,
            )

        # Retry-логика с экспоненциальной задержкой
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return await self._circuit_breaker.call(_do_chat)
            except ResponseError as e:
                last_error = e
                self._stats.failed_requests += 1
                self._stats.last_error = f"Ollama API error: {e}"
                logger.error(f"❌ Ollama API error (попытка {attempt + 1}/{max_retries + 1}): {type(e).__name__}: {e}")
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)  # Экспоненциальная задержка
                    logger.warning(f"⏳ Повторная попытка через {delay:.1f}с...")
                    await asyncio.sleep(delay)
                else:
                    raise LLMProviderError(f"Ollama API error: {e}", provider='ollama')
            except asyncio.TimeoutError as e:
                last_error = e
                self._stats.failed_requests += 1
                self._stats.last_error = f"Ollama timeout: {e}"
                logger.warning(f"⏱️ Ollama timeout (попытка {attempt + 1}/{max_retries + 1}): {e}")
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt) * 2  # Более длительная задержка для таймаутов
                    logger.warning(f"⏳ Повторная попытка через {delay:.1f}с...")
                    await asyncio.sleep(delay)
                else:
                    raise LLMProviderError(f"Ollama timeout: {e}", provider='ollama')
            except Exception as e:
                last_error = e
                self._stats.failed_requests += 1
                self._stats.last_error = f"Ollama error: {e}"
                logger.error(f"❌ Ollama error (попытка {attempt + 1}/{max_retries + 1}): {type(e).__name__}: {e}")
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"⏳ Повторная попытка через {delay:.1f}с...")
                    await asyncio.sleep(delay)
                else:
                    raise LLMProviderError(f"Ollama error: {e}", provider='ollama')

        # Не должно произойти, но на всякий случай
        if last_error:
            raise LLMProviderError(f"Ollama error after {max_retries} retries: {last_error}", provider='ollama')

    async def is_available(self) -> bool:
        """Проверить доступность Ollama."""
        try:
            await self.client.list()
            self._stats.is_healthy = True
            self._stats.last_check = asyncio.get_event_loop().time()
            return True
        except Exception as e:
            self._stats.is_healthy = False
            self._stats.last_error = f"Ollama unavailable: {e}"
            logger.debug(f"⚠️ Ollama недоступен: {e}")
            return False

    def get_stats(self) -> ProviderStats:
        """Получить статистику провайдера."""
        return self._stats

    def get_circuit_breaker_state(self) -> Optional[dict]:
        """Получить состояние circuit breaker."""
        if hasattr(self, '_circuit_breaker'):
            return self._circuit_breaker.get_state_dict()
        return None


class OpenAIProvider(LLMProvider):
    """
    Провайдер для работы с OpenAI API.

    Поддерживает GPT-4, GPT-4o, GPT-4o-mini и другие модели.
    Встроенный circuit breaker защищает от каскадных сбоев.
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = 'gpt-4o-mini',
        base_url: Optional[str] = None,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.base_url = base_url
        self._client = None
        self._stats = ProviderStats()

        # Circuit breaker
        from services.core.circuit_breaker import CircuitBreaker
        self._circuit_breaker = CircuitBreaker(
            name=f"openai:{base_url or 'api.openai.com'}",
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            timeout=timeout,
            expected_exceptions=(Exception,),
        )

    @property
    def name(self) -> str:
        return 'openai'

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OPENAI

    @property
    def client(self):
        """Ленивая инициализация клиента."""
        if self._client is None:
            from openai import AsyncOpenAI
            kwargs = {'api_key': self.api_key}
            if self.base_url:
                kwargs['base_url'] = self.base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def chat(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Отправить запрос к OpenAI API через circuit breaker."""
        import time
        from openai import APIError

        model = model or self.default_model

        async def _do_chat():
            self._stats.total_requests += 1
            start_time = time.time()

            openai_messages = [
                {'role': msg.role, 'content': msg.content}
                for msg in messages
            ]

            response = await self.client.chat.completions.create(
                model=model,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            latency_ms = int((time.time() - start_time) * 1000)
            self._stats.successful_requests += 1
            self._stats.avg_latency_ms = (
                (self._stats.avg_latency_ms * (self._stats.successful_requests - 1) + latency_ms)
                / self._stats.successful_requests
            )

            return LLMResponse(
                content=response.choices[0].message.content,
                model=model,
                provider='openai',
                usage={
                    'prompt_tokens': response.usage.prompt_tokens,
                    'completion_tokens': response.usage.completion_tokens,
                    'total_tokens': response.usage.total_tokens,
                },
                latency_ms=latency_ms,
            )

        try:
            return await self._circuit_breaker.call(_do_chat)
        except APIError as e:
            self._stats.failed_requests += 1
            self._stats.last_error = f"OpenAI API error: {e}"
            logger.error(f"❌ OpenAI API error: {type(e).__name__}: {e}")
            raise LLMProviderError(f"OpenAI API error: {e}", provider='openai')
        except Exception as e:
            self._stats.failed_requests += 1
            self._stats.last_error = f"OpenAI error: {e}"
            logger.error(f"❌ OpenAI error: {type(e).__name__}: {e}")
            raise LLMProviderError(f"OpenAI error: {e}", provider='openai')

    async def is_available(self) -> bool:
        """Проверить доступность OpenAI API."""
        try:
            await self.client.models.list()
            self._stats.is_healthy = True
            self._stats.last_check = asyncio.get_event_loop().time()
            return True
        except Exception as e:
            self._stats.is_healthy = False
            self._stats.last_error = f"OpenAI unavailable: {e}"
            logger.debug(f"⚠️ OpenAI недоступен: {e}")
            return False

    def get_stats(self) -> ProviderStats:
        """Получить статистику провайдера."""
        return self._stats

    def get_circuit_breaker_state(self) -> Optional[dict]:
        """Получить состояние circuit breaker."""
        if hasattr(self, '_circuit_breaker'):
            return self._circuit_breaker.get_state_dict()
        return None


class AnthropicProvider(LLMProvider):
    """
    Провайдер для работы с Anthropic API.

    Поддерживает Claude 3/4 модели.
    Встроенный circuit breaker защищает от каскадных сбоев.
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = 'claude-sonnet-4-20250514',
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self._client = None
        self._stats = ProviderStats()

        # Circuit breaker
        from services.core.circuit_breaker import CircuitBreaker
        self._circuit_breaker = CircuitBreaker(
            name=f"anthropic:{default_model}",
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            timeout=timeout,
            expected_exceptions=(Exception,),
        )

    @property
    def name(self) -> str:
        return 'anthropic'

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.ANTHROPIC

    @property
    def client(self):
        """Ленивая инициализация клиента."""
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def chat(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Отправить запрос к Anthropic API через circuit breaker."""
        import time
        from anthropic import APIError

        model = model or self.default_model

        async def _do_chat():
            self._stats.total_requests += 1
            start_time = time.time()

            # Anthropic требует system message отдельно
            system_message = ""
            anthropic_messages = []

            for msg in messages:
                if msg.role == 'system':
                    system_message = msg.content
                else:
                    anthropic_messages.append({
                        'role': msg.role,
                        'content': msg.content
                    })

            response = await self.client.messages.create(
                model=model,
                max_tokens=max_tokens or 2048,
                system=system_message,
                messages=anthropic_messages,
                temperature=temperature,
            )

            latency_ms = int((time.time() - start_time) * 1000)
            self._stats.successful_requests += 1
            self._stats.avg_latency_ms = (
                (self._stats.avg_latency_ms * (self._stats.successful_requests - 1) + latency_ms)
                / self._stats.successful_requests
            )

            return LLMResponse(
                content=response.content[0].text,
                model=model,
                provider='anthropic',
                usage={
                    'prompt_tokens': response.usage.input_tokens,
                    'completion_tokens': response.usage.output_tokens,
                    'total_tokens': response.usage.input_tokens + response.usage.output_tokens,
                },
                latency_ms=latency_ms,
            )

        try:
            return await self._circuit_breaker.call(_do_chat)
        except APIError as e:
            self._stats.failed_requests += 1
            self._stats.last_error = f"Anthropic API error: {e}"
            logger.error(f"❌ Anthropic API error: {type(e).__name__}: {e}")
            raise LLMProviderError(f"Anthropic API error: {e}", provider='anthropic')
        except Exception as e:
            self._stats.failed_requests += 1
            self._stats.last_error = f"Anthropic error: {e}"
            logger.error(f"❌ Anthropic error: {type(e).__name__}: {e}")
            raise LLMProviderError(f"Anthropic error: {e}", provider='anthropic')

    async def is_available(self) -> bool:
        """Проверить доступность Anthropic API."""
        try:
            await self.client.messages.create(
                model=self.default_model,
                max_tokens=1,
                messages=[{'role': 'user', 'content': '.'}]
            )
            self._stats.is_healthy = True
            self._stats.last_check = asyncio.get_event_loop().time()
            return True
        except Exception as e:
            self._stats.is_healthy = False
            self._stats.last_error = f"Anthropic unavailable: {e}"
            logger.debug(f"⚠️ Anthropic недоступен: {e}")
            return False

    def get_stats(self) -> ProviderStats:
        """Получить статистику провайдера."""
        return self._stats

    def get_circuit_breaker_state(self) -> Optional[dict]:
        """Получить состояние circuit breaker."""
        if hasattr(self, '_circuit_breaker'):
            return self._circuit_breaker.get_state_dict()
        return None


class FallbackLLMProvider(LLMProvider):
    """
    Fallback-провайдер с автоматическим переключением между провайдерами.

    Стратегия:
    1. Попытка выполнить запрос через основной провайдер
    2. При ошибке — retry с экспоненциальной задержкой
    3. После исчерпания retry — переключение на следующий провайдер в цепочке
    4. Логирование всех переключений и статистики
    """

    def __init__(
        self,
        providers: Sequence[LLMProvider],
        retry_attempts: int = 3,
        retry_delay_seconds: float = 2.0,
    ) -> None:
        """
        Инициализация fallback-провайдера.

        Args:
            providers: Список провайдеров в порядке приоритета
            retry_attempts: Количество попыток перед fallback
            retry_delay_seconds: Задержка между попытками
        """
        if not providers:
            raise ValueError("Требуется хотя бы один провайдер")

        self._providers = list(providers)
        self._retry_attempts = retry_attempts
        self._retry_delay = retry_delay_seconds
        self._stats = ProviderStats()

    @property
    def name(self) -> str:
        return 'fallback'

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.FALLBACK

    @property
    def providers(self) -> List[LLMProvider]:
        """Список провайдеров."""
        return self._providers

    @property
    def primary_provider(self) -> LLMProvider:
        """Основной провайдер (первый в списке)."""
        return self._providers[0]

    async def chat(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Отправить запрос с fallback-логикой.

        Последовательность:
        1. Попытка через текущий провайдер
        2. При ошибке — retry с экспоненциальной задержкой
        3. После исчерпания retry — следующий провайдер
        """
        self._stats.total_requests += 1

        for i, provider in enumerate(self._providers):
            last_error = None

            # Попытки через текущий провайдер
            for attempt in range(self._retry_attempts):
                try:
                    logger.debug(
                        f"📡 Попытка {attempt + 1}/{self._retry_attempts} через {provider.name}..."
                    )

                    response = await provider.chat(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                    # Успех!
                    if i > 0:
                        # Запись fallback-события
                        self._stats.fallback_count += 1
                        response.is_fallback = True
                        logger.warning(
                            f"✅ Fallback сработал: {provider.name} после {i} неудачных провайдеров"
                        )

                    self._stats.successful_requests += 1
                    self._stats.is_healthy = True
                    return response

                except LLMProviderError as e:
                    last_error = e
                    logger.warning(
                        f"⚠️ {provider.name} ошибка (попытка {attempt + 1}/{self._retry_attempts}): {e}"
                    )

                    if attempt < self._retry_attempts - 1:
                        # Экспоненциальная задержка
                        delay = self._retry_delay * (2 ** attempt)
                        logger.debug(f"⏳ Пауза {delay}с перед следующей попыткой...")
                        await asyncio.sleep(delay)

                except Exception as e:
                    last_error = LLMProviderError(str(e), provider=provider.name)
                    logger.warning(
                        f"⚠️ {provider.name} неожиданная ошибка: {type(e).__name__}: {e}"
                    )

                    if attempt < self._retry_attempts - 1:
                        delay = self._retry_delay * (2 ** attempt)
                        await asyncio.sleep(delay)

            # Все попытки исчерпаны — следующий провайдер
            if i < len(self._providers) - 1:
                logger.warning(
                    f"🔄 Переключение с {provider.name} на {self._providers[i + 1].name}"
                )
                self._stats.failed_requests += 1
            else:
                # Последний провайдер тоже не сработал
                self._stats.failed_requests += 1
                self._stats.is_healthy = False
                self._stats.last_error = f"All providers failed. Last error: {last_error}"

                logger.error(
                    f"❌ Все LLM провайдеры недоступны! Последняя ошибка: {last_error}"
                )

                raise LLMProviderError(
                    f"Все провайдеры недоступны. Последняя ошибка: {last_error}",
                    provider='fallback'
                )

        # Недостижимый код, но для type checker
        raise LLMProviderError("Нет доступных провайдеров", provider='fallback')

    async def is_available(self) -> bool:
        """Проверить доступность хотя бы одного провайдера."""
        for provider in self._providers:
            if await provider.is_available():
                return True
        return False

    def get_stats(self) -> ProviderStats:
        """Получить общую статистику."""
        return self._stats

    def get_all_stats(self) -> Dict[str, ProviderStats]:
        """Получить статистику всех провайдеров."""
        return {
            provider.name: provider.get_stats()
            for provider in self._providers
        }


# =============================================================================
# Глобальные функции для получения провайдера
# =============================================================================

_default_provider: Optional[LLMProvider] = None


def create_fallback_provider_from_settings() -> FallbackLLMProvider:
    """
    Создать fallback-провайдер из настроек.

    Returns:
        FallbackLLMProvider с провайдерами из конфига
    """
    settings = _get_settings()

    providers: List[LLMProvider] = []

    # Основной провайдер
    primary = settings.llm_primary_provider.lower()

    if primary == 'ollama':
        providers.append(OllamaProvider(
            base_url=settings.ollama_base_url,
            default_model=settings.model_name,
        ))
    elif primary == 'openai':
        if settings.openai_api_key:
            providers.append(OpenAIProvider(
                api_key=settings.openai_api_key,
                default_model=settings.openai_model,
                base_url=settings.openai_base_url,
            ))
        else:
            logger.warning("⚠️ OpenAI API ключ не указан, пропускаю")
    elif primary == 'anthropic':
        if settings.anthropic_api_key:
            providers.append(AnthropicProvider(
                api_key=settings.anthropic_api_key,
                default_model=settings.anthropic_model,
            ))
        else:
            logger.warning("⚠️ Anthropic API ключ не указан, пропускаю")

    # Fallback провайдеры (автоматически добавляем остальные)
    if primary != 'ollama':
        providers.append(OllamaProvider(
            base_url=settings.ollama_base_url,
            default_model=settings.model_name,
        ))

    if primary != 'openai' and settings.openai_api_key:
        providers.append(OpenAIProvider(
            api_key=settings.openai_api_key,
            default_model=settings.openai_model,
            base_url=settings.openai_base_url,
        ))

    if primary != 'anthropic' and settings.anthropic_api_key:
        providers.append(AnthropicProvider(
            api_key=settings.anthropic_api_key,
            default_model=settings.anthropic_model,
        ))

    if not providers:
        # Fallback по умолчанию — только Ollama
        logger.warning("⚠️ Ни один провайдер не настроен, использую Ollama по умолчанию")
        providers.append(OllamaProvider())

    return FallbackLLMProvider(
        providers=providers,
        retry_attempts=settings.llm_retry_attempts,
        retry_delay_seconds=settings.llm_retry_delay_seconds,
    )


def get_llm_provider() -> LLMProvider:
    """
    Получить LLM провайдер.

    Returns:
        LLM провайдер (fallback по умолчанию)
    """
    global _default_provider
    if _default_provider is None:
        _default_provider = create_fallback_provider_from_settings()
        logger.info(f"✅ LLM провайдер инициализирован: {_default_provider.name}")
    return _default_provider


def set_llm_provider(provider: LLMProvider) -> None:
    """
    Установить LLM провайдер.

    Args:
        provider: Провайдер для установки
    """
    global _default_provider
    _default_provider = provider
    logger.info(f"🔧 LLM провайдер изменён на: {provider.name}")


def reset_llm_provider() -> None:
    """Сбросить провайдер (для тестов)."""
    global _default_provider
    _default_provider = None


__all__ = [
    'LLMMessage',
    'LLMResponse',
    'LLMProvider',
    'LLMProviderError',
    'ProviderType',
    'ProviderStats',
    'OllamaProvider',
    'OpenAIProvider',
    'AnthropicProvider',
    'FallbackLLMProvider',
    'get_llm_provider',
    'set_llm_provider',
    'create_fallback_provider_from_settings',
    'reset_llm_provider',
]
