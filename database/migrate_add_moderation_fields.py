"""
Миграция: Добавление полей для системы модерации и тэгирования

Что добавляется:
1. GeneratedNews.tags — JSON список тэгов
2. GeneratedNews.moderation_status — статус модерации (pending/approved/rejected)
3. GeneratedNews.admin_id — ID админа, принявшего решение
4. EventContext.tags — JSON список тэгов события
5. EventContext.summary — выжимка для векторного поиска
6. EventContext.last_processed_at — время последней обработки планировщиком

Запуск:
    .venv/Scripts/python.exe -m database.migrate_add_moderation_fields
"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import text
from database.models import engine

logging.basicConfig(
    level=logging.INFO,
    format='[LOG - %(levelname)s] %(asctime)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


async def migrate():
    """Выполняет миграцию БД"""

    async with engine.begin() as conn:
        logger.info("🔍 Проверка существующих таблиц...")

        result = await conn.execute(text("""
            SELECT name FROM sqlite_master WHERE type='table'
        """))
        existing_tables = [row[0] for row in result.fetchall()]
        logger.info(f"Существующие таблицы: {existing_tables}")

        # 1. Обновляем таблицу generated_news
        if 'generated_news' in existing_tables:
            logger.info("📊 Проверка таблицы generated_news...")

            result = await conn.execute(text("PRAGMA table_info(generated_news)"))
            columns = [row[1] for row in result.fetchall()]

            # Добавляем tags
            if 'tags' not in columns:
                logger.info("➕ Добавление поля tags...")
                await conn.execute(text("""
                    ALTER TABLE generated_news ADD COLUMN tags TEXT DEFAULT '[]'
                """))
                logger.info("✅ Поле tags добавлено")
            else:
                logger.info("✓ Поле tags уже существует")

            # Добавляем moderation_status
            if 'moderation_status' not in columns:
                logger.info("➕ Добавление поля moderation_status...")
                await conn.execute(text("""
                    ALTER TABLE generated_news ADD COLUMN moderation_status TEXT DEFAULT 'pending'
                """))
                logger.info("✅ Поле moderation_status добавлено")
            else:
                logger.info("✓ Поле moderation_status уже существует")

            # Добавляем admin_id
            if 'admin_id' not in columns:
                logger.info("➕ Добавление поля admin_id...")
                await conn.execute(text("""
                    ALTER TABLE generated_news ADD COLUMN admin_id INTEGER
                """))
                logger.info("✅ Поле admin_id добавлено")
            else:
                logger.info("✓ Поле admin_id уже существует")
        else:
            logger.warning("⚠️ Таблица generated_news не найдена")

        # 2. Обновляем таблицу events
        if 'events' in existing_tables:
            logger.info("📊 Проверка таблицы events...")

            result = await conn.execute(text("PRAGMA table_info(events)"))
            columns = [row[1] for row in result.fetchall()]

            # Добавляем tags
            if 'tags' not in columns:
                logger.info("➕ Добавление поля tags...")
                await conn.execute(text("""
                    ALTER TABLE events ADD COLUMN tags TEXT DEFAULT '[]'
                """))
                logger.info("✅ Поле tags добавлено")
            else:
                logger.info("✓ Поле tags уже существует")

            # Добавляем summary
            if 'summary' not in columns:
                logger.info("➕ Добавление поля summary...")
                await conn.execute(text("""
                    ALTER TABLE events ADD COLUMN summary TEXT DEFAULT ''
                """))
                logger.info("✅ Поле summary добавлено")
            else:
                logger.info("✓ Поле summary уже существует")

            # Добавляем last_processed_at
            if 'last_processed_at' not in columns:
                logger.info("➕ Добавление поля last_processed_at...")
                await conn.execute(text("""
                    ALTER TABLE events ADD COLUMN last_processed_at DATETIME
                """))
                logger.info("✅ Поле last_processed_at добавлено")
            else:
                logger.info("✓ Поле last_processed_at уже существует")
        else:
            logger.warning("⚠️ Таблица events не найдена")

        logger.info("🎉 Миграция успешно завершена!")
        logger.info("")
        logger.info("Изменения в схеме БД:")
        logger.info("  generated_news.tags — JSON список тэгов новости")
        logger.info("  generated_news.moderation_status — pending/approved/rejected")
        logger.info("  generated_news.admin_id — ID админа")
        logger.info("  events.tags — JSON список тэгов события")
        logger.info("  events.summary — выжимка для векторного поиска")
        logger.info("  events.last_processed_at — время обработки планировщиком")


def main():
    """Точка входа"""
    logger.info("🚀 Запуск миграции: добавление полей модерации и тэгирования")
    logger.info("=" * 60)

    try:
        asyncio.run(migrate())
    except Exception as e:
        logger.error(f"❌ Ошибка миграции: {e}")
        raise


if __name__ == '__main__':
    main()
