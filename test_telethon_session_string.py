#!/usr/bin/env python3
"""
Extract a StringSession from an existing .session file.

If you have a working userbot.session file, this script will convert it
to a StringSession that you can put in .env as TELEGRAM_SESSION_STRING.

Usage:
  python test_telethon_session_string.py

This requires the session file to exist and be readable.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings


async def main():
    session_file = "userbot.session"

    print("🔍 Looking for session file...")
    print(f"   Checking: {os.path.abspath(session_file)}")

    if not os.path.exists(session_file):
        print(f"  ❌ {session_file} not found!")
        print(f"     Current directory: {os.getcwd()}")
        print()
        print("  💡 If you have a backup of the old session file:")
        print("     1. Copy it to this directory as 'userbot.session'")
        print("     2. Run this script again")
        return

    print(f"  ✅ Found {session_file} ({os.path.getsize(session_file)} bytes)")

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        print(f"\n  🔑 Loading session...")

        client = TelegramClient(
            session_file,
            api_id=settings.api_id,
            api_hash=settings.api_hash,
            connection_retries=3,
            retry_delay=1,
            timeout=15,
            use_ipv6=False,
        )

        try:
            await client.connect()
            print(f"  ✅ Connected!")

            is_auth = await client.is_user_authorized()
            print(f"  Authorized: {is_auth}")

            if is_auth:
                me = await client.get_me()
                print(f"  🐑 User: @{me.username} (ID: {me.id}, name: {me.first_name})")

                # Generate StringSession
                session_str = client.session.save()
                print(f"\n  ✅ StringSession generated successfully!")
                print(f"  ┌─────────────────────────────────────────────────────────────┐")
                print(f"  │  Add this to your .env file:                              │")
                print(f"  │                                                            │")
                print(f"  │  TELEGRAM_SESSION_STRING={session_str}  │")
                print(f"  │                                                            │")
                print(f"  └─────────────────────────────────────────────────────────────┘")
                print(f"\n  💡 After adding to .env, the listener will use this string session")
                print(f"     instead of the file, which works on network drives!")
            else:
                print(f"  ❌ Session exists but user is NOT authorized")
                print(f"     This session file is empty/expired")

        except Exception as e:
            print(f"  ❌ Session error: {type(e).__name__}: {e}")
            print(f"     The session file may be corrupted")

    except ImportError as e:
        print(f"  ❌ Import error: {e}")
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

    print(f"\n  🏁 Done")


if __name__ == "__main__":
    asyncio.run(main())
