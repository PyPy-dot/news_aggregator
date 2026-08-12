"""
Миграция: Добавление полей trust_rating и is_trusted в таблицу channels
Запуск: python -m database.migrate_add_trust_fields
"""

import asyncio
import logging
from sqlalchemy import text
from services.core.database import get_database_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Добавляет новые поля в таблицу channels если их нет"""
    db_service = get_database_service()
    async with db_service.engine.begin() as conn:
        # Проверяем是否存在 столбец trust_rating
        result = await conn.execute(text(
            "PRAGMA table_info(channels)"
        ))
        columns = [row[1] for row in result.fetchall()]

        # Добавляем trust_rating если нет
        if 'trust_rating' not in columns:
            logger.info("Добавляем колонку trust_rating...")
            await conn.execute(text(
                "ALTER TABLE channels ADD COLUMN trust_rating FLOAT DEFAULT 0.5"
            ))
            logger.info("✅ trust_rating добавлена")
        else:
            logger.info("trust_rating уже существует")

        # Добавляем is_trusted если нет
        if 'is_trusted' not in columns:
            logger.info("Добавляем колонку is_trusted...")
            await conn.execute(text(
                "ALTER TABLE channels ADD COLUMN is_trusted BOOLEAN DEFAULT 0"
            ))
            logger.info("✅ is_trusted добавлена")
        else:
            logger.info("is_trusted уже существует")

        # Добавляем source_trust_rating в posts если нет
        result = await conn.execute(text(
            "PRAGMA table_info(posts)"
        ))
        post_columns = [row[1] for row in result.fetchall()]

        if 'source_trust_rating' not in post_columns:
            logger.info("Добавляем колонку source_trust_rating в posts...")
            await conn.execute(text(
                "ALTER TABLE posts ADD COLUMN source_trust_rating FLOAT DEFAULT 0.5"
            ))
            logger.info("✅ source_trust_rating добавлена")
        else:
            logger.info("source_trust_rating уже существует")

        logger.info("🎉 Миграция завершена!")


if __name__ == '__main__':
    asyncio.run(migrate())
