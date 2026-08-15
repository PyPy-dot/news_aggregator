#!/usr/bin/env python3
"""
Quick test: try to send auth code via Telethon with and without IPv6.
Usage: python test_telethon_auth.py
"""

import asyncio
import os
import sys

# Project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings
from telethon import TelegramClient


async def test_client(label, use_ipv6, session_prefix):
    print(f"\n{'='*60}")
    print(f"  {label} (use_ipv6={use_ipv6})")
    print(f"{'='*60}")

    session_path = f"test_session_{session_prefix}"
    # Remove old session
    for s in [f"{session_path}.session", f"{session_path}.session-journal"]:
        if os.path.exists(s):
            os.remove(s)
            print(f"  🗑 Deleted old session: {s}")

    phone = settings.phone_number.strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    print(f"  Phone: {phone}")
    print(f"  API ID: {settings.api_id}")
    print(f"  API Hash: {settings.api_hash[:10]}...")

    client = TelegramClient(
        session_path,
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        use_ipv6=use_ipv6,
        connection_retries=5,
        retry_delay=2,
        timeout=30,
        device_model=f"TestClient {label}",
        system_version="Test 1.0",
        app_version="1.0.0",
    )

    try:
        print(f"  🔌 Connecting...")
        await client.connect()
        print(f"  ✅ Connected!")

        is_auth = await client.is_user_authorized()
        print(f"  Authorized: {is_auth}")

        if not is_auth:
            print(f"  📤 Sending code request...")
            sent = await client.send_code_request(phone)
            print(f"  ✅ Code sent! phone_code_hash: {sent.phone_code_hash}")

            if hasattr(sent, "type") and sent.type:
                from telethon.tl.types import auth as auth_types
                t = sent.type
                if isinstance(t, auth_types.SentCodeTypeApp):
                    print(f"  📱 Delivery: Telegram App")
                elif isinstance(t, auth_types.SentCodeTypeSms):
                    print(f"  📱 Delivery: SMS")
                elif isinstance(t, auth_types.SentCodeTypeCall):
                    print(f"  📱 Delivery: Call")
                elif isinstance(t, auth_types.SentCodeTypeFragment):
                    print(f"  📱 Delivery: Fragment SMS")
                else:
                    print(f"  📱 Delivery: {type(t).__name__}")

            if hasattr(sent, "next_type") and sent.next_type:
                print(f"  📱 Next retry: {type(sent.next_type).__name__}")

            print(f"\n  ⏳ Waiting for you to confirm... (type 'y' in console)")
            try:
                code = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, input, "Code: "),
                    timeout=120
                )
                if code.strip():
                    print(f"  🔑 Signing in with code...")
                    try:
                        await client.sign_in(phone, code.strip(), phone_code_hash=sent.phone_code_hash)
                        print(f"  ✅ AUTHENTICATED!")
                        me = await client.get_me()
                        print(f"  🐑 User: @{me.username} (ID: {me.id})")
                    except Exception as e:
                        print(f"  ❌ sign_in failed: {e}")
            except asyncio.TimeoutError:
                print(f"  ⏰ Timeout waiting for code")

    except Exception as e:
        print(f"  ❌ ERROR: {type(e).__name__}: {e}")
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
        # Cleanup test sessions
        for s in [f"{session_path}.session", f"{session_path}.session-journal"]:
            if os.path.exists(s):
                try:
                    os.remove(s)
                except Exception:
                    pass

    print(f"  🏁 {label} done")


async def main():
    print("🧪 Telethon Auth Test")
    print(f"   Testing on: {os.getcwd()}")

    await test_client("IPv6", use_ipv6=True, session_prefix="ipv6")
    await test_client("No IPv6", use_ipv6=False, session_prefix="noipv6")

    print("\n" + "=" * 60)
    print("  All tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
