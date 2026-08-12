"""
Миграция: Изменение типа поля analyzed_at на Boolean (checked_at)

Запуск:
    python -m database.migrate_checked_at_boolean
"""

import asyncio
import logging
import aiosqlite

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_PATH = 'db.sqlite3'


async def migrate():
    """Выполнить миграцию."""
    logger.info("🔄 Начало миграции: analyzed_at → checked_at (Boolean)")

    async with aiosqlite.connect(DB_PATH) as db:
        # Проверяем существование старой колонки
        cursor = await db.execute("PRAGMA table_info(posts)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        logger.info(f"📋 Текущие колонки в posts: {column_names}")

        # Проверяем наличие analyzed_at
        if 'analyzed_at' not in column_names:
            logger.warning("⚠️ Поле analyzed_at не найдено, миграция не требуется")
            return

        # Проверяем наличие checked_at
        if 'checked_at' in column_names:
            logger.warning("⚠️ Поле checked_at уже существует, пропускаем создание")
        else:
            # Добавляем новую колонку checked_at с дефолтным значением FALSE
            logger.info("➕ Добавление поля checked_at (BOOLEAN DEFAULT FALSE)...")
            await db.execute("""
                ALTER TABLE posts ADD COLUMN checked_at BOOLEAN DEFAULT 0
            """)
            await db.commit()
            logger.info("✅ Поле checked_at добавлено")

        # Копируем данные из analyzed_at в checked_at
        # analyzed_at IS NOT NULL → checked_at = TRUE, иначе FALSE
        logger.info("📊 Копирование данных из analyzed_at в checked_at...")
        await db.execute("""
            UPDATE posts
            SET checked_at = CASE
                WHEN analyzed_at IS NOT NULL THEN 1
                ELSE 0
            END
        """)
        await db.commit()
        logger.info("✅ Данные скопированы")

        # SQLite не поддерживает DROP COLUMN напрямую в старых версиях
        # Но начиная с 3.35.0 (2021) поддерживает ALTER TABLE ... DROP COLUMN
        # Проверяем версию SQLite
        cursor = await db.execute("SELECT sqlite_version()")
        version = await cursor.fetchone()
        logger.info(f"📌 Версия SQLite: {version[0]}")

        # Пытаемся удалить старую колонку
        try:
            logger.info("🗑️ Удаление поля analyzed_at...")
            await db.execute("ALTER TABLE posts DROP COLUMN analyzed_at")
            await db.commit()
            logger.info("✅ Поле analyzed_at удалено")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить analyzed_at: {e}")
            logger.info("ℹ️ Поле analyzed_at будет удалено при следующем создании таблиц")

        # Проверяем результат
        cursor = await db.execute("PRAGMA table_info(posts)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        logger.info(f"📋 Итоговые колонки в posts: {column_names}")

    logger.info("✅ Миграция завершена")
    logger.info("  posts.checked_at — флаг обработки (Boolean)")


async def rollback():
    """Откат миграции."""
    logger.info("🔄 Откат миграции: checked_at → analyzed_at")

    async with aiosqlite.connect(DB_PATH) as db:
        # Проверяем существование checked_at
        cursor = await db.execute("PRAGMA table_info(posts)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if 'checked_at' not in column_names:
            logger.warning("⚠️ Поле checked_at не найдено, откат не требуется")
            return

        # Добавляем analyzed_at обратно
        if 'analyzed_at' not in column_names:
            logger.info("➕ Добавление поля analyzed_at (DATETIME)...")
            await db.execute("""
                ALTER TABLE posts ADD COLUMN analyzed_at DATETIME
            """)
            await db.commit()
            logger.info("✅ Поле analyzed_at добавлено")

        # Копируем данные из checked_at в analyzed_at
        logger.info("📊 Копирование данных из checked_at в analyzed_at...")
        await db.execute("""
            UPDATE posts
            SET analyzed_at = CASE
                WHEN checked_at = 1 THEN datetime('now')
                ELSE NULL
            END
        """)
        await db.commit()
        logger.info("✅ Данные скопированы")

        # Удаляем checked_at
        try:
            logger.info("🗑️ Удаление поля checked_at...")
            await db.execute("ALTER TABLE posts DROP COLUMN checked_at")
            await db.commit()
            logger.info("✅ Поле checked_at удалено")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить checked_at: {e}")

    logger.info("✅ Откат завершён")


async def main():
    """Точка входа."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--rollback':
        await rollback()
    else:
        await migrate()


if __name__ == '__main__':
    asyncio.run(main())
