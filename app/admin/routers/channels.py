from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.common.channels_query import load_channels
from app.common.redis_client import CHANNELS_UPDATE_TOPIC
from app.config import STATIC_VERSION

router = APIRouter(prefix="/channels", tags=["channels"])
templates = Jinja2Templates(directory="app/admin/templates")
templates.env.globals["static_v"] = STATIC_VERSION


@router.get("")
async def list_channels(request: Request):
    channels = await load_channels(request.app.state.pool)
    return templates.TemplateResponse(request, "channels.html", {"channels": channels, "active_page": "channels"})


@router.get("/fragment")
async def channels_fragment(request: Request):
    channels = await load_channels(request.app.state.pool)
    return templates.TemplateResponse(
        request, "_channels_content.html", {"channels": channels}, headers={"Cache-Control": "no-store"}
    )


@router.post("")
async def add_channel(
    request: Request,
    channel_identifier: str = Form(...),
    identifier_type: str = Form("username"),
):
    pool = request.app.state.pool
    await pool.execute(
        "INSERT INTO monitoring_channels (channel_identifier, identifier_type, added_at) "
        "VALUES ($1, $2, now()) ON CONFLICT (channel_identifier) DO NOTHING",
        channel_identifier.strip(),
        identifier_type,
    )
    await request.app.state.redis.publish(CHANNELS_UPDATE_TOPIC, "added")
    return RedirectResponse(url="/channels", status_code=303)


@router.post("/{channel_id}/deactivate")
async def deactivate_channel(request: Request, channel_id: int):
    pool = request.app.state.pool
    await pool.execute("UPDATE monitoring_channels SET is_active = FALSE WHERE id = $1", channel_id)
    await request.app.state.redis.publish(CHANNELS_UPDATE_TOPIC, "removed")
    return RedirectResponse(url="/channels", status_code=303)


@router.post("/{channel_id}/delete")
async def delete_channel(request: Request, channel_id: int):
    pool = request.app.state.pool
    # Не видаляє рядок одразу — юзербот спершу вийде з каналу (якщо ще
    # підписаний), потім видалить картку сам (sync_pending_deletes).
    await pool.execute(
        "UPDATE monitoring_channels SET is_active = FALSE, pending_delete = TRUE WHERE id = $1",
        channel_id,
    )
    await request.app.state.redis.publish(CHANNELS_UPDATE_TOPIC, "deleted")
    return RedirectResponse(url="/channels", status_code=303)
