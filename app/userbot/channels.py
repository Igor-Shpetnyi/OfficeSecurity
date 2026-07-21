import asyncio
import logging
import os
from dataclasses import dataclass

import asyncpg
from telethon import TelegramClient
from telethon.errors import FloodWaitError, InviteHashExpiredError, UserAlreadyParticipantError
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.utils import get_peer_id

from app.common.avatars import AVATAR_DIR, extract_avg_color

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
    title: str | None = None,
    avatar_color: str | None = None,
    error: str | None = None,
) -> None:
    await pool.execute(
        "UPDATE monitoring_channels "
        "SET join_status = $1, telegram_id = COALESCE($2, telegram_id), "
        "title = COALESCE($3, title), avatar_color = COALESCE($4, avatar_color), join_error = $5 "
        "WHERE id = $6",
        status,
        telegram_id,
        title,
        avatar_color,
        error,
        channel_id,
    )


async def fetch_avatar(client: TelegramClient, entity, telegram_id: int) -> str | None:
    """Завантажує поточне фото профілю каналу в app/admin/static/avatars/<id>.jpg
    і повертає його середній колір (для акценту в UI — замість випадкового
    хешу). Канали без фото (download повертає None) — адмін-панель тоді
    показує кольоровий ініціал (процедурний фолбек-колір), помилка не потрібна."""
    try:
        os.makedirs(AVATAR_DIR, exist_ok=True)
        path = os.path.join(AVATAR_DIR, f"{telegram_id}.jpg")
        result = await client.download_profile_photo(entity, file=path)
        if result is None:
            return None
        return extract_avg_color(path)
    except Exception as e:
        logger.warning("Failed to download avatar for %s: %s", telegram_id, e)
        return None


async def join_channel(client: TelegramClient, channel: MonitoredChannel) -> tuple[int, str, str | None]:
    """Приєднує юзербот-акаунт до каналу — без цього Telethon не отримує NewMessage-події.

    Повертає "marked" ID (get_peer_id), а НЕ сирий entity.id — саме marked ID
    Telethon підставляє в event.chat_id для NewMessage/MessageEdited (для каналів
    це entity.id з префіксом -100). Порівняння сирого ID з marked ID ніколи не
    співпаде, і повідомлення мовчки відфільтровуються. Заразом тягне title і
    аватарку — для адмін-панелі краще показувати їх, а не сирий @username.
    """
    if channel.identifier_type == "invite":
        result = await client(ImportChatInviteRequest(channel.channel_identifier))
        entity = result.chats[0]
    else:
        entity = await client.get_entity(channel.channel_identifier)
        await client(JoinChannelRequest(entity))
    telegram_id = get_peer_id(entity)
    avatar_color = await fetch_avatar(client, entity, telegram_id)
    return telegram_id, entity.title, avatar_color


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
            telegram_id, title, avatar_color = await join_channel(client, channel)
            await mark_join_status(
                pool, channel.id, "joined", telegram_id=telegram_id, title=title, avatar_color=avatar_color
            )
            logger.info("Joined channel %s -> telegram_id=%s", channel.channel_identifier, telegram_id)
        except UserAlreadyParticipantError:
            entity = await client.get_entity(channel.channel_identifier)
            telegram_id = get_peer_id(entity)
            avatar_color = await fetch_avatar(client, entity, telegram_id)
            await mark_join_status(
                pool, channel.id, "joined", telegram_id=telegram_id, title=entity.title, avatar_color=avatar_color
            )
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
        "WHERE is_active = FALSE AND join_status = 'joined' AND telegram_id IS NOT NULL "
        "AND pending_delete = FALSE"
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


async def sync_pending_deletes(client: TelegramClient, pool: asyncpg.Pool) -> None:
    """Остаточно видаляє картки каналів, позначені на видалення в адмін-панелі.

    Якщо акаунт ще підписаний — спершу виходить з каналу (той самий урок з
    @durov 2026-07-16: не можна просто прибрати рядок і лишити підписку
    висіти в Telegram назавжди), потім видаляє рядок незалежно від
    попереднього join_status. events_log не чіпається — це лог подій,
    не довідник каналів, історія лишається навіть якщо канал прибрали з панелі.
    """
    rows = await pool.fetch(
        "SELECT id, channel_identifier, telegram_id, join_status FROM monitoring_channels "
        "WHERE pending_delete = TRUE"
    )
    for row in rows:
        if row["join_status"] == "joined" and row["telegram_id"] is not None:
            try:
                entity = await client.get_entity(row["telegram_id"])
                await client(LeaveChannelRequest(entity))
                logger.info("Left channel %s before delete", row["channel_identifier"])
            except FloodWaitError as e:
                logger.warning(
                    "FloodWait %ss while leaving %s before delete, will retry on next sync",
                    e.seconds,
                    row["channel_identifier"],
                )
                await asyncio.sleep(e.seconds)
                return
            except Exception as e:
                logger.warning(
                    "Could not leave %s before delete (deleting card anyway): %s",
                    row["channel_identifier"],
                    e,
                )

        await pool.execute("DELETE FROM monitoring_channels WHERE id = $1", row["id"])
        logger.info("Deleted channel card %s", row["channel_identifier"])

        await asyncio.sleep(JOIN_DELAY_SECONDS)


async def sync_missing_metadata(client: TelegramClient, pool: asyncpg.Pool) -> None:
    """Доповнює title/аватарку/колір для каналів, приєднаних до того, як їх
    почали зберігати — без цього вони назавжди лишились би з NULL, бо
    звичайний join більше не повторюється для вже 'joined' каналів."""
    rows = await pool.fetch(
        "SELECT id, channel_identifier, telegram_id FROM monitoring_channels "
        "WHERE is_active = TRUE AND join_status = 'joined' AND telegram_id IS NOT NULL "
        "AND (title IS NULL OR avatar_color IS NULL)"
    )
    for row in rows:
        try:
            entity = await client.get_entity(row["telegram_id"])
            avatar_color = await fetch_avatar(client, entity, row["telegram_id"])
            await mark_join_status(pool, row["id"], "joined", title=entity.title, avatar_color=avatar_color)
            logger.info("Backfilled metadata for %s", row["channel_identifier"])
        except Exception as e:
            logger.warning("Failed to backfill metadata for %s: %s", row["channel_identifier"], e)

        await asyncio.sleep(JOIN_DELAY_SECONDS)
