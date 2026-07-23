from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.common.formatting import relative_time, to_kyiv
from app.config import STATIC_VERSION

router = APIRouter(prefix="/notifications", tags=["notifications"])
templates = Jinja2Templates(directory="app/admin/templates")
templates.env.globals["static_v"] = STATIC_VERSION

_QUERY = (
    "SELECT n.id, n.transition_type, n.level, n.location, n.composed_text, n.composed_by, "
    "n.confirmation_count, n.contributing_channels, n.source_event_log_id, n.created_at, "
    "e.source_channel AS source_event_channel, e.telegram_message_id AS source_event_message_id "
    "FROM threat_notifications n "
    "LEFT JOIN events_log e ON e.id = n.source_event_log_id "
    "ORDER BY n.created_at DESC "
    "LIMIT $1"
)


async def _load_notifications(request: Request, limit: int = 50) -> list[dict]:
    pool = request.app.state.pool
    rows = await pool.fetch(_QUERY, limit)
    notifications = [dict(row) for row in rows]

    channel_ids = {c for n in notifications for c in (n["contributing_channels"] or [])}
    name_map: dict[str, str] = {}
    if channel_ids:
        rows = await pool.fetch(
            "SELECT telegram_id, title, channel_identifier FROM monitoring_channels "
            "WHERE telegram_id::text = ANY($1::text[])",
            list(channel_ids),
        )
        name_map = {str(r["telegram_id"]): (r["title"] or r["channel_identifier"]) for r in rows}

    for n in notifications:
        n["created_at"] = to_kyiv(n["created_at"])
        n["created_at_relative"] = relative_time(n["created_at"])
        n["contributing_channel_names"] = [
            name_map.get(c, c) for c in (n["contributing_channels"] or [])
        ]
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
