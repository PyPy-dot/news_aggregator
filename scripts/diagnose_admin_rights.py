#!/usr/bin/env python3
"""
Скрипт для диагностики проблемы с проверкой прав администратора.

Показывает:
- Ваш Telegram ID
- Хеш, который используется для поиска в БД
- Все записи в таблице users
- Соответствие хешей
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / '.env')

from services.database import get_database_service
from services.util import hash_user_id_for_lookup
from database.repositories.users import UserRepository


async def diagnose():
    """Диагностика проблемы с правами."""
    print("=" * 60)
    print("🔍 Диагностика проверки прав администратора")
    print("=" * 60)
    print()

    # Ваш Telegram ID (получим из бота)
    from config.settings import settings

    # Если ADMIN_ID установлен, используем его
    admin_id = None
    if hasattr(settings, 'admin_id') and settings.admin_id:
        admin_id = settings.admin_id
        print(f"📋 ADMIN_ID из .env: {admin_id}")
    else:
        print("⚠️  ADMIN_ID не установлен в .env")

    print()

    # Подключаемся к БД и смотрим всех пользователей
    db_service = get_database_service()
    async with db_service.session_context() as session:
        from sqlalchemy import select
        from database.models import User

        # Получаем всех пользователей
        result = await session.execute(select(User))
        users = result.scalars().all()

        print(f"📊 Всего пользователей в БД: {len(users)}")
        print()

        if not users:
            print("❌ В БД нет пользователей!")
            print()
            print("Решение:")
            print("  1. Запустите бота")
            print("  2. Отправьте команду /start")
            print("  3. Пользователь будет создан в БД")
            print()
        else:
            print("Пользователи в БД:")
            print("-" * 60)
            for u in users:
                print(f"  ID={u.id}, user_id_hash={u.user_id_hash[:30]}..., role={u.role}")

                # Пытаемся расшифровать ID для сравнения
                try:
                    # Проверяем, совпадает ли хеш с ADMIN_ID
                    if admin_id:
                        expected_hash = hash_user_id_for_lookup(admin_id)
                        if u.user_id_hash == expected_hash:
                            print(f"    ✅ СОВПАДЕНИЕ с ADMIN_ID={admin_id}")
                        else:
                            print(f"    ⚠️  Не совпадает с ADMIN_ID={admin_id}")
                            print(f"        Ожидался хеш: {expected_hash[:30]}...")
                except Exception as e:
                    print(f"    ⚠️  Ошибка сравнения: {e}")
            print()

        # Если есть ADMIN_ID, проверяем его напрямую
        if admin_id:
            print(f"🔍 Проверка ADMIN_ID={admin_id}:")
            expected_hash = hash_user_id_for_lookup(admin_id)
            print(f"   Ожидаемый хеш: {expected_hash[:30]}...")

            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(admin_id)

            if user:
                print(f"   ✅ Пользователь найден: role={user.role}")
                if user.role == 'admin':
                    print(f"   ✅ Пользователь имеет права администратора")
                else:
                    print(f"   ❌ Пользователь НЕ имеет прав администратора (role={user.role})")
                    print()
                    print("   Решение:")
                    print(f"   UPDATE users SET role='admin' WHERE id={user.id};")
            else:
                print(f"   ❌ Пользователь НЕ найден в БД")
                print()
                print("   Решение:")
                print("   1. Отправьте команду /start боту")
                print("   2. Или создайте запись вручную:")
                print(f"      INSERT INTO users (user_id_encrypted, user_id_hash, role)")
                print(f"      VALUES ('...', '{expected_hash}', 'admin');")
        print()

    # Рекомендации
    print("=" * 60)
    print("📋 Рекомендации:")
    print("=" * 60)
    print()

    if not admin_id:
        print("1. Установите ADMIN_ID в .env:")
        print(f"   ADMIN_ID=ваш_telegram_id")
        print()
        print("   Как узнать свой Telegram ID:")
        print("   1. Отправьте команду /start боту")
        print("   2. Посмотрите логи — там будет ваш ID")
        print()

    print("2. Проверьте, что пользователь существует в БД:")
    print("   - Запустите бота")
    print("   - Отправьте команду /start")
    print()

    print("3. Если пользователь есть, но role != 'admin':")
    print("   UPDATE users SET role='admin' WHERE user_id_hash='<hash>';")
    print()


if __name__ == "__main__":
    asyncio.run(diagnose())
