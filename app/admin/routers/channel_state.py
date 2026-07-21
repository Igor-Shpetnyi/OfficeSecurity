from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.common import channel_state
from app.common.formatting import relative_time, to_kyiv
from app.config import STATIC_VERSION

router = APIRouter(prefix="/channels/state", tags=["channel-state"])
templates = Jinja2Templates(directory="app/admin/templates")
templates.env.globals["static_v"] = STATIC_VERSION


async def _load_slots(request: Request) -> list[dict]:
    slots = await channel_state.all_active_slots(request.app.state.redis)
    if slots:
        pool = request.app.state.pool
        channel_ids = list({s["channel_id"] for s in slots})
        rows = await pool.fetch(
            "SELECT telegram_id, title, channel_identifier FROM monitoring_channels "
            "WHERE telegram_id::text = ANY($1::text[])",
            channel_ids,
        )
        name_map = {str(r["telegram_id"]): (r["title"] or r["channel_identifier"]) for r in rows}
        for s in slots:
            s["channel_name"] = name_map.get(s["channel_id"], s["channel_id"])
    slots.sort(key=lambda s: s["updated_at"], reverse=True)
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    for s in slots:
        updated_at = to_kyiv(datetime.fromisoformat(s["updated_at"]))
        s["updated_at_relative"] = relative_time(updated_at)
        s["updated_at_time"] = updated_at.strftime("%H:%M:%S")
        s["ttl_minutes"] = s["ttl"] // 60
        s["ttl_seconds"] = s["ttl"] % 60
        # epoch ms для клієнтського посекундного тікера (startTtlTicker,
        # live-refresh.js) — сервер лишається єдиним джерелом правди про
        # точний TTL (Redis), JS лише інтерполює відлік між fetch-циклами.
        s["ttl_expires_at_ms"] = int(now_ms + s["ttl"] * 1000)
    return slots


@router.get("")
async def show_state(request: Request):
    slots = await _load_slots(request)
    return templates.TemplateResponse(
        request, "channel_state.html", {"active_page": "channel_state", "slots": slots}
    )


@router.get("/fragment")
async def state_fragment(request: Request):
    slots = await _load_slots(request)
    return templates.TemplateResponse(
        request, "_channel_state_content.html", {"slots": slots}, headers={"Cache-Control": "no-store"}
    )
