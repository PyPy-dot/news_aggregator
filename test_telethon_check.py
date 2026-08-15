#!/usr/bin/env python3
"""
Check if the phone number is under FloodWait by trying a code request
and catching the FloodWait error to see how long we need to wait.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings
from telethon import TelegramClient
from telethon.errors import FloodWaitError


async def main():
    phone = settings.phone_number.strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    print(f"🔍 Checking flood status for {phone}")

    for label, use_ipv6 in [("IPv6", True), ("No IPv6", False)]:
        print(f"\n--- {label} (use_ipv6={use_ipv6}) ---")
        session_path = f"test_flood_{label.lower().replace(' ', '_')}"
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
            device_model=f"FloodCheck {label}",
        )

        try:
            await client.connect()
            print(f"  ✅ Connected")

            try:
                sent = await client.send_code_request(phone)
                print(f"  ✅ Code sent! hash: {sent.phone_code_hash}")
                if hasattr(sent, "type") and sent.type:
                    print(f"  📱 Delivery: {type(sent.type).__name__}")
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

    print("\n🏁 Done")


if __name__ == "__main__":
    asyncio.run(main())
