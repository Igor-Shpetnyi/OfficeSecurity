import json
import logging

import asyncpg
from telethon import TelegramClient, events

from app.common import lexicon
from app.common.normalize import normalize

logger = logging.getLogger(__name__)

# Порядок важливий: .gif — теж MessageMediaDocument з mime_type video/mp4,
# тому перевіряється до .video; .sticker/.voice/.audio так само уточнюють
# конкретний під-тип document перед загальним фолбеком. Короткий код, не
# готовий підпис — людський текст рахує app/common/media.py, щоб не
# дублювати мапінг у двох місцях.
_MEDIA_CHECKS = ("photo", "gif", "video", "sticker", "voice", "audio", "poll", "document")


def _media_type(event) -> str | None:
    for attr in _MEDIA_CHECKS:
        if getattr(event, attr, None):
            return attr
    return "other" if event.media else None


async def _store_event(pool: asyncpg.Pool, event, event_type: str) -> None:
    text = event.raw_text or ""
    normalized = normalize(text)
    trace = lexicon.analyze(normalized)
    # Рівень 2 (стан активної цілі на канал) підключається окремим кроком —
    # поки що resolved_by='lexicon' лише коли Рівень 1 щось зловив.
    resolved_by = "lexicon" if (trace.level or trace.status or trace.location) else None
    await pool.execute(
        "INSERT INTO events_log "
        "(raw_text, source_channel, telegram_message_id, reply_to_message_id, media_type, grouped_id, "
        "event_type, detected_at, regex_matched_level, matched_status, matched_location, resolved_by, "
        "decision_trace) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, now(), $8, $9, $10, $11, $12)",
        text,
        str(event.chat_id),
        event.id,
        event.reply_to_msg_id,
        _media_type(event),
        event.grouped_id,
        event_type,
        trace.level,
        trace.status,
        trace.location,
        resolved_by,
        json.dumps(trace.as_dict()),
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
