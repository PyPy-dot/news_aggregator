"""
Фабрика сервисов базы данных.

Автоматически выбирает правильный провайдер на основе
конфигурации или URL подключения.
"""

import logging
from typing import Optional, Type

from services.database.config import DatabaseConfig
from services.database.enums import DatabaseType
from services.database.interfaces import IDatabaseService
from services.database.exceptions import ProviderNotFoundError, UnsupportedDatabaseError
from services.database.providers import (
    SQLiteDatabaseService,
    PostgreSQLDatabaseService,
    MySQLDatabaseService,
)

logger = logging.getLogger(__name__)


class DatabaseServiceFactory:
    """
    Фабрика для создания сервисов базы данных.

    Автоматически определяет тип СУБД и создаёт соответствующий сервис.

    Examples:
        >>> # Создание из URL
        >>> service = DatabaseServiceFactory.create(
        ...     DatabaseConfig.from_url('postgresql+asyncpg://user:pass@localhost/db')
        ... )

        >>> # Создание для SQLite
        >>> service = DatabaseServiceFactory.create(
        ...     DatabaseConfig.from_sqlite('db.sqlite3')
        ... )

        >>> # Создание для PostgreSQL
        >>> service = DatabaseServiceFactory.create(
        ...     DatabaseConfig.from_postgresql(
        ...         host='localhost',
        ...         database='mydb',
        ...         username='user',
        ...         password='secret'
        ...     )
        ... )
    """

    # Регистрация провайдеров
    _providers: dict[DatabaseType, Type[IDatabaseService]] = {
        DatabaseType.SQLITE: SQLiteDatabaseService,
        DatabaseType.POSTGRESQL: PostgreSQLDatabaseService,
        DatabaseType.MYSQL: MySQLDatabaseService,
    }

    @classmethod
    def create(cls, config: Optional[DatabaseConfig] = None) -> IDatabaseService:
        """
        Создать сервис базы данных.

        Args:
            config: Конфигурация подключения

        Returns:
            IDatabaseService экземпляр

        Raises:
            ProviderNotFoundError: Если провайдер не найден
            UnsupportedDatabaseError: Если СУБД не поддерживается
        """
        if config is None:
            # Пытаемся получить конфигурацию из настроек приложения
            config = cls._get_config_from_settings()

        # Определяем тип СУБД
        db_type = config.db_type

        if db_type == DatabaseType.UNKNOWN:
            # Пытаемся определить из URL
            if config.url:
                db_type = DatabaseType.from_url(config.url)
            else:
                raise UnsupportedDatabaseError(
                    "Не удалось определить тип СУБД. "
                    "Укажите url или используйте методы from_*()"
                )

        # Получаем класс провайдера
        provider_class = cls._providers.get(db_type)

        if provider_class is None:
            raise ProviderNotFoundError(
                f"Провайдер для {db_type.name} не найден. "
                f"Поддерживаемые: {list(cls._providers.keys())}"
            )

        logger.info(f"Создание провайдера для {db_type.name}")

        # Создаём и возвращаем сервис
        return provider_class(config)

    @classmethod
    def create_from_url(cls, url: str, **kwargs) -> IDatabaseService:
        """
        Создать сервис из URL подключения.

        Args:
            url: URL подключения
            **kwargs: Дополнительные параметры конфигурации

        Returns:
            IDatabaseService экземпляр

        Examples:
            >>> service = DatabaseServiceFactory.create_from_url(
            ...     'sqlite+aiosqlite:///db.sqlite3'
            ... )
            >>> service = DatabaseServiceFactory.create_from_url(
            ...     'postgresql+asyncpg://user:pass@localhost:5432/mydb'
            ... )
            >>> service = DatabaseServiceFactory.create_from_url(
            ...     'mysql+aiomysql://user:pass@localhost:3306/mydb'
            ... )
        """
        config = DatabaseConfig.from_url(url, **kwargs)
        return cls.create(config)

    @classmethod
    def create_sqlite(cls, db_path: str, **kwargs) -> IDatabaseService:
        """
        Создать сервис для SQLite.

        Args:
            db_path: Путь к файлу базы данных
            **kwargs: Дополнительные параметры

        Returns:
            IDatabaseService экземпляр
        """
        config = DatabaseConfig.from_sqlite(db_path, **kwargs)
        return cls.create(config)

    @classmethod
    def create_postgresql(
        cls,
        host: str,
        port: int = 5432,
        database: str = 'postgres',
        username: str = 'postgres',
        password: str = '',
        **kwargs
    ) -> IDatabaseService:
        """
        Создать сервис для PostgreSQL.

        Args:
            host: Хост сервера
            port: Порт (по умолчанию 5432)
            database: Имя базы данных
            username: Имя пользователя
            password: Пароль
            **kwargs: Дополнительные параметры

        Returns:
            IDatabaseService экземпляр
        """
        config = DatabaseConfig.from_postgresql(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            **kwargs
        )
        return cls.create(config)

    @classmethod
    def create_mysql(
        cls,
        host: str,
        port: int = 3306,
        database: str = 'mysql',
        username: str = 'root',
        password: str = '',
        **kwargs
    ) -> IDatabaseService:
        """
        Создать сервис для MySQL.

        Args:
            host: Хост сервера
            port: Порт (по умолчанию 3306)
            database: Имя базы данных
            username: Имя пользователя
            password: Пароль
            **kwargs: Дополнительные параметры

        Returns:
            IDatabaseService экземпляр
        """
        config = DatabaseConfig.from_mysql(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            **kwargs
        )
        return cls.create(config)

    @classmethod
    def register_provider(
        cls,
        db_type: DatabaseType,
        provider_class: Type[IDatabaseService]
    ) -> None:
        """
        Зарегистрировать кастомный провайдер.

        Args:
            db_type: Тип СУБД
            provider_class: Класс провайдера

        Examples:
            >>> class MyCustomDBService(BaseDatabaseService):
            ...     pass
            >>> DatabaseServiceFactory.register_provider(
            ...     DatabaseType.CUSTOM,
            ...     MyCustomDBService
            ... )
        """
        cls._providers[db_type] = provider_class
        logger.info(f"Зарегистрирован провайдер для {db_type.name}")

    @classmethod
    def get_registered_providers(cls) -> list[str]:
        """
        Получить список зарегистрированных провайдеров.

        Returns:
            Список названий типов СУБД
        """
        return [db_type.name for db_type in cls._providers.keys()]

    @classmethod
    def _get_config_from_settings(cls) -> DatabaseConfig:
        """
        Получить конфигурацию из настроек приложения.

        Returns:
            DatabaseConfig экземпляр
        """
        try:
            from config.settings import settings

            if settings.database_url:
                return DatabaseConfig.from_url(settings.database_url)
            else:
                return DatabaseConfig.from_sqlite(settings.db_path)

        except ImportError:
            # Настройки не найдены, возвращаем SQLite по умолчанию
            logger.warning("Настройки не найдены, используем SQLite по умолчанию")
            return DatabaseConfig.from_sqlite('db.sqlite3')
