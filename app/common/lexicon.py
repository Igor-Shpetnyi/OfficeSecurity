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
    tier: str = "oblast"  # city/oblast/source — див. заголовок toponyms.yaml


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
    тим самим принципом — не власну окрему структуру.

    `location`/`location_evidence` — КОРТЕЖІ, не одне значення: реальні
    повідомлення (особливо "Повітряні Сили") часто називають маршрут через
    кілька топонімів одним реченням ("курсом на Шостку, Ямпіль, Глухів") —
    одна локація на подію губила б інформацію про весь маршрут (знайдено
    на живих даних 2026-07-21)."""

    layer: str
    level: str | None
    level_evidence: str | None
    status: str | None
    status_evidence: str | None
    location: tuple[str, ...]
    location_evidence: tuple[str, ...]
    # Фраза напрямку ("курсом на Суми", "у бік Сумщини"), якщо знайдена —
    # None, якщо в повідомленні жодної немає. Додано 2026-07-24 для тексту
    # сповіщень (ціль+напрямок) і гео-фільтра релевантності (is_geo_relevant).
    direction_evidence: str | None = None

    def as_dict(self) -> dict:
        return {
            "layer": self.layer,
            "level": self.level,
            "level_evidence": self.level_evidence,
            "status": self.status,
            "status_evidence": self.status_evidence,
            "location": list(self.location),
            "location_evidence": list(self.location_evidence),
            "direction_evidence": self.direction_evidence,
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
    return tuple(
        Toponym(canonical=e["canonical"], forms=tuple(e["forms"]), tier=e.get("tier", "oblast"))
        for e in raw
    )


@lru_cache(maxsize=1)
def _toponym_tiers() -> dict[str, str]:
    return {t.canonical: t.tier for t in _load_toponyms()}


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
    Ще НЕ використовується в match_locations() — див. заголовок streets_sumy.yaml."""
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


def match_direction(normalized_text: str) -> str | None:
    """Фраза напрямку ("курсом на Суми", "у бік Сумщини") — перша знайдена,
    разом із ~60 символами тексту після стему як людський evidence-рядок
    (не лише прапорець — фраза йде напряму в текст сповіщення). None, якщо
    жодної не знайдено. Той самий принцип, що match_status()/_find_level_word,
    substring-пошук у нормалізованому тексті, не regex — консистентно з
    рештою Рівня 1 (детерміновано, версійовано в YAML, без regex-складності)."""
    for stem in _load_triggers().get("direction", ()):
        idx = normalized_text.find(stem)
        if idx != -1:
            return normalized_text[idx : idx + len(stem) + 60].strip()
    return None


def is_geo_relevant(locations: tuple[str, ...], direction_evidence: str | None) -> bool:
    """Гео-фільтр релевантності для Сум (запит користувача 2026-07-24):
    без локацій — релевантно (рівень без топоніма й досі про Сумщину, не
    регресує наявну поведінку). Є бодай одна локація tier city/oblast —
    релевантно, НАВІТЬ без слова "Суми" в тексті (село Сумщини релевантне
    саме по собі — уточнення користувача). Лише tier=source (Крим/Бєлгород/
    Брянськ/Курськ/Харківщина/Чернігівщина — джерела, не цілі) — релевантно,
    ТІЛЬКИ якщо в тексті ще й є фраза напрямку (інакше "далеко", можна не
    повідомляти)."""
    if not locations:
        return True
    tiers = _toponym_tiers()
    matched_tiers = {tiers.get(loc, "oblast") for loc in locations}
    if matched_tiers & {"city", "oblast"}:
        return True
    return direction_evidence is not None


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


def _match_locations_explained(normalized_text: str) -> list[tuple[str, str]]:
    """УСІ канонічні топоніми з газетиру, згадані в повідомленні (не лише
    один найдовший збіг) + людське пояснення для кожного. Для кожного
    топоніма — спершу пряме входження найдовшої словоформи; якщо не
    знайдено — fuzzy-match (поріг ~0.85) проти однослівних/двослівних вікон
    тексту (толерантно до одруківок)."""
    toponyms = _load_toponyms()
    words = _WORD_RE.findall(normalized_text)
    windows = list(words)
    windows += [f"{a} {b}" for a, b in zip(words, words[1:])]

    results: list[tuple[str, str]] = []
    for topo in toponyms:
        best_form: str | None = None
        for form in topo.forms:
            if form in normalized_text:
                if best_form is None or len(form) > len(best_form):
                    best_form = form
        if best_form is not None:
            results.append((topo.canonical, f'пряме входження форми "{best_form}"'))
            continue

        best_fuzzy: tuple[float, str, str] | None = None
        for form in topo.forms:
            for window in windows:
                ratio = difflib.SequenceMatcher(None, form, window).ratio()
                if ratio >= _FUZZY_THRESHOLD and (best_fuzzy is None or ratio > best_fuzzy[0]):
                    best_fuzzy = (ratio, form, window)
        if best_fuzzy is not None:
            ratio, form, window = best_fuzzy
            results.append((topo.canonical, f'fuzzy-збіг {ratio:.2f} — "{window}" проти форми "{form}"'))

    return results


def match_locations(normalized_text: str) -> tuple[str, ...]:
    """Канонічні назви ВСІХ топонімів з газетиру, знайдених у повідомленні."""
    return tuple(canonical for canonical, _ in _match_locations_explained(normalized_text))


def analyze(normalized_text: str) -> DecisionTrace:
    """Єдина точка входу Рівня 1 для конвеєра (ADR-0013): рахує рівень/
    статус/локації ОДНИМ проходом і одразу повертає, ЧЕРЕЗ ЩО кожне
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

    locations = _match_locations_explained(normalized_text)
    direction_evidence = match_direction(normalized_text)

    return DecisionTrace(
        layer="lexicon",
        level=level,
        level_evidence=level_evidence,
        status=status,
        status_evidence=status_evidence,
        location=tuple(c for c, _ in locations),
        location_evidence=tuple(e for _, e in locations),
        direction_evidence=direction_evidence,
    )
