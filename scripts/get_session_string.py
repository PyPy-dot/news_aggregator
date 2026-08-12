#!/usr/bin/env python3
"""
Скрипт для получения session string Telethon.

Запустите один раз, скопируйте session string в .env:
TELEGRAM_SESSION_STRING=<скопированная строка>

После этого ListenerBot будет запускаться без запроса кода.
"""

import asyncio
from telethon import TelegramClient
from config.settings import settings

async def main():
    print("🔐 Получение session string для ListenerBot\n")
    print(f"API ID: {settings.api_id}")
    print(f"API Hash: {settings.api_hash[:8]}...")
    print(f"Phone: {settings.phone_number}\n")

    client = TelegramClient('temp_session', settings.api_id, settings.api_hash)

    await client.connect()

    if await client.is_user_authorized():
        print("✅ Сессия уже авторизована!")
        session_string = client.session.save()
        print(f"\n📋 Session string:\n{session_string}\n")
        print("Скопируйте эту строку в .env:")
        print(f"TELEGRAM_SESSION_STRING={session_string}")
    else:
        print("⚠️ Требуется авторизация")
        print("📱 Код будет отправлен в приложение Telegram на ваш номер\n")

        await client.send_code_request(settings.phone_number)

        code = input("Введите код из Telegram: ").strip()

        try:
            await client.sign_in(settings.phone_number, code)
            session_string = client.session.save()
            print(f"\n✅ Авторизация успешна!")
            print(f"\n📋 Session string:\n{session_string}\n")
            print("Скопируйте эту строку в .env:")
            print(f"TELEGRAM_SESSION_STRING={session_string}")
        except Exception as e:
            print(f"❌ Ошибка: {e}")

    await client.disconnect()

    # Удаляем временный файл сессии
    import os
    for f in ['temp_session.session', 'temp_session.session-journal']:
        if os.path.exists(f):
            os.remove(f)

if __name__ == '__main__':
    asyncio.run(main())
