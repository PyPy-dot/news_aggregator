#!/usr/bin/env python3
"""
Скрипт для миграции на новый слой абстракции БД.

Автоматически заменяет импорты:
  from services.core.database import get_database_service
на:
  from services.database import get_database_service
"""

import re
from pathlib import Path

# Файлы для обновления
FILES_TO_UPDATE = [
    # Categorization
    'services/categorization/processor.py',

    # Listener
    'services/listener/bot.py',

    # Core (кроме database.py и container.py - их вручную)

    # Payment
    'services/payment/service.py',

    # Scheduler
    'services/scheduler/scheduler.py',

    # News
    'services/news/helpers.py',

    # AI Agent
    'services/ai_agent/vector_routers.py',

    # Telegram
    'services/telegram/notification.py',

    # Bot
    'services/bot/bot.py',
    'services/bot/utils.py',
    'services/bot/handlers/direct_news.py',
    'services/bot/handlers/subscription.py',
    'services/bot/handlers/tasks.py',
    'services/bot/handlers/callbacks_channels.py',
    'services/bot/handlers/messages.py',
    'services/bot/handlers/callbacks_preferences.py',
    'services/bot/handlers/callbacks_moderation.py',
    'services/bot/handlers/access.py',
    'services/bot/handlers/publishers.py',
    'services/bot/handlers/commands.py',
    'services/bot/handlers/callbacks_admin.py',
    'services/bot/handlers/payment.py',
    'services/bot/handlers/filters.py',

    # Web Admin
    'services/web_admin/api/app.py',
    'services/web_admin/api/auth.py',
]

def migrate_file(filepath: str) -> bool:
    """
    Мигрировать файл на новый слой БД.

    Returns:
        True если файл обновлён
    """
    path = Path(filepath)
    if not path.exists():
        print(f"⚠️ Файл не найден: {filepath}")
        return False

    content = path.read_text(encoding='utf-8')
    original = content

    # Заменяем импорты
    # 1. Прямые импорты get_database_service
    content = re.sub(
        r'from services\.core\.database import get_database_service',
        'from services.database import get_database_service',
        content
    )

    # 2. Импорты DatabaseService
    content = re.sub(
        r'from services\.core\.database import DatabaseService',
        'from services.database import IDatabaseService',
        content
    )

    # 3. Комбинированные импорты
    content = re.sub(
        r'from services\.core\.database import DatabaseService, get_database_service',
        'from services.database import IDatabaseService, get_database_service',
        content
    )

    content = re.sub(
        r'from services\.core\.database import get_database_service, DatabaseService',
        'from services.database import get_database_service, IDatabaseService',
        content
    )

    # 4. Заменяем get_db_session если используется
    content = re.sub(
        r'from services\.core\.database import get_db_session',
        'from services.database import get_db_session',
        content
    )

    # 5. Обновляем аннотации типов
    content = re.sub(
        r': DatabaseService',
        ': IDatabaseService',
        content
    )

    content = re.sub(
        r'\| DatabaseService',
        '| IDatabaseService',
        content
    )

    if content != original:
        path.write_text(content, encoding='utf-8')
        print(f"✅ Обновлён: {filepath}")
        return True

    print(f"⏭️ Пропущен (нет изменений): {filepath}")
    return False


def main():
    """Запустить миграцию."""
    print("🚀 Миграция на новый слой абстракции БД\n")

    updated = 0
    skipped = 0
    errors = 0

    for filepath in FILES_TO_UPDATE:
        try:
            if migrate_file(filepath):
                updated += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"❌ Ошибка {filepath}: {e}")
            errors += 1

    print(f"\n📊 Результаты:")
    print(f"   ✅ Обновлено: {updated}")
    print(f"   ⏭️ Пропущено: {skipped}")
    print(f"   ❌ Ошибок: {errors}")

    if errors == 0:
        print("\n✅ Миграция завершена успешно!")
    else:
        print(f"\n⚠️ Миграция завершена с {errors} ошибками")


if __name__ == '__main__':
    main()
