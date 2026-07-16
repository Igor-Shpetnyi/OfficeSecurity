import asyncpg
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/admin/templates")


async def _load_dashboard_data(pool: asyncpg.Pool) -> dict:
    active_channels = await pool.fetchval(
        "SELECT count(*) FROM monitoring_channels WHERE is_active = TRUE"
    )
    events_24h = await pool.fetchval(
        "SELECT count(*) FROM events_log WHERE detected_at >= now() - interval '24 hours'"
    )
    last_message_at = await pool.fetchval("SELECT max(last_message_at) FROM monitoring_channels")
    channels = await pool.fetch(
        "SELECT id, channel_identifier, is_active, join_status, last_message_at "
        "FROM monitoring_channels ORDER BY added_at DESC LIMIT 8"
    )
    events = await pool.fetch(
        "SELECT id, raw_text, source_channel, event_type, detected_at FROM events_log "
        "ORDER BY detected_at DESC LIMIT 8"
    )
    return {
        "active_channels": active_channels,
        "events_24h": events_24h,
        "last_message_at": last_message_at,
        "channels": channels,
        "events": events,
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
    return templates.TemplateResponse(request, "_dashboard_content.html", data)
