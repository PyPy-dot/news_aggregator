"""
Миграция: Добавление таблицы news_categories (справочник категорий).

Создаёт таблицу для хранения категорий новостей с возможностью
управления предпочтениями пользователей.

Запуск:
    python3 -m database.migrations.migrate_add_categories_table
"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import text
from services.core.database import get_database_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Предустановленные категории
DEFAULT_CATEGORIES = [
    ('Политика', 'Власть, выборы, законы, международные отношения, санкции'),
    ('Экономика', 'Финансы, рынки, курсы валют, бизнес, налоги, инфляция'),
    ('Технологии', 'IT, гаджеты, софт, интернет, цифровизация, стартапы'),
    ('Происшествия', 'Аварии, катастрофы, преступления, пожары, ЧП'),
    ('Спорт', 'Соревнования, атлеты, тренеры, трансферы, результаты'),
    ('Культура', 'Искусство, музыка, кино, театр, выставки, фестивали'),
    ('Наука', 'Исследования, открытия, космос, медицина, экология'),
    ('Общество', 'Социум, образование, здравоохранение, демография, права'),
    ('Война', 'Боевые действия, оружие, фронт, мобилизация, ВПК'),
    ('Воздушная тревога', 'Сирены, обстрелы, укрытия, ПВО, угроза с воздуха'),
]


async def migrate():
    """Выполнить миграцию."""
    db_service = get_database_service()

    async with db_service.session_context() as session:
        # Создаём таблицу
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS news_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT DEFAULT '',
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Проверяем, есть ли уже категории
        result = await session.execute(text("SELECT COUNT(*) FROM news_categories"))
        count = result.scalar()

        if count == 0:
            # Вставляем категории по умолчанию
            for name, description in DEFAULT_CATEGORIES:
                await session.execute(
                    text("""
                        INSERT INTO news_categories (name, description, is_active, created_at)
                        VALUES (:name, :description, 1, :created_at)
                    """),
                    {
                        'name': name,
                        'description': description,
                        'created_at': datetime.now()
                    }
                )
            logger.info(f"✅ Добавлено {len(DEFAULT_CATEGORIES)} категорий по умолчанию")
        else:
            logger.info(f"ℹ️ Таблица уже содержит {count} записей, пропускаем вставку")

        await session.commit()

    logger.info("✅ Миграция 'add_categories_table' выполнена успешно")


async def rollback():
    """Откатить миграцию."""
    db_service = get_database_service()

    async with db_service.session_context() as session:
        await session.execute(text("DROP TABLE IF EXISTS news_categories"))
        await session.commit()

    logger.info("✅ Миграция 'add_categories_table' откатана")


async def main():
    """Точка входа."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'rollback':
        await rollback()
    else:
        await migrate()


if __name__ == '__main__':
    asyncio.run(main())
