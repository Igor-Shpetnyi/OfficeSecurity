import re

_WHITESPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """lowercase + згортання пробілів. Рекламні підписи каналів навмисно НЕ
    вирізаються — вони не заважають пошуку тригер-слів усередині тексту,
    повне вирізання футерів не потрібне для матчингу (Рівень 1, ADR-0012)."""
    return _WHITESPACE_RE.sub(" ", text.lower()).strip()
