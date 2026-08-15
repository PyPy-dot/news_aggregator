"""
Тесты для фабрики сервисов базы данных.
"""

import pytest

from services.database.factory import DatabaseServiceFactory
from services.database.config import DatabaseConfig
from services.database.enums import DatabaseType
from services.database.providers import (
    SQLiteDatabaseService,
    PostgreSQLDatabaseService,
    MySQLDatabaseService,
)
from services.database.exceptions import ProviderNotFoundError


class TestDatabaseServiceFactoryCreate:
    """Тесты создания сервиса через фабрику."""

    def test_create_from_sqlite_config(self):
        """Создание сервиса для SQLite из конфигурации."""
        config = DatabaseConfig.from_sqlite('test.db')
        service = DatabaseServiceFactory.create(config)
        assert isinstance(service, SQLiteDatabaseService)
        assert service.db_type == DatabaseType.SQLITE

    def test_create_from_postgresql_config(self):
        """Создание сервиса для PostgreSQL из конфигурации."""
        config = DatabaseConfig.from_postgresql(
            host='localhost',
            database='testdb',
            username='test',
            password='test'
        )
        service = DatabaseServiceFactory.create(config)
        assert isinstance(service, PostgreSQLDatabaseService)
        assert service.db_type == DatabaseType.POSTGRESQL

    def test_create_from_mysql_config(self):
        """Создание сервиса для MySQL из конфигурации."""
        config = DatabaseConfig.from_mysql(
            host='localhost',
            database='testdb',
            username='test',
            password='test'
        )
        service = DatabaseServiceFactory.create(config)
        assert isinstance(service, MySQLDatabaseService)
        assert service.db_type == DatabaseType.MYSQL


class TestDatabaseServiceFactoryCreateFromUrl:
    """Тесты создания сервиса из URL."""

    def test_create_from_url_sqlite(self):
        """Создание сервиса для SQLite из URL."""
        service = DatabaseServiceFactory.create_from_url('sqlite+aiosqlite:///test.db')
        assert isinstance(service, SQLiteDatabaseService)

    def test_create_from_url_postgresql(self):
        """Создание сервиса для PostgreSQL из URL."""
        service = DatabaseServiceFactory.create_from_url(
            'postgresql+asyncpg://user:pass@localhost/testdb'
        )
        assert isinstance(service, PostgreSQLDatabaseService)

    def test_create_from_url_mysql(self):
        """Создание сервиса для MySQL из URL."""
        service = DatabaseServiceFactory.create_from_url(
            'mysql+aiomysql://user:pass@localhost/testdb'
        )
        assert isinstance(service, MySQLDatabaseService)


class TestDatabaseServiceFactoryHelperMethods:
    """Тесты вспомогательных методов фабрики."""

    def test_create_sqlite(self):
        """Создание сервиса для SQLite через helper метод."""
        service = DatabaseServiceFactory.create_sqlite('test.db')
        assert isinstance(service, SQLiteDatabaseService)

    def test_create_postgresql(self):
        """Создание сервиса для PostgreSQL через helper метод."""
        service = DatabaseServiceFactory.create_postgresql(
            host='localhost',
            database='testdb',
            username='test'
        )
        assert isinstance(service, PostgreSQLDatabaseService)

    def test_create_mysql(self):
        """Создание сервиса для MySQL через helper метод."""
        service = DatabaseServiceFactory.create_mysql(
            host='localhost',
            database='testdb',
            username='test'
        )
        assert isinstance(service, MySQLDatabaseService)


class TestDatabaseServiceFactoryEdgeCases:
    """Тесты краевых случаев."""

    def test_create_without_config_fallback_to_settings(self):
        """Создание без конфигурации использует настройки приложения."""
        # Если настройки не найдены, используется SQLite по умолчанию
        service = DatabaseServiceFactory.create()
        assert isinstance(service, SQLiteDatabaseService)

    def test_get_registered_providers(self):
        """Получение списка зарегистрированных провайдеров."""
        providers = DatabaseServiceFactory.get_registered_providers()
        assert 'SQLITE' in providers
        assert 'POSTGRESQL' in providers
        assert 'MYSQL' in providers

    def test_unknown_database_type(self):
        """Ошибка при неизвестном типе СУБД."""
        with pytest.raises(ProviderNotFoundError):
            config = DatabaseConfig(url='unknown://localhost/db')
            DatabaseServiceFactory.create(config)


class TestDatabaseServiceFactoryCustomProvider:
    """Тесты регистрации кастомного провайдера."""

    def test_register_custom_provider(self):
        """Регистрация кастомного провайдера."""
        from services.database.providers.base import BaseDatabaseService

        class CustomDBService(BaseDatabaseService):
            @property
            def db_type(self):
                return DatabaseType.UNKNOWN

            def get_provider(self):
                pass

        DatabaseServiceFactory.register_provider(DatabaseType.UNKNOWN, CustomDBService)

        providers = DatabaseServiceFactory.get_registered_providers()
        assert 'UNKNOWN' in providers

        # Очищаем регистрацию
        DatabaseServiceFactory._providers[DatabaseType.UNKNOWN] = None
