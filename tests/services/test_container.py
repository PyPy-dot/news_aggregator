"""
Tests for DI Container and DatabaseService.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.core.container import Container
from services.database import IDatabaseService, get_database_service
from services.telegram.notification import NotificationService

# Для обратной совместимости в тестах
DatabaseService = IDatabaseService


class TestDatabaseService:
    """Тесты для IDatabaseService (новый слой абстракции)."""

    @pytest.mark.asyncio
    async def test_init(self):
        """Тест инициализации IDatabaseService."""
        db_service = get_database_service()
        await db_service.connect()  # Явное подключение
        assert db_service is not None
        assert db_service.engine is not None
        assert "sqlite" in db_service.config.resolved_url

    def test_singleton(self):
        """Тест singleton паттерна."""
        db1 = get_database_service()
        db2 = get_database_service()
        assert db1 is db2

    @pytest.mark.asyncio
    async def test_create_session(self):
        """Тест создания сессии."""
        db_service = get_database_service()
        await db_service.connect()  # Явное подключение
        session = await db_service.create_session()
        assert isinstance(session, AsyncSession)
        await session.close()

    @pytest.mark.asyncio
    async def test_session_context(self):
        """Тест контекстного менеджера сессии."""
        db_service = get_database_service()
        await db_service.connect()
        async with db_service.session_context() as session:
            assert isinstance(session, AsyncSession)
            # Контекстный менеджер сам закрывает сессию


class TestContainer:
    """Тесты для DI Container."""

    def test_init(self):
        """Тест инициализации контейнера."""
        container = Container()
        assert container._initialized is False
        # Базовые сервисы зарегистрированы
        assert DatabaseService in container._factories
        assert NotificationService in container._factories
        # CategorizationService не регистрируется автоматически (циклическая зависимость)

    def test_singleton_registration(self):
        """Тест регистрации singleton."""
        container = Container()

        class TestService:
            pass

        container.register_singleton(TestService, lambda: TestService())

        service1 = container.get(TestService)
        service2 = container.get(TestService)

        assert service1 is service2  # Один экземпляр

    def test_factory_registration(self):
        """Тест регистрации factory."""
        container = Container()

        class TestService:
            def __init__(self):
                self.id = id(self)

        container.register_factory(TestService, lambda: TestService())

        service1 = container.get(TestService)
        service2 = container.get(TestService)

        assert service1 is not service2  # Разные экземпляры
        assert service1.id != service2.id

    def test_instance_registration(self):
        """Тест регистрации экземпляра."""
        container = Container()

        class TestService:
            pass

        instance = TestService()
        container.register_instance(TestService, instance)

        assert container.get(TestService) is instance

    def test_get_unregistered_service(self):
        """Тест получения незарегистрированного сервиса."""
        container = Container()

        class TestService:
            pass

        with pytest.raises(ValueError) as exc_info:
            container.get(TestService)

        assert "не зарегистрирован" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_init(self):
        """Тест инициализации контейнера."""
        container = Container()
        await container.init()
        assert container._initialized is True

    @pytest.mark.asyncio
    async def test_dispose(self):
        """Тест освобождения ресурсов."""
        container = Container()
        await container.init()
        await container.dispose()
        assert container._initialized is False
        assert len(container._services) == 0

    @pytest.mark.asyncio
    async def test_session_context(self):
        """Тест контекстного менеджера сессии."""
        container = Container()
        await container.init()

        async with container.session() as session:
            assert isinstance(session, AsyncSession)

    @pytest.mark.asyncio
    async def test_create_orchestrator(self):
        """Тест создания NewsOrchestrator."""
        container = Container()
        await container.init()

        async with container.session() as session:
            orchestrator = await container.create_orchestrator(session)
            assert orchestrator is not None
            assert orchestrator.repo_factory is not None
            assert orchestrator.notification_service is not None
            # Проверяем что стратегии инициализированы
            assert len(orchestrator._strategies) == 3


