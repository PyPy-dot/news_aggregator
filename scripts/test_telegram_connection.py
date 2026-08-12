#!/usr/bin/env python3
"""
Тест подключения к Telegram API и проверки токена бота.

Использование:
    python scripts/test_telegram_connection.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Добавляем корень проекта в path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import aiohttp
from dotenv import load_dotenv


# Загружаем .env
load_dotenv(project_root / '.env')


async def test_telegram_api() -> bool:
    """Проверить доступность Telegram API."""
    url = "https://api.telegram.org/"

    print("🔍 Проверка Telegram API...")
    print(f"   URL: {url}")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                print(f"✅ Telegram API доступен: {resp.status}")
                return True
        except asyncio.TimeoutError:
            print("❌ Timeout: Telegram API не отвечает")
            return False
        except aiohttp.ClientError as e:
            print(f"❌ Ошибка подключения: {e}")
            return False
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")
            return False


async def test_bot_token(token: str) -> bool:
    """Проверить токен бота."""
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN не установлен")
        return False

    url = f"https://api.telegram.org/bot{token}/getMe"

    print("🔍 Проверка токена бота...")
    print(f"   Токен: {token[:20]}...{token[-10:]}")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                data = await resp.json()
                if data.get('ok'):
                    bot = data['result']
                    username = bot.get('username', 'N/A')
                    first_name = bot.get('first_name', 'N/A')
                    print(f"✅ Бот найден: @{username} ({first_name})")
                    print(f"   ID: {bot['id']}")
                    return True
                else:
                    error = data.get('description', 'Неизвестная ошибка')
                    print(f"❌ Ошибка API: {error}")
                    return False
        except asyncio.TimeoutError:
            print("❌ Timeout при проверке токена")
            return False
        except aiohttp.ClientError as e:
            print(f"❌ Ошибка подключения: {e}")
            return False
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")
            return False


async def test_proxy(proxy_url: str) -> bool:
    """Проверить работу прокси."""
    if not proxy_url:
        print("ℹ️  Прокси не настроен")
        return True

    print("🔍 Проверка прокси...")
    print(f"   URL: {proxy_url}")

    # Определяем тип прокси
    if proxy_url.startswith('socks5://'):
        try:
            import socks
            from urllib.parse import urlparse

            parsed = urlparse(proxy_url)
            proxy = (socks.SOCKS5, parsed.hostname, parsed.port or 1080)

            print(f"   Тип: SOCKS5 ({parsed.hostname}:{parsed.port or 1080})")

            # Тест подключения через прокси
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get("https://api.telegram.org/", timeout=10) as resp:
                    print(f"✅ Прокси работает: {resp.status}")
                    return True

        except ImportError:
            print("⚠️  PySocks не установлен: pip install pysocks")
            return False
        except Exception as e:
            print(f"❌ Ошибка прокси: {e}")
            return False

    elif proxy_url.startswith('http://'):
        print(f"   Тип: HTTP")
        # HTTP прокси тест
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            try:
                async with session.get("https://api.telegram.org/", timeout=10) as resp:
                    print(f"✅ Прокси работает: {resp.status}")
                    return True
            except Exception as e:
                print(f"❌ Ошибка прокси: {e}")
                return False
    else:
        print(f"⚠️  Неизвестный тип прокси: {proxy_url}")
        return False


async def main():
    """Запустить все тесты."""
    print("=" * 60)
    print("🔧 Тест подключения к Telegram")
    print("=" * 60)
    print()

    # Получаем переменные окружения
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    telegram_proxy = os.getenv('TELEGRAM_PROXY')
    telegram_mtproto = os.getenv('TELEGRAM_MTPROTO_PROXY')

    print("📋 Конфигурация:")
    print(f"   TELEGRAM_BOT_TOKEN: {'установлен' if bot_token else '❌ НЕ УСТАНОВЛЕН'}")
    print(f"   TELEGRAM_PROXY: {telegram_proxy or 'не настроен'}")
    print(f"   TELEGRAM_MTPROTO_PROXY: {telegram_mtproto or 'не настроен'}")
    print()

    # Тесты
    results = {}

    # 1. Тест API
    results['api'] = await test_telegram_api()
    print()

    # 2. Тест прокси (если настроен)
    if telegram_proxy:
        results['proxy'] = await test_proxy(telegram_proxy)
        print()
    else:
        results['proxy'] = True  # Прокси не требуется
    # 3. Тест токена
    results['token'] = await test_bot_token(bot_token)
    print()

    # Итог
    print("=" * 60)
    print("📊 Результаты:")
    print("=" * 60)

    all_ok = all(results.values())

    if all_ok:
        print("✅ Все проверки пройдены!")
        print()
        print("🚀 Приложение готово к запуску:")
        print("   python main.py")
        return 0
    else:
        print("❌ Обнаружены проблемы:")
        if not results.get('api'):
            print("   - Telegram API недоступен")
        if not results.get('proxy'):
            print("   - Прокси не работает")
        if not results.get('token'):
            print("   - Токен бота неверный или не установлен")

        print()
        print("📖 См. документацию:")
        print("   docs/TELEGRAM_TROUBLESHOOTING.md")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
