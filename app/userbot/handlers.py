import logging

import asyncpg
from telethon import TelegramClient, events

logger = logging.getLogger(__name__)


async def _store_event(pool: asyncpg.Pool, event, event_type: str) -> None:
    text = event.raw_text or ""
    await pool.execute(
        "INSERT INTO events_log "
        "(raw_text, source_channel, telegram_message_id, reply_to_message_id, event_type, detected_at) "
        "VALUES ($1, $2, $3, $4, $5, now())",
        text,
        str(event.chat_id),
        event.id,
        event.reply_to_msg_id,
        event_type,
    )
    await pool.execute(
        "UPDATE monitoring_channels SET last_message_at = now() WHERE telegram_id = $1",
        event.chat_id,
    )
    logger.info("Stored %s message from %s: %.80s", event_type, event.chat_id, text)


async def _last_stored_text(pool: asyncpg.Pool, chat_id: int, message_id: int) -> str | None:
    return await pool.fetchval(
        "SELECT raw_text FROM events_log WHERE source_channel = $1 AND telegram_message_id = $2 "
        "ORDER BY detected_at DESC LIMIT 1",
        str(chat_id),
        message_id,
    )


def register_message_handler(client: TelegramClient, pool: asyncpg.Pool, active_ids: set[int]) -> None:
    @client.on(events.NewMessage(func=lambda e: e.chat_id in active_ids))
    async def new_message_handler(event: events.NewMessage.Event) -> None:
        await _store_event(pool, event, "new")

    @client.on(events.MessageEdited(func=lambda e: e.chat_id in active_ids))
    async def edited_message_handler(event: events.MessageEdited.Event) -> None:
        # Telegram шле updateEditChannelMessage і для зміни лічильника
        # переглядів/реакцій каналу — не лише для реального редагування
        # тексту (повідомлення — це весь об'єкт, views/reactions теж його
        # частина). Без цієї перевірки один допис накопичував по 5-10
        # "редагувань" за хвилини після публікації без жодної зміни тексту
        # (виміряно: 141 з 189 edit-подій за 2 год мали ідентичний текст).
        new_text = event.raw_text or ""
        last_text = await _last_stored_text(pool, event.chat_id, event.id)
        if last_text is not None and last_text == new_text:
            return
        await _store_event(pool, event, "edit")
