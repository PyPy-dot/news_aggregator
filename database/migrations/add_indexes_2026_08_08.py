"""
Миграция: Добавление индексов для улучшения производительности.

Индексы добавляются на поля:
- TelegramPost: category, urgency, created_at, checked_at
- GeneratedNews: category, moderation_status, created_at
"""

import asyncio
import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_migration():
    """Выполнить миграцию."""
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine('sqlite+aiosqlite:///db.sqlite3', echo=False)

    async with engine.connect() as conn:
        # TelegramPost индексы
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_posts_category ON posts(category)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_posts_urgency ON posts(urgency)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_posts_checked_at ON posts(checked_at)"
        ))

        # GeneratedNews индексы
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_generated_news_category ON generated_news(category)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_generated_news_moderation_status ON generated_news(moderation_status)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_generated_news_created_at ON generated_news(created_at)"
        ))

        await conn.commit()
        logger.info("✅ Индексы успешно добавлены")

    await engine.dispose()


if __name__ == '__main__':
    asyncio.run(run_migration())
