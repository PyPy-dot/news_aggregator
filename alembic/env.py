"""
Alembic env.py для News Aggregator.

Настроен для работы с:
- SQLAlchemy 2.0
- SQLite (aiosqlite)
- PostgreSQL (asyncpg)
- Autogenerate для моделей
"""

from logging.config import fileConfig
import re

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy import create_engine

from alembic import context

# Импортируем модели для autogenerate
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.models import Base
from config.settings import settings

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def get_url() -> str:
    """
    Получить URL базы данных из настроек.

    Поддержка SQLite и PostgreSQL:
    - SQLite: sqlite+aiosqlite:///db.sqlite3 → sqlite:///db.sqlite3
    - PostgreSQL: postgresql+asyncpg://... → postgresql://...
    """
    # Получаем URL из настроек (используем новый метод database_url_resolved)
    database_url = settings.database_url_resolved

    # Alembic работает с sync версией драйверов
    # Преобразуем async драйверы в sync
    if database_url.startswith('sqlite+aiosqlite://'):
        # SQLite: sqlite+aiosqlite:///db.sqlite3 → sqlite:///db.sqlite3
        return database_url.replace('+aiosqlite', '')
    elif database_url.startswith('postgresql+asyncpg://'):
        # PostgreSQL: postgresql+asyncpg://... → postgresql://...
        return database_url.replace('+asyncpg', '')
    elif database_url.startswith('postgresql://'):
        # Уже sync версия PostgreSQL
        return database_url
    else:
        # По умолчанию считаем SQLite
        db_path = settings.db_path
        return f"sqlite:///{db_path}"


def is_postgresql(url: str) -> bool:
    """Проверить, является ли URL PostgreSQL."""
    return url.startswith('postgresql://')


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    is_pg = is_postgresql(url)

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=not is_pg,  # Только для SQLite
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = get_url()
    is_pg = is_postgresql(url)

    if is_pg:
        # PostgreSQL: используем PoolQueue для лучшей производительности
        connectable = create_engine(
            url,
            poolclass=pool.QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
        logger_msg = "✅ PostgreSQL"
    else:
        # SQLite: используем NullPool для простоты
        connectable = create_engine(
            url,
            poolclass=pool.NullPool,
        )
        logger_msg = "✅ SQLite"

    print(f"{logger_msg}: {url}")

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=not is_pg,  # Только для SQLite
            compare_type=True,  # Сравнивать типы колонок
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
