#!/usr/bin/env python3
"""
Проверка отправки кода с force_sms=True (устарело, но попробуем).
"""

import asyncio
import logging
from telethon import TelegramClient
from telethon.tl.types import auth as auth_types
from config.settings import settings

logging.basicConfig(level=logging.WARNING)

async def main():
    print(f"Номер: {settings.phone_number}")
    print()
    
    client = TelegramClient('userbot_sms_test', settings.api_id, settings.api_hash, use_ipv6=True)
    
    await client.connect()
    
    if await client.is_user_authorized():
        print("✅ Уже авторизован")
        await client.disconnect()
        return
    
    print("📤 Запрос кода с force_sms=True...")
    try:
        sent_code = await client.send_code_request(settings.phone_number, force_sms=True)
        
        print(f"\nТип отправки: {type(sent_code.type).__name__}")
        
        if isinstance(sent_code.type, auth_types.SentCodeTypeApp):
            print(f"   📱 В приложение Telegram (force_sms не сработал)")
        elif isinstance(sent_code.type, auth_types.SentCodeTypeSms):
            print(f"   📱 Через SMS (force_sms сработал!)")
        else:
            print(f"   ❓ Другой тип: {sent_code.type}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
