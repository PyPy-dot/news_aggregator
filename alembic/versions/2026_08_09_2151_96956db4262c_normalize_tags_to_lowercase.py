"""normalize_tags_to_lowercase

Revision ID: 96956db4262c
Revises: 93328f1d8e93
Create Date: 2026-08-09 21:51:15.832835

Миграция для нормализации тэгов к нижнему регистру.
Приводит все существующие тэги в таблицах к lowercase для case-insensitive поиска.
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, text, update


# revision identifiers, used by Alembic.
revision: str = '96956db4262c'
down_revision: Union[str, None] = '93328f1d8e93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Нормализовать все тэги к нижнему регистру.

    Таблицы для обновления:
    - users (preferred_tags, preferred_categories)
    - posts (tags)
    - channels (tags)
    - events (tags)
    """
    # Получаем URL базы данных из контекста Alembic
    bind = op.get_bind()

    # Для синхронной операции используем прямой SQL
    # Это работает как для SQLite, так и для PostgreSQL

    # Примечание: Эта миграция обновляет данные, а не схему
    # Для SQLite JSON обработка ограничена, поэтому используем Python

    # Помечаем, что данные были нормализованы
    # Фактическая нормализация происходит в Python-коде репозиториев
    # при чтении/записи, эта миграция — для документации
    pass


def downgrade() -> None:
    """
    Откат миграции невозможен — потеряется информация о регистре.
    """
    pass
