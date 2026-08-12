"""
Перечисления для абстрактного слоя базы данных.
"""

from enum import Enum, auto


class DatabaseType(Enum):
    """Тип поддерживаемых СУБД."""
    SQLITE = auto()
    POSTGRESQL = auto()
    MYSQL = auto()
    UNKNOWN = auto()

    @classmethod
    def from_url(cls, url: str) -> 'DatabaseType':
        """
        Определить тип СУБД по URL подключения.

        Args:
            url: URL подключения к БД

        Returns:
            DatabaseType значение

        Examples:
            >>> DatabaseType.from_url('sqlite+aiosqlite:///db.sqlite3')
            <DatabaseType.SQLITE: 1>
            >>> DatabaseType.from_url('postgresql+asyncpg://user:pass@localhost/db')
            <DatabaseType.POSTGRESQL: 2>
            >>> DatabaseType.from_url('mysql+aiomysql://user:pass@localhost/db')
            <DatabaseType.MYSQL: 3>
        """
        url_lower = url.lower()

        if url_lower.startswith('sqlite'):
            return cls.SQLITE
        elif url_lower.startswith('postgresql'):
            return cls.POSTGRESQL
        elif url_lower.startswith('mysql'):
            return cls.MYSQL
        else:
            return cls.UNKNOWN

    @property
    def driver_prefix(self) -> str:
        """Префикс драйвера для SQLAlchemy URL."""
        return {
            DatabaseType.SQLITE: 'sqlite+aiosqlite',
            DatabaseType.POSTGRESQL: 'postgresql+asyncpg',
            DatabaseType.MYSQL: 'mysql+aiomysql',
        }.get(self, 'sqlite+aiosqlite')


class IsolationLevel(Enum):
    """Уровни изоляции транзакций."""
    READ_UNCOMMITTED = "READ UNCOMMITTED"
    READ_COMMITTED = "READ COMMITTED"
    REPEATABLE_READ = "REPEATABLE READ"
    SERIALIZABLE = "SERIALIZABLE"
    AUTOCOMMIT = "AUTOCOMMIT"

    @classmethod
    def get_default(cls, db_type: DatabaseType) -> 'IsolationLevel':
        """
        Получить уровень изоляции по умолчанию для СУБД.

        Args:
            db_type: Тип СУБД

        Returns:
            IsolationLevel значение
        """
        defaults = {
            DatabaseType.SQLITE: cls.SERIALIZABLE,
            DatabaseType.POSTGRESQL: cls.READ_COMMITTED,
            DatabaseType.MYSQL: cls.REPEATABLE_READ,
        }
        return defaults.get(db_type, cls.READ_COMMITTED)


class ConnectionStatus(Enum):
    """Статус подключения к базе данных."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    ERROR = auto()
    CLOSED = auto()
