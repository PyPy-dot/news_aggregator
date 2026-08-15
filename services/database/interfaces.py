"""
Абстрактные интерфейсы для слоя базы данных.

Определяют контракты для провайдеров СУБД, обеспечивая
единообразие использования независимо от выбранной СУБД.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncContextManager, Optional, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine

from services.database.enums import DatabaseType, ConnectionStatus
from services.database.config import DatabaseConfig

T = TypeVar('T')


class IDatabaseService(ABC):
    """
    Абстрактный интерфейс сервиса базы данных.

    Определяет контракт для работы с СУБД любого типа.
    Все провайдеры (SQLite, PostgreSQL, MySQL) должны реализовать этот интерфейс.
    """

    @property
    @abstractmethod
    def db_type(self) -> DatabaseType:
        """Тип СУБД."""

    @property
    @abstractmethod
    def status(self) -> ConnectionStatus:
        """Текущий статус подключения."""

    @property
    @abstractmethod
    def config(self) -> DatabaseConfig:
        """Конфигурация подключения."""

    @abstractmethod
    async def connect(self) -> None:
        """
        Установить подключение к базе данных.

        Raises:
            DatabaseError: Если не удалось подключиться
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Закрыть подключение к базе данных.

        Raises:
            DatabaseError: Если произошла ошибка при закрытии
        """

    @abstractmethod
    async def create_session(self) -> AsyncSession:
        """
        Создать новую сессию базы данных.

        Returns:
            AsyncSession сессия

        Raises:
            DatabaseError: Если сессия не создана
        """

    @abstractmethod
    def session_context(
        self,
        isolation_level: Optional[Any] = None
    ) -> AsyncContextManager[AsyncSession]:
        """
        Контекстный менеджер для сессии БД.

        Args:
            isolation_level: Уровень изоляции (переопределяет конфиг)

        Returns:
            AsyncContextManager с AsyncSession

        Raises:
            DatabaseError: Если контекст не создан
        """

    @abstractmethod
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
            DatabaseError: Если запрос не выполнен
        """

    @abstractmethod
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
            DatabaseError: Если запрос не выполнен
        """

    @abstractmethod
    async def begin_transaction(
        self,
        isolation_level: Optional[Any] = None
    ) -> AsyncContextManager[Any]:
        """
        Начать транзакцию.

        Args:
            isolation_level: Уровень изоляции (переопределяет конфиг)

        Returns:
            AsyncContextManager транзакции

        Raises:
            DatabaseError: Если транзакция не начата
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Проверить доступность базы данных.

        Returns:
            True если база данных доступна

        Raises:
            DatabaseError: Если проверка не пройдена
        """


class IConnectionPool(ABC):
    """
    Абстрактный интерфейс пула подключений.
    """

    @property
    @abstractmethod
    def size(self) -> int:
        """Текущий размер пула."""

    @property
    @abstractmethod
    def available(self) -> int:
        """Количество доступных подключений."""

    @abstractmethod
    async def acquire(self) -> Any:
        """
        Получить подключение из пула.

        Returns:
            Подключение

        Raises:
            PoolError: Если не удалось получить подключение
        """

    @abstractmethod
    async def release(self, connection: Any) -> None:
        """
        Вернуть подключение в пул.

        Args:
            connection: Подключение для возврата

        Raises:
            PoolError: Если не удалось вернуть подключение
        """

    @abstractmethod
    async def close(self) -> None:
        """
        Закрыть все подключения в пуле.

        Raises:
            PoolError: Если произошла ошибка при закрытии
        """


class IProvider(ABC):
    """
    Базовый интерфейс провайдера СУБД.
    """

    @property
    @abstractmethod
    def engine(self) -> AsyncEngine:
        """SQLAlchemy engine."""

    @abstractmethod
    def get_dialect(self) -> Any:
        """Получить диалект SQLAlchemy для СУБД."""

    @abstractmethod
    def get_driver(self) -> str:
        """Получить название драйвера."""

    @abstractmethod
    async def create_database(self, name: str) -> bool:
        """
        Создать новую базу данных.

        Args:
            name: Имя базы данных

        Returns:
            True если база создана

        Raises:
            DatabaseError: Если не удалось создать базу
        """

    @abstractmethod
    async def drop_database(self, name: str) -> bool:
        """
        Удалить базу данных.

        Args:
            name: Имя базы данных

        Returns:
            True если база удалена

        Raises:
            DatabaseError: Если не удалось удалить базу
        """

    @abstractmethod
    async def database_exists(self, name: str) -> bool:
        """
        Проверить существование базы данных.

        Args:
            name: Имя базы данных

        Returns:
            True если база существует

        Raises:
            DatabaseError: Если проверка не пройдена
        """
