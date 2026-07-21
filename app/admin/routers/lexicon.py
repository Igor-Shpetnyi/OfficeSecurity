from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.common import lexicon
from app.config import STATIC_VERSION

router = APIRouter(prefix="/lexicon", tags=["lexicon"])
templates = Jinja2Templates(directory="app/admin/templates")
templates.env.globals["static_v"] = STATIC_VERSION

_LEVEL_ORDER = ("red", "orange", "yellow", "status")


@router.get("")
async def show_lexicon(request: Request):
    triggers = lexicon.get_triggers()
    levels = [(level, triggers.get(level, ())) for level in _LEVEL_ORDER if triggers.get(level)]
    toponyms = lexicon.get_toponyms()
    streets = lexicon.get_streets()
    return templates.TemplateResponse(
        request,
        "lexicon.html",
        {
            "active_page": "lexicon",
            "levels": levels,
            "toponyms": toponyms,
            "streets": streets,
        },
    )
