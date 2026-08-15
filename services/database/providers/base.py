"""
Базовый класс для провайдеров баз данных.
"""

import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from services.database.interfaces import IDatabaseService, IProvider
from services.database.config import DatabaseConfig
from services.database.enums import DatabaseType, ConnectionStatus
from services.database.exceptions import (
    DatabaseError,
    ConnectionError,
    QueryError,
    TransactionError,
    SessionError,
)

logger = logging.getLogger(__name__)


class BaseDatabaseService(IDatabaseService, ABC):
    """
    Базовый класс для сервисов базы данных.

    Реализует общую логику для всех СУБД, оставляя специфичные
    методы для переопределения в наследниках.

    Attributes:
        config: Конфигурация подключения
        _engine: SQLAlchemy engine
        _status: Текущий статус подключения
    """

    def __init__(self, config: DatabaseConfig) -> None:
        """
        Инициализация сервиса базы данных.

        Args:
            config: Конфигурация подключения
        """
        self._config = config
        self._engine: Optional[AsyncEngine] = None
        self._status = ConnectionStatus.DISCONNECTED
        self._initialized = False

    @property
    def config(self) -> DatabaseConfig:
        """Конфигурация подключения."""
        return self._config

    @property
    def status(self) -> ConnectionStatus:
        """Текущий статус подключения."""
        return self._status

    @property
    def engine(self) -> AsyncEngine:
        """SQLAlchemy engine."""
        if self._engine is None:
            raise SessionError("Engine не инициализирован. Вызовите connect()")
        return self._engine

    @property
    @abstractmethod
    def db_type(self) -> DatabaseType:
        """Тип СУБД."""

    def _create_engine(self) -> AsyncEngine:
        """
        Создать SQLAlchemy engine.

        Returns:
            AsyncEngine экземпляр

        Raises:
            ConnectionError: Если не удалось создать engine
        """
        try:
            url = self._config.resolved_url

            # Общие параметры для всех СУБД
            engine_kwargs = {
                'echo': self._config.echo,
                'pool_pre_ping': self._config.pool_pre_ping,
            }

            # Специфичные настройки для SQLite
            if self.db_type == DatabaseType.SQLITE:
                # SQLite не поддерживает параметры пула
                engine_kwargs['connect_args'] = {'check_same_thread': False}
            else:
                # PostgreSQL и MySQL поддерживают пул подключений
                engine_kwargs.update({
                    'pool_size': self._config.pool_size,
                    'max_overflow': self._config.max_overflow,
                    'pool_timeout': self._config.pool_timeout,
                    'pool_recycle': self._config.pool_recycle,
                })

            logger.info(f"Создание engine для {self.db_type.name}")
            logger.debug(f"URL: {self._mask_password(url)}")

            engine = create_async_engine(url, **engine_kwargs)

            logger.info(f"✅ Engine создан для {self.db_type.name}")
            return engine

        except Exception as e:
            raise ConnectionError(
                f"Не удалось создать engine: {e}",
                original_error=e
            )

    def _mask_password(self, url: str) -> str:
        """Замаскировать пароль в URL для логирования."""
        if '://' not in url:
            return url

        prefix, rest = url.split('://', 1)
        if '@' not in rest:
            return url

        host_part = rest.split('@', 1)[1]
        return f"{prefix}://***:***@{host_part}"

    async def connect(self) -> None:
        """
        Установить подключение к базе данных.

        Raises:
            ConnectionError: Если не удалось подключиться
        """
        if self._status == ConnectionStatus.CONNECTED:
            logger.debug("Уже подключено")
            return

        self._status = ConnectionStatus.CONNECTING

        try:
            self._engine = self._create_engine()

            # Проверка подключения
            await self.health_check()

            self._status = ConnectionStatus.CONNECTED
            self._initialized = True

            logger.info(f"✅ Подключено к {self.db_type.name}")

        except Exception as e:
            self._status = ConnectionStatus.ERROR
            raise ConnectionError(
                f"Не удалось подключиться к {self.db_type.name}: {e}",
                original_error=e
            )

    async def disconnect(self) -> None:
        """
        Закрыть подключение к базе данных.

        Raises:
            DatabaseError: Если произошла ошибка при закрытии
        """
        if self._status == ConnectionStatus.DISCONNECTED:
            logger.debug("Уже отключено")
            return

        try:
            if self._engine:
                await self._engine.dispose()
                self._engine = None

            self._status = ConnectionStatus.CLOSED
            self._initialized = False

            logger.info(f"👋 Отключено от {self.db_type.name}")

        except Exception as e:
            self._status = ConnectionStatus.ERROR
            raise DatabaseError(
                f"Ошибка при закрытии подключения: {e}",
                original_error=e
            )

    async def create_session(self) -> AsyncSession:
        """
        Создать новую сессию базы данных.

        Returns:
            AsyncSession сессия

        Raises:
            SessionError: Если сессия не создана
        """
        if not self._initialized or self._engine is None:
            await self.connect()

        try:
            from sqlalchemy.ext.asyncio import async_sessionmaker

            session_factory = async_sessionmaker(
                self._engine,
                expire_on_commit=False,
                class_=AsyncSession
            )

            return session_factory()

        except Exception as e:
            raise SessionError(
                f"Не удалось создать сессию: {e}",
                original_error=e
            )

    @asynccontextmanager
    async def session_context(
        self,
        isolation_level: Optional[Any] = None
    ) -> AsyncGenerator[AsyncSession, None]:
        """
        Контекстный менеджер для сессии БД.

        Args:
            isolation_level: Уровень изоляции (переопределяет конфиг)

        Yields:
            AsyncSession сессия

        Raises:
            SessionError: Если контекст не создан
        """
        import gc

        session = await self.create_session()

        try:
            # Установка уровня изоляции если указан
            if isolation_level:
                await session.connection(
                    execution_options={'isolation_level': isolation_level}
                )

            yield session
            await session.commit()

        except Exception:
            await session.rollback()
            raise

        finally:
            await session.close()
            del session
            gc.collect()
            logger.debug("Сессия закрыта")

    async def execute_query(
        self,
        query: Any,
        params: Optional[dict] = None
    ) -> list[dict[str, Any]]:
        """
        Выполнить SQL запрос и вернуть результаты.

        Args:
            query: SQL запрос (текст или SQLAlchemy)
            params: Параметры запроса

        Returns:
            Список словарей с результатами

        Raises:
            QueryError: Если запрос не выполнен
        """
        async with self.session_context() as session:
            try:
                # Преобразуем query в TextClause если это строка
                if isinstance(query, str):
                    query = text(query)

                result = await session.execute(query, params or {})
                rows = result.mappings().all()

                return [dict(row) for row in rows]

            except SQLAlchemyError as e:
                raise QueryError(
                    f"Ошибка выполнения запроса: {e}",
                    original_error=e,
                    context={'query': str(query), 'params': params}
                )

    async def execute_many(
        self,
        query: Any,
        params_list: list[dict]
    ) -> int:
        """
        Выполнить SQL запрос с несколькими наборами параметров.

        Args:
            query: SQL запрос
            params_list: Список наборов параметров

        Returns:
            Количество затронутых строк

        Raises:
            QueryError: Если запрос не выполнен
        """
        async with self.session_context() as session:
            try:
                if isinstance(query, str):
                    query = text(query)

                result = await session.execute(query, params_list)

                return result.rowcount or 0

            except SQLAlchemyError as e:
                raise QueryError(
                    f"Ошибка выполнения запроса: {e}",
                    original_error=e,
                    context={'query': str(query), 'params_count': len(params_list)}
                )

    @asynccontextmanager
    async def begin_transaction(
        self,
        isolation_level: Optional[Any] = None
    ) -> AsyncGenerator[Any, None]:
        """
        Начать транзакцию.

        Args:
            isolation_level: Уровень изоляции (переопределяет конфиг)

        Yields:
            Транзакция

        Raises:
            TransactionError: Если транзакция не начата
        """
        async with self.session_context() as session:
            try:
                # Для SQLite игнорируем isolation_level
                if self.db_type != DatabaseType.SQLITE and isolation_level:
                    await session.connection(
                        execution_options={'isolation_level': isolation_level}
                    )

                yield session

            except Exception as e:
                raise TransactionError(
                    f"Ошибка транзакции: {e}",
                    original_error=e
                )

    async def health_check(self) -> bool:
        """
        Проверить доступность базы данных.

        Returns:
            True если база данных доступна

        Raises:
            ConnectionError: Если проверка не пройдена
        """
        try:
            async with self.engine.connect() as conn:
                # Простой запрос для проверки подключения
                if self.db_type == DatabaseType.SQLITE:
                    await conn.execute(text("SELECT 1"))
                else:
                    await conn.execute(text("SELECT 1"))

            logger.debug(f"{self.db_type.name} health check: OK")
            return True

        except Exception as e:
            raise ConnectionError(
                f"Health check failed: {e}",
                original_error=e
            )

    @abstractmethod
    def get_provider(self) -> IProvider:
        """
        Получить провайдер СУБД.

        Returns:
            IProvider экземпляр
        """
