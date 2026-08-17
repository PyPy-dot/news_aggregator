"""
Миграция: Мульти-источниковая поддержка (Phase 1)

Что изменяется:
1. generated_news — новое поле source_ids (JSON: ["tg_5", "rss_13", "web_10"])
2. events — post_id становится nullable без FK; новое поле source_news_ids
3. rss_news — новые поля: urgency, category_confidence, rate, generated_news_id;
   удаление post_id (FK к posts больше не нужен)
4. web_news — новые поля: urgency, category_confidence, rate, generated_news_id;
   удаление post_id (FK к posts больше не нужен)

Запуск:
    python -m database.migrations.migrate_multisource_2026_08_17
"""

import asyncio
import logging

from sqlalchemy import text
from services.core.database import get_database_service

logging.basicConfig(
    level=logging.INFO,
    format='[LOG - %(levelname)s] %(asctime)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


async def migrate():
    """Выполняет миграцию БД"""

    db_service = get_database_service()
    await db_service._service.connect()

    async with db_service.engine.begin() as conn:
        logger.info("🔍 Проверка существующих полей...")

        # Проверяем какие таблицы уже существуют
        result = await conn.execute(text("""
            SELECT name FROM sqlite_master WHERE type='table'
        """))
        existing_tables = [row[0] for row in result.fetchall()]
        logger.info(f"Существующие таблицы: {existing_tables}")

        # ============================================================
        # 1. generated_news — поле source_ids
        # ============================================================
        if 'generated_news' in existing_tables:
            if await _column_exists(conn, 'generated_news', 'source_ids'):
                logger.info("✅ generated_news.source_ids уже существует")
            else:
                logger.info("➕ Добавляю generated_news.source_ids")
                await conn.execute(text("""
                    ALTER TABLE generated_news
                    ADD COLUMN source_ids TEXT DEFAULT '[]'
                """))

        # ============================================================
        # 2. events — post_id nullable + source_news_ids
        # ============================================================
        if 'events' in existing_tables:
            # source_news_ids — новое поле
            if await _column_exists(conn, 'events', 'source_news_ids'):
                logger.info("✅ events.source_news_ids уже существует")
            else:
                logger.info("➕ Добавляю events.source_news_ids")
                await conn.execute(text("""
                    ALTER TABLE events
                    ADD COLUMN source_news_ids TEXT DEFAULT '[]'
                """))

            # post_id: нужно сделать nullable и убрать FK
            # В SQLite нельзя убрать FK напрямую — пересоздаём таблицу
            if await _column_exists(conn, 'events', 'post_id'):
                logger.info("🔄 Обновляю events.post_id (nullable, без FK)")
                await _recreate_events_table(conn)

        # ============================================================
        # 3. rss_news — поля категоризации + generated_news_id
        # ============================================================
        if 'rss_news' in existing_tables:
            # urgency
            if await _column_exists(conn, 'rss_news', 'urgency'):
                logger.info("✅ rss_news.urgency уже существует")
            else:
                logger.info("➕ Добавляю rss_news.urgency")
                await conn.execute(text("""
                    ALTER TABLE rss_news
                    ADD COLUMN urgency INTEGER
                """))

            # category_confidence
            if await _column_exists(conn, 'rss_news', 'category_confidence'):
                logger.info("✅ rss_news.category_confidence уже существует")
            else:
                logger.info("➕ Добавляю rss_news.category_confidence")
                await conn.execute(text("""
                    ALTER TABLE rss_news
                    ADD COLUMN category_confidence REAL DEFAULT 0.0
                """))

            # rate
            if await _column_exists(conn, 'rss_news', 'rate'):
                logger.info("✅ rss_news.rate уже существует")
            else:
                logger.info("➕ Добавляю rss_news.rate")
                await conn.execute(text("""
                    ALTER TABLE rss_news
                    ADD COLUMN rate INTEGER DEFAULT 50
                """))

            # generated_news_id
            if await _column_exists(conn, 'rss_news', 'generated_news_id'):
                logger.info("✅ rss_news.generated_news_id уже существует")
            else:
                logger.info("➕ Добавляю rss_news.generated_news_id")
                await conn.execute(text("""
                    ALTER TABLE rss_news
                    ADD COLUMN generated_news_id INTEGER
                """))

        # ============================================================
        # 4. web_news — поля категоризации + generated_news_id
        # ============================================================
        if 'web_news' in existing_tables:
            # urgency
            if await _column_exists(conn, 'web_news', 'urgency'):
                logger.info("✅ web_news.urgency уже существует")
            else:
                logger.info("➕ Добавляю web_news.urgency")
                await conn.execute(text("""
                    ALTER TABLE web_news
                    ADD COLUMN urgency INTEGER
                """))

            # category_confidence
            if await _column_exists(conn, 'web_news', 'category_confidence'):
                logger.info("✅ web_news.category_confidence уже существует")
            else:
                logger.info("➕ Добавляю web_news.category_confidence")
                await conn.execute(text("""
                    ALTER TABLE web_news
                    ADD COLUMN category_confidence REAL DEFAULT 0.0
                """))

            # rate
            if await _column_exists(conn, 'web_news', 'rate'):
                logger.info("✅ web_news.rate уже существует")
            else:
                logger.info("➕ Добавляю web_news.rate")
                await conn.execute(text("""
                    ALTER TABLE web_news
                    ADD COLUMN rate INTEGER DEFAULT 50
                """))

            # generated_news_id
            if await _column_exists(conn, 'web_news', 'generated_news_id'):
                logger.info("✅ web_news.generated_news_id уже существует")
            else:
                logger.info("➕ Добавляю web_news.generated_news_id")
                await conn.execute(text("""
                    ALTER TABLE web_news
                    ADD COLUMN generated_news_id INTEGER
                """))

    logger.info("✅ Миграция мульти-источниковой поддержки завершена")


async def _column_exists(conn, table: str, column: str) -> bool:
    """Проверить, существует ли колонка в таблице."""
    result = await conn.execute(text(f"""
        PRAGMA table_info({table})
    """))
    columns = [row[1] for row in result.fetchall()]
    return column in columns


async def _recreate_events_table(conn):
    """
    Пересоздать таблицу events: post_id без FK, nullable.

    SQLite не поддерживает DROP COLUMN / ALTER FK,
    поэтому пересоздаём таблицу полностью с сохранением данных.
    """
    # 1. Создаём новую таблицу с нужной схемой
    await conn.execute(text("""
        CREATE TABLE events_new (
            id INTEGER PRIMARY KEY,
            post_id INTEGER,
            source_news_ids TEXT DEFAULT '[]',
            context_data TEXT NOT NULL,
            event_category TEXT NOT NULL,
            tags TEXT DEFAULT '[]',
            last_processed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # 2. Копируем данные
    # Проверяем, есть ли уже source_news_ids в старой таблице
    has_source_news_ids = await _column_exists(conn, 'events', 'source_news_ids')

    if has_source_news_ids:
        await conn.execute(text("""
            INSERT INTO events_new (id, post_id, source_news_ids, context_data, event_category, tags, last_processed_at, created_at)
            SELECT id, post_id, source_news_ids, context_data, event_category, tags, last_processed_at, created_at
            FROM events
        """))
    else:
        await conn.execute(text("""
            INSERT INTO events_new (id, post_id, source_news_ids, context_data, event_category, tags, last_processed_at, created_at)
            SELECT id, post_id, '[]', context_data, event_category, tags, last_processed_at, created_at
            FROM events
        """))

    # 3. Заменяем таблицу
    await conn.execute(text("DROP TABLE events"))
    await conn.execute(text("ALTER TABLE events_new RENAME TO events"))

    logger.info("✅ Таблица events пересоздана (post_id без FK, добавлен source_news_ids)")


async def main():
    """Точка входа."""
    await migrate()


if __name__ == '__main__':
    asyncio.run(main())
