"""
AI Agent Remote Client — клиент для вызова удалённых AI-агентов.

Использует микросервис AI-агентов через HTTP API.
При недоступности сервиса автоматически переключается на локальные агенты (fallback).

Usage:
    client = AIAgentRemoteClient(base_url="http://ai-agent-service:8002")

    # Категоризация
    result = await client.categorize(text, channel_title, channel_desc)

    # Анализ
    result = await client.analyze(text, category, urgency)

    # Генерация новости
    news = await client.generate_news(contexts)

    # Создание контекста
    context = await client.create_context(contexts, news_text)
"""

import logging
import asyncio
from typing import Optional, Any

import httpx

logger = logging.getLogger(__name__)


class AIAgentRemoteClient:
    """
    Клиент для удалённого вызова AI-агентов.

    Attributes:
        base_url: URL микросервиса AI-агентов
        timeout: Таймаут запросов (секунды)
        max_retries: Максимальное количество попыток
        use_remote: Флаг использования удалённого сервиса
    """

    def __init__(
        self,
        base_url: str = "http://ai-agent-service:8002",
        timeout: float = 30.0,
        max_retries: int = 3,
        use_remote: bool = True,
    ) -> None:
        """
        Инициализация клиента.

        Args:
            base_url: URL микросервиса
            timeout: Таймаут запросов
            max_retries: Максимум попыток при ошибке
            use_remote: Использовать ли удалённый сервис (или только локально)
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.use_remote = use_remote

        self._client: Optional[httpx.AsyncClient] = None
        self._healthy = False
        self._local_fallback = None

    async def connect(self) -> None:
        """Подключиться к микросервису."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
        )

        # Проверяем доступность
        self._healthy = await self.health_check()

        if self._healthy:
            logger.info(f"✅ Подключено к AI Agent Service: {self.base_url}")
        else:
            logger.warning(f"⚠️ AI Agent Service недоступен, используем локальные агенты")

    async def disconnect(self) -> None:
        """Отключиться от микросервиса."""
        if self._client:
            await self._client.aclose()
            self._client = None
            self._healthy = False
            logger.info("👋 Отключено от AI Agent Service")

    async def health_check(self) -> bool:
        """
        Проверить доступность сервиса.

        Returns:
            True если сервис доступен
        """
        if not self._client:
            return False

        try:
            response = await self._client.get("/health")
            return response.status_code == 200
        except Exception:
            return False

    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[dict]:
        """
        Выполнить HTTP запрос с retry.

        Args:
            method: HTTP метод
            endpoint: Endpoint URL
            **kwargs: Аргументы для запроса

        Returns:
            Ответ сервера или None при ошибке
        """
        if not self._healthy or not self._client:
            return None

        for attempt in range(self.max_retries):
            try:
                response = await self._client.request(method, endpoint, **kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException:
                logger.warning(f"⏱️ Таймаут запроса {endpoint} (попытка {attempt + 1}/{self.max_retries})")
            except httpx.HTTPStatusError as e:
                logger.error(f"❌ HTTP ошибка {e.response.status_code}: {e}")
                if e.response.status_code < 500:  # Client error - не retry
                    return None
            except httpx.RequestError as e:
                logger.error(f"❌ Ошибка запроса: {e}")
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка: {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(1.0 * (attempt + 1))  # Экспоненциальная задержка

        # Все попытки исчерпаны
        self._healthy = False
        logger.warning("🔄 Переключение на локальные агенты")
        return None

    async def categorize(
        self,
        text: str,
        channel_title: str = "",
        channel_desc: str = "",
    ) -> Optional[dict]:
        """
        Категоризировать новость.

        Args:
            text: Текст новости
            channel_title: Название канала
            channel_desc: Описание канала

        Returns:
            dict: {text, category, urgency} или None при ошибке
        """
        if self.use_remote and self._healthy:
            result = await self._request(
                "POST",
                "/api/v1/categorize",
                json={
                    "text": text,
                    "channel_title": channel_title,
                    "channel_desc": channel_desc,
                },
            )
            if result:
                return result

        # Fallback на локальный агент
        logger.debug("🔄 Используем локальный CategorizerAgent")
        from services.ai_agent.agents.categorizer import CategorizerAgent

        agent = CategorizerAgent()
        return await agent.categorize(text, channel_title, channel_desc)

    async def analyze(
        self,
        text: str,
        category: str,
        urgency: int,
    ) -> Optional[dict]:
        """
        Анализировать новость.

        Args:
            text: Текст новости
            category: Категория
            urgency: Срочность (1-5)

        Returns:
            dict: {tags, confidence, facts} или None при ошибке
        """
        if self.use_remote and self._healthy:
            result = await self._request(
                "POST",
                "/api/v1/analyze",
                json={
                    "text": text,
                    "category": category,
                    "urgency": urgency,
                },
            )
            if result:
                return result

        # Fallback на локальный агент
        logger.debug("🔄 Используем локальный AnalystAgent")
        from services.ai_agent.agents.analyst import AnalystAgent

        agent = AnalystAgent()
        return await agent.analyze(text, category, urgency)

    async def generate_news(self, contexts: list[dict]) -> Optional[str]:
        """
        Сгенерировать новость.

        Args:
            contexts: Список контекстов событий

        Returns:
            Текст новости или None при ошибке
        """
        if self.use_remote and self._healthy:
            result = await self._request(
                "POST",
                "/api/v1/generate-news",
                json={"contexts": contexts},
            )
            if result:
                return result.get("news_text")

        # Fallback на локальный агент
        logger.debug("🔄 Используем локальный EditorAgent")
        from services.ai_agent.agents.editor import EditorAgent

        agent = EditorAgent()
        return await agent.generate_news(contexts)

    async def create_context(
        self,
        contexts: list[dict],
        news_text: str,
    ) -> Optional[dict]:
        """
        Создать контекст для векторного поиска.

        Args:
            contexts: Список контекстов
            news_text: Текст новости

        Returns:
            dict: Структурированный контекст или None при ошибке
        """
        if self.use_remote and self._healthy:
            result = await self._request(
                "POST",
                "/api/v1/create-context",
                json={
                    "contexts": contexts,
                    "news_text": news_text,
                },
            )
            if result:
                return result.get("context")

        # Fallback на локальный агент
        logger.debug("🔄 Используем локальный ArchivistAgent")
        from services.ai_agent.agents.archivist import ArchivistAgent

        agent = ArchivistAgent()
        return await agent.create_context(contexts, news_text)

    @property
    def is_healthy(self) -> bool:
        """Проверить работоспособность сервиса."""
        return self._healthy and self.use_remote

    def enable_remote(self) -> None:
        """Включить использование удалённого сервиса."""
        self.use_remote = True
        logger.info("✅ Включено использование удалённого AI Agent Service")

    def disable_remote(self) -> None:
        """Выключить использование удалённого сервиса (только локальные агенты)."""
        self.use_remote = False
        logger.info("✅ Выключено использование удалённого AI Agent Service")


# =============================================================================
# Singleton для глобального клиента
# =============================================================================

_remote_client: Optional[AIAgentRemoteClient] = None


def get_ai_agent_client() -> AIAgentRemoteClient:
    """
    Получить глобальный клиент AI-агентов.

    Returns:
        AIAgentRemoteClient экземпляр
    """
    global _remote_client

    if _remote_client is None:
        import os

        # Получаем URL из окружения
        base_url = os.environ.get(
            "AI_AGENT_SERVICE_URL",
            "http://ai-agent-service:8002"
        )

        _remote_client = AIAgentRemoteClient(base_url=base_url)

    return _remote_client


async def init_ai_agent_client() -> AIAgentRemoteClient:
    """
    Инициализировать глобальный клиент.

    Returns:
        Инициализированный AIAgentRemoteClient
    """
    client = get_ai_agent_client()
    await client.connect()
    return client


async def shutdown_ai_agent_client() -> None:
    """Остановить глобальный клиент."""
    global _remote_client

    if _remote_client:
        await _remote_client.disconnect()
        _remote_client = None
