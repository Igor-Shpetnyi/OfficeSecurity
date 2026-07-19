"""Надсилає тестове повідомлення в приватний тестовий канал проєкту
(створений scripts/create_test_channel.py), щоб згенерувати контрольовану
подію в pipeline без залежності від активності реальних моніторинг-каналів.

Використання:
    .venv\\Scripts\\python.exe scripts\\send_test_event.py "текст повідомлення"
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

TEST_CHANNEL_TELEGRAM_ID = -1004387323164


async def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else "Тестова подія"

    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session = os.environ["TELEGRAM_SESSION_STRING"]

    async with TelegramClient(StringSession(session), api_id, api_hash) as client:
        await client.send_message(TEST_CHANNEL_TELEGRAM_ID, text)
        print("Sent.")
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
