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


@dataclass(frozen=True)
class DecisionTrace:
    """Не лише ЩО вирішив конвеєр про повідомлення, а й ЧЕРЕЗ ЩО — яке саме
    слово/форма спрацювали, або чому рівень був приглушений. Мета — щоб
    людина, що дивиться на подію в панелі, розуміла причину рішення без
    читання коду чи словників. `layer` — який рівень конвеєра це вирішив
    (ADR-0012/ADR-0013); Рівень 2 (стан каналу) і Рівень 3 (LLM) додадуть
    власні значення `layer` і власні `*_evidence` формулювання пізніше, за
    тим самим принципом — не власну окрему структуру."""

    layer: str
    level: str | None
    level_evidence: str | None
    status: str | None
    status_evidence: str | None
    location: str | None
    location_evidence: str | None

    def as_dict(self) -> dict:
        return {
            "layer": self.layer,
            "level": self.level,
            "level_evidence": self.level_evidence,
            "status": self.status,
            "status_evidence": self.status_evidence,
            "location": self.location,
            "location_evidence": self.location_evidence,
        }


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


def _find_level_word(normalized_text: str, level: str) -> str | None:
    for stem in _load_triggers().get(level, ()):
        if stem in normalized_text:
            return stem
    return None


def match_level(normalized_text: str) -> str | None:
    """Найвищий зловлений рівень загрози (red/orange/yellow) або None.
    "status"-слова (відбій тощо) сюди не входять — окремий match_status()."""
    for level in _LEVEL_PRIORITY:
        if _find_level_word(normalized_text, level) is not None:
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


def _match_location_explained(normalized_text: str) -> tuple[str | None, str | None]:
    """Канонічна назва топоніма з газетиру + людське пояснення, ЯКА форма
    спрацювала і як (пряме входження чи fuzzy — і з яким відсотком
    подібності, якщо fuzzy). Спершу пряме входження словоформи (довша форма
    перемагає, якщо збіглось кілька); якщо не знайдено — fuzzy-match
    однослівних/двослівних вікон тексту проти словоформ (толерантно до
    одруківок, поріг ~0.85)."""
    toponyms = _load_toponyms()

    best_direct: tuple[int, str, str] | None = None
    for topo in toponyms:
        for form in topo.forms:
            if form in normalized_text:
                if best_direct is None or len(form) > best_direct[0]:
                    best_direct = (len(form), topo.canonical, form)
    if best_direct is not None:
        _, canonical, form = best_direct
        return canonical, f'пряме входження форми "{form}"'

    words = _WORD_RE.findall(normalized_text)
    windows = list(words)
    windows += [f"{a} {b}" for a, b in zip(words, words[1:])]

    best_fuzzy: tuple[float, str, str, str] | None = None
    for topo in toponyms:
        for form in topo.forms:
            for window in windows:
                ratio = difflib.SequenceMatcher(None, form, window).ratio()
                if ratio >= _FUZZY_THRESHOLD and (best_fuzzy is None or ratio > best_fuzzy[0]):
                    best_fuzzy = (ratio, topo.canonical, form, window)
    if best_fuzzy is not None:
        ratio, canonical, form, window = best_fuzzy
        return canonical, f'fuzzy-збіг {ratio:.2f} — "{window}" проти форми "{form}"'
    return None, None


def match_location(normalized_text: str) -> str | None:
    """Канонічна назва топоніма з газетиру, або None. Тонка обгортка над
    `_match_location_explained` для викликів, яким не потрібне пояснення."""
    canonical, _ = _match_location_explained(normalized_text)
    return canonical


def analyze(normalized_text: str) -> DecisionTrace:
    """Єдина точка входу Рівня 1 для конвеєра (ADR-0013): рахує рівень/
    статус/локацію ОДНИМ проходом і одразу повертає, ЧЕРЕЗ ЩО кожне
    значення отримано — а не лише саме значення. handlers.py викликає це
    замість окремих match_*()/resolve_level(), щоб evidence і значення не
    могли розійтись (порахувались одним викликом з тих самих даних)."""
    status = match_status(normalized_text)
    status_evidence = f'зловлено слово "{status}"' if status else None

    raw_level = match_level(normalized_text)
    if raw_level is not None and status is not None:
        level = None
        word = _find_level_word(normalized_text, raw_level)
        level_evidence = f'рівень "{raw_level}" (слово "{word}") приглушено — знайдено status "{status}"'
    elif raw_level is not None:
        level = raw_level
        word = _find_level_word(normalized_text, raw_level)
        level_evidence = f'зловлено слово "{word}" ({level})'
    else:
        level = None
        level_evidence = None

    location, location_evidence = _match_location_explained(normalized_text)

    return DecisionTrace(
        layer="lexicon",
        level=level,
        level_evidence=level_evidence,
        status=status,
        status_evidence=status_evidence,
        location=location,
        location_evidence=location_evidence,
    )
