"""
Тесты для LLM fallback-провайдера.

Проверяют:
- Переключение между провайдерами при ошибках
- Retry логику с экспоненциальной задержкой
- Статистику провайдеров
- Интеграцию с настройками
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from services.core.llm_provider import (
    LLMMessage,
    LLMResponse,
    LLMProvider,
    LLMProviderError,
    ProviderType,
    ProviderStats,
    OllamaProvider,
    OpenAIProvider,
    AnthropicProvider,
    FallbackLLMProvider,
)


# =============================================================================
# Mock провайдеры для тестирования
# =============================================================================

class MockProvider(LLMProvider):
    """Mock провайдер для тестирования."""

    def __init__(
        self,
        name: str = "mock",
        provider_type: ProviderType = ProviderType.OLLAMA,
        should_fail: bool = False,
        fail_count: int = 0,
        response_content: str = "mock response",
        latency_ms: int = 100,
    ) -> None:
        self._name = name
        self._provider_type = provider_type
        self._should_fail = should_fail
        self._fail_count = fail_count
        self._call_count = 0
        self._response_content = response_content
        self._latency_ms = latency_ms
        self._stats = ProviderStats()

    @property
    def name(self) -> str:
        return self._name

    @property
    def provider_type(self) -> ProviderType:
        return self._provider_type

    async def chat(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self._call_count += 1
        self._stats.total_requests += 1

        # Fail на первые N вызовов
        if self._should_fail and self._call_count <= self._fail_count:
            self._stats.failed_requests += 1
            raise LLMProviderError(f"{self.name} failed", provider=self.name)

        self._stats.successful_requests += 1
        return LLMResponse(
            content=self._response_content,
            model=model or "mock-model",
            provider=self.name,
            latency_ms=self._latency_ms,
        )

    async def is_available(self) -> bool:
        return not self._should_fail

    def get_stats(self) -> ProviderStats:
        return self._stats

    @property
    def call_count(self) -> int:
        return self._call_count


# =============================================================================
# Тесты FallbackLLMProvider
# =============================================================================

class TestFallbackLLMProvider:
    """Тесты для FallbackLLMProvider."""

    @pytest.mark.asyncio
    async def test_single_provider_success(self):
        """Тест: единственный провайдер успешен."""
        mock = MockProvider(name="primary", response_content="success")
        fallback = FallbackLLMProvider([mock], retry_attempts=1)

        messages = [LLMMessage(role="user", content="test")]
        response = await fallback.chat(messages)

        assert response.content == "success"
        assert response.provider == "primary"
        assert not response.is_fallback
        assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_fallback_on_first_failure(self):
        """Тест: fallback при неудаче первого провайдера."""
        primary = MockProvider(
            name="primary",
            should_fail=True,
            fail_count=10,  # Всегда падает
        )
        secondary = MockProvider(
            name="secondary",
            response_content="fallback success",
        )

        fallback = FallbackLLMProvider(
            [primary, secondary],
            retry_attempts=2,
            retry_delay_seconds=0.01,  # Быстрый тест
        )

        messages = [LLMMessage(role="user", content="test")]
        response = await fallback.chat(messages)

        assert response.content == "fallback success"
        assert response.provider == "secondary"
        assert response.is_fallback
        assert primary.call_count == 2  # retry_attempts
        assert secondary.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_before_fallback(self):
        """Тест: retry попытки перед fallback."""
        # Провайдер падает первые 2 вызова, затем успешен
        call_count = [0]

        class RetryMockProvider(MockProvider):
            async def chat(self, messages, model=None, temperature=0.7, max_tokens=None):
                call_count[0] += 1
                self._stats.total_requests += 1
                if call_count[0] <= 2:
                    self._stats.failed_requests += 1
                    raise LLMProviderError(f"{self.name} failed", provider=self.name)
                self._stats.successful_requests += 1
                return LLMResponse(
                    content=self._response_content,
                    model=model or "mock-model",
                    provider=self.name,
                    latency_ms=self._latency_ms,
                )

        primary = RetryMockProvider(name="primary", response_content="retry success")

        fallback = FallbackLLMProvider(
            [primary],
            retry_attempts=3,
            retry_delay_seconds=0.01,
        )

        messages = [LLMMessage(role="user", content="test")]
        response = await fallback.chat(messages)

        assert response.content == "retry success"
        assert call_count[0] == 3  # 2失败 + 1 успех

    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        """Тест: все провайдеры недоступны."""
        primary = MockProvider(name="primary", should_fail=True, fail_count=10)
        secondary = MockProvider(name="secondary", should_fail=True, fail_count=10)

        fallback = FallbackLLMProvider(
            [primary, secondary],
            retry_attempts=2,
            retry_delay_seconds=0.01,
        )

        messages = [LLMMessage(role="user", content="test")]

        with pytest.raises(LLMProviderError) as exc_info:
            await fallback.chat(messages)

        assert "Все провайдеры недоступны" in str(exc_info.value)
        assert primary.call_count == 2
        assert secondary.call_count == 2

    @pytest.mark.asyncio
    async def test_fallback_stats(self):
        """Тест: статистика fallback."""
        primary = MockProvider(name="primary", should_fail=True, fail_count=10)
        secondary = MockProvider(name="secondary", response_content="success")

        fallback = FallbackLLMProvider(
            [primary, secondary],
            retry_attempts=1,
            retry_delay_seconds=0.01,
        )

        messages = [LLMMessage(role="user", content="test")]
        await fallback.chat(messages)

        stats = fallback.get_stats()
        assert stats.total_requests == 1
        assert stats.successful_requests == 1
        assert stats.fallback_count == 1

        # Проверка статистики всех провайдеров
        all_stats = fallback.get_all_stats()
        assert "primary" in all_stats
        assert "secondary" in all_stats
        assert all_stats["primary"].failed_requests == 1
        assert all_stats["secondary"].successful_requests == 1

    @pytest.mark.asyncio
    async def test_three_provider_chain(self):
        """Тест: цепочка из трёх провайдеров."""
        primary = MockProvider(name="primary", should_fail=True, fail_count=10)
        secondary = MockProvider(name="secondary", should_fail=True, fail_count=10)
        tertiary = MockProvider(name="tertiary", response_content="tertiary success")

        fallback = FallbackLLMProvider(
            [primary, secondary, tertiary],
            retry_attempts=1,
            retry_delay_seconds=0.01,
        )

        messages = [LLMMessage(role="user", content="test")]
        response = await fallback.chat(messages)

        assert response.content == "tertiary success"
        assert response.provider == "tertiary"
        assert response.is_fallback
        assert primary.call_count == 1
        assert secondary.call_count == 1
        assert tertiary.call_count == 1

    @pytest.mark.asyncio
    async def test_empty_providers_list(self):
        """Тест: пустой список провайдеров."""
        with pytest.raises(ValueError) as exc_info:
            FallbackLLMProvider([])

        assert "Требуется хотя бы один провайдер" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_is_available_any_provider(self):
        """Тест: проверка доступности хотя бы одного провайдера."""
        primary = MockProvider(name="primary", should_fail=True)
        secondary = MockProvider(name="secondary", should_fail=False)

        fallback = FallbackLLMProvider([primary, secondary])

        assert await fallback.is_available() is True

    @pytest.mark.asyncio
    async def test_is_available_all_unavailable(self):
        """Тест: все провайдеры недоступны."""
        primary = MockProvider(name="primary", should_fail=True)
        secondary = MockProvider(name="secondary", should_fail=True)

        fallback = FallbackLLMProvider([primary, secondary])

        assert await fallback.is_available() is False


# =============================================================================
# Тесты интеграции с настройками
# =============================================================================

class TestSettingsIntegration:
    """Тесты интеграции с настройками приложения."""

    @pytest.mark.asyncio
    async def test_create_fallback_from_settings_ollama_only(self):
        """Тест: создание fallback из настроек (только Ollama)."""
        # Создаём mock настроек
        mock_settings = MagicMock()
        mock_settings.llm_primary_provider = 'ollama'
        mock_settings.ollama_base_url = 'http://localhost:11434'
        mock_settings.model_name = 'qwen2.5:7b'
        mock_settings.openai_api_key = None
        mock_settings.anthropic_api_key = None
        mock_settings.llm_retry_attempts = 3
        mock_settings.llm_retry_delay_seconds = 2

        # Патчим _get_settings вместо settings
        with patch('services.core.llm_provider._get_settings', return_value=mock_settings):
            from services.core.llm_provider import create_fallback_provider_from_settings

            fallback = create_fallback_provider_from_settings()

            assert isinstance(fallback, FallbackLLMProvider)
            assert len(fallback.providers) >= 1
            assert fallback.providers[0].provider_type == ProviderType.OLLAMA

    @pytest.mark.asyncio
    async def test_create_fallback_from_settings_with_openai(self):
        """Тест: создание fallback из настроек (Ollama + OpenAI)."""
        mock_settings = MagicMock()
        mock_settings.llm_primary_provider = 'openai'
        mock_settings.openai_api_key = 'sk-test-key'
        mock_settings.openai_model = 'gpt-4o-mini'
        mock_settings.ollama_base_url = 'http://localhost:11434'
        mock_settings.model_name = 'qwen2.5:7b'
        mock_settings.anthropic_api_key = None
        mock_settings.llm_retry_attempts = 3
        mock_settings.llm_retry_delay_seconds = 2

        with patch('services.core.llm_provider._get_settings', return_value=mock_settings):
            from services.core.llm_provider import create_fallback_provider_from_settings

            fallback = create_fallback_provider_from_settings()

            assert isinstance(fallback, FallbackLLMProvider)
            # Первым должен быть OpenAI (основной)
            assert fallback.providers[0].provider_type == ProviderType.OPENAI


# =============================================================================
# Тесты LLMMessage и LLMResponse
# =============================================================================

class TestLLMDataClasses:
    """Тесты для структур данных LLM."""

    def test_llm_message(self):
        """Тест: LLMMessage создание."""
        msg = LLMMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_llm_response(self):
        """Тест: LLMResponse создание."""
        response = LLMResponse(
            content="Test response",
            model="gpt-4",
            provider="openai",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            latency_ms=150,
            is_fallback=True,
        )

        assert response.content == "Test response"
        assert response.model == "gpt-4"
        assert response.provider == "openai"
        assert response.usage["total_tokens"] == 30
        assert response.latency_ms == 150
        assert response.is_fallback is True

    def test_provider_stats_defaults(self):
        """Тест: ProviderStats значения по умолчанию."""
        stats = ProviderStats()

        assert stats.total_requests == 0
        assert stats.successful_requests == 0
        assert stats.failed_requests == 0
        assert stats.fallback_count == 0
        assert stats.avg_latency_ms == 0.0
        assert stats.last_error is None
        assert stats.is_healthy is True


# =============================================================================
# Тесты ProviderType enum
# =============================================================================

class TestProviderType:
    """Тесты для перечисления типов провайдеров."""

    def test_provider_type_values(self):
        """Тест: значения ProviderType."""
        assert ProviderType.OLLAMA.value == "ollama"
        assert ProviderType.OPENAI.value == "openai"
        assert ProviderType.ANTHROPIC.value == "anthropic"
        assert ProviderType.FALLBACK.value == "fallback"
