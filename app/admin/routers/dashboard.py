import asyncpg
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.common.channels_query import load_channels
from app.common.events_query import count_unresolved, load_recent_events
from app.common.formatting import relative_time, to_kyiv
from app.config import STATIC_VERSION

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/admin/templates")
templates.env.globals["static_v"] = STATIC_VERSION


async def _load_dashboard_data(pool: asyncpg.Pool) -> dict:
    active_channels = await pool.fetchval(
        "SELECT count(*) FROM monitoring_channels WHERE is_active = TRUE"
    )
    events_24h = await pool.fetchval(
        "SELECT count(*) FROM events_log WHERE detected_at >= now() - interval '24 hours'"
    )
    last_message_at = await pool.fetchval("SELECT max(last_message_at) FROM monitoring_channels")
    channels = await load_channels(pool, limit=8)
    events = await load_recent_events(pool, limit=8)
    unresolved_count = await count_unresolved(pool)
    return {
        "active_channels": active_channels,
        "events_24h": events_24h,
        "last_message_at": to_kyiv(last_message_at),
        "last_message_relative": relative_time(last_message_at) if last_message_at else None,
        "channels": channels,
        "events": events,
        "unresolved_count": unresolved_count,
    }


@router.get("/")
@router.get("/dashboard")
async def dashboard(request: Request):
    data = await _load_dashboard_data(request.app.state.pool)
    return templates.TemplateResponse(
        request, "dashboard.html", {"active_page": "dashboard", **data}
    )


@router.get("/dashboard/fragment")
async def dashboard_fragment(request: Request):
    data = await _load_dashboard_data(request.app.state.pool)
    return templates.TemplateResponse(request, "_dashboard_content.html", data, headers={"Cache-Control": "no-store"})
