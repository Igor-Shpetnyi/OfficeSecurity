"""Одноразовий інспекційний скрипт: показує тип/опис/кількість учасників
для списку @username-каналів БЕЗ приєднання. Read-only."""

import asyncio
import os
import sys

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import Channel

load_dotenv()


async def main() -> None:
    usernames = sys.argv[1:]
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session = os.environ["TELEGRAM_SESSION_STRING"]

    async with TelegramClient(StringSession(session), api_id, api_hash) as client:
        for username in usernames:
            try:
                entity = await client.get_entity(username)
                if not isinstance(entity, Channel):
                    print(f"{username}\tNOT_A_CHANNEL\t{type(entity).__name__}")
                    continue
                full = await client(GetFullChannelRequest(entity))
                kind = "broadcast" if entity.broadcast else ("megagroup" if entity.megagroup else "chat")
                about = (full.full_chat.about or "").replace("\n", " ")[:150]
                print(f"{username}\t{kind}\tparticipants={full.full_chat.participants_count}\ttitle={entity.title}\tabout={about}")
            except Exception as e:
                print(f"{username}\tERROR\t{e}")


if __name__ == "__main__":
    asyncio.run(main())
