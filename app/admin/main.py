import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.admin.routers import channel_state, channels, dashboard, events, lexicon, notifications
from app.common import threat_state
from app.common.auth import require_admin
from app.common.redis_client import get_redis
from app.config import load_settings
from app.db.pool import create_pool

settings = load_settings()
logger = logging.getLogger(__name__)


async def _cascade_loop(pool, interval: int = 7) -> None:
    # Каскадна стейт-машина (ТЗ §10, план "Сповіщення" 2026-07-23) — тікає
    # в адмін-процесі (asyncio.create_task, той самий патерн, що
    # periodic_join_sync у app/userbot/main.py, лише в іншому процесі,
    # свідомо без третього непіднаглядного процесу). Помилка в одному тіку
    # не повинна вбивати весь цикл — просто чекаємо наступного.
    while True:
        await asyncio.sleep(interval)
        try:
            await threat_state.cascade_tick(pool)
        except Exception:
            logger.exception("cascade_tick failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await create_pool(settings.database_url)
    app.state.redis = get_redis(settings.redis_url)
    cascade_task = asyncio.create_task(_cascade_loop(app.state.pool))
    yield
    cascade_task.cancel()
    await app.state.pool.close()


app = FastAPI(lifespan=lifespan, dependencies=[Depends(require_admin(settings))])

app.mount("/static", StaticFiles(directory="app/admin/static"), name="static")

app.include_router(dashboard.router)
app.include_router(channels.router)
app.include_router(channel_state.router)
app.include_router(events.router)
app.include_router(lexicon.router)
app.include_router(notifications.router)


@app.get("/health")
async def health(request: Request) -> dict:
    await request.app.state.pool.fetchval("SELECT 1")
    return {"status": "ok"}
