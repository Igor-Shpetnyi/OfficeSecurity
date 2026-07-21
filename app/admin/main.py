from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.admin.routers import channels, dashboard, events, lexicon
from app.common.auth import require_admin
from app.common.redis_client import get_redis
from app.config import load_settings
from app.db.pool import create_pool

settings = load_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await create_pool(settings.database_url)
    app.state.redis = get_redis(settings.redis_url)
    yield
    await app.state.pool.close()


app = FastAPI(lifespan=lifespan, dependencies=[Depends(require_admin(settings))])

app.mount("/static", StaticFiles(directory="app/admin/static"), name="static")

app.include_router(dashboard.router)
app.include_router(channels.router)
app.include_router(events.router)
app.include_router(lexicon.router)


@app.get("/health")
async def health(request: Request) -> dict:
    await request.app.state.pool.fetchval("SELECT 1")
    return {"status": "ok"}
