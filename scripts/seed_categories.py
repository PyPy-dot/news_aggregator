"""
Скрипт для создания категорий новостей по умолчанию.

Запуск:
    .venv/bin/python scripts/seed_categories.py
"""

import asyncio
import sys
sys.path.insert(0, '.')

from database.models import NewsCategory
from services.database import get_database_service


DEFAULT_CATEGORIES = [
    "Политика",
    "Экономика",
    "Общество",
    "Происшествия",
    "Спорт",
    "Технологии",
    "Наука",
    "Культура",
    "Здоровье",
    "Образование",
    "Погода",
    "Воздушная тревога",
    "Экстренные новости",
]


async def seed_categories():
    """Создать категории по умолчанию."""
    db_service = get_database_service()
    
    async with db_service.session_context() as session:
        created_count = 0
        skipped_count = 0
        
        for cat_name in DEFAULT_CATEGORIES:
            # Проверяем, существует ли уже категория
            from sqlalchemy import select
            result = await session.execute(
                select(NewsCategory).where(NewsCategory.name == cat_name)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                skipped_count += 1
                print(f"⚠️  Категория '{cat_name}' уже существует")
                continue
            
            # Создаём категорию
            category = NewsCategory(
                name=cat_name,
                description=f"Категория '{cat_name}'",
                is_active=True,
            )
            session.add(category)
            created_count += 1
            print(f"✅ Создана категория: {cat_name}")
        
        await session.commit()
        
        print(f"\n📊 Итого:")
        print(f"   Создано: {created_count}")
        print(f"   Пропущено: {skipped_count}")
        print(f"   Всего: {created_count + skipped_count}")


if __name__ == "__main__":
    asyncio.run(seed_categories())
