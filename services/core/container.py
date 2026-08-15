"""
Dependency Injection Container.

Контейнер для управления зависимостями приложения.
Поддерживает:
- Singleton зависимости
- Factory зависимости
- Context-dependent зависимости

Корректное управление жизненным циклом сервисов.
"""

import logging
from typing import Any, Callable, Dict, Optional, Type, TypeVar, AsyncGenerator, TYPE_CHECKING
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from services.database import IDatabaseService, get_database_service
from database import RepositoryFactory

if TYPE_CHECKING:
    from aiogram import Bot
    from services.telegram.notification import NotificationService

logger = logging.getLogger(__name__)

T = TypeVar('T')


class Container:
    """
    DI контейнер для управления зависимостями.

    Пример использования:
        container = Container()
        await container.init()

        # Получить сервис
        db_service = container.get(DatabaseService)

        # Использовать в контексте
        async with container.session() as session:
            factory = RepositoryFactory(session)
    """

    def __init__(self) -> None:
        """Инициализация контейнера."""
        self._services: Dict[type, Any] = {}
        self._factories: Dict[type, Callable] = {}
        self._initialized = False
        self._disposed = False

        # Регистрируем базовые сервисы
        self._register_defaults()

    def register_singleton(self, service_type: Type[T], factory: Callable[[], T]) -> None:
        """
        Зарегистрировать singleton сервис.

        Args:
            service_type: Тип сервиса
            factory: Фабрика для создания
        """
        self._services[service_type] = None  # Будет создан при первом запросе
        self._factories[service_type] = factory

    def register_instance(self, service_type: Type[T], instance: T) -> None:
        """
        Зарегистрировать существующий экземпляр.

        Args:
            service_type: Тип сервиса
            instance: Экземпляр сервиса
        """
        self._services[service_type] = instance

    def register_instance_by_name(self, name: str, instance: Any) -> None:
        """
        Зарегистрировать экземпляр по строковому имени (для сервисов с циклической зависимостью).

        Args:
            name: Имя сервиса
            instance: Экземпляр сервиса
        """
        self._services[name] = instance

    def register_factory(self, service_type: Type[T], factory: Callable[[], T]) -> None:
        """
        Зарегистрировать factory сервис (создаётся каждый раз).

        Args:
            service_type: Тип сервиса
            factory: Фабрика для создания
        """
        self._factories[service_type] = factory

    def get(self, service_type: Type[T] | str) -> T:
        """
        Получить сервис из контейнера.

        Args:
            service_type: Тип сервиса или строковое имя

        Returns:
            Экземпляр сервиса

        Raises:
            RuntimeError: Если контейнер не инициализирован или утилизирован
        """
        if self._disposed:
            logger.warning("⚠️ Попытка получить сервис из утилизированного контейнера")

        # Поддержка строкового имени для сервисов с циклической зависимостью
        if isinstance(service_type, str):
            key = service_type
        else:
            key = service_type

        # Проверяем singleton
        if key in self._services:
            if self._services[key] is not None:
                return self._services[key]
            # singleton с None значением — создаём и сохраняем
            if key in self._factories:
                instance = self._factories[key]()
                self._services[key] = instance
                return instance

        # Factory (создаётся каждый раз)
        if key in self._factories:
            return self._factories[key]()

        raise ValueError(f"Сервис {service_type} не зарегистрирован")

    def get_bot(self) -> Optional['Bot']:
        """
        Получить экземпляр бота из контейнера.

        Returns:
            Bot экземпляр или None
        """
        return self._services.get('Bot')

    def get_notification_service(self) -> Optional['NotificationService']:
        """
        Получить NotificationService из контейнера.

        Returns:
            NotificationService экземпляр или None
        """
        return self._services.get('NotificationService')

    def get_vector_search_service(self) -> Optional['VectorSearchService']:
        """
        Получить VectorSearchService из контейнера.

        Returns:
            VectorSearchService экземпляр или None
        """
        return self.get('VectorSearchService')

    async def create_orchestrator(self, session: AsyncSession):
        """
        Создать NewsOrchestrator с зависимостями.

        Args:
            session: Сессия БД

        Returns:
            NewsOrchestrator экземпляр
        """
        from services.news.orchestrator import NewsOrchestrator

        repo_factory = RepositoryFactory(session)

        # Получаем NotificationService через строковый ключ (lazy import)
        notification_service = self.get('NotificationService')

        # Получаем VectorSearchService через строковый ключ
        vector_search_service = self.get('VectorSearchService')

        return NewsOrchestrator(
            repo_factory=repo_factory,
            notification_service=notification_service,
            vector_search_service=vector_search_service,
        )

    async def create_categorization_components(self, session: AsyncSession):
        """
        Создать компоненты категоризации.

        Args:
            session: Сессия БД

        Returns:
            Dict с компонентами {queue, processor, saver, classifier}
        """
        from services.categorization import (
            CategorizationQueue,
            CategorizationProcessor,
            NewsSaver,
            NewsClassifier,
        )
        from services.ai_agent.agents import CategorizerAgent
        from config.settings import settings

        repo_factory = RepositoryFactory(session)

        # Создаём компоненты
        queue = CategorizationQueue()
        classifier = NewsClassifier()
        saver = NewsSaver(
            posts_repo=repo_factory.posts(),
            channels_repo=repo_factory.channels(),
            events_repo=repo_factory.events(),
        )
        categorizer = CategorizerAgent(model=settings.agent_model)
        notification_service = self.get('NotificationService')

        processor = CategorizationProcessor(
            categorizer=categorizer,
            saver=saver,
            channel_provider=repo_factory.channels(),
            notification_service=notification_service,
        )

        return {
            'queue': queue,
            'processor': processor,
            'saver': saver,
            'classifier': classifier,
            'categorizer': categorizer,
        }

    def _register_defaults(self) -> None:
        """Зарегистрировать базовые зависимости."""

        # IDatabaseService — singleton (используем новый слой абстракции)
        self.register_singleton(IDatabaseService, lambda: get_database_service())

        # NotificationService — singleton (lazy import для избежания циклической зависимости)
        def _create_notification_service():
            from services.telegram.notification import NotificationService
            return NotificationService()

        # Регистрируем через строковое имя для избежания циклического импорта
        self._services['NotificationService'] = None
        self._factories['NotificationService'] = _create_notification_service

        # VectorSearchService — singleton (lazy import)
        def _create_vector_search_service():
            from services.vector_search import VectorSearchService
            return VectorSearchService()

        self._services['VectorSearchService'] = None
        self._factories['VectorSearchService'] = _create_vector_search_service

        # CategorizationService компоненты регистрируются отдельно для избежания циклической зависимости

    async def init(self) -> None:
        """Инициализировать контейнер."""
        if self._initialized:
            logger.debug("DI контейнер уже инициализирован")
            return

        logger.debug("🔧 Инициализация DI контейнера...")

        # Инициализируем IDatabaseService (новый слой абстракции)
        db_service = self.get(IDatabaseService)
        await db_service.connect()  # Явное подключение
        logger.info(f"✅ БД подключена: {db_service.db_type.name}")

        self._initialized = True
        logger.debug("✅ DI контейнер инициализирован")

    async def dispose(self) -> None:
        """Освободить ресурсы контейнера."""
        if self._disposed:
            logger.debug("DI контейнер уже утилизирован")
            return

        logger.info("👋 Освобождение ресурсов DI контейнера...")

        # Освобождаем IDatabaseService
        if IDatabaseService in self._services and self._services[IDatabaseService]:
            try:
                await self._services[IDatabaseService].disconnect()
                logger.info("✅ БД отключена")
            except Exception as e:
                logger.error(f"❌ Ошибка отключения БД: {e}")

        # Очищаем сервисы
        self._services.clear()
        self._factories.clear()
        self._initialized = False
        self._disposed = True

        logger.info("✅ DI контейнер полностью остановлен")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Контекстный менеджер для сессии БД.

        Usage:
            async with container.session() as session:
                factory = RepositoryFactory(session)
        """
        db_service = self.get(IDatabaseService)
        async with db_service.session_context() as session:
            yield session


