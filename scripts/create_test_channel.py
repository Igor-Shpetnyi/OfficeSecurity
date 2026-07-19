"""Одноразовий скрипт: створює приватний Telegram-канал під керуванням акаунта
юзербота, призначений виключно для тестування пайплайну подій (RegEx/LLM-шар,
live-refresh адмін-панелі тощо). Канал приватний (без публічного @username),
щоб не плутати з реальними моніторинг-каналами і не давати стороннім доступу."""

import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.tl.functions.messages import ExportChatInviteRequest

load_dotenv()


async def main() -> None:
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session = os.environ["TELEGRAM_SESSION_STRING"]

    async with TelegramClient(StringSession(session), api_id, api_hash) as client:
        result = await client(CreateChannelRequest(
            title="OfficeSecurity — тестовий канал",
            about="Приватний канал лише для тестування пайплайну подій. Не моніторинг-джерело.",
            broadcast=True,
            megagroup=False,
        ))
        channel = result.chats[0]
        invite = await client(ExportChatInviteRequest(peer=channel))
        print(f"telegram_id={channel.id}")
        print(f"marked_id=-100{channel.id}")
        print(f"invite_link={invite.link}")


if __name__ == "__main__":
    asyncio.run(main())
