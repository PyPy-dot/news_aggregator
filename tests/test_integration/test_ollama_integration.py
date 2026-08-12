"""
Интеграционные тесты для Ollama.

Проверяют:
- Подключение к Ollama серверу
- Генерацию ответов моделью
- Streaming ответы
- Обработку ошибок

Требования:
- Запущенный Ollama сервер (localhost:11434 или в Docker)
- Модель qwen2.5:7b загружена
"""

import os
import pytest
import asyncio
from typing import Optional

# Пропускаем тесты если OLLAMA_HOST не настроен
pytestmark = pytest.mark.skipif(
    not os.environ.get('OLLAMA_HOST'),
    reason="Требуется Ollama (OLLAMA_HOST в окружении)"
)

from services.core.llm_provider import (
    OllamaProvider,
    LLMMessage,
    LLMProviderError,
    get_llm_provider,
)


@pytest.fixture
def ollama_host():
    """Получить Ollama host из окружения."""
    return os.environ.get('OLLAMA_HOST', 'http://localhost:11434')


@pytest.fixture
def model_name():
    """Имя модели для тестов."""
    return os.environ.get('OLLAMA_MODEL', 'qwen2.5:7b')


@pytest.fixture
async def provider(ollama_host):
    """Создать Ollama провайдера для тестов."""
    p = OllamaProvider(base_url=ollama_host)
    yield p
    # Очистка после теста
    await p._session.close()


class TestOllamaConnection:
    """Тесты подключения к Ollama."""

    @pytest.mark.asyncio
    async def test_connection_success(self, provider):
        """Тест успешного подключения."""
        # Проверка что сессия создана
        assert provider._session is not None

    @pytest.mark.asyncio
    async def test_list_models(self, provider):
        """Тест получения списка моделей."""
        models = await provider.list_models()

        assert isinstance(models, list)
        # Хотя бы одна модель должна быть
        assert len(models) > 0

    @pytest.mark.asyncio
    async def test_model_exists(self, provider, model_name):
        """Тест что требуемая модель доступна."""
        models = await provider.list_models()
        model_names = [m.lower() for m in models]

        # Проверяем наличие модели (с учётом что может быть qwen2.5:7b или qwen2.5:7b-instruct)
        found = any(model_name.lower() in m or m in model_name.lower() for m in model_names)
        assert found, f"Модель {model_name} не найдена. Доступные: {models}"


class TestOllamaChat:
    """Тесты чата с Ollama."""

    @pytest.mark.asyncio
    async def test_simple_question(self, provider, model_name):
        """Тест простого вопроса."""
        messages = [
            LLMMessage(role='user', content='Скажи только "OK" если ты меня понимаешь.')
        ]

        response = await provider.chat(messages, model=model_name, temperature=0.5)

        assert response is not None
        assert response.content is not None
        assert len(response.content) > 0
        assert response.provider == 'ollama'
        assert response.latency_ms > 0

    @pytest.mark.asyncio
    async def test_json_response(self, provider, model_name):
        """Тест JSON ответа."""
        messages = [
            LLMMessage(
                role='user',
                content='Верни JSON: {"name": "test", "value": 123}. Только JSON, без пояснений.'
            )
        ]

        response = await provider.chat(messages, model=model_name, temperature=0.1)

        assert response is not None
        assert 'name' in response.content or 'test' in response.content

    @pytest.mark.asyncio
    async def test_context_preservation(self, provider, model_name):
        """Тест сохранения контекста диалога."""
        messages = [
            LLMMessage(role='user', content='Запомни число 42. В следующем вопросе я спрошу его.'),
            LLMMessage(role='assistant', content='Хорошо, я запомнил число 42.'),
            LLMMessage(role='user', content='Какое число я просил запомнить?'),
        ]

        response = await provider.chat(messages, model=model_name, temperature=0.1)

        assert '42' in response.content

    @pytest.mark.asyncio
    async def test_system_prompt(self, provider, model_name):
        """Тест системного промпта."""
        messages = [
            LLMMessage(role='system', content='Ты полезный ассистент. Отвечай кратко.'),
            LLMMessage(role='user', content='Что такое 2 + 2?'),
        ]

        response = await provider.chat(messages, model=model_name, temperature=0.1)

        assert response is not None
        assert '4' in response.content

    @pytest.mark.asyncio
    async def test_long_context(self, provider, model_name):
        """Тест длинного контекста."""
        # Создаём длинный текст
        long_text = "Факт " * 1000

        messages = [
            LLMMessage(
                role='user',
                content=f'Посчитай сколько раз встречается слово "Факт" в этом тексте:\n{long_text}'
            )
        ]

        response = await provider.chat(messages, model=model_name, temperature=0.1)

        assert response is not None
        assert '1000' in response.content


class TestOllamaStreaming:
    """Тесты streaming ответов."""

    @pytest.mark.asyncio
    async def test_stream_response(self, provider, model_name):
        """Тест потокового ответа."""
        messages = [
            LLMMessage(role='user', content='Перечисли числа от 1 до 10.')
        ]

        chunks = []
        async for chunk in provider.chat_stream(messages, model=model_name):
            chunks.append(chunk)

        assert len(chunks) > 0
        full_response = ''.join(chunks)
        assert len(full_response) > 0
        assert '1' in full_response and '10' in full_response


class TestOllamaErrors:
    """Тесты обработки ошибок."""

    @pytest.mark.asyncio
    async def test_invalid_model(self, provider):
        """Тест несуществующей модели."""
        messages = [LLMMessage(role='user', content='Test')]

        with pytest.raises(LLMProviderError):
            await provider.chat(messages, model='nonexistent_model_12345')

    @pytest.mark.asyncio
    async def test_empty_messages(self, provider, model_name):
        """Тест пустых сообщений."""
        with pytest.raises(LLMProviderError):
            await provider.chat([], model=model_name)

    @pytest.mark.asyncio
    async def test_connection_refused(self):
        """Тест отказа подключения."""
        provider = OllamaProvider(base_url='http://localhost:9999')

        messages = [LLMMessage(role='user', content='Test')]

        with pytest.raises(LLMProviderError):
            await provider.chat(messages, model='test')


class TestOllamaProviderStats:
    """Тесты статистики провайдера."""

    @pytest.mark.asyncio
    async def test_stats_tracking(self, provider, model_name):
        """Тест отслеживания статистики."""
        # Делаем несколько запросов
        for i in range(3):
            messages = [LLMMessage(role='user', content=f'Вопрос {i}')]
            await provider.chat(messages, model=model_name)

        stats = provider.get_stats()

        assert stats.total_requests >= 3
        assert stats.successful_requests >= 3
        assert stats.avg_latency_ms > 0
        assert stats.is_healthy is True


class TestGetLLMProvider:
    """Тесты фабрики провайдеров."""

    def test_get_ollama_provider(self, ollama_host):
        """Тест получения Ollama провайдера."""
        old_host = os.environ.get('OLLAMA_HOST')
        os.environ['OLLAMA_HOST'] = ollama_host

        try:
            provider = get_llm_provider('ollama')
            assert isinstance(provider, OllamaProvider)
        finally:
            if old_host:
                os.environ['OLLAMA_HOST'] = old_host
            elif 'OLLAMA_HOST' in os.environ:
                del os.environ['OLLAMA_HOST']

    def test_get_default_provider(self, ollama_host):
        """Тест получения провайдера по умолчанию."""
        old_host = os.environ.get('OLLAMA_HOST')
        os.environ['OLLAMA_HOST'] = ollama_host

        try:
            # По умолчанию должен быть Ollama
            provider = get_llm_provider()
            assert provider.name == 'ollama'
        finally:
            if old_host:
                os.environ['OLLAMA_HOST'] = old_host
            elif 'OLLAMA_HOST' in os.environ:
                del os.environ['OLLAMA_HOST']


class TestOllamaPerformance:
    """Тесты производительности."""

    @pytest.mark.asyncio
    async def test_response_time(self, provider, model_name):
        """Тест времени ответа."""
        messages = [LLMMessage(role='user', content='Скажи привет')]

        import time
        start = time.time()
        response = await provider.chat(messages, model=model_name)
        elapsed = time.time() - start

        # Ответ должен быть получен за разумное время (< 30 секунд)
        assert elapsed < 30, f"Ответ занял слишком долго: {elapsed:.2f}с"
        assert response.latency_ms > 0

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, provider, model_name):
        """Тест параллельных запросов."""
        async def ask_question(i):
            messages = [LLMMessage(role='user', content=f'Вопрос {i}')]
            return await provider.chat(messages, model=model_name)

        # Запускаем 5 параллельных запросов
        results = await asyncio.gather(*[ask_question(i) for i in range(5)])

        assert len(results) == 5
        assert all(r is not None for r in results)
        assert all(len(r.content) > 0 for r in results)
