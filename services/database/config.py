"""
Конфигурация подключения к базе данных.
"""

from dataclasses import dataclass
from typing import Optional

from services.database.enums import DatabaseType, IsolationLevel


@dataclass(frozen=True)
class DatabaseConfig:
    """
    Конфигурация подключения к базе данных.

    Attributes:
        url: Полный URL подключения (приоритет над остальными)
        db_type: Тип СУБД (определяется автоматически из url если не указан)
        host: Хост сервера БД (для PostgreSQL/MySQL)
        port: Порт сервера БД
        database: Имя базы данных
        username: Имя пользователя
        password: Пароль
        driver: Драйвер подключения (например, 'asyncpg', 'aiosqlite', 'aiomysql')
        isolation_level: Уровень изоляции транзакций
        echo: Логировать SQL запросы
        pool_size: Размер пула подключений
        max_overflow: Максимальное количество подключений сверх pool_size
        pool_timeout: Таймаут ожидания подключения из пула (секунды)
        pool_recycle: Время пересоздания подключения (секунды)
        pool_pre_ping: Проверять подключение перед использованием
    """
    url: Optional[str] = None
    db_type: DatabaseType = DatabaseType.UNKNOWN
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    driver: Optional[str] = None
    isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 1800
    pool_pre_ping: bool = True

    @classmethod
    def from_url(cls, url: str, **kwargs) -> 'DatabaseConfig':
        """
        Создать конфигурацию из URL.

        Args:
            url: URL подключения
            **kwargs: Дополнительные параметры

        Returns:
            DatabaseConfig экземпляр

        Examples:
            >>> config = DatabaseConfig.from_url(
            ...     'postgresql+asyncpg://user:pass@localhost:5432/mydb',
            ...     pool_size=20
            ... )
        """
        return cls(url=url, **kwargs)

    @classmethod
    def from_sqlite(cls, db_path: str, **kwargs) -> 'DatabaseConfig':
        """
        Создать конфигурацию для SQLite.

        Args:
            db_path: Путь к файлу базы данных
            **kwargs: Дополнительные параметры

        Returns:
            DatabaseConfig экземпляр

        Examples:
            >>> config = DatabaseConfig.from_sqlite('db.sqlite3')
        """
        return cls(
            url=f'sqlite+aiosqlite:///{db_path}',
            db_type=DatabaseType.SQLITE,
            **kwargs
        )

    @classmethod
    def from_postgresql(
        cls,
        host: str,
        port: int = 5432,
        database: str = 'postgres',
        username: str = 'postgres',
        password: str = '',
        driver: str = 'asyncpg',
        **kwargs
    ) -> 'DatabaseConfig':
        """
        Создать конфигурацию для PostgreSQL.

        Args:
            host: Хост сервера
            port: Порт (по умолчанию 5432)
            database: Имя базы данных
            username: Имя пользователя
            password: Пароль
            driver: Драйвер (по умолчанию 'asyncpg')
            **kwargs: Дополнительные параметры

        Returns:
            DatabaseConfig экземпляр

        Examples:
            >>> config = DatabaseConfig.from_postgresql(
            ...     host='localhost',
            ...     database='mydb',
            ...     username='user',
            ...     password='secret'
            ... )
        """
        url = f'postgresql+{driver}://{username}:{password}@{host}:{port}/{database}'
        return cls(
            url=url,
            db_type=DatabaseType.POSTGRESQL,
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            driver=driver,
            **kwargs
        )

    @classmethod
    def from_mysql(
        cls,
        host: str,
        port: int = 3306,
        database: str = 'mysql',
        username: str = 'root',
        password: str = '',
        driver: str = 'aiomysql',
        **kwargs
    ) -> 'DatabaseConfig':
        """
        Создать конфигурацию для MySQL.

        Args:
            host: Хост сервера
            port: Порт (по умолчанию 3306)
            database: Имя базы данных
            username: Имя пользователя
            password: Пароль
            driver: Драйвер (по умолчанию 'aiomysql')
            **kwargs: Дополнительные параметры

        Returns:
            DatabaseConfig экземпляр

        Examples:
            >>> config = DatabaseConfig.from_mysql(
            ...     host='localhost',
            ...     database='mydb',
            ...     username='root',
            ...     password='secret'
            ... )
        """
        url = f'mysql+{driver}://{username}:{password}@{host}:{port}/{database}'
        return cls(
            url=url,
            db_type=DatabaseType.MYSQL,
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            driver=driver,
            **kwargs
        )

    def __post_init__(self) -> None:
        """Валидация и нормализация конфигурации после инициализации."""
        # Определяем тип СУБД из URL если не указан
        if self.db_type == DatabaseType.UNKNOWN and self.url:
            object.__setattr__(self, 'db_type', DatabaseType.from_url(self.url))

        # Устанавливаем уровень изоляции по умолчанию для СУБД
        if self.isolation_level == IsolationLevel.READ_COMMITTED:
            object.__setattr__(
                self,
                'isolation_level',
                IsolationLevel.get_default(self.db_type)
            )

    @property
    def resolved_url(self) -> str:
        """
        Получить разрешённый URL подключения.

        Returns:
            URL строка подключения

        Raises:
            ValueError: Если URL не указан и невозможно построить
        """
        if self.url:
            return self.url

        # Строим URL из компонентов
        if self.db_type == DatabaseType.SQLITE:
            # Для SQLite нужен путь к файлу
            raise ValueError(
                "Для SQLite необходимо указать url или использовать from_sqlite()"
            )

        if not all([self.host, self.database, self.username]):
            raise ValueError(
                "Необходимо указать url или host, database, username"
            )

        driver = self.driver or self._get_default_driver()
        port = self.port or self._get_default_port()

        password_part = f':{self.password}' if self.password else ''
        return (
            f'{self.db_type.driver_prefix}://'
            f'{self.username}{password_part}@{self.host}:{port}/{self.database}'
        )

    def _get_default_driver(self) -> str:
        """Получить драйвер по умолчанию для СУБД."""
        drivers = {
            DatabaseType.SQLITE: 'aiosqlite',
            DatabaseType.POSTGRESQL: 'asyncpg',
            DatabaseType.MYSQL: 'aiomysql',
        }
        return drivers.get(self.db_type, 'aiosqlite')

    def _get_default_port(self) -> int:
        """Получить порт по умолчанию для СУБД."""
        ports = {
            DatabaseType.SQLITE: 0,
            DatabaseType.POSTGRESQL: 5432,
            DatabaseType.MYSQL: 3306,
        }
        return ports.get(self.db_type, 5432)
