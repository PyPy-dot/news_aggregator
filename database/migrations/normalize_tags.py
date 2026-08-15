#!/usr/bin/env python3
"""
Скрипт для нормализации существующих тэгов к нижнему регистру.

Запуск:
    python -m database.migrations.normalize_tags

Или:
    python database/migrations/normalize_tags.py

Скрипт обновляет все тэги и категории в таблицах:
- users (preferred_tags, preferred_categories)
- posts (tags)
- channels (tags)
- events (tags)
"""

import asyncio
import json
import logging
from pathlib import Path
import sys

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, TelegramPost, Channel, EventContext
from services.core.database import get_database_service

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def normalize_json_field(session: AsyncSession, model, field: str) -> int:
    """
    Нормализовать JSON поле к нижнему регистру.

    Args:
        session: Сессия БД
        model: Модель SQLAlchemy
        field: Имя поля

    Returns:
        Количество обновлённых записей
    """
    # Получаем все записи с непустым полем
    result = await session.execute(
        select(model).where(getattr(model, field) != '[]')
    )
    records = result.scalars().all()

    updated_count = 0
    for record in records:
        try:
            data = json.loads(getattr(record, field) or '[]')
            if isinstance(data, list):
                # Нормализация к нижнему регистру
                normalized = [item.lower() if isinstance(item, str) else item for item in data]
                # Проверяем, были ли изменения
                if normalized != data:
                    setattr(record, field, json.dumps(normalized, ensure_ascii=False))
                    updated_count += 1
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ Ошибка парсинга JSON в {model.__tablename__}.{field} (id={record.id}): {e}")
            # Устанавливаем пустой список при ошибке
            setattr(record, field, '[]')
            updated_count += 1

    if updated_count > 0:
        await session.commit()

    return updated_count


async def normalize_all_tags():
    """Нормализовать все тэги и категории в базе данных."""

    db_service = get_database_service()

    async with db_service.session_context() as session:
        logger.info("🔍 Начинаю нормализацию тэгов...")

        # users.preferred_tags
        count = await normalize_json_field(session, User, 'preferred_tags')
        logger.info(f"✅ users.preferred_tags: обновлено {count} записей")

        # users.preferred_categories
        count = await normalize_json_field(session, User, 'preferred_categories')
        logger.info(f"✅ users.preferred_categories: обновлено {count} записей")

        # posts.tags
        count = await normalize_json_field(session, TelegramPost, 'tags')
        logger.info(f"✅ posts.tags: обновлено {count} записей")

        # channels.tags
        count = await normalize_json_field(session, Channel, 'tags')
        logger.info(f"✅ channels.tags: обновлено {count} записей")

        # events.tags
        count = await normalize_json_field(session, EventContext, 'tags')
        logger.info(f"✅ events.tags: обновлено {count} записей")

        logger.info("🎉 Нормализация завершена!")


def main():
    """Точка входа."""
    try:
        asyncio.run(normalize_all_tags())
    except KeyboardInterrupt:
        logger.info("⌨️ Прервано пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
