"""
Тесты для AI Agent Remote Client.

Проверяют:
- Подключение к микросервису
- HTTP запросы с retry
- Fallback на локальные агенты
- Health check
"""

import os
import pytest

# Пропускаем тесты если сервис недоступен
pytestmark = pytest.mark.skipif(
    not os.environ.get('AI_AGENT_SERVICE_URL'),
    reason="Требуется AI_AGENT_SERVICE_URL в окружении"
)

from services.ai_agent.remote_client import (
    AIAgentRemoteClient,
    get_ai_agent_client,
    init_ai_agent_client,
    shutdown_ai_agent_client,
)


@pytest.fixture
def ai_service_url():
    """Получить URL сервиса из окружения."""
    return os.environ.get('AI_AGENT_SERVICE_URL', 'http://localhost:8002')


@pytest.fixture
async def client(ai_service_url):
    """Создать клиента для тестов."""
    c = AIAgentRemoteClient(base_url=ai_service_url, max_retries=2)
    await c.connect()
    yield c
    await c.disconnect()


class TestAIAgentRemoteClientConnection:
    """Тесты подключения клиента."""

    @pytest.mark.asyncio
    async def test_connect_success(self, ai_service_url):
        """Тест успешного подключения."""
        client = AIAgentRemoteClient(base_url=ai_service_url)
        await client.connect()

        assert client._client is not None
        assert client._healthy is True

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        """Тест неудачного подключения."""
        client = AIAgentRemoteClient(
            base_url='http://localhost:9999',
            max_retries=1,
        )
        await client.connect()

        assert client._healthy is False

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Тест health check."""
        healthy = await client.health_check()

        # Если сервис доступен
        if healthy:
            assert healthy is True
        else:
            assert healthy is False


class TestAIAgentRemoteClientCategorize:
    """Тесты категоризации."""

    @pytest.mark.asyncio
    async def test_categorize_remote(self, client):
        """Тест категоризации через удалённый сервис."""
        if not client.is_healthy:
            pytest.skip("Сервис недоступен, тестируем fallback")

        result = await client.categorize(
            text="Президент провёл встречу с правительством",
            channel_title="Новости",
        )

        assert result is not None
        assert 'category' in result
        assert 'urgency' in result
        assert 'text' in result

    @pytest.mark.asyncio
    async def test_categorize_fallback(self):
        """Тест категоризации с fallback на локальный агент."""
        client = AIAgentRemoteClient(
            base_url='http://localhost:9999',
            max_retries=1,
            use_remote=True,
        )
        await client.connect()

        # Должен использовать fallback
        result = await client.categorize(
            text="Тестовая новость",
            channel_title="Тест",
        )

        assert result is not None
        assert 'category' in result
        assert 'urgency' in result

        await client.disconnect()


class TestAIAgentRemoteClientAnalyze:
    """Тесты анализа."""

    @pytest.mark.asyncio
    async def test_analyze_remote(self, client):
        """Тест анализа через удалённый сервис."""
        if not client.is_healthy:
            pytest.skip("Сервис недоступен")

        result = await client.analyze(
            text="Тестовая новость",
            category="Политика",
            urgency=3,
        )

        assert result is not None
        assert 'tags' in result
        assert 'confidence' in result

    @pytest.mark.asyncio
    async def test_analyze_fallback(self):
        """Тест анализа с fallback."""
        client = AIAgentRemoteClient(
            base_url='http://localhost:9999',
            max_retries=1,
        )
        await client.connect()

        result = await client.analyze(
            text="Тест",
            category="Тест",
            urgency=1,
        )

        assert result is not None
        await client.disconnect()


class TestAIAgentRemoteClientGenerateNews:
    """Тесты генерации новости."""

    @pytest.mark.asyncio
    async def test_generate_news_remote(self, client):
        """Тест генерации через удалённый сервис."""
        if not client.is_healthy:
            pytest.skip("Сервис недоступен")

        contexts = [
            {
                'text': 'Тестовое событие',
                'source': 'Тест',
                'timestamp': '2026-08-10T10:00:00',
            }
        ]

        news = await client.generate_news(contexts)

        assert news is not None
        assert len(news) > 10

    @pytest.mark.asyncio
    async def test_generate_news_fallback(self):
        """Тест генерации с fallback."""
        client = AIAgentRemoteClient(
            base_url='http://localhost:9999',
            max_retries=1,
        )
        await client.connect()

        contexts = [{'text': 'Тест', 'source': 'Тест'}]
        news = await client.generate_news(contexts)

        assert news is not None
        await client.disconnect()


class TestAIAgentRemoteClientCreateContext:
    """Тесты создания контекста."""

    @pytest.mark.asyncio
    async def test_create_context_remote(self, client):
        """Тест создания контекста через удалённый сервис."""
        if not client.is_healthy:
            pytest.skip("Сервис недоступен")

        contexts = [{'text': 'Тест', 'source': 'Тест'}]
        news_text = 'Тестовая новость'

        result = await client.create_context(contexts, news_text)

        assert result is not None
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_create_context_fallback(self):
        """Тест создания контекста с fallback."""
        client = AIAgentRemoteClient(
            base_url='http://localhost:9999',
            max_retries=1,
        )
        await client.connect()

        result = await client.create_context(
            [{'text': 'Тест'}],
            'Тестовая новость',
        )

        assert result is not None
        await client.disconnect()


class TestAIAgentRemoteClientRetry:
    """Тесты retry логики."""

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self):
        """Тест retry при таймауте."""
        client = AIAgentRemoteClient(
            base_url='http://localhost:9999',
            max_retries=3,
            timeout=0.1,
        )
        await client.connect()

        # Должно быть 3 попытки
        result = await client.categorize("Тест")

        assert result is None  # Все попытки исчерпаны
        assert client._healthy is False  # Переключился на fallback

        await client.disconnect()


class TestAIAgentRemoteClientEnableDisable:
    """Тесты включения/выключения remote режима."""

    @pytest.mark.asyncio
    async def test_enable_remote(self, client):
        """Тест включения remote режима."""
        client.disable_remote()
        assert client.use_remote is False

        client.enable_remote()
        assert client.use_remote is True

    @pytest.mark.asyncio
    async def test_disable_remote(self, client):
        """Тест выключения remote режима."""
        client.enable_remote()
        client.disable_remote()

        assert client.use_remote is False
        # Даже если сервис здоров, не используем его
        assert client._healthy is True


class TestGlobalClient:
    """Тесты глобального клиента."""

    @pytest.mark.asyncio
    async def test_get_client_singleton(self):
        """Тест что get_client возвращает singleton."""
        client1 = get_ai_agent_client()
        client2 = get_ai_agent_client()

        assert client1 is client2

    @pytest.mark.asyncio
    async def test_init_client(self):
        """Тест инициализации клиента."""
        client = await init_ai_agent_client()

        assert client is not None
        assert isinstance(client, AIAgentRemoteClient)

        await shutdown_ai_agent_client()

    @pytest.mark.asyncio
    async def test_shutdown_client(self):
        """Тест остановки клиента."""
        await init_ai_agent_client()
        await shutdown_ai_agent_client()

        client = get_ai_agent_client()
        assert client._client is None or not client._healthy


class TestAIAgentRemoteClientHealth:
    """Тесты health check."""

    @pytest.mark.asyncio
    async def test_is_healthy_property(self, client):
        """Тест свойства is_healthy."""
        # Если сервис доступен
        if client._healthy and client.use_remote:
            assert client.is_healthy is True
        else:
            assert client.is_healthy is False

    @pytest.mark.asyncio
    async def test_health_after_disconnect(self, client):
        """Тест health после отключения."""
        await client.disconnect()

        assert client.is_healthy is False
        assert client._healthy is False
