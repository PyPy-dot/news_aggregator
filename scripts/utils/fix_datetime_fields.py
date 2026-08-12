"""
Скрипт для исправления некорректных datetime полей в БД.

Проблема: некоторые записи имеют пустые строки '' вместо NULL в полях
subscription_started_at и subscription_ends_at, что вызывает ошибку:
"Invalid isoformat string: ''"

Использование:
    python fix_datetime_fields.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s — %(name)s — %(levelname)s — %(message)s'
)
logger = logging.getLogger(__name__)


async def fix_datetime_fields():
    """Исправить пустые строки в datetime полях."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine('sqlite+aiosqlite:///db.sqlite3', echo=False)

    async with engine.connect() as conn:
        # Исправляем subscription_started_at
        result = await conn.execute(
            text("UPDATE users SET subscription_started_at = NULL WHERE subscription_started_at = ''")
        )
        fixed_started = result.rowcount

        # Исправляем subscription_ends_at
        result = await conn.execute(
            text("UPDATE users SET subscription_ends_at = NULL WHERE subscription_ends_at = ''")
        )
        fixed_ends = result.rowcount

        await conn.commit()

        total_fixed = fixed_started + fixed_ends
        if total_fixed > 0:
            logger.info(f"✅ Исправлено записей: {total_fixed}")
            logger.info(f"   - subscription_started_at: {fixed_started}")
            logger.info(f"   - subscription_ends_at: {fixed_ends}")
        else:
            logger.info("✅ Нет записей с некорректными datetime полями")

    await engine.dispose()
    return total_fixed


async def add_indexes():
    """Добавить индексы для улучшения производительности."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine('sqlite+aiosqlite:///db.sqlite3', echo=False)

    async with engine.connect() as conn:
        # TelegramPost индексы
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_posts_category ON posts(category)",
            "CREATE INDEX IF NOT EXISTS idx_posts_urgency ON posts(urgency)",
            "CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_posts_checked_at ON posts(checked_at)",
            # GeneratedNews индексы
            "CREATE INDEX IF NOT EXISTS idx_generated_news_category ON generated_news(category)",
            "CREATE INDEX IF NOT EXISTS idx_generated_news_moderation_status ON generated_news(moderation_status)",
            "CREATE INDEX IF NOT EXISTS idx_generated_news_created_at ON generated_news(created_at)",
        ]

        for sql in indexes:
            await conn.execute(text(sql))

        await conn.commit()

    logger.info("✅ Индексы успешно добавлены")
    await engine.dispose()


async def main():
    """Главная функция."""
    logger.info("🔧 Начало исправления данных...")

    # Исправляем datetime поля
    fixed_count = await fix_datetime_fields()

    # Добавляем индексы
    await add_indexes()

    logger.info("✅ Все исправления применены")


if __name__ == '__main__':
    asyncio.run(main())
