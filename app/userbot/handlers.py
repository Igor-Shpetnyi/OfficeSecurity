import logging

import asyncpg
from telethon import TelegramClient, events

logger = logging.getLogger(__name__)


async def _store_event(pool: asyncpg.Pool, event, event_type: str) -> None:
    text = event.raw_text or ""
    await pool.execute(
        "INSERT INTO events_log (raw_text, source_channel, telegram_message_id, event_type, detected_at) "
        "VALUES ($1, $2, $3, $4, now())",
        text,
        str(event.chat_id),
        event.id,
        event_type,
    )
    await pool.execute(
        "UPDATE monitoring_channels SET last_message_at = now() WHERE telegram_id = $1",
        event.chat_id,
    )
    logger.info("Stored %s message from %s: %.80s", event_type, event.chat_id, text)


def register_message_handler(client: TelegramClient, pool: asyncpg.Pool, active_ids: set[int]) -> None:
    @client.on(events.NewMessage(func=lambda e: e.chat_id in active_ids))
    async def new_message_handler(event: events.NewMessage.Event) -> None:
        await _store_event(pool, event, "new")

    @client.on(events.MessageEdited(func=lambda e: e.chat_id in active_ids))
    async def edited_message_handler(event: events.MessageEdited.Event) -> None:
        await _store_event(pool, event, "edit")
