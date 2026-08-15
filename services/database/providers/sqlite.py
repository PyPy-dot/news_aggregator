"""
SQLite провайдер для абстрактного слоя базы данных.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncEngine

from services.database.providers.base import BaseDatabaseService
from services.database.interfaces import IProvider
from services.database.config import DatabaseConfig
from services.database.enums import DatabaseType
from services.database.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class SQLiteProvider(IProvider):
    """
    Провайдер для SQLite базы данных.

    Реализует специфичные для SQLite операции.
    """

    def __init__(self, engine: AsyncEngine, config: DatabaseConfig) -> None:
        """
        Инициализация SQLite провайдера.

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
        """Получить диалект SQLAlchemy для SQLite."""
        from sqlalchemy.dialects import sqlite
        return sqlite.dialect()

    def get_driver(self) -> str:
        """Получить название драйвера."""
        return 'aiosqlite'

    async def create_database(self, name: str) -> bool:
        """
        Создать новую SQLite базу данных (файл).

        SQLite создаёт файл автоматически при подключении,
        поэтому этот метод просто проверяет существование файла.

        Args:
            name: Имя/путь к базе данных

        Returns:
            True если база создана или существует
        """
        try:
            # Для SQLite name - это путь к файлу
            db_path = Path(name)

            # Создаём директорию если не существует
            db_path.parent.mkdir(parents=True, exist_ok=True)

            # Файл будет создан при первом подключении
            logger.debug(f"SQLite база готова к созданию: {db_path}")
            return True

        except Exception as e:
            raise DatabaseError(
                f"Не удалось создать SQLite базу: {e}",
                original_error=e
            )

    async def drop_database(self, name: str) -> bool:
        """
        Удалить SQLite базу данных (файл).

        Args:
            name: Имя/путь к базе данных

        Returns:
            True если база удалена
        """
        try:
            db_path = Path(name)

            if db_path.exists():
                db_path.unlink()
                logger.info(f"SQLite база удалена: {db_path}")
                return True

            logger.warning(f"SQLite база не найдена: {db_path}")
            return False

        except Exception as e:
            raise DatabaseError(
                f"Не удалось удалить SQLite базу: {e}",
                original_error=e
            )

    async def database_exists(self, name: str) -> bool:
        """
        Проверить существование SQLite базы данных.

        Args:
            name: Имя/путь к базе данных

        Returns:
            True если база существует
        """
        db_path = Path(name)
        return db_path.exists()


class SQLiteDatabaseService(BaseDatabaseService):
    """
    Сервис для работы с SQLite базой данных.

    Наследует общую логику из BaseDatabaseService,
    добавляет SQLite-специфичные настройки.
    """

    def __init__(self, config: Optional[DatabaseConfig] = None) -> None:
        """
        Инициализация SQLite сервиса.

        Args:
            config: Конфигурация подключения (опционально)
        """
        if config is None:
            # Конфигурация по умолчанию для SQLite
            from services.database.config import DatabaseConfig
            config = DatabaseConfig.from_sqlite('db.sqlite3')

        super().__init__(config)
        self._provider: Optional[SQLiteProvider] = None

    @property
    def db_type(self) -> DatabaseType:
        """Тип СУБД - SQLite."""
        return DatabaseType.SQLITE

    def _create_engine(self) -> AsyncEngine:
        """
        Создать SQLAlchemy engine для SQLite.

        Returns:
            AsyncEngine экземпляр
        """
        # SQLite специфичные настройки
        sqlite_config = DatabaseConfig(
            url=self._config.resolved_url,
            db_type=DatabaseType.SQLITE,
            echo=self._config.echo,
            pool_pre_ping=self._config.pool_pre_ping,
            # Для SQLite используем StaticPool - параметры пула не применяются
        )

        self._config = sqlite_config
        return super()._create_engine()

    async def connect(self) -> None:
        """
        Подключиться к SQLite базе данных.

        Создаёт файл базы данных если он не существует.
        """
        # Сначала создаём engine через базовый класс
        await super().connect()

        # Создаём файл базы данных если не существует (после создания engine)
        url = self._config.resolved_url
        if url.startswith('sqlite+aiosqlite:///'):
            db_path = url.replace('sqlite+aiosqlite:///', '')
            # Создаём провайдер и файл БД
            provider = SQLiteProvider(self._engine, self._config)
            await provider.create_database(db_path)
            self._provider = provider

    def get_provider(self) -> SQLiteProvider:
        """
        Получить SQLite провайдер.

        Returns:
            SQLiteProvider экземпляр
        """
        if self._provider is None:
            if self._engine is None:
                raise DatabaseError("Engine не инициализирован. Вызовите connect()")
            self._provider = SQLiteProvider(self._engine, self._config)
        return self._provider

    # SQLite специфичные методы

    async def enable_wal_mode(self) -> bool:
        """
        Включить режим Write-Ahead Logging (WAL).

        WAL позволяет читать данные во время записи,
        что улучшает производительность при конкурентном доступе.

        Returns:
            True если режим включён
        """
        try:
            await self.execute_query("PRAGMA journal_mode=WAL")
            logger.info("SQLite WAL режим включён")
            return True
        except Exception as e:
            logger.error(f"Не удалось включить WAL режим: {e}")
            return False

    async def set_synchronous(self, mode: str = 'NORMAL') -> bool:
        """
        Установить режим синхронизации.

        Args:
            mode: Режим синхронизации (OFF, NORMAL, FULL)

        Returns:
            True если режим установлен
        """
        try:
            await self.execute_query(f"PRAGMA synchronous={mode}")
            logger.info(f"SQLite synchronous={mode}")
            return True
        except Exception as e:
            logger.error(f"Не удалось установить synchronous: {e}")
            return False

    async def optimize(self) -> bool:
        """
        Выполнить оптимизацию базы данных.

        Returns:
            True если оптимизация выполнена
        """
        try:
            await self.execute_query("VACUUM")
            await self.execute_query("ANALYZE")
            logger.info("SQLite оптимизирована")
            return True
        except Exception as e:
            logger.error(f"Не удалось оптимизировать SQLite: {e}")
            return False
