import asyncio
import logging

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.common.redis_client import CHANNELS_UPDATE_TOPIC, get_redis
from app.config import load_settings
from app.db.pool import create_pool
from app.userbot.channels import (
    fetch_active_channels,
    sync_missing_metadata,
    sync_pending_deletes,
    sync_pending_joins,
    sync_pending_leaves,
)
from app.userbot.handlers import register_message_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def refresh_active_ids(pool, active_ids: set[int]) -> None:
    channels = await fetch_active_channels(pool)
    resolved = {c.telegram_id for c in channels if c.telegram_id is not None}
    active_ids.clear()
    active_ids.update(resolved)
    logger.info("Active channel set refreshed: %d channels", len(active_ids))


async def channel_updates_listener(redis_client, pool, client, active_ids: set[int]) -> None:
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(CHANNELS_UPDATE_TOPIC)
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        logger.info("Channel list update signal received")
        await sync_pending_joins(client, pool)
        await sync_pending_leaves(client, pool)
        await sync_pending_deletes(client, pool)
        await refresh_active_ids(pool, active_ids)


async def periodic_join_sync(client, pool, active_ids: set[int], interval: int = 60) -> None:
    # Страхувальна сітка на випадок, якщо pub/sub-повідомлення (ADR-0004) було втрачено.
    while True:
        await asyncio.sleep(interval)
        await sync_pending_joins(client, pool)
        await sync_pending_leaves(client, pool)
        await sync_pending_deletes(client, pool)
        await sync_missing_metadata(client, pool)
        await refresh_active_ids(pool, active_ids)


async def main() -> None:
    settings = load_settings()
    pool = await create_pool(settings.database_url)
    redis_client = get_redis(settings.redis_url)

    client = TelegramClient(
        StringSession(settings.telegram_session_string),
        settings.telegram_api_id,
        settings.telegram_api_hash,
        # За замовчуванням Telethon обробляє кожен update у власному asyncio-таску
        # (паралельно). Для одного повідомлення Telegram часто шле NewMessage і
        # MessageEdited (напр. підтягування прев'ю посилання) буквально
        # мілісекунда в мілісекунду — паралельна обробка ламала dedup-перевірку
        # "чи текст справді змінився" в handlers.py (check-then-insert race:
        # обидва handler'и встигали прочитати БД до того, як інший встиг
        # записати), і в events_log потрапляли дублікати-редагування з
        # ідентичним текстом. sequential_updates=True обробляє update'и по
        # черзі в порядку надходження — усуває race в самому джерелі.
        sequential_updates=True,
    )
    await client.start()
    logger.info("Userbot session started")

    active_ids: set[int] = set()
    await sync_pending_joins(client, pool)
    await sync_pending_leaves(client, pool)
    await sync_pending_deletes(client, pool)
    await sync_missing_metadata(client, pool)
    await refresh_active_ids(pool, active_ids)

    register_message_handler(client, pool, active_ids)

    await asyncio.gather(
        client.run_until_disconnected(),
        channel_updates_listener(redis_client, pool, client, active_ids),
        periodic_join_sync(client, pool, active_ids),
    )


if __name__ == "__main__":
    asyncio.run(main())
