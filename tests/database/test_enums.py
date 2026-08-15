"""
Тесты для перечислений абстрактного слоя базы данных.
"""


from services.database.enums import DatabaseType, IsolationLevel, ConnectionStatus


class TestDatabaseType:
    """Тесты для DatabaseType."""

    def test_from_url_sqlite(self):
        """Определение SQLite из URL."""
        assert DatabaseType.from_url('sqlite+aiosqlite:///db.sqlite3') == DatabaseType.SQLITE
        assert DatabaseType.from_url('sqlite:///db.sqlite3') == DatabaseType.SQLITE

    def test_from_url_postgresql(self):
        """Определение PostgreSQL из URL."""
        assert DatabaseType.from_url('postgresql+asyncpg://user:pass@localhost/db') == DatabaseType.POSTGRESQL
        assert DatabaseType.from_url('postgresql://user:pass@localhost/db') == DatabaseType.POSTGRESQL

    def test_from_url_mysql(self):
        """Определение MySQL из URL."""
        assert DatabaseType.from_url('mysql+aiomysql://user:pass@localhost/db') == DatabaseType.MYSQL
        assert DatabaseType.from_url('mysql://user:pass@localhost/db') == DatabaseType.MYSQL

    def test_from_url_unknown(self):
        """Определение неизвестной СУБД."""
        assert DatabaseType.from_url('unknown://localhost/db') == DatabaseType.UNKNOWN
        assert DatabaseType.from_url('') == DatabaseType.UNKNOWN

    def test_from_url_case_insensitive(self):
        """URL регистронезависимый."""
        assert DatabaseType.from_url('SQLITE+AIOSQLITE:///db.sqlite3') == DatabaseType.SQLITE
        assert DatabaseType.from_url('POSTGRESQL+ASYNCPG://localhost/db') == DatabaseType.POSTGRESQL
        assert DatabaseType.from_url('MYSQL+AIOMYSQL://localhost/db') == DatabaseType.MYSQL

    def test_driver_prefix(self):
        """Префикс драйвера для SQLAlchemy."""
        assert DatabaseType.SQLITE.driver_prefix == 'sqlite+aiosqlite'
        assert DatabaseType.POSTGRESQL.driver_prefix == 'postgresql+asyncpg'
        assert DatabaseType.MYSQL.driver_prefix == 'mysql+aiomysql'
        assert DatabaseType.UNKNOWN.driver_prefix == 'sqlite+aiosqlite'


class TestIsolationLevel:
    """Тесты для IsolationLevel."""

    def test_get_default_sqlite(self):
        """Уровень изоляции по умолчанию для SQLite."""
        assert IsolationLevel.get_default(DatabaseType.SQLITE) == IsolationLevel.SERIALIZABLE

    def test_get_default_postgresql(self):
        """Уровень изоляции по умолчанию для PostgreSQL."""
        assert IsolationLevel.get_default(DatabaseType.POSTGRESQL) == IsolationLevel.READ_COMMITTED

    def test_get_default_mysql(self):
        """Уровень изоляции по умолчанию для MySQL."""
        assert IsolationLevel.get_default(DatabaseType.MYSQL) == IsolationLevel.REPEATABLE_READ

    def test_get_default_unknown(self):
        """Уровень изоляции по умолчанию для неизвестной СУБД."""
        assert IsolationLevel.get_default(DatabaseType.UNKNOWN) == IsolationLevel.READ_COMMITTED

    def test_values(self):
        """Значения уровней изоляции."""
        assert IsolationLevel.READ_UNCOMMITTED.value == "READ UNCOMMITTED"
        assert IsolationLevel.READ_COMMITTED.value == "READ COMMITTED"
        assert IsolationLevel.REPEATABLE_READ.value == "REPEATABLE READ"
        assert IsolationLevel.SERIALIZABLE.value == "SERIALIZABLE"
        assert IsolationLevel.AUTOCOMMIT.value == "AUTOCOMMIT"


class TestConnectionStatus:
    """Тесты для ConnectionStatus."""

    def test_statuses_exist(self):
        """Проверка существования статусов."""
        assert ConnectionStatus.DISCONNECTED is not None
        assert ConnectionStatus.CONNECTING is not None
        assert ConnectionStatus.CONNECTED is not None
        assert ConnectionStatus.ERROR is not None
        assert ConnectionStatus.CLOSED is not None
