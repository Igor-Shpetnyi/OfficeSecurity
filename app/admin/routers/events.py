from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/events", tags=["events"])
templates = Jinja2Templates(directory="app/admin/templates")


@router.get("/recent")
async def recent_events(request: Request):
    pool = request.app.state.pool
    rows = await pool.fetch(
        "SELECT id, raw_text, source_channel, event_type, detected_at FROM events_log "
        "ORDER BY detected_at DESC LIMIT 50"
    )
    return templates.TemplateResponse(request, "events.html", {"events": rows, "active_page": "events"})
