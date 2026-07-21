from app.common.avatars import avatar_url, fallback_color
from app.common.channel_display import initials
from app.common.formatting import to_kyiv

_BASE_QUERY = (
    "SELECT id, channel_identifier, identifier_type, title, is_active, join_status, "
    "join_error, telegram_id, avatar_color, last_message_at, pending_delete "
    "FROM monitoring_channels ORDER BY added_at DESC"
)


async def load_channels(pool, limit: int | None = None) -> list[dict]:
    if limit is None:
        rows = await pool.fetch(_BASE_QUERY)
    else:
        rows = await pool.fetch(_BASE_QUERY + " LIMIT $1", limit)

    channels = []
    for row in rows:
        c = dict(row)
        name = c["title"] or c["channel_identifier"]
        c["channel_name"] = name
        c["initials"] = initials(name)
        c["chan_color"] = c["avatar_color"] or fallback_color(name)
        c["avatar_url"] = avatar_url(c["telegram_id"])
        c["last_message_at"] = to_kyiv(c["last_message_at"])
        channels.append(c)
    return channels
