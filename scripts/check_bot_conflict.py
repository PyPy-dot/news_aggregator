#!/usr/bin/env python3
"""
Скрипт для диагностики TelegramConflictError.

Проверяет:
1. Запущен ли бот локально (процессы)
2. Запущен ли бот в Docker
3. Статус webhook в Telegram
4. Предлагает решения
"""

import asyncio
import aiohttp
import subprocess

BOT_TOKEN = "8813165455:AAHVdNRZVK4ywuwhwyP_FmDg88ygHAFoPBE"


def run_cmd(cmd: str) -> tuple[str, str]:
    """Выполнить команду и вернуть stdout, stderr."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        return result.stdout, result.stderr
    except Exception as e:
        return "", str(e)


def check_local_processes() -> list[str]:
    """Проверить локальные процессы Python с main.py."""
    stdout, _ = run_cmd("ps aux | grep -E 'python.*main|python.*bot' | grep -v grep")
    if stdout.strip():
        return stdout.strip().split("\n")
    return []


def check_docker() -> list[str]:
    """Проверить Docker контейнеры."""
    containers = []

    # docker ps
    stdout, _ = run_cmd("docker ps --format '{{.Names}}: {{.Status}}'")
    if stdout.strip():
        containers.extend(stdout.strip().split("\n"))

    # docker compose ps
    stdout, _ = run_cmd("docker compose ps --format '{{.Name}}: {{.Status}}'")
    if stdout.strip():
        containers.extend(stdout.strip().split("\n"))

    return [c for c in containers if "news" in c.lower() or "bot" in c.lower() or "app" in c.lower()]


def check_launchd() -> list[str]:
    """Проверить launchd демоны."""
    stdout, _ = run_cmd("launchctl list | grep -v 'com.apple'")
    if stdout.strip():
        lines = stdout.strip().split("\n")[1:]  # Пропускаем заголовок
        return [l for l in lines if "bot" in l.lower() or "news" in l.lower()]
    return []


async def check_webhook() -> dict:
    """Проверить webhook через Telegram API."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()


async def main():
    print("=" * 70)
    print("🔍 Диагностика TelegramConflictError")
    print("=" * 70)
    print()

    # 1. Локальные процессы
    print("1️⃣ Локальные процессы Python:")
    processes = check_local_processes()
    if processes:
        print("   ⚠️ Найдены процессы:")
        for p in processes:
            print(f"      {p}")
    else:
        print("   ✅ Нет локальных процессов с ботом")
    print()

    # 2. Docker
    print("2️⃣ Docker контейнеры:")
    docker = check_docker()
    if docker:
        print("   ⚠️ Найдены контейнеры:")
        for c in docker:
            print(f"      {c}")
    else:
        print("   ✅ Нет Docker контейнеров с ботом")
    print()

    # 3. Launchd
    print("3️⃣ Launchd демоны:")
    launchd = check_launchd()
    if launchd:
        print("   ⚠️ Найдены демоны:")
        for l in launchd:
            print(f"      {l}")
    else:
        print("   ✅ Нет launchd демонов с ботом")
    print()

    # 4. Webhook
    print("4️⃣ Telegram Webhook:")
    webhook = await check_webhook()
    if webhook.get("ok"):
        result = webhook.get("result", {})
        url = result.get("url") or "не установлен"
        pending = result.get("pending_update_count", 0)
        print(f"   URL: {url}")
        print(f"   Pending updates: {pending}")
        if url and url != "не установлен":
            print("   ⚠️ Webhook активен на другой сервер!")
        else:
            print("   ✅ Webhook не установлен")
    else:
        print(f"   ❌ Ошибка: {webhook}")
    print()

    # 5. Рекомендации
    print("=" * 70)
    print("📋 Рекомендации:")
    print("=" * 70)

    issues = []
    if processes:
        issues.append("локальные процессы")
    if docker:
        issues.append("Docker контейнеры")
    if launchd:
        issues.append("launchd демоны")

    if issues:
        print(f"   Найдены конфликты: {', '.join(issues)}")
        print("   → Остановите эти процессы перед запуском")
    else:
        print("   ✅ Локально конфликтов не найдено")
        print()
        print("   Скорее всего, бот запущен НА ДРУГОЙ МАШИНЕ:")
        print("   • Production сервер (SSH)")
        print("   • Docker на удалённом хосте")
        print("   • Облако (Heroku, Railway, VPS)")
        print()
        print("   Решения:")
        print("   1. Найдите и остановите бота на сервере:")
        print("      ssh user@server 'ps aux | grep python'")
        print("      ssh user@server 'docker compose down'")
        print()
        print("   2. ИЛИ смените токен бота в @BotFather:")
        print("      • Откройте @BotFather")
        print("      • /mybots → ваш бот → Revoke Token")
        print("      • Обновите BOT_TOKEN в .env")
        print()
        print("   3. ИЛИ используйте webhook вместо polling")
    print()
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
