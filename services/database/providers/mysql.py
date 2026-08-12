"""
MySQL провайдер для абстрактного слоя базы данных.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, Optional, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine

from services.database.providers.base import BaseDatabaseService
from services.database.interfaces import IProvider
from services.database.config import DatabaseConfig
from services.database.enums import DatabaseType, IsolationLevel
from services.database.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class MySQLProvider(IProvider):
    """
    Провайдер для MySQL базы данных.

    Реализует специфичные для MySQL операции.
    """

    def __init__(self, engine: AsyncEngine, config: DatabaseConfig) -> None:
        """
        Инициализация MySQL провайдера.

        Args:
            engine: SQLAlchemy engine
            config: Конфигурация подключения
        """
        self._engine = engine
        self._config = config

    @property
    def engine(self) -> AsyncEngine:
        """SQLAlchemy engine."""
        return self._engine

    def get_dialect(self) -> Any:
        """Получить диалект SQLAlchemy для MySQL."""
        from sqlalchemy.dialects import mysql
        return mysql.dialect()

    def get_driver(self) -> str:
        """Получить название драйвера."""
        return 'aiomysql'

    async def create_database(self, name: str) -> bool:
        """
        Создать новую базу данных MySQL.

        Args:
            name: Имя базы данных

        Returns:
            True если база создана
        """
        try:
            if await self.database_exists(name):
                logger.info(f"База данных уже существует: {name}")
                return True

            # Создаём базу данных
            # Подключаемся к mysql базе для создания новой
            url = str(self._engine.url).rsplit('/', 1)[0] + '/mysql'

            from sqlalchemy.ext.asyncio import create_async_engine
            temp_engine = create_async_engine(url)

            try:
                async with temp_engine.connect() as conn:
                    await conn.execution_options(isolation_level='AUTOCOMMIT').execute(
                        f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )

                logger.info(f"✅ База данных создана: {name}")
                return True

            finally:
                await temp_engine.dispose()

        except Exception as e:
            raise DatabaseError(
                f"Не удалось создать базу данных {name}: {e}",
                original_error=e
            )

    async def drop_database(self, name: str) -> bool:
        """
        Удалить базу данных MySQL.

        Args:
            name: Имя базы данных

        Returns:
            True если база удалена
        """
        try:
            if not await self.database_exists(name):
                logger.warning(f"База данных не найдена: {name}")
                return False

            url = str(self._engine.url).rsplit('/', 1)[0] + '/mysql'

            from sqlalchemy.ext.asyncio import create_async_engine
            temp_engine = create_async_engine(url)

            try:
                async with temp_engine.connect() as conn:
                    await conn.execution_options(isolation_level='AUTOCOMMIT').execute(
                        f"DROP DATABASE `{name}`"
                    )

                logger.info(f"✅ База данных удалена: {name}")
                return True

            finally:
                await temp_engine.dispose()

        except Exception as e:
            raise DatabaseError(
                f"Не удалось удалить базу данных {name}: {e}",
                original_error=e
            )

    async def database_exists(self, name: str) -> bool:
        """
        Проверить существование базы данных MySQL.

        Args:
            name: Имя базы данных

        Returns:
            True если база существует
        """
        try:
            from sqlalchemy import text

            async with self._engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = :name"
                    ),
                    {'name': name}
                )
                exists = result.fetchone() is not None

            logger.debug(f"База данных {name}: {'существует' if exists else 'не существует'}")
            return exists

        except Exception as e:
            raise DatabaseError(
                f"Ошибка проверки существования базы {name}: {e}",
                original_error=e
            )

    async def get_version(self) -> str:
        """
        Получить версию MySQL.

        Returns:
            Строка версии
        """
        try:
            result = await self.execute_query("SELECT VERSION() as version")
            return result[0]['version'] if result else 'Unknown'

        except Exception as e:
            raise DatabaseError(
                f"Ошибка получения версии: {e}",
                original_error=e
            )

    async def get_table_sizes(self) -> list[dict[str, Any]]:
        """
        Получить размеры таблиц базы данных.

        Returns:
            Список словарей с информацией о размерах
        """
        try:
            db_name = self._config.database
            query = f"""
                SELECT
                    table_name,
                    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
                FROM information_schema.TABLES
                WHERE table_schema = '{db_name}'
                ORDER BY (data_length + index_length) DESC
            """
            return await self.execute_query(query)

        except Exception as e:
            raise DatabaseError(
                f"Ошибка получения размеров таблиц: {e}",
                original_error=e
            )

    async def optimize_tables(self) -> bool:
        """
        Выполнить OPTIMIZE TABLE для всех таблиц.

        Returns:
            True если оптимизация выполнена
        """
        try:
            db_name = self._config.database

            # Получаем список таблиц
            tables = await self.execute_query(
                f"SHOW TABLES FROM `{db_name}`"
            )

            for table_row in tables:
                table_name = list(table_row.values())[0]
                await self.execute_query(f"OPTIMIZE TABLE `{table_name}`")

            logger.info("MySQL таблицы оптимизированы")
            return True

        except Exception as e:
            raise DatabaseError(
                f"Ошибка оптимизации таблиц: {e}",
                original_error=e
            )

    async def set_charset(self, charset: str = 'utf8mb4') -> bool:
        """
        Установить кодировку соединения.

        Args:
            charset: Кодировка (по умолчанию utf8mb4)

        Returns:
            True если кодировка установлена
        """
        try:
            await self.execute_query(f"SET NAMES {charset}")
            logger.info(f"MySQL кодировка установлена: {charset}")
            return True

        except Exception as e:
            raise DatabaseError(
                f"Ошибка установки кодировки: {e}",
                original_error=e
            )


class MySQLDatabaseService(BaseDatabaseService):
    """
    Сервис для работы с MySQL базой данных.

    Наследует общую логику из BaseDatabaseService,
    добавляет MySQL-специфичные настройки.
    """

    def __init__(self, config: Optional[DatabaseConfig] = None) -> None:
        """
        Инициализация MySQL сервиса.

        Args:
            config: Конфигурация подключения (опционально)
        """
        if config is None:
            # Конфигурация по умолчанию для MySQL
            config = DatabaseConfig.from_mysql(
                host='localhost',
                database='mysql',
                username='root',
                password=''
            )

        super().__init__(config)
        self._provider: Optional[MySQLProvider] = None

    @property
    def db_type(self) -> DatabaseType:
        """Тип СУБД - MySQL."""
        return DatabaseType.MYSQL

    def _create_engine(self) -> AsyncEngine:
        """
        Создать SQLAlchemy engine для MySQL.

        Returns:
            AsyncEngine экземпляр
        """
        # MySQL специфичные настройки
        mysql_config = DatabaseConfig(
            url=self._config.resolved_url,
            db_type=DatabaseType.MYSQL,
            echo=self._config.echo,
            pool_pre_ping=self._config.pool_pre_ping,
            pool_size=self._config.pool_size or 15,
            max_overflow=self._config.max_overflow or 30,
            pool_timeout=self._config.pool_timeout or 30,
            pool_recycle=self._config.pool_recycle or 1800,
        )

        self._config = mysql_config
        return super()._create_engine()

    def get_provider(self) -> MySQLProvider:
        """
        Получить MySQL провайдер.

        Returns:
            MySQLProvider экземпляр
        """
        if self._provider is None:
            if self._engine is None:
                raise DatabaseError("Engine не инициализирован. Вызовите connect()")
            self._provider = MySQLProvider(self._engine, self._config)
        return self._provider

    async def connect(self) -> None:
        """
        Подключиться к MySQL базе данных.

        Устанавливает кодировку utf8mb4 после подключения.
        """
        await super().connect()

        # Устанавливаем кодировку
        await self.get_provider().set_charset('utf8mb4')

    @asynccontextmanager
    async def begin_transaction(
        self,
        isolation_level: Optional[Any] = None
    ) -> AsyncGenerator[Any, None]:
        """
        Начать транзакцию с поддержкой MySQL isolation levels.

        Args:
            isolation_level: Уровень изоляции

        Yields:
            Транзакция
        """
        async with self.session_context() as session:
            try:
                # MySQL поддерживает ограниченные уровни изоляции
                if isolation_level is None:
                    isolation_level = IsolationLevel.get_default(DatabaseType.MYSQL)

                await session.connection(
                    execution_options={'isolation_level': isolation_level.value if hasattr(isolation_level, 'value') else isolation_level}
                )

                yield session

            except Exception as e:
                raise DatabaseError(
                    f"Ошибка транзакции MySQL: {e}",
                    original_error=e
                )
