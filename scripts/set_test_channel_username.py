"""Встановлює публічний @username для тестового каналу (створеного
create_test_channel.py), щоб додавати його через звичайний /channels-флоу
(identifier_type=username) — той самий код-шлях, що й для реальних каналів,
із коректним резолвом entity в Telethon."""

import asyncio
import os
import random
import string

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import UpdateUsernameRequest

load_dotenv()

TEST_CHANNEL_TELEGRAM_ID = -1004387323164


async def main() -> None:
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session = os.environ["TELEGRAM_SESSION_STRING"]

    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    username = f"officesecurity_test_{suffix}"

    async with TelegramClient(StringSession(session), api_id, api_hash) as client:
        entity = await client.get_entity(TEST_CHANNEL_TELEGRAM_ID)
        await client(UpdateUsernameRequest(channel=entity, username=username))
        print(f"@{username}")


if __name__ == "__main__":
    asyncio.run(main())
