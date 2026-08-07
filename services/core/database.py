"""
Database Service — управление сессиями базы данных.

Изолирует логику создания и управления сессиями БД,
устраняя необходимость в глобальном async_session.

Корректное управление жизненным циклом подключений.
"""

import logging
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine,
)
from config.settings import settings

logger = logging.getLogger(__name__)


class DatabaseService:
    """
    Сервис для управления подключением к базе данных.

    Attributes:
        engine: SQLAlchemy async engine
        session_factory: Фабрика сессий
    """

    def __init__(self, database_url: str | None = None) -> None:
        """
        Инициализация сервиса БД.

        Args:
            database_url: URL базы данных (по умолчанию из конфига)
        """
        self.database_url = database_url or settings.database_url
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker] = None
        self._initialized = False
        self._disposed = False

        # Создаём engine лениво при первом использовании
        self._init_engine()

        logger.info(f"📁 DatabaseService инициализирован: {self.database_url}")

    def _init_engine(self) -> None:
        """Инициализировать engine и фабрику сессий."""
        # Создаём engine
        self._engine = create_async_engine(
            url=self.database_url,
            echo=False,  # Отключаем вывод SQL-запросов
            pool_pre_ping=True,  # Проверка подключения перед использованием
        )

        # Создаём фабрику сессий
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession
        )

        self._initialized = True
        logger.debug("✅ DatabaseService engine инициализирован")

    @property
    def engine(self) -> AsyncEngine:
        """Получить engine."""
        if self._engine is None:
            raise RuntimeError("DatabaseService not initialized")
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker:
        """Получить фабрику сессий."""
        if self._session_factory is None:
            raise RuntimeError("DatabaseService not initialized")
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

        return self.session_factory()

    @asynccontextmanager
    async def session_context(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Контекстный менеджер для сессии БД.

        Usage:
            async with db_service.session_context() as session:
                # работа с сессией
        """
        session = await self.create_session()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

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

        if self._engine:
            try:
                await self._engine.dispose()
                logger.info("👋 Подключение к базе данных закрыто")
            except Exception as e:
                logger.error(f"❌ Ошибка закрытия подключения к БД: {e}")

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
