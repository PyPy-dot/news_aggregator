"""
Миграция: Добавление таблиц для системы генерации новостей

Что добавляется:
1. Поле category_confidence в таблицу posts (оценка категории от второй ЛЛМ)
2. Таблица generated_news (сгенерированные ЛЛМ новости)
3. Таблица events (контекст событий)

Запуск:
    .venv/Scripts/python.exe -m database.migrate_add_news_tables
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

        # Проверяем какие таблицы уже существуют
        result = await conn.execute(text("""
            SELECT name FROM sqlite_master WHERE type='table'
        """))
        existing_tables = [row[0] for row in result.fetchall()]

        logger.info(f"Существующие таблицы: {existing_tables}")

        # 1. Добавляем поле category_confidence в posts (если нет)
        if 'posts' in existing_tables:
            logger.info("📊 Проверка поля category_confidence в таблице posts...")

            result = await conn.execute(text("""
                PRAGMA table_info(posts)
            """))
            columns = [row[1] for row in result.fetchall()]

            if 'category_confidence' not in columns:
                logger.info("➕ Добавление поля category_confidence...")
                await conn.execute(text("""
                    ALTER TABLE posts ADD COLUMN category_confidence FLOAT DEFAULT 0.0
                """))
                logger.info("✅ Поле category_confidence добавлено")
            else:
                logger.info("✓ Поле category_confidence уже существует")
        else:
            logger.warning("⚠️ Таблица posts не найдена — миграция невозможна")
            return

        # 2. Создаём таблицу events (контекст событий)
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

        # 3. Создаём таблицу generated_news
        if 'generated_news' not in existing_tables:
            logger.info("➕ Создание таблицы generated_news...")
            await conn.execute(text("""
                CREATE TABLE generated_news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_post_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    event_context_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (original_post_id) REFERENCES posts(id) ON DELETE CASCADE,
                    FOREIGN KEY (event_context_id) REFERENCES events(id) ON DELETE SET NULL
                )
            """))
            logger.info("✅ Таблица generated_news создана")
        else:
            logger.info("✓ Таблица generated_news уже существует")

        logger.info("🎉 Миграция успешно завершена!")
        logger.info("")
        logger.info("Схема БД:")
        logger.info("  posts.category_confidence — оценка категории (0.0-1.0)")
        logger.info("  events — контекст событий (JSON)")
        logger.info("  generated_news — сгенерированные ЛЛМ новости")


def main():
    """Точка входа"""
    logger.info("🚀 Запуск миграции: добавление таблиц для генерации новостей")
    logger.info("=" * 60)

    try:
        asyncio.run(migrate())
    except Exception as e:
        logger.error(f"❌ Ошибка миграции: {e}")
        raise


if __name__ == '__main__':
    main()
