#!/usr/bin/env python3
"""
Скрипт для выполнения миграции tasks_add_recurring_fields.

Запуск: python3 run_migrate_recurring.py
"""

import asyncio
import sys
import os

# Добавляем корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.core.database import get_database_service
from database.migrations.migrate_tasks_add_recurring_fields import migrate


async def run_migration():
    """Выполнить миграцию."""
    print("🔄 Выполнение миграции: tasks_add_recurring_fields")
    print("   - Переименование is_daily -> recurring")
    print("   - Добавление recurrence_pattern")
    print()

    try:
        db_service = get_database_service()
        async with db_service.session_context() as session:
            await migrate(session)

        print()
        print("✅ Миграция выполнена успешно!")
        return True

    except Exception as e:
        print()
        print(f"❌ Ошибка миграции: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = asyncio.run(run_migration())
    sys.exit(0 if success else 1)
