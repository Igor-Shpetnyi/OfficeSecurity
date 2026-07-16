import asyncio
import logging
from dataclasses import dataclass

import asyncpg
from telethon import TelegramClient
from telethon.errors import FloodWaitError, InviteHashExpiredError, UserAlreadyParticipantError
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.utils import get_peer_id

logger = logging.getLogger(__name__)

# Затримка між приєднаннями до каналів — швидке масове приєднання підвищує
# ризик FloodWait/бану єдиного активного юзербот-акаунта (ADR-0004).
JOIN_DELAY_SECONDS = 15


@dataclass
class MonitoredChannel:
    id: int
    channel_identifier: str
    identifier_type: str
    telegram_id: int | None
    is_active: bool


async def fetch_active_channels(pool: asyncpg.Pool) -> list[MonitoredChannel]:
    rows = await pool.fetch(
        "SELECT id, channel_identifier, identifier_type, telegram_id, is_active "
        "FROM monitoring_channels WHERE is_active = TRUE"
    )
    return [MonitoredChannel(**dict(row)) for row in rows]


async def mark_join_status(
    pool: asyncpg.Pool,
    channel_id: int,
    status: str,
    telegram_id: int | None = None,
    error: str | None = None,
) -> None:
    await pool.execute(
        "UPDATE monitoring_channels "
        "SET join_status = $1, telegram_id = COALESCE($2, telegram_id), join_error = $3 "
        "WHERE id = $4",
        status,
        telegram_id,
        error,
        channel_id,
    )


async def join_channel(client: TelegramClient, channel: MonitoredChannel) -> int:
    """Приєднує юзербот-акаунт до каналу — без цього Telethon не отримує NewMessage-події.

    Повертає "marked" ID (get_peer_id), а НЕ сирий entity.id — саме marked ID
    Telethon підставляє в event.chat_id для NewMessage/MessageEdited (для каналів
    це entity.id з префіксом -100). Порівняння сирого ID з marked ID ніколи не
    співпаде, і повідомлення мовчки відфільтровуються.
    """
    if channel.identifier_type == "invite":
        result = await client(ImportChatInviteRequest(channel.channel_identifier))
        entity = result.chats[0]
    else:
        entity = await client.get_entity(channel.channel_identifier)
        await client(JoinChannelRequest(entity))
    return get_peer_id(entity)


async def sync_pending_joins(client: TelegramClient, pool: asyncpg.Pool) -> None:
    """Пробує приєднатись до всіх каналів у статусі 'pending', з троттлінгом."""
    rows = await pool.fetch(
        "SELECT id, channel_identifier, identifier_type FROM monitoring_channels "
        "WHERE is_active = TRUE AND join_status = 'pending'"
    )
    for row in rows:
        channel = MonitoredChannel(
            id=row["id"],
            channel_identifier=row["channel_identifier"],
            identifier_type=row["identifier_type"],
            telegram_id=None,
            is_active=True,
        )
        try:
            telegram_id = await join_channel(client, channel)
            await mark_join_status(pool, channel.id, "joined", telegram_id=telegram_id)
            logger.info("Joined channel %s -> telegram_id=%s", channel.channel_identifier, telegram_id)
        except UserAlreadyParticipantError:
            entity = await client.get_entity(channel.channel_identifier)
            await mark_join_status(pool, channel.id, "joined", telegram_id=get_peer_id(entity))
        except FloodWaitError as e:
            logger.warning(
                "FloodWait %ss while joining %s, will retry on next sync",
                e.seconds,
                channel.channel_identifier,
            )
            await asyncio.sleep(e.seconds)
            return
        except (InviteHashExpiredError, ValueError) as e:
            await mark_join_status(pool, channel.id, "failed", error=str(e))
            logger.error("Failed to join %s: %s", channel.channel_identifier, e)

        await asyncio.sleep(JOIN_DELAY_SECONDS)


async def sync_pending_leaves(client: TelegramClient, pool: asyncpg.Pool) -> None:
    """Виходить з каналів, деактивованих в адмін-панелі, але з яких акаунт ще не вийшов.

    Деактивація (is_active=false) сама по собі лише вимикає інжест — без цього
    кроку акаунт лишався б підписаним на Telegram назавжди (реальний випадок,
    що стався з @durov 2026-07-16).
    """
    rows = await pool.fetch(
        "SELECT id, channel_identifier, telegram_id FROM monitoring_channels "
        "WHERE is_active = FALSE AND join_status = 'joined' AND telegram_id IS NOT NULL"
    )
    for row in rows:
        try:
            entity = await client.get_entity(row["telegram_id"])
            await client(LeaveChannelRequest(entity))
            await mark_join_status(pool, row["id"], "left")
            logger.info("Left channel %s", row["channel_identifier"])
        except FloodWaitError as e:
            logger.warning(
                "FloodWait %ss while leaving %s, will retry on next sync",
                e.seconds,
                row["channel_identifier"],
            )
            await asyncio.sleep(e.seconds)
            return
        except Exception as e:
            # Найчастіша причина — акаунт уже не в каналі (вийшли вручну, канал
            # видалено, чи немає закешованого entity після рестарту без
            # персистентного session-файлу). Кінцевий стан для нас однаковий:
            # ми не учасник і не отримуємо апдейтів — тому фіксуємо 'left', а не
            # ретраїмо вічно той самий провал щохвилини.
            logger.error("Failed to leave %s (treating as left): %s", row["channel_identifier"], e)
            await mark_join_status(pool, row["id"], "left", error=str(e))

        await asyncio.sleep(JOIN_DELAY_SECONDS)
