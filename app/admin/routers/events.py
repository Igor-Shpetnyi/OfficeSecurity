from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.common.events_query import count_unresolved, load_recent_events
from app.config import STATIC_VERSION

router = APIRouter(prefix="/events", tags=["events"])
templates = Jinja2Templates(directory="app/admin/templates")
templates.env.globals["static_v"] = STATIC_VERSION


@router.get("/recent")
async def recent_events(request: Request):
    unresolved = request.query_params.get("filter") == "unresolved"
    events = await load_recent_events(request.app.state.pool, limit=50, unresolved_only=unresolved)
    unresolved_count = await count_unresolved(request.app.state.pool)
    return templates.TemplateResponse(
        request,
        "events.html",
        {
            "events": events,
            "active_page": "events",
            "unresolved_filter": unresolved,
            "unresolved_count": unresolved_count,
        },
    )


@router.get("/recent/fragment")
async def recent_events_fragment(request: Request):
    unresolved = request.query_params.get("filter") == "unresolved"
    events = await load_recent_events(request.app.state.pool, limit=50, unresolved_only=unresolved)
    return templates.TemplateResponse(
        request, "_events_content.html", {"events": events}, headers={"Cache-Control": "no-store"}
    )
