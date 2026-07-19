from datetime import datetime
from zoneinfo import ZoneInfo

KYIV_TZ = ZoneInfo("Europe/Kyiv")


def to_kyiv(dt: datetime | None) -> datetime | None:
    """asyncpg завжди повертає timestamptz як UTC-datetime незалежно від
    сесійного часового поясу (бінарний протокол, SET TIME ZONE на з'єднанні
    тут не діє) — конвертація в Europe/Kyiv потрібна явно перед показом."""
    if dt is None:
        return None
    return dt.astimezone(KYIV_TZ)


def relative_time(dt: datetime) -> str:
    dt = to_kyiv(dt)
    now = datetime.now(KYIV_TZ)
    seconds = (now - dt).total_seconds()
    if seconds < 60:
        return "щойно"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} хв тому"
    hours = int(minutes // 60)
    if hours < 24:
        return f"{hours} год тому"
    days = int(hours // 24)
    if days == 1:
        return "учора"
    if days < 7:
        return f"{days} дн тому"
    return dt.strftime("%Y-%m-%d")
