from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.common.formatting import relative_time, to_kyiv
from app.common.media import media_label
from app.config import STATIC_VERSION

router = APIRouter(prefix="/notifications", tags=["notifications"])
templates = Jinja2Templates(directory="app/admin/templates")
templates.env.globals["static_v"] = STATIC_VERSION

_QUERY = (
    "SELECT n.id, n.transition_type, n.level, n.location, n.composed_text, n.composed_by, "
    "n.confirmation_count, n.contributing_channels, n.contributing_event_ids, "
    "n.source_event_log_id, n.created_at, "
    "e.source_channel AS source_event_channel, e.telegram_message_id AS source_event_message_id "
    "FROM threat_notifications n "
    "LEFT JOIN events_log e ON e.id = n.source_event_log_id "
    "ORDER BY n.created_at DESC "
    "LIMIT $1"
)

_EVENTS_QUERY = (
    "SELECT id, source_channel, telegram_message_id, raw_text, media_type, detected_at "
    "FROM events_log WHERE id = ANY($1::int[])"
)


async def _load_notifications(request: Request, limit: int = 50) -> list[dict]:
    pool = request.app.state.pool
    rows = await pool.fetch(_QUERY, limit)
    notifications = [dict(row) for row in rows]

    channel_ids = {c for n in notifications for c in (n["contributing_channels"] or [])}

    all_event_ids = {eid for n in notifications for eid in (n["contributing_event_ids"] or [])}
    events_map: dict[int, dict] = {}
    if all_event_ids:
        event_rows = await pool.fetch(_EVENTS_QUERY, list(all_event_ids))
        events_map = {r["id"]: dict(r) for r in event_rows}
        channel_ids |= {e["source_channel"] for e in events_map.values()}

    name_map: dict[str, str] = {}
    if channel_ids:
        chan_rows = await pool.fetch(
            "SELECT telegram_id, title, channel_identifier FROM monitoring_channels "
            "WHERE telegram_id::text = ANY($1::text[])",
            list(channel_ids),
        )
        name_map = {str(r["telegram_id"]): (r["title"] or r["channel_identifier"]) for r in chan_rows}

    for eid, e in events_map.items():
        e["channel_name"] = name_map.get(e["source_channel"], e["source_channel"])
        e["detected_at"] = to_kyiv(e["detected_at"])
        e["media_label"] = media_label(e.get("media_type"))

    for n in notifications:
        n["created_at"] = to_kyiv(n["created_at"])
        n["created_at_relative"] = relative_time(n["created_at"])
        n["contributing_channel_names"] = [
            name_map.get(c, c) for c in (n["contributing_channels"] or [])
        ]
        # Хронологічно, найстаріше перше — та сама історія, з якої зросла ціль.
        contributing_events = [
            events_map[eid] for eid in (n["contributing_event_ids"] or []) if eid in events_map
        ]
        contributing_events.sort(key=lambda e: e["detected_at"])
        n["contributing_events"] = contributing_events
    return notifications


@router.get("")
async def show_notifications(request: Request):
    notifications = await _load_notifications(request)
    return templates.TemplateResponse(
        request, "notifications.html", {"active_page": "notifications", "notifications": notifications}
    )


@router.get("/fragment")
async def notifications_fragment(request: Request):
    notifications = await _load_notifications(request)
    return templates.TemplateResponse(
        request, "_notifications_content.html", {"notifications": notifications},
        headers={"Cache-Control": "no-store"},
    )
