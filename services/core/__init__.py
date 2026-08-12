"""
Core services package.

Базовые сервисы и инфраструктура:
- container: DI контейнер
- database: Управление сессиями БД
"""

from services.core.container import Container
from services.database import IDatabaseService, get_db_session

__all__ = [
    'Container',
    'IDatabaseService',
    'get_db_session',
]
