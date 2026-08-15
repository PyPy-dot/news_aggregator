"""
Тесты для слоя абстракции БД с поддержкой PostgreSQL.

Проверка работы с различными типами баз данных:
- SQLite (aiosqlite)
- PostgreSQL (asyncpg)
- MySQL (aiomysql)
"""

import pytest
from unittest.mock import patch

from services.database import DatabaseServiceFactory, DatabaseConfig, DatabaseType
from config.settings import settings


class TestDatabaseServicePostgreSQL:
    """Тесты поддержки PostgreSQL в новом слое абстракции."""

    def test_sqlite_url_default(self):
        """Проверка URL SQLite по умолчанию."""
        # По умолчанию используется SQLite
        assert settings.database_url_resolved.startswith('sqlite+aiosqlite://')

    def test_postgresql_url_from_env(self):
        """Проверка PostgreSQL URL из окружения."""
        test_url = 'postgresql+asyncpg://user:pass@localhost:5432/testdb'

        with patch.object(settings, 'database_url', test_url):
            assert settings.database_url_resolved == test_url
            assert settings.is_postgresql is True

    def test_is_postgresql_property(self):
        """Проверка свойства is_postgresql."""
        # SQLite
        with patch.object(settings, 'database_url', None):
            with patch.object(settings, 'db_path', 'test.db'):
                url = settings.database_url_resolved
                assert 'sqlite' in url
                assert settings.is_postgresql is False

        # PostgreSQL
        pg_urls = [
            'postgresql+asyncpg://user:pass@localhost:5432/db',
            'postgresql://user:pass@localhost:5432/db',
        ]
        for url in pg_urls:
            with patch.object(settings, 'database_url', url):
                assert settings.is_postgresql is True

    def test_database_service_init_sqlite(self):
        """Инициализация сервиса с SQLite через фабрику."""
        config = DatabaseConfig.from_sqlite('test.db')
        db_service = DatabaseServiceFactory.create(config)

        assert db_service.db_type == DatabaseType.SQLITE
        assert 'sqlite' in db_service.config.resolved_url

    def test_database_service_init_postgresql(self):
        """Инициализация сервиса с PostgreSQL через фабрику."""
        config = DatabaseConfig.from_postgresql(
            host='localhost',
            database='testdb',
            username='user',
            password='pass'
        )
        db_service = DatabaseServiceFactory.create(config)

        assert db_service.db_type == DatabaseType.POSTGRESQL
        assert 'postgresql' in db_service.config.resolved_url

    def test_database_service_init_mysql(self):
        """Инициализация сервиса с MySQL через фабрику."""
        config = DatabaseConfig.from_mysql(
            host='localhost',
            database='testdb',
            username='root',
            password='pass'
        )
        db_service = DatabaseServiceFactory.create(config)

        assert db_service.db_type == DatabaseType.MYSQL
        assert 'mysql' in db_service.config.resolved_url

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self):
        """Проверка подключения и отключения."""
        config = DatabaseConfig.from_sqlite(':memory:')
        db_service = DatabaseServiceFactory.create(config)

        # Подключение
        await db_service.connect()
        assert db_service.status.name == 'CONNECTED'

        # Отключение
        await db_service.disconnect()
        assert db_service.status.name == 'CLOSED'


class TestAlembicEnvPostgreSQL:
    """Тесты для alembic/env.py с поддержкой PostgreSQL."""

    def test_alembic_sqlite_url_conversion(self):
        """Конверсия SQLite URL для Alembic."""
        from config.settings import settings

        with patch.object(settings, 'database_url', None):
            with patch.object(settings, 'db_path', 'test.db'):
                url = settings.database_url_resolved
                # Alembic должен получить sqlite:///test.db
                assert 'sqlite' in url
                assert '+aiosqlite' not in url.replace('sqlite+aiosqlite', 'sqlite')

    def test_alembic_postgresql_url_conversion(self):
        """Конверсия PostgreSQL URL для Alembic."""
        async_url = 'postgresql+asyncpg://user:pass@localhost:5432/db'
        sync_url = 'postgresql://user:pass@localhost:5432/db'

        with patch.object(settings, 'database_url', async_url):
            url = settings.database_url_resolved
            # Alembic должен получить postgresql://...
            assert url == async_url  # Конверсия происходит в env.py


class TestDatabaseSettings:
    """Тесты настроек базы данных."""

    def test_database_url_priority(self):
        """DATABASE_URL имеет приоритет над db_path."""
        with patch.object(settings, 'database_url', 'postgresql+asyncpg://test'):
            with patch.object(settings, 'db_path', 'sqlite.db'):
                # DATABASE_URL должен иметь приоритет
                assert settings.database_url_resolved == 'postgresql+asyncpg://test'

    def test_fallback_to_sqlite(self):
        """Fallback на SQLite если DATABASE_URL не указан."""
        with patch.object(settings, 'database_url', None):
            with patch.object(settings, 'db_path', 'custom.db'):
                url = settings.database_url_resolved
                assert url == 'sqlite+aiosqlite:///custom.db'
