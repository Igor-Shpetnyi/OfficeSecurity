import colorsys
import os

from PIL import Image

# Спільний шлях: сюди юзербот качає аватарки (app/userbot/channels.py),
# звідси FastAPI StaticFiles віддає їх адмін-панелі — одне джерело правди.
AVATAR_DIR = "app/admin/static/avatars"

# Світлість/насиченість, фіксовані для будь-якого hue — без цього середній
# колір фото (часто темний/приглушений через темний фон лого чи змішування
# багатьох відтінків) губиться на фоні картки: виміряний контраст доходив
# до ~1.2:1 замість читабельних 4.5:1+. Тон (hue) лишається реальним, тому
# канал усе одно розрізняється за кольором його аватарки.
_LIGHTNESS = 0.55
_SATURATION = 0.55


def avatar_url(telegram_id: int | None) -> str | None:
    if telegram_id is None:
        return None
    if not os.path.exists(os.path.join(AVATAR_DIR, f"{telegram_id}.jpg")):
        return None
    return f"/static/avatars/{telegram_id}.jpg"


def _legible(hue: float) -> str:
    r, g, b = colorsys.hls_to_rgb(hue, _LIGHTNESS, _SATURATION)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def extract_avg_color(path: str) -> str:
    """Тон (hue) — середній колір зображення, просте й швидке наближення
    "домінantного" кольору аватарки. Світлість/насиченість нормалізуються
    окремо (_legible), інакше приглушений/темний середній колір нечитабельний
    на картці."""
    with Image.open(path) as img:
        r, g, b = img.convert("RGB").resize((1, 1)).getpixel((0, 0))
    hue, _l, _s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return _legible(hue)


def fallback_color(name: str) -> str:
    """Детермінований колір для каналів без завантаженої аватарки — та сама
    роль (акцент для розрізнення каналів у стрічці), просто процедурно
    згенерований hue за назвою замість витягнутого із зображення."""
    hue = ((sum(ord(c) for c in name) * 37) % 360) / 360
    return _legible(hue)
