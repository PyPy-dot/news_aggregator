"""
Миграция: Обновление схемы для генерации новостей v2

Что изменяется:
1. Поле tags в таблицу channels (JSON список категорий)
2. Пересоздание таблицы generated_news (без связи с posts, с source_post_ids)

Запуск:
    .venv/Scripts/python.exe -m database.migrate_update_news_schema
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
    async with db_service.engine.begin() as conn:
        logger.info("🔍 Проверка существующих таблиц...")

        # Проверяем какие таблицы уже существуют
        result = await conn.execute(text("""
            SELECT name FROM sqlite_master WHERE type='table'
        """))
        existing_tables = [row[0] for row in result.fetchall()]

        logger.info(f"Существующие таблицы: {existing_tables}")

        # 1. Добавляем поле tags в channels (если нет)
        if 'channels' in existing_tables:
            logger.info("📊 Проверка поля tags в таблице channels...")

            result = await conn.execute(text("""
                PRAGMA table_info(channels)
            """))
            columns = [row[1] for row in result.fetchall()]

            if 'tags' not in columns:
                logger.info("➕ Добавление поля tags...")
                await conn.execute(text("""
                    ALTER TABLE channels ADD COLUMN tags TEXT DEFAULT '[]'
                """))
                logger.info("✅ Поле tags добавлено")
            else:
                logger.info("✓ Поле tags уже существует")
        else:
            logger.warning("⚠️ Таблица channels не найдена")

        # 2. Пересоздаём таблицу generated_news с новой схемой
        logger.info("🔄 Обновление таблицы generated_news...")

        # Сначала удаляем старую таблицу (если есть)
        if 'generated_news' in existing_tables:
            logger.info("🗑️ Удаление старой таблицы generated_news...")
            await conn.execute(text("DROP TABLE IF EXISTS generated_news"))

        # Создаём новую таблицу
        logger.info("➕ Создание новой таблицы generated_news...")
        await conn.execute(text("""
            CREATE TABLE generated_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                source_post_ids TEXT NOT NULL,
                source_event_ids TEXT DEFAULT '[]',
                category TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        logger.info("✅ Таблица generated_news обновлена")

        # 3. Проверяем таблицу events (должна уже существовать)
        if 'events' not in existing_tables:
            logger.info("➕ Создание таблицы events...")
            await conn.execute(text("""
                CREATE TABLE events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    context_data TEXT NOT NULL,
                    event_category TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
                )
            """))
            logger.info("✅ Таблица events создана")
        else:
            logger.info("✓ Таблица events уже существует")

        logger.info("🎉 Миграция успешно завершена!")
        logger.info("")
        logger.info("Изменения в схеме БД:")
        logger.info("  channels.tags — JSON список категорий канала")
        logger.info("  generated_news.text — сгенерированный текст новости")
        logger.info("  generated_news.source_post_ids — JSON [1, 2, 3] ID исходных постов")
        logger.info("  generated_news.source_event_ids — JSON [1, 2] ID событий")
        logger.info("  generated_news.category — категория новости")


def main():
    """Точка входа"""
    logger.info("🚀 Запуск миграции: обновление схемы новостей v2")
    logger.info("=" * 60)

    try:
        asyncio.run(migrate())
    except Exception as e:
        logger.error(f"❌ Ошибка миграции: {e}")
        raise


if __name__ == '__main__':
    main()
