"""
Database package

Модуль для работы с базой данных:
- models: SQLAlchemy модели
- repositories: Repository pattern
- factory: Фабрика репозиториев

Примечание: engine создаётся в DatabaseService (services/core/database.py)
"""

from database.models import (
    Base,
    Channel,
    TelegramPost,
    GeneratedNews,
    EventContext,
)

from database.factory import RepositoryFactory

__all__ = [
    'Base',
    'Channel',
    'TelegramPost',
    'GeneratedNews',
    'EventContext',
    'RepositoryFactory',
]