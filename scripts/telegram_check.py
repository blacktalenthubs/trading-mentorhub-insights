#!/usr/bin/env python3
"""Diagnose Telegram bot configuration.

Usage:
    python scripts/telegram_check.py          # Show bot info + recent chats
    python scripts/telegram_check.py --test   # Send test message to configured chat_id
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

# Load .env
sys.path.insert(0, ".")
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from alert_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def _api(method: str, **params) -> dict:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = urllib.parse.urlencode(params).encode() if params else None
    resp = urllib.request.urlopen(url, data, timeout=10)
    return json.loads(resp.read())


def main():
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set in .env")
        return

    # 1. Bot info
    me = _api("getMe")
    bot = me["result"]
    print(f"Bot: @{bot['username']} (id: {bot['id']})")
    print()

    # 2. Check configured chat_id
    print(f"Configured TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")
    if TELEGRAM_CHAT_ID:
        try:
            chat = _api("getChat", chat_id=TELEGRAM_CHAT_ID)
            c = chat["result"]
            chat_type = c.get("type", "unknown")
            title = c.get("title") or c.get("first_name", "N/A")
            print(f"  -> Type: {chat_type}, Title: {title}")
            if chat_type in ("group", "supergroup"):
                print(f"  -> This IS a group/supergroup. Bot should be able to send here.")
            else:
                print(f"  -> This is a {chat_type} chat, NOT a group.")
        except urllib.error.HTTPError as e:
            error = json.loads(e.read())
            print(f"  -> ERROR: {error.get('description', str(e))}")
            print("  -> The chat_id may be wrong, or bot was removed from the group.")
    print()

    # 3. Recent updates (shows which chats the bot received messages in)
    print("Recent chats the bot has seen (send a message in the group first):")
    try:
        updates = _api("getUpdates", limit=20)
        seen_chats: dict[int, dict] = {}
        for u in updates.get("result", []):
            msg = u.get("message") or u.get("my_chat_member", {}).get("chat")
            if msg:
                chat = msg.get("chat", msg) if isinstance(msg, dict) else msg
                cid = chat.get("id")
                if cid and cid not in seen_chats:
                    seen_chats[cid] = {
                        "id": cid,
                        "type": chat.get("type", "?"),
                        "title": chat.get("title") or chat.get("first_name", "?"),
                    }
        if seen_chats:
            for c in seen_chats.values():
                marker = " <-- CONFIGURED" if str(c["id"]) == str(TELEGRAM_CHAT_ID) else ""
                print(f"  chat_id={c['id']}  type={c['type']}  title={c['title']}{marker}")
        else:
            print("  (none — send a message in the group to make the bot see it)")
    except Exception as e:
        print(f"  Error fetching updates: {e}")

    # 4. Optional test send
    if "--test" in sys.argv:
        print()
        print(f"Sending test message to chat_id={TELEGRAM_CHAT_ID}...")
        try:
            result = _api("sendMessage", chat_id=TELEGRAM_CHAT_ID,
                          text="TradeCoPilot test alert - ignore this message")
            print("  -> SUCCESS")
        except urllib.error.HTTPError as e:
            error = json.loads(e.read())
            desc = error.get("description", str(e))
            print(f"  -> FAILED: {desc}")
            if "chat not found" in desc.lower():
                print("  FIX: The chat_id is wrong. Use a chat_id from the list above.")
            elif "bot was kicked" in desc.lower() or "forbidden" in desc.lower():
                print("  FIX: Add the bot back to the group and give it permission to send messages.")


if __name__ == "__main__":
    main()
