"""
PostgreSQL провайдер для абстрактного слоя базы данных.
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


class PostgreSQLProvider(IProvider):
    """
    Провайдер для PostgreSQL базы данных.

    Реализует специфичные для PostgreSQL операции.
    """

    def __init__(self, engine: AsyncEngine, config: DatabaseConfig) -> None:
        """
        Инициализация PostgreSQL провайдера.

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
        """Получить диалект SQLAlchemy для PostgreSQL."""
        from sqlalchemy.dialects import postgresql
        return postgresql.dialect()

    def get_driver(self) -> str:
        """Получить название драйвера."""
        return 'asyncpg'

    async def create_database(self, name: str) -> bool:
        """
        Создать новую базу данных PostgreSQL.

        Args:
            name: Имя базы данных

        Returns:
            True если база создана
        """
        try:
            # Проверяем существование
            if await self.database_exists(name):
                logger.info(f"База данных уже существует: {name}")
                return True

            # Создаём базу данных
            # Подключаемся к default базе для создания новой
            default_db = self._config.database or 'postgres'
            url = str(self._engine.url).replace(
                f'/{default_db}',
                '/postgres'
            )

            from sqlalchemy.ext.asyncio import create_async_engine
            temp_engine = create_async_engine(url)

            try:
                async with temp_engine.connect() as conn:
                    await conn.execution_options(isolation_level='AUTOCOMMIT').execute(
                        f"CREATE DATABASE {name}"
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
        Удалить базу данных PostgreSQL.

        Args:
            name: Имя базы данных

        Returns:
            True если база удалена
        """
        try:
            if not await self.database_exists(name):
                logger.warning(f"База данных не найдена: {name}")
                return False

            # Подключаемся к default базе для удаления
            url = str(self._engine.url).replace(
                f'/{name}',
                '/postgres'
            )

            from sqlalchemy.ext.asyncio import create_async_engine
            temp_engine = create_async_engine(url)

            try:
                async with temp_engine.connect() as conn:
                    await conn.execution_options(isolation_level='AUTOCOMMIT').execute(
                        f"DROP DATABASE {name}"
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
        Проверить существование базы данных PostgreSQL.

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
                        "SELECT 1 FROM pg_database WHERE datname = :name"
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
        Получить версию PostgreSQL.

        Returns:
            Строка версии
        """
        try:
            from sqlalchemy import text

            result = await self.execute_query("SELECT version()")
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
            query = """
                SELECT
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
                FROM pg_tables
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
            """
            return await self.execute_query(query)

        except Exception as e:
            raise DatabaseError(
                f"Ошибка получения размеров таблиц: {e}",
                original_error=e
            )

    async def analyze_tables(self) -> bool:
        """
        Выполнить ANALYZE для всех таблиц.

        Returns:
            True если анализ выполнен
        """
        try:
            await self.execute_query("ANALYZE")
            logger.info("PostgreSQL ANALYZE выполнен")
            return True

        except Exception as e:
            raise DatabaseError(
                f"Ошибка ANALYZE: {e}",
                original_error=e
            )

    async def vacuum(self, full: bool = False) -> bool:
        """
        Выполнить VACUUM.

        Args:
            full: Если True, выполнить VACUUM FULL

        Returns:
            True если VACUUM выполнен
        """
        try:
            command = "VACUUM FULL" if full else "VACUUM"
            await self.execute_query(command)
            logger.info(f"PostgreSQL {command} выполнен")
            return True

        except Exception as e:
            raise DatabaseError(
                f"Ошибка {command}: {e}",
                original_error=e
            )


class PostgreSQLDatabaseService(BaseDatabaseService):
    """
    Сервис для работы с PostgreSQL базой данных.

    Наследует общую логику из BaseDatabaseService,
    добавляет PostgreSQL-специфичные настройки.
    """

    def __init__(self, config: Optional[DatabaseConfig] = None) -> None:
        """
        Инициализация PostgreSQL сервиса.

        Args:
            config: Конфигурация подключения (опционально)
        """
        if config is None:
            # Конфигурация по умолчанию для PostgreSQL
            config = DatabaseConfig.from_postgresql(
                host='localhost',
                database='postgres',
                username='postgres',
                password=''
            )

        super().__init__(config)
        self._provider: Optional[PostgreSQLProvider] = None

    @property
    def db_type(self) -> DatabaseType:
        """Тип СУБД - PostgreSQL."""
        return DatabaseType.POSTGRESQL

    def _create_engine(self) -> AsyncEngine:
        """
        Создать SQLAlchemy engine для PostgreSQL.

        Returns:
            AsyncEngine экземпляр
        """
        # PostgreSQL специфичные настройки
        postgres_config = DatabaseConfig(
            url=self._config.resolved_url,
            db_type=DatabaseType.POSTGRESQL,
            echo=self._config.echo,
            pool_pre_ping=self._config.pool_pre_ping,
            pool_size=self._config.pool_size or 20,
            max_overflow=self._config.max_overflow or 40,
            pool_timeout=self._config.pool_timeout or 30,
            pool_recycle=self._config.pool_recycle or 1800,
        )

        self._config = postgres_config
        return super()._create_engine()

    def get_provider(self) -> PostgreSQLProvider:
        """
        Получить PostgreSQL провайдер.

        Returns:
            PostgreSQLProvider экземпляр
        """
        if self._provider is None:
            if self._engine is None:
                raise DatabaseError("Engine не инициализирован. Вызовите connect()")
            self._provider = PostgreSQLProvider(self._engine, self._config)
        return self._provider

    @asynccontextmanager
    async def begin_transaction(
        self,
        isolation_level: Optional[Any] = None
    ) -> AsyncGenerator[Any, None]:
        """
        Начать транзакцию с поддержкой PostgreSQL isolation levels.

        Args:
            isolation_level: Уровень изоляции

        Yields:
            Транзакция
        """
        async with self.session_context() as session:
            try:
                # PostgreSQL поддерживает все уровни изоляции
                if isolation_level is None:
                    isolation_level = IsolationLevel.get_default(DatabaseType.POSTGRESQL)

                await session.connection(
                    execution_options={'isolation_level': isolation_level.value if hasattr(isolation_level, 'value') else isolation_level}
                )

                yield session

            except Exception as e:
                raise DatabaseError(
                    f"Ошибка транзакции PostgreSQL: {e}",
                    original_error=e
                )
