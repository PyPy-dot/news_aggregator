"""
Миграция: Добавление таблицы tasks (задачи для обработки).

Создаёт таблицу для хранения задач:
- Прямая генерация новостей
- Внеплановая обработка плановых новостей

Запуск:
    python3 -m database.migrations.migrate_add_tasks_table
"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import text
from services.core.database import get_database_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Выполнить миграцию."""
    db_service = get_database_service()

    async with db_service.session_context() as session:
        # Создаём таблицу
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                description TEXT DEFAULT '',
                post_id INTEGER,
                news_id INTEGER,
                scheduled_at TIMESTAMP,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """))

        await session.commit()

    logger.info("✅ Миграция 'add_tasks_table' выполнена успешно")


async def rollback():
    """Откатить миграцию."""
    db_service = get_database_service()

    async with db_service.session_context() as session:
        await session.execute(text("DROP TABLE IF EXISTS tasks"))
        await session.commit()

    logger.info("✅ Миграция 'add_tasks_table' откатана")


async def main():
    """Точка входа."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'rollback':
        await rollback()
    else:
        await migrate()


if __name__ == '__main__':
    asyncio.run(main())
