"""
Database package

Модуль для работы с базой данных:
- models: SQLAlchemy модели
- repositories: Repository pattern
- factory: Фабрика репозиториев
"""

from database.models import (
    Base,
    Channel,
    TelegramPost,
    GeneratedNews,
    EventContext,
    engine,
    async_session,
)

from database.factory import RepositoryFactory

__all__ = [
    'Base',
    'Channel',
    'TelegramPost',
    'GeneratedNews',
    'EventContext',
    'engine',
    'async_session',
    'RepositoryFactory',
]