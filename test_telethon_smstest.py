#!/usr/bin/env python3
"""
Try to force SMS delivery by requesting code twice.
The first request goes to the app, the second should go to SMS.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import auth as auth_types


async def main():
    phone = settings.phone_number.strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    print(f"📱 Force SMS test for {phone}")
    print(f"   API ID: {settings.api_id}")
    print(f"   API Hash: {settings.api_hash[:10]}...")

    for attempt_num, use_ipv6 in [(1, True), (2, False)]:
        label = f"Attempt {attempt_num} (ipv6={use_ipv6})"
        print(f"\n{'='*50}")
        print(f"  {label}")
        print(f"{'='*50}")

        session_path = f"test_sms_{attempt_num}"
        for s in [f"{session_path}.session", f"{session_path}.session-journal"]:
            if os.path.exists(s):
                try:
                    os.remove(s)
                except Exception:
                    pass

        client = TelegramClient(
            session_path,
            api_id=settings.api_id,
            api_hash=settings.api_hash,
            use_ipv6=use_ipv6,
            connection_retries=3,
            retry_delay=1,
            timeout=15,
            device_model=f"SMSForceAttempt{attempt_num}",
            system_version="Test 1.0",
            app_version="1.0.0",
        )

        try:
            await client.connect()
            print(f"  ✅ Connected")

            try:
                sent = await client.send_code_request(phone)
                code_hash = sent.phone_code_hash
                code_type = sent.type if hasattr(sent, "type") else None
                next_type = sent.next_type if hasattr(sent, "next_type") else None

                type_name = type(code_type).__name__ if code_type else "None"
                next_name = type(next_type).__name__ if next_type else "None"

                print(f"  ✅ Code sent! hash: {code_hash}")
                print(f"  📱 This attempt delivery: {type_name}")
                print(f"  📱 Next request delivery: {next_name}")

                # If next_type is SMS, make a second request to force SMS
                if next_type and isinstance(next_type, auth_types.SentCodeTypeSms):
                    print(f"  🔄 Requesting code again to force SMS...")
                    await asyncio.sleep(2)

                    sent2 = await client.send_code_request(phone)
                    code_hash2 = sent2.phone_code_hash
                    type2 = type(sent2.type).__name__ if sent2.type else "None"
                    next2 = type(sent2.next_type).__name__ if sent2.next_type else "None"

                    print(f"  ✅ 2nd code sent! hash: {code_hash2}")
                    print(f"  📱 SMS delivery: {type2}")
                    print(f"  📱 Next: {next2}")

                # If already SMS
                if code_type and isinstance(code_type, auth_types.SentCodeTypeSms):
                    print(f"  📱 Code should arrive as SMS on your phone!")

                # If app
                if code_type and isinstance(code_type, auth_types.SentCodeTypeApp):
                    print(f"  📱 Code sent to Telegram app. Check main menu.")

            except FloodWaitError as e:
                seconds = e.seconds
                minutes = seconds / 60
                hours = minutes / 60
                if hours >= 1:
                    wait_str = f"{hours:.1f} hours"
                elif minutes >= 1:
                    wait_str = f"{minutes:.1f} minutes"
                else:
                    wait_str = f"{seconds} seconds"
                print(f"  🚫 FLOOD WAIT: {wait_str} ({seconds}s)")
                print(f"     Message: {e.message}")
                print(f"\n  💡 Wait {wait_str} before trying again!")
            except Exception as e:
                print(f"  ❌ Error: {type(e).__name__}: {e}")
        except Exception as e:
            print(f"  ❌ Connect failed: {type(e).__name__}: {e}")
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
            for s in [f"{session_path}.session", f"{session_path}.session-journal"]:
                if os.path.exists(s):
                    try:
                        os.remove(s)
                    except Exception:
                        pass

    print(f"\n{'='*50}")
    print(f"  Summary:")
    print(f"  1. Check Telegram app main menu for code")
    print(f"  2. Check SMS messages on your phone")
    print(f"  3. If neither works, you may need to wait for flood ban")
    print(f"  4. Or use a working session from before the refactoring")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
