#!/usr/bin/env python3
"""
Проверка типа отправки кода.
"""

import asyncio
import logging
from telethon import TelegramClient
from telethon.tl.types import auth as auth_types
from config.settings import settings

logging.basicConfig(level=logging.WARNING)  # Только ошибки

async def main():
    print(f"Номер: {settings.phone_number}")
    print()
    
    client = TelegramClient('userbot_check', settings.api_id, settings.api_hash, use_ipv6=True)
    
    await client.connect()
    
    if await client.is_user_authorized():
        print("✅ Уже авторизован — выходим")
        await client.disconnect()
        return
    
    print("📤 Запрос кода...")
    sent_code = await client.send_code_request(settings.phone_number)
    
    print(f"\nТип отправки: {type(sent_code.type).__name__}")
    
    if isinstance(sent_code.type, auth_types.SentCodeTypeApp):
        print(f"   📱 В приложение Telegram")
        print(f"   🔍 Длина phone_code_hash: {len(sent_code.phone_code_hash) if sent_code.phone_code_hash else 0}")
        print(f"   📋 phone_code_hash (первые 20 символов): {sent_code.phone_code_hash[:20] if sent_code.phone_code_hash else 'None'}...")
    elif isinstance(sent_code.type, auth_types.SentCodeTypeSms):
        print(f"   📱 Через SMS")
    elif isinstance(sent_code.type, auth_types.SentCodeTypeCall):
        print(f"   📞 Звонком")
    elif isinstance(sent_code.type, auth_types.SentCodeTypeMissedCall):
        print(f"   📞 Пропущенный вызов")
    elif isinstance(sent_code.type, auth_types.SentCodeTypeEmailCode):
        print(f"   📧 На email")
    else:
        print(f"   ❓ Неизвестный тип: {sent_code.type}")
    
    print(f"\n⏳ Ждём 30 секунд, проверяйте Telegram...")
    await asyncio.sleep(30)
    
    await client.disconnect()
    print("\n✅ Готово")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Отменено")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
