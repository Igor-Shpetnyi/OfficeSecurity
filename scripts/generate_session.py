"""Одноразовий скрипт для генерації Telethon StringSession.

Запускати вручну, локально, в інтерактивному терміналі — Telegram запросить
номер телефону і код підтвердження (і, за потреби, 2FA-пароль). Це дія
автентифікації особистого акаунта, тому виконується користувачем самостійно.

Використання (TELEGRAM_API_ID/TELEGRAM_API_HASH читаються з .env):
    .venv\\Scripts\\python.exe scripts\\generate_session.py
"""

import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()


async def main() -> None:
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]

    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        session_string = client.session.save()
        print("\nВаш TELEGRAM_SESSION_STRING (додайте в .env, тримайте в секреті):\n")
        print(session_string)


if __name__ == "__main__":
    asyncio.run(main())
