#!/usr/bin/env python3
"""
Сохранение строки сессии Telethon для последующего использования.
"""

import asyncio
import logging
from telethon import TelegramClient
from config.settings import settings

logging.basicConfig(level=logging.WARNING)

async def main():
    print("=" * 60)
    print("💾 Сохранение сессии Telethon")
    print("=" * 60)
    print()
    
    client = TelegramClient(
        'userbot_save',
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        use_ipv6=True,
        device_model="Telegram Desktop",
        system_version="Windows 10",
        app_version="4.9.2",
    )
    
    await client.connect()
    
    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"✅ Авторизован: @{me.username} (ID: {me.id})")
        
        # Сохраняем строку сессии
        session_string = await client.save_session()
        print()
        print("📋 Строка сессии (сохраните в TELEGRAM_SESSION_STRING в .env):")
        print("-" * 60)
        print(session_string)
        print("-" * 60)
    else:
        print("⚠️ Требуется авторизация!")
        print()
        
        phone = settings.phone_number.strip()
        if not phone.startswith('+'):
            phone = '+' + phone.replace(' ', '').replace('(', '').replace(')', '').replace('-', '')
        
        print(f"📤 Запрос кода для {phone}...")
        sent_code = await client.send_code_request(phone)
        
        from telethon.tl.types import auth as auth_types
        if isinstance(sent_code.type, auth_types.SentCodeTypeApp):
            print("📱 Код отправлен В ПРИЛОЖЕНИЕ Telegram")
        
        code = input("Введите код: ")
        
        try:
            await client.sign_in(phone, code, phone_code_hash=sent_code.phone_code_hash)
            print("✅ Авторизация успешна!")
            
            me = await client.get_me()
            print(f"   Пользователь: @{me.username} (ID: {me.id})")
            
            # Сохраняем строку сессии
            session_string = await client.save_session()
            print()
            print("📋 Строка сессии (сохраните в .env):")
            print("-" * 60)
            print(session_string)
            print("-" * 60)
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Отменено")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
