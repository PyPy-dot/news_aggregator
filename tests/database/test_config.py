"""
Тесты для конфигурации базы данных.
"""

import pytest

from services.database.config import DatabaseConfig
from services.database.enums import DatabaseType, IsolationLevel


class TestDatabaseConfigFromUrl:
    """Тесты создания конфигурации из URL."""

    def test_from_url_sqlite(self):
        """Создание конфигурации для SQLite."""
        config = DatabaseConfig.from_url('sqlite+aiosqlite:///db.sqlite3')
        assert config.db_type == DatabaseType.SQLITE
        assert config.url == 'sqlite+aiosqlite:///db.sqlite3'

    def test_from_url_postgresql(self):
        """Создание конфигурации для PostgreSQL."""
        config = DatabaseConfig.from_url('postgresql+asyncpg://user:pass@localhost:5432/mydb')
        assert config.db_type == DatabaseType.POSTGRESQL
        assert 'postgresql+asyncpg://user:pass@localhost:5432/mydb' in config.resolved_url

    def test_from_url_mysql(self):
        """Создание конфигурации для MySQL."""
        config = DatabaseConfig.from_url('mysql+aiomysql://root:secret@localhost:3306/testdb')
        assert config.db_type == DatabaseType.MYSQL
        assert 'mysql+aiomysql://root:secret@localhost:3306/testdb' in config.resolved_url

    def test_from_url_with_extra_params(self):
        """Создание конфигурации с дополнительными параметрами."""
        config = DatabaseConfig.from_url(
            'postgresql+asyncpg://localhost/db',
            pool_size=25,
            echo=True
        )
        assert config.pool_size == 25
        assert config.echo is True


class TestDatabaseConfigFromSqlite:
    """Тесты создания конфигурации для SQLite."""

    def test_from_sqlite_basic(self):
        """Создание конфигурации для SQLite."""
        config = DatabaseConfig.from_sqlite('db.sqlite3')
        assert config.db_type == DatabaseType.SQLITE
        assert config.url == 'sqlite+aiosqlite:///db.sqlite3'

    def test_from_sqlite_with_path(self):
        """Создание конфигурации для SQLite с путём."""
        config = DatabaseConfig.from_sqlite('/var/data/db.sqlite3')
        assert config.url == 'sqlite+aiosqlite:////var/data/db.sqlite3'

    def test_from_sqlite_with_params(self):
        """Создание конфигурации для SQLite с параметрами."""
        config = DatabaseConfig.from_sqlite(
            'db.sqlite3',
            echo=True,
            pool_size=5
        )
        assert config.echo is True
        assert config.pool_size == 5


class TestDatabaseConfigFromPostgresql:
    """Тесты создания конфигурации для PostgreSQL."""

    def test_from_postgresql_basic(self):
        """Создание конфигурации для PostgreSQL."""
        config = DatabaseConfig.from_postgresql(
            host='localhost',
            database='mydb',
            username='user',
            password='secret'
        )
        assert config.db_type == DatabaseType.POSTGRESQL
        assert config.host == 'localhost'
        assert config.port == 5432  # default
        assert config.database == 'mydb'
        assert config.username == 'user'
        assert config.password == 'secret'

    def test_from_postgresql_custom_port(self):
        """Создание конфигурации для PostgreSQL с кастомным портом."""
        config = DatabaseConfig.from_postgresql(
            host='db.example.com',
            port=6432,
            database='production'
        )
        assert config.port == 6432

    def test_from_postgresql_driver(self):
        """Создание конфигурации для PostgreSQL с кастомным драйвером."""
        config = DatabaseConfig.from_postgresql(
            host='localhost',
            driver='asyncpg'
        )
        assert config.driver == 'asyncpg'


class TestDatabaseConfigFromMysql:
    """Тесты создания конфигурации для MySQL."""

    def test_from_mysql_basic(self):
        """Создание конфигурации для MySQL."""
        config = DatabaseConfig.from_mysql(
            host='localhost',
            database='mydb',
            username='root',
            password='secret'
        )
        assert config.db_type == DatabaseType.MYSQL
        assert config.host == 'localhost'
        assert config.port == 3306  # default
        assert config.database == 'mydb'

    def test_from_mysql_custom_port(self):
        """Создание конфигурации для MySQL с кастомным портом."""
        config = DatabaseConfig.from_mysql(
            host='db.example.com',
            port=13306
        )
        assert config.port == 13306


class TestDatabaseConfigResolvedUrl:
    """Тесты разрешения URL конфигурации."""

    def test_resolved_url_from_url(self):
        """Разрешение URL из заданного URL."""
        config = DatabaseConfig.from_url('sqlite+aiosqlite:///db.sqlite3')
        assert config.resolved_url == 'sqlite+aiosqlite:///db.sqlite3'

    def test_resolved_url_sqlite(self):
        """Разрешение URL для SQLite."""
        config = DatabaseConfig.from_sqlite('db.sqlite3')
        assert config.resolved_url == 'sqlite+aiosqlite:///db.sqlite3'

    def test_resolved_url_postgresql(self):
        """Разрешение URL для PostgreSQL."""
        config = DatabaseConfig.from_postgresql(
            host='localhost',
            database='mydb',
            username='user',
            password='pass'
        )
        assert 'postgresql+asyncpg://user:pass@localhost:5432/mydb' == config.resolved_url

    def test_resolved_url_mysql(self):
        """Разрешение URL для MySQL."""
        config = DatabaseConfig.from_mysql(
            host='localhost',
            database='mydb',
            username='root'
        )
        assert 'mysql+aiomysql://root:@localhost:3306/mydb' == config.resolved_url

    def test_resolved_url_empty_password(self):
        """Разрешение URL с пустым паролем."""
        config = DatabaseConfig.from_postgresql(
            host='localhost',
            database='mydb',
            username='user',
            password=''
        )
        # Пароль включается в URL как пустая строка
        assert 'postgresql+asyncpg://user:@localhost:5432/mydb' == config.resolved_url


class TestDatabaseConfigDefaults:
    """Тесты значений по умолчанию."""

    def test_default_isolation_level(self):
        """Уровень изоляции по умолчанию определяется СУБД."""
        sqlite_config = DatabaseConfig.from_sqlite('db.sqlite3')
        assert sqlite_config.isolation_level == IsolationLevel.SERIALIZABLE

        pg_config = DatabaseConfig.from_postgresql('localhost', database='db', username='u')
        assert pg_config.isolation_level == IsolationLevel.READ_COMMITTED

        mysql_config = DatabaseConfig.from_mysql('localhost', database='db', username='u')
        assert mysql_config.isolation_level == IsolationLevel.REPEATABLE_READ

    def test_default_pool_settings(self):
        """Настройки пула по умолчанию."""
        config = DatabaseConfig.from_sqlite('db.sqlite3')
        assert config.pool_size == 10
        assert config.max_overflow == 20
        assert config.pool_timeout == 30
        assert config.pool_recycle == 1800
        assert config.pool_pre_ping is True

    def test_default_echo(self):
        """Логирование SQL по умолчанию отключено."""
        config = DatabaseConfig.from_sqlite('db.sqlite3')
        assert config.echo is False
