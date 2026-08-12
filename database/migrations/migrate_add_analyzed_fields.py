"""
Миграция: Добавление полей для отслеживания обработки Аналитиком

Что добавляется:
1. TelegramPost.analyzed_at — дата и время обработки Аналитиком
2. TelegramPost.generated_news_id — ID сгенерированной новости

Запуск:
    .venv/Scripts/python.exe -m database.migrate_add_analyzed_fields
"""

import asyncio
import logging
from datetime import datetime

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

        result = await conn.execute(text("""
            SELECT name FROM sqlite_master WHERE type='table'
        """))
        existing_tables = [row[0] for row in result.fetchall()]
        logger.info(f"Существующие таблицы: {existing_tables}")

        # 1. Обновляем таблицу posts
        if 'posts' in existing_tables:
            logger.info("📊 Проверка таблицы posts...")

            result = await conn.execute(text("PRAGMA table_info(posts)"))
            columns = [row[1] for row in result.fetchall()]

            # Добавляем analyzed_at
            if 'analyzed_at' not in columns:
                logger.info("➕ Добавление поля analyzed_at...")
                await conn.execute(text("""
                    ALTER TABLE posts ADD COLUMN analyzed_at DATETIME
                """))
                logger.info("✅ Поле analyzed_at добавлено")
            else:
                logger.info("✓ Поле analyzed_at уже существует")

            # Добавляем generated_news_id
            if 'generated_news_id' not in columns:
                logger.info("➕ Добавление поля generated_news_id...")
                await conn.execute(text("""
                    ALTER TABLE posts ADD COLUMN generated_news_id INTEGER
                """))
                logger.info("✅ Поле generated_news_id добавлено")
            else:
                logger.info("✓ Поле generated_news_id уже существует")
        else:
            logger.warning("⚠️ Таблица posts не найдена")

        logger.info("🎉 Миграция успешно завершена!")
        logger.info("")
        logger.info("Изменения в схеме БД:")
        logger.info("  posts.analyzed_at — дата обработки Аналитиком")
        logger.info("  posts.generated_news_id — ID сгенерированной новости")
        logger.info("")
        logger.info("Преимущества:")
        logger.info("  - Планировщик пропускает уже обработанные посты")
        logger.info("  - Нет дублирования новостей")
        logger.info("  - Экономия токенов и времени обработки")


def main():
    """Точка входа"""
    logger.info("🚀 Запуск миграции: добавление полей отслеживания анализа")
    logger.info("=" * 60)

    try:
        asyncio.run(migrate())
    except Exception as e:
        logger.error(f"❌ Ошибка миграции: {e}")
        raise


if __name__ == '__main__':
    main()
