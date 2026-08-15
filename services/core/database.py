"""
Database Service — управление сессиями базы данных.

Использует новый слой абстракции (services.database) для поддержки
SQLite, PostgreSQL и MySQL с единым API.

Корректное управление жизненным циклом подключений с подробным логированием.
"""

import logging
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    AsyncEngine,
)
from config.settings import settings

# Импортируем новый слой абстракции
from services.database import (
    IDatabaseService,
    DatabaseType,
)

logger = logging.getLogger(__name__)


class DatabaseService:
    """
    Сервис для управления подключением к базе данных.

    Обёртка над новым слоем абстракции (services.database) для
    обратной совместимости со старым API.

    Attributes:
        engine: SQLAlchemy async engine
        session_factory: Фабрика сессий
        database_url: URL базы данных
    """

    def __init__(self, database_url: str | None = None) -> None:
        """
        Инициализация сервиса БД.

        Args:
            database_url: URL базы данных (по умолчанию из конфига)
        """
        self.database_url = database_url or settings.database_url_resolved
        self._service: Optional[IDatabaseService] = None
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker] = None
        self._initialized = False
        self._disposed = False

        # Создаём engine лениво при первом использовании
        self._init_engine()

    def _init_engine(self) -> None:
        """Инициализировать engine через новый слой абстракции."""
        from services.database import DatabaseServiceFactory, DatabaseConfig

        # Определяем тип БД по URL
        db_type = DatabaseType.from_url(self.database_url)

        # Создаём конфигурацию
        config = DatabaseConfig(
            url=self.database_url,
            db_type=db_type,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
            echo=settings.db_echo,
            pool_pre_ping=True,
        )

        # Создаём сервис через фабрику
        self._service = DatabaseServiceFactory.create(config)

        # Логирование типа СУБД и параметров
        logger.info(f"📊 СУБД: {db_type.name}")
        logger.info(f"📊 URL: {self._mask_password(self.database_url)}")
        logger.info(f"📊 Параметры пула: size={config.pool_size}, overflow={config.max_overflow}, timeout={config.pool_timeout}s")

        self._initialized = True
        logger.debug("✅ DatabaseService инициализирован")

    def _mask_password(self, url: str) -> str:
        """Замаскировать пароль в URL для логирования."""
        if '://' not in url:
            return url

        prefix, rest = url.split('://', 1)
        if '@' not in rest:
            return url

        host_part = rest.split('@', 1)[1]
        return f"{prefix}://***:***@{host_part}"

    @property
    def engine(self) -> AsyncEngine:
        """Получить engine."""
        if self._service is None:
            raise RuntimeError("DatabaseService not initialized")
        return self._service.engine

    @property
    def session_factory(self) -> async_sessionmaker:
        """Получить фабрику сессий."""
        if self._session_factory is None:
            if self._service is None:
                raise RuntimeError("DatabaseService not initialized")

            from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
            self._session_factory = async_sessionmaker(
                self._service.engine,
                expire_on_commit=False,
                class_=AsyncSession
            )
        return self._session_factory

    async def create_session(self) -> AsyncSession:
        """
        Создать новую сессию БД.

        Returns:
            AsyncSession сессия

        Raises:
            RuntimeError: Если сервис не инициализирован
        """
        if not self._initialized:
            self._init_engine()

        if self._service is None:
            raise RuntimeError("DatabaseService not initialized")

        return await self._service.create_session()

    @asynccontextmanager
    async def session_context(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Контекстный менеджер для сессии БД.

        Usage:
            async with db_service.session_context() as session:
                # работа с сессией
        """
        import gc

        if self._service is None:
            raise RuntimeError("DatabaseService not initialized")

        async with self._service.session_context() as session:
            yield session

        gc.collect()
        logger.debug("Сессия БД закрыта")

    async def init_db(self) -> None:
        """
        Инициализировать базу данных (создать таблицы).

        Usage:
            await db_service.init_db()
        """
        from database.models import Base

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("✅ База данных инициализирована")

    async def dispose(self) -> None:
        """
        Закрыть подключение к базе данных.

        Освобождает все ресурсы engine.
        """
        if self._disposed:
            logger.debug("DatabaseService уже утилизирован")
            return

        if self._service:
            try:
                await self._service.disconnect()
                logger.info(f"👋 Подключение к {self._service.db_type.name} закрыто")
            except Exception as e:
                logger.error(f"❌ Ошибка закрытия подключения к БД: {e}")

        self._service = None
        self._engine = None
        self._session_factory = None
        self._initialized = False
        self._disposed = True


# Глобальный экземпляр (singleton)
_db_service: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    """
    Получить глобальный сервис БД (singleton).

    Returns:
        DatabaseService экземпляр
    """
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Получить сессию БД (для dependency injection).

    Usage:
        async for session in get_db_session():
            # работа с сессией

    Или через контекстный менеджер:
        async with get_db_session() as session:
            # работа с сессией
    """
    db_service = get_database_service()
    async with db_service.session_context() as session:
        yield session


async def dispose_database_service() -> None:
    """
    Утилизировать глобальный сервис БД.

    Вызывается при завершении приложения.
    """
    global _db_service
    if _db_service is not None:
        await _db_service.dispose()
        _db_service = None
