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
from typing import Any, Callable, Dict, Optional, Type, TypeVar, AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from services.core.database import DatabaseService, get_database_service
from database import RepositoryFactory
from config.settings import settings

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

        return NewsOrchestrator(
            repo_factory=repo_factory,
            model=settings.agent_model,
            notification_service=notification_service,
        )

    def _register_defaults(self) -> None:
        """Зарегистрировать базовые зависимости."""

        # DatabaseService — singleton
        self.register_singleton(DatabaseService, lambda: DatabaseService())

        # NotificationService — singleton (lazy import для избежания циклической зависимости)
        def _create_notification_service():
            from services.telegram.notification import NotificationService
            return NotificationService()

        # Регистрируем через строковое имя для избежания циклического импорта
        self._services['NotificationService'] = None
        self._factories['NotificationService'] = _create_notification_service

        # CategorizationService регистрируется отдельно для избежания циклической зависимости

    async def init(self) -> None:
        """Инициализировать контейнер."""
        if self._initialized:
            logger.debug("DI контейнер уже инициализирован")
            return

        logger.info("🔧 Инициализация DI контейнера...")

        # Инициализируем DatabaseService
        db_service = self.get(DatabaseService)
        logger.info(f"✅ DatabaseService готов: {db_service.database_url}")

        self._initialized = True
        logger.info("✅ DI контейнер инициализирован")

    async def dispose(self) -> None:
        """Освободить ресурсы контейнера."""
        if self._disposed:
            logger.debug("DI контейнер уже утилизирован")
            return

        logger.info("👋 Освобождение ресурсов DI контейнера...")

        # Освобождаем DatabaseService
        if DatabaseService in self._services and self._services[DatabaseService]:
            try:
                await self._services[DatabaseService].dispose()
                logger.info("✅ DatabaseService остановлен")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки DatabaseService: {e}")

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
        db_service = self.get(DatabaseService)
        async with db_service.session_context() as session:
            yield session


# Глобальный контейнер (singleton)
_container: Optional[Container] = None


def get_container() -> Container:
    """
    Получить глобальный контейнер (singleton).

    Returns:
        Container экземпляр
    """
    global _container
    if _container is None:
        _container = Container()
    return _container


async def init_container() -> Container:
    """
    Инициализировать глобальный контейнер.

    Returns:
        Инициализированный Container
    """
    container = get_container()
    await container.init()
    return container


async def dispose_container() -> None:
    """
    Утилизировать глобальный контейнер.

    Вызывается при завершении приложения.
    """
    global _container
    if _container is not None:
        await _container.dispose()
        _container = None
