#!/usr/bin/env python3
"""
Тестовый скрипт для проверки авторизации с IPv4.
"""

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
    stream=sys.stdout
)

from telethon import TelegramClient
from config.settings import settings

async def main():
    print("=" * 60)
    print("🔐 Тест авторизации Telegram UserBot (IPv4)")
    print("=" * 60)
    print()
    
    # Создаём клиент с IPv4 (как в старой версии)
    client = TelegramClient(
        'userbot_test_ipv4',
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        use_ipv6=False,  # IPv4 как в старой версии
        connection_retries=5,
        retry_delay=2,
        timeout=60,
    )
    
    print("🔌 Подключение к Telegram (IPv4)...")
    await client.connect()
    print("✅ Подключение установлено")
    
    if await client.is_user_authorized():
        print("✅ Уже авторизован!")
        me = await client.get_me()
        print(f"   Пользователь: @{me.username} (ID: {me.id})")
    else:
        print("⚠️ Требуется авторизация!")
        print()
        print("📤 Отправка запроса кода...")
        
        phone = settings.phone_number.strip()
        if not phone.startswith('+'):
            phone = '+' + phone.replace(' ', '').replace('(', '').replace(')', '').replace('-', '')
        
        print(f"   Номер: {phone}")
        
        try:
            sent_code = await client.send_code_request(phone)
            print("✅ Код отправлен!")
            
            if hasattr(sent_code, 'type') and sent_code.type:
                from telethon.tl.types import auth as auth_types
                code_type = sent_code.type
                
                if isinstance(code_type, auth_types.SentCodeTypeApp):
                    print("   📱 Код будет отправлен В ПРИЛОЖЕНИЕ Telegram")
                elif isinstance(code_type, auth_types.SentCodeTypeSms):
                    print("   📱 Код будет отправлен через SMS")
                else:
                    print(f"   📋 Тип: {type(code_type).__name__}")
            
            print()
            print("🔢 Введите код из Telegram (или нажмите Ctrl+C):")
            
            code = await asyncio.get_event_loop().run_in_executor(
                None, input, 'Код: '
            )
            
            try:
                await client.sign_in(phone, code)
                print("✅ Авторизация успешна!")
            except Exception as e:
                print(f"❌ Ошибка авторизации: {e}")
                
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
        sys.exit(1)
