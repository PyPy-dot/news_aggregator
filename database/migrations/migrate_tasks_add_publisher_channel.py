"""
Миграция: Добавить поле publisher_channel_id в таблицу tasks.

Дата: 2026-08-08
"""

import asyncio
import logging
from sqlalchemy import text
from services.core.database import get_database_service, Task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Добавить поле publisher_channel_id в таблицу tasks."""
    logger.info("🔧 Начало миграции: Добавление publisher_channel_id в tasks...")

    try:
        db_service = get_database_service()
    async with db_service.engine.begin() as conn:
            # Пробуем добавить колонку (игнорируем ошибку если уже существует)
            try:
                await conn.execute(text(
                    "ALTER TABLE tasks ADD COLUMN publisher_channel_id INTEGER"
                ))
                await conn.commit()
                logger.info("✅ Миграция завершена: добавлена колонка publisher_channel_id")
            except Exception as e:
                if "duplicate column" in str(e).lower():
                    logger.info("✅ Колонка publisher_channel_id уже существует")
                else:
                    raise
    except Exception as e:
        logger.error(f"❌ Ошибка миграции: {e}")
        raise


if __name__ == '__main__':
    asyncio.run(migrate())
