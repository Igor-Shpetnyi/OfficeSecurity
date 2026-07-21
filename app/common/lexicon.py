import difflib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_DATA_DIR = Path(__file__).parent / "data"
_LEVEL_PRIORITY = ("red", "orange", "yellow")
_FUZZY_THRESHOLD = 0.85

_WORD_RE = re.compile(r"[а-щьюяєіїґ'\-]+", re.IGNORECASE)


@dataclass(frozen=True)
class Toponym:
    canonical: str
    forms: tuple[str, ...]


@dataclass(frozen=True)
class Street:
    type: str
    name: str
    old_name: str | None = None


@lru_cache(maxsize=1)
def _load_triggers() -> dict[str, tuple[str, ...]]:
    with open(_DATA_DIR / "triggers.yaml", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return {level: tuple(words) for level, words in raw.items()}


@lru_cache(maxsize=1)
def _load_toponyms() -> tuple[Toponym, ...]:
    with open(_DATA_DIR / "toponyms.yaml", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return tuple(Toponym(canonical=e["canonical"], forms=tuple(e["forms"])) for e in raw)


def get_triggers() -> dict[str, tuple[str, ...]]:
    """Публічний доступ до словника тригерів для відображення в адмін-панелі
    (сторінка /lexicon) — той самий кешований словник, що й matching-функції."""
    return _load_triggers()


def get_toponyms() -> tuple[Toponym, ...]:
    """Публічний доступ до газетиру для відображення в адмін-панелі."""
    return _load_toponyms()


@lru_cache(maxsize=1)
def _load_streets() -> tuple[Street, ...]:
    with open(_DATA_DIR / "streets_sumy.yaml", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return tuple(Street(type=e["type"], name=e["name"], old_name=e.get("old_name")) for e in raw)


def get_streets() -> tuple[Street, ...]:
    """Публічний доступ до реєстру вулиць Сум для відображення в адмін-панелі.
    Ще НЕ використовується в match_location() — див. заголовок streets_sumy.yaml."""
    return _load_streets()


def match_level(normalized_text: str) -> str | None:
    """Найвищий зловлений рівень загрози (red/orange/yellow) або None.
    "status"-слова (відбій тощо) сюди не входять — окремий match_status()."""
    triggers = _load_triggers()
    for level in _LEVEL_PRIORITY:
        if any(stem in normalized_text for stem in triggers.get(level, ())):
            return level
    return None


def match_status(normalized_text: str) -> str | None:
    """Маркер зміни стану (відбій/втрата фіксації/нейтралізація) — не рівень
    загрози. Повертає перший зловлений стем як є (для показу в бейджі)."""
    for stem in _load_triggers().get("status", ()):
        if stem in normalized_text:
            return stem
    return None


def resolve_level(normalized_text: str) -> str | None:
    """match_level(), але приглушений, коли в тому самому повідомленні є
    status-маркер. Усі поточні status-слова (відбій/чисто/знищено/збито/...)
    означають ЗАВЕРШЕННЯ чи зняття загрози — показувати поруч 🔴/🟠/🟡 було б
    оманливо (напр. "🟢 відбій повітряної тривоги" ловив би "red" через
    саме слово "тривога", хоча повідомлення — протилежне: усе чисто).
    Знайдено на живих даних 2026-07-21 (аудит Рівня 1)."""
    if match_status(normalized_text) is not None:
        return None
    return match_level(normalized_text)


def match_location(normalized_text: str) -> str | None:
    """Канонічна назва топоніма з газетиру, або None. Спершу пряме входження
    словоформи; якщо не знайдено — fuzzy-match однослівних/двослівних вікон
    тексту проти словоформ (толерантно до одруківок)."""
    toponyms = _load_toponyms()

    best_direct: tuple[int, str] | None = None
    for topo in toponyms:
        for form in topo.forms:
            if form in normalized_text:
                if best_direct is None or len(form) > best_direct[0]:
                    best_direct = (len(form), topo.canonical)
    if best_direct is not None:
        return best_direct[1]

    words = _WORD_RE.findall(normalized_text)
    windows = list(words)
    windows += [f"{a} {b}" for a, b in zip(words, words[1:])]

    best_fuzzy: tuple[float, str] | None = None
    for topo in toponyms:
        for form in topo.forms:
            for window in windows:
                ratio = difflib.SequenceMatcher(None, form, window).ratio()
                if ratio >= _FUZZY_THRESHOLD and (best_fuzzy is None or ratio > best_fuzzy[0]):
                    best_fuzzy = (ratio, topo.canonical)
    return best_fuzzy[1] if best_fuzzy else None
