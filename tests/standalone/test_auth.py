#!/usr/bin/env python3
"""
Тестовый скрипт для проверки авторизации Listener Bot.
"""

import asyncio
import logging
import sys

# Минимальное логирование
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s: %(message)s',
    stream=sys.stdout
)

from telethon import TelegramClient
from config.settings import settings

async def main():
    print("=" * 60)
    print("🔐 Тест авторизации Telegram UserBot")
    print("=" * 60)
    print()
    print(f"API ID: {settings.api_id}")
    print(f"API Hash: {settings.api_hash[:10]}...")
    print(f"Phone: {settings.phone_number}")
    print()
    
    # Создаём клиент с IPv6 (как в production)
    client = TelegramClient(
        'userbot_test',
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        use_ipv6=True,  # Требуется для работы в вашей сети
        connection_retries=5,
        retry_delay=2,
        timeout=60,
    )
    
    print("🔌 Подключение к Telegram...")
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
        
        # Нормализуем номер
        phone = settings.phone_number.strip()
        if not phone.startswith('+'):
            phone = '+' + phone.replace(' ', '').replace('(', '').replace(')', '').replace('-', '')
        
        print(f"   Номер: {phone}")
        
        try:
            sent_code = await client.send_code_request(phone)
            print("✅ Код отправлен!")
            
            # Проверяем тип отправки
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
            print("🔢 Введите код из Telegram (или нажмите Ctrl+C для отмены):")
            
            # Неблокирующий ввод
            code = await asyncio.get_event_loop().run_in_executor(
                None, input, 'Код: '
            )
            
            try:
                await client.sign_in(phone, code)
                print("✅ Авторизация успешна!")
                me = await client.get_me()
                print(f"   Пользователь: @{me.username} (ID: {me.id})")
            except Exception as e:
                print(f"❌ Ошибка авторизации: {e}")
                
        except Exception as e:
            print(f"❌ Ошибка отправки кода: {e}")
    
    await client.disconnect()
    print()
    print("=" * 60)
    print("Готово!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Отменено пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
