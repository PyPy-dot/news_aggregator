"""
Миграция: Добавить поля recurring и recurrence_pattern в таблицу tasks.

- Переименовать is_daily -> recurring
- Добавить recurrence_pattern (INT, nullable)
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def migrate(session) -> None:
    """
    Выполнить миграцию.

    Args:
        session: SQLAlchemy сессия
    """
    logger.info("Миграция: Обновление таблицы tasks...")

    try:
        # Проверяем существование столбца is_daily
        result = await session.execute(
            text("PRAGMA table_info(tasks)")
        )
        columns = [row[1] for row in result.all()]

        if 'is_daily' in columns:
            # Переименовываем is_daily -> recurring
            # SQLite не поддерживает прямое переименование столбцов,
            # поэтому создаём временную таблицу, копируем данные и пересоздаём оригинальную
            logger.info("Переименование is_daily -> recurring...")

            # Создаём временную таблицу с новой структурой
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS tasks_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    post_id INTEGER,
                    news_id INTEGER,
                    scheduled_at DATETIME,
                    status TEXT DEFAULT 'pending',
                    recurring BOOLEAN DEFAULT FALSE,
                    recurrence_pattern INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME
                )
            """))

            # Копируем данные, переименовывая is_daily -> recurring
            await session.execute(text("""
                INSERT INTO tasks_new (
                    id, task_type, description, post_id, news_id,
                    scheduled_at, status, recurring, created_at, completed_at
                )
                SELECT
                    id, task_type, description, post_id, news_id,
                    scheduled_at, status, is_daily, created_at, completed_at
                FROM tasks
            """))

            # Удаляем старую таблицу
            await session.execute(text("DROP TABLE tasks"))

            # Переименовываем новую таблицу
            await session.execute(text("ALTER TABLE tasks_new RENAME TO tasks"))

            logger.info("✅ Миграция is_daily -> recurring завершена")
        else:
            logger.info("Столбец is_daily не найден, возможно миграция уже выполнена")

        # Проверяем существование столбца recurrence_pattern
        result = await session.execute(
            text("PRAGMA table_info(tasks)")
        )
        columns = [row[1] for row in result.all()]

        if 'recurrence_pattern' not in columns:
            # Добавляем новый столбец
            logger.info("Добавление столбца recurrence_pattern...")
            await session.execute(text("""
                ALTER TABLE tasks ADD COLUMN recurrence_pattern INTEGER
            """))
            logger.info("✅ Столбец recurrence_pattern добавлен")
        else:
            logger.info("Столбец recurrence_pattern уже существует")

        await session.commit()
        logger.info("✅ Миграция таблицы tasks завершена")

    except Exception as e:
        logger.error(f"❌ Ошибка миграции: {e}")
        await session.rollback()
        raise


async def rollback(session) -> None:
    """
    Откатить миграцию.

    Args:
        session: SQLAlchemy сессия
    """
    logger.info("Откат миграции таблицы tasks...")

    try:
        # Создаём временную таблицу со старой структурой
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS tasks_old (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                description TEXT DEFAULT '',
                post_id INTEGER,
                news_id INTEGER,
                scheduled_at DATETIME,
                status TEXT DEFAULT 'pending',
                is_daily BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME
            )
        """))

        # Копируем данные, переименовывая recurring -> is_daily
        await session.execute(text("""
            INSERT INTO tasks_old (
                id, task_type, description, post_id, news_id,
                scheduled_at, status, is_daily, created_at, completed_at
            )
            SELECT
                id, task_type, description, post_id, news_id,
                scheduled_at, status, recurring, created_at, completed_at
            FROM tasks
        """))

        # Удаляем новую таблицу
        await session.execute(text("DROP TABLE tasks"))

        # Переименовываем старую таблицу
        await session.execute(text("ALTER TABLE tasks_old RENAME TO tasks"))

        await session.commit()
        logger.info("✅ Миграция откатана")

    except Exception as e:
        logger.error(f"❌ Ошибка отката миграции: {e}")
        await session.rollback()
        raise
