"""Одноразовий інспекційний скрипт: список каналів (broadcast, без приватних груп/DM),
на які підписаний акаунт юзербота. Read-only, нічого не змінює."""

import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel

load_dotenv()


async def main() -> None:
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session = os.environ["TELEGRAM_SESSION_STRING"]

    async with TelegramClient(StringSession(session), api_id, api_hash) as client:
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if isinstance(entity, Channel) and entity.broadcast and not entity.megagroup:
                username = f"@{entity.username}" if entity.username else "(приватний, invite-only)"
                print(f"{entity.id}\t{username}\t{dialog.title}\t{dialog.unread_count} unread")


if __name__ == "__main__":
    asyncio.run(main())
