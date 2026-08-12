#!/usr/bin/env python3
"""
Скрипт для авторизации Telegram UserBot без запуска всего приложения.

Использование:
    python3 auth_telegram.py

Введите код из Telegram когда будет запрошено.
"""

import asyncio
import logging
import sys

# Минимальное логирование во время авторизации
logging.basicConfig(
    level=logging.WARNING,  # Только предупреждения и ошибки
    format='%(levelname)s: %(message)s',
    stream=sys.stdout
)

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from config.settings import settings


async def main():
    """Авторизация в Telegram."""
    print("=" * 60)
    print("🔐 Авторизация Telegram UserBot")
    print("=" * 60)
    print()
    print(f"API ID: {settings.api_id}")
    print(f"Phone: {settings.phone_number}")
    print()
    print("Сейчас будет отправлен код на ваш Telegram...")
    print()

    client = TelegramClient(
        'userbot',
        api_id=settings.api_id,
        api_hash=settings.api_hash,
    )

    await client.connect()

    if await client.is_user_authorized():
        print("✅ Уже авторизован!")
        me = await client.get_me()
        print(f"   Пользователь: @{me.username} (ID: {me.id})")
    else:
        print("📤 Отправка кода...")
        await client.send_code_request(settings.phone_number)
        print()

        # Ввод кода
        code = input("🔢 Введите код из Telegram: ")
        try:
            await client.sign_in(settings.phone_number, code)
        except SessionPasswordNeededError:
            print()
            print("🔒 Требуется двухфакторная аутентификация")
            password = input("   Введите пароль: ")
            await client.sign_in(password=password)

        print()
        print("✅ Авторизация успешна!")
        me = await client.get_me()
        print(f"   Пользователь: @{me.username} (ID: {me.id})")

    await client.disconnect()
    print()
    print("=" * 60)
    print("Готово! Теперь можно запустить: python3 main.py")
    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Отменено пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)
