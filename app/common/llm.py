"""Рівень 3 конвеєра виявлення (ADR-0012/0015). Google Gemini (безкоштовний
тариф) — свідомий вибір замість платних провайдерів, поки бюджет = $0
(Уточнення ADR-0015, 2026-07-24; спершу було Anthropic, замінено того ж дня
до першого коміту). Fail-closed фолбек на детермінований шаблон — жодна
помилка звідси НІКОЛИ не піднімається вище (жоден except не пропускається),
лише повертає стаб.

Дві ролі:
(а) compose_alert_text — компонує людський текст сповіщення для стрічки "Сповіщення".
(б) resolve_ambiguous_slot — tie-break для Рівня 2, коли в каналі одночасно
    кілька активних цілей (channel_state_ambiguous).

Клієнт — лінивий модульний singleton (той самий принцип, що app/common/lexicon.py
для YAML: модуль сам керує своїм ресурсом, не інжектиться з main.py). Ключ
читається напряму з os.environ — безпечно, бо app/config.py викликає
load_dotenv() на рівні імпорту, раніше за будь-який виклик цього модуля.

Circuit breaker (ТЗ §13): 3 поспіль невдалі виклики → пауза 30с, під час якої
жодного мережевого звернення не робиться (лише dict-lookup) — критично для
гарячого шляху: app/userbot/handlers.py обробляє повідомлення послідовно
(ADR-0010, sequential_updates=True), тож повільний/зависаючий виклик тут
затримав би ВСІ наступні повідомлення з УСІХ каналів, не лише поточне."""

import json
import os
import time
from dataclasses import dataclass
from functools import lru_cache

from google import genai
from google.genai import errors, types

# "gemini-2.5-flash" (пінована назва) повертає 404 — недоступна для нових
# ключів; "gemini-2.0-flash" повертає 429 — 0 безкоштовної квоти саме на
# цю пінован назву. Обидва знайдено прямим тестом на реальному ключі
# 2026-07-24. "-latest" аліаси (їх Google підтримує актуальними) працюють
# і мають реальну безкоштовну квоту — той самий клас проблеми, що вже
# вчив нас не покладатись на здогад про форму зовнішнього API без перевірки.
_MODEL = "gemini-flash-lite-latest"
# API Gemini відхиляє дедлайн коротший за 10с (400 INVALID_ARGUMENT,
# знайдено прямим тестом на реальному ключі 2026-07-24) — 4с (як спершу
# планувалось для Anthropic) тут технічно неможливі. 12с — невеликий запас
# над мінімумом, найгірший блок гарячого шляху (Telethon, ADR-0010) тепер
# відповідно вищий, ніж початково закладалось, це прийнятний компроміс.
_CALL_TIMEOUT_SECONDS = 12.0
_MAX_TEXT_TOKENS = 300

_BREAKER_FAILURE_THRESHOLD = 3
_BREAKER_PAUSE_SECONDS = 30.0  # ТЗ §13, буквально

_breaker_failure_count = 0
_breaker_opened_at: float | None = None  # time.monotonic(), не wall clock

_LEVEL_UA = {
    "red": ("🔴", "ЧЕРВОНИЙ"),
    "orange": ("🟠", "ПОМАРАНЧЕВИЙ"),
    "yellow": ("🟡", "ЖОВТИЙ"),
    "green": ("🟢", "ЗЕЛЕНИЙ"),
}

_TRANSITION_UA = {
    "new": "Нова ціль",
    "escalated": "Підвищення рівня",
    "downgraded": "Зниження рівня",
    "cleared": "Відбій",
}


@lru_cache(maxsize=1)
def _get_client() -> "genai.Client | None":
    key = os.environ.get("GEMINI_API_KEY") or None
    if key is None:
        return None
    return genai.Client(
        api_key=key,
        http_options=types.HttpOptions(timeout=int(_CALL_TIMEOUT_SECONDS * 1000)),  # мс, не сек
    )


def _breaker_allows_call() -> bool:
    global _breaker_opened_at
    if _breaker_opened_at is None:
        return True
    if time.monotonic() - _breaker_opened_at >= _BREAKER_PAUSE_SECONDS:
        _breaker_opened_at = None
        return True
    return False


def _record_success() -> None:
    global _breaker_failure_count
    _breaker_failure_count = 0


def _record_failure() -> None:
    global _breaker_failure_count, _breaker_opened_at
    _breaker_failure_count += 1
    if _breaker_failure_count >= _BREAKER_FAILURE_THRESHOLD:
        _breaker_opened_at = time.monotonic()


@dataclass(frozen=True)
class ComposedAlert:
    text: str
    is_stub: bool
    model: str | None  # None для стаба, назва моделі — коли реальна відповідь
    # None — фіча не увімкнена (нема ключа); "circuit_open"/"api_error" —
    # реальна спроба щойно провалилась (ТЗ §13 "⚠️ без ШІ-верифікації").
    stub_reason: str | None


def _stub_alert_text(
    level: str, location: tuple[str, ...], threat_type_evidence: str | None,
    transition_type: str, confirmation_count: int, contributing_channels: tuple[str, ...],
    stub_reason: str,
) -> ComposedAlert:
    emoji, level_label = _LEVEL_UA.get(level, ("⚪", level.upper()))
    transition_label = _TRANSITION_UA.get(transition_type, transition_type)
    location_str = ", ".join(location) if location else "локація не визначена"
    evidence_line = threat_type_evidence or "Джерело — лексичний тригер, без деталізації типу"
    # Кількість підтверджень/каналів НЕ дублюється тут — вона вже окремо
    # показана в UI-бейджі ("Підтверджено N повідомленням(и) з...", запит
    # користувача 2026-07-24: ця мета-інформація не мала бути в самому тексті
    # сповіщення, лише в інтерфейсі навколо нього).
    text = f"{emoji} {level_label} — {location_str}\n{transition_label}. {evidence_line}"
    if stub_reason in ("circuit_open", "api_error"):
        text += "\n⚠️ без ШІ-верифікації"
    return ComposedAlert(text=text, is_stub=True, model=None, stub_reason=stub_reason)


async def compose_alert_text(
    level: str,
    location: tuple[str, ...],
    threat_type_evidence: str | None,
    transition_type: str,
    confirmation_count: int,
    contributing_channels: tuple[str, ...],
) -> ComposedAlert:
    client = _get_client()
    if client is None:
        return _stub_alert_text(
            level, location, threat_type_evidence, transition_type,
            confirmation_count, contributing_channels, "no_key",
        )
    if not _breaker_allows_call():
        return _stub_alert_text(
            level, location, threat_type_evidence, transition_type,
            confirmation_count, contributing_channels, "circuit_open",
        )

    emoji, level_label = _LEVEL_UA.get(level, ("⚪", level.upper()))
    # Кількість підтверджень/каналів свідомо НЕ передається як факт — вона
    # вже окремо в UI-бейджі, не має дублюватись/переказуватись у самому
    # тексті сповіщення (запит користувача 2026-07-24).
    facts = (
        f"рівень: {emoji} {level_label}\n"
        f"локація: {', '.join(location) if location else 'не визначена'}\n"
        f"тип переходу: {_TRANSITION_UA.get(transition_type, transition_type)}\n"
        f"деталі: {threat_type_evidence or 'без деталізації типу'}"
    )
    try:
        response = await client.aio.models.generate_content(
            model=_MODEL,
            contents=facts,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Ти складаєш одне коротке (2-4 речення) сповіщення про загрозу "
                    "українською мовою для мешканців Сумщини на основі структурованих "
                    "фактів нижче. Тон — стисний, діловий, без паніки. Тільки текст "
                    "сповіщення, без преамбули на кшталт \"Ось сповіщення:\", "
                    "без markdown-розмітки.\n\n"
                    "КРИТИЧНО: використовуй ЛИШЕ факти, надані нижче — нічого понад "
                    "них. Якщо локація 'не визначена' — не називай жодної конкретної "
                    "місцевості (не пиши 'Сумщина'/'Суми', якщо цього немає у фактах). "
                    "Не додавай конкретних тверджень чи інструкцій, яких немає у "
                    "фактах (напр. 'оголошено тривогу', 'прямуйте до укриття', "
                    "'дотримуйтесь тиші') — рядок 'деталі' нижче часто лише одне "
                    "зловлене слово без контексту, не опис факту, що щось оголошено "
                    "чи наказано. Просто повідом рівень і те, що відомо, без "
                    "додавання власних припущень. НЕ згадуй кількість підтверджень, "
                    "джерел чи каналів і не давай оцінку надійності інформації "
                    "(напр. 'перевірено за одним каналом', 'інформація потребує "
                    "уваги') — це вже окремо показано в інтерфейсі, не пиши про це "
                    "в самому тексті сповіщення."
                ),
                max_output_tokens=_MAX_TEXT_TOKENS,
            ),
        )
        text = (response.text or "").strip()
        if not text:
            raise ValueError("empty response")
    except Exception:
        _record_failure()
        return _stub_alert_text(
            level, location, threat_type_evidence, transition_type,
            confirmation_count, contributing_channels, "api_error",
        )
    _record_success()
    return ComposedAlert(text=text, is_stub=False, model=_MODEL, stub_reason=None)


@dataclass(frozen=True)
class TieBreakResult:
    chosen_slot: int | None
    is_new_target: bool
    is_stub: bool


def _stub_tie_break(candidate_slots: list[tuple[int, dict]]) -> TieBreakResult:
    if not candidate_slots:
        return TieBreakResult(chosen_slot=None, is_new_target=True, is_stub=True)
    slot_idx, _ = max(candidate_slots, key=lambda x: x[1]["updated_at"])
    return TieBreakResult(chosen_slot=slot_idx, is_new_target=False, is_stub=True)


_TIE_BREAK_SCHEMA = {
    "type": "object",
    "properties": {
        "chosen_slot_index": {
            "type": ["integer", "null"],
            "description": "Індекс обраної цілі, або null якщо is_new_target=true",
        },
        "is_new_target": {
            "type": "boolean",
            "description": "true, якщо повідомлення не стосується жодної з активних цілей",
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["chosen_slot_index", "is_new_target", "confidence"],
}


async def resolve_ambiguous_slot(
    candidate_slots: list[tuple[int, dict]], new_trace, new_text: str
) -> TieBreakResult:
    """new_trace — DecisionTrace нового повідомлення (рівень/локація вже
    відомі з Рівня 1); new_text — сирий текст цього повідомлення (не
    normalized — модель читає природну мову). candidate_slots — активні
    слоти Рівня 2, кожен з "text_snippet" (перші ~150 символів повідомлення,
    що відкрило/оновило слот)."""
    if not candidate_slots:
        return TieBreakResult(chosen_slot=None, is_new_target=True, is_stub=True)

    client = _get_client()
    if client is None or not _breaker_allows_call():
        return _stub_tie_break(candidate_slots)

    candidates_desc = "\n".join(
        f"[{idx}] рівень={data.get('level')}, локація={', '.join(data.get('location') or ())}, "
        f"текст=\"{data.get('text_snippet', '')}\""
        for idx, data in candidate_slots
    )
    user_content = (
        f"Активні цілі каналу:\n{candidates_desc}\n\n"
        f"Нове повідомлення (без явного тригер-слова): \"{new_text[:200]}\"\n\n"
        "До якої з активних цілей воно найімовірніше належить, чи це зовсім "
        "не пов'язана тема?"
    )
    valid_indices = {idx for idx, _ in candidate_slots}
    try:
        response = await client.aio.models.generate_content(
            model=_MODEL,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Ти визначаєш, чи є нове повідомлення в Telegram-каналі "
                    "продовженням однієї з активних тем (напр. відстеження дрона), "
                    "чи це геть інша, не пов'язана тема (напр. новини, реклама). "
                    "Якщо не впевнений — обирай confidence=low."
                ),
                max_output_tokens=200,
                response_mime_type="application/json",
                response_json_schema=_TIE_BREAK_SCHEMA,
            ),
        )
        data = json.loads(response.text)
        if data["confidence"] == "low":
            raise ValueError("low confidence")
        if data["is_new_target"]:
            _record_success()
            return TieBreakResult(chosen_slot=None, is_new_target=True, is_stub=False)
        idx = data["chosen_slot_index"]
        if idx not in valid_indices:
            raise ValueError("hallucinated slot index")
    except Exception:
        _record_failure()
        return _stub_tie_break(candidate_slots)
    _record_success()
    return TieBreakResult(chosen_slot=idx, is_new_target=False, is_stub=False)
