"""
Миграция: Добавление таблицы publishers и полей bypass_ara, publisher_channel_id, published_at

Изменения:
- Создана таблица publishers
- Добавлены поля в generated_news: bypass_ara, publisher_channel_id, published_at
- Добавлены поля в posts: bypass_ara, publisher_channel_id
"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import text
from database.models import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Выполнить миграцию."""
    async with engine.begin() as conn:
        logger.info("Начало миграции: добавление publishers и связанных полей")

        # Создаём таблицу publishers
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS publishers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id BIGINT UNIQUE NOT NULL,
                title VARCHAR NOT NULL,
                description VARCHAR DEFAULT '',
                is_active BOOLEAN DEFAULT 1,
                category VARCHAR,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        logger.info("✅ Таблица publishers создана")

        # Добавляем поля в generated_news
        try:
            await conn.execute(text(
                "ALTER TABLE generated_news ADD COLUMN bypass_ara BOOLEAN DEFAULT 0"
            ))
            logger.info("✅ Добавлено поле bypass_ara в generated_news")
        except Exception as e:
            logger.warning(f"Поле bypass_ara уже существует: {e}")

        try:
            await conn.execute(text(
                "ALTER TABLE generated_news ADD COLUMN publisher_channel_id INTEGER REFERENCES publishers(id)"
            ))
            logger.info("✅ Добавлено поле publisher_channel_id в generated_news")
        except Exception as e:
            logger.warning(f"Поле publisher_channel_id уже существует: {e}")

        try:
            await conn.execute(text(
                "ALTER TABLE generated_news ADD COLUMN published_at DATETIME"
            ))
            logger.info("✅ Добавлено поле published_at в generated_news")
        except Exception as e:
            logger.warning(f"Поле published_at уже существует: {e}")

        # Добавляем поля в posts
        try:
            await conn.execute(text(
                "ALTER TABLE posts ADD COLUMN bypass_ara BOOLEAN DEFAULT 0"
            ))
            logger.info("✅ Добавлено поле bypass_ara в posts")
        except Exception as e:
            logger.warning(f"Поле bypass_ara уже существует: {e}")

        try:
            await conn.execute(text(
                "ALTER TABLE posts ADD COLUMN publisher_channel_id INTEGER REFERENCES publishers(id)"
            ))
            logger.info("✅ Добавлено поле publisher_channel_id в posts")
        except Exception as e:
            logger.warning(f"Поле publisher_channel_id уже существует: {e}")

        logger.info("🎉 Миграция завершена успешно")


if __name__ == '__main__':
    asyncio.run(migrate())
