"""Рівень 3 конвеєра виявлення (ADR-0012). НАРАЗІ СТУБ: жодного реального
виклику LLM API, жодного ключа — це свідомо не змінюється тут, підключення
реального провайдера гейтоване окремим бюджетним рішенням (ADR-0012).

Дві ролі, обидві заявлені в ADR-0012:
(а) compose_alert_text — компонує людський текст сповіщення зі структурованих
    даних (рівень, локація, evidence) для стрічки "Сповіщення".
(б) resolve_ambiguous_slot — tie-break для Рівня 2, коли в каналі одночасно
    кілька активних цілей (channel_state_ambiguous) і незрозуміло, якої з
    них стосується нове повідомлення без явної локації.

Кожна відповідь стуба позначена is_stub=True — щоб реальну відповідь LLM
пізніше не сплутати зі стабом при читанні БД/логів (composed_by='template_stub'
у threat_notifications — те саме розрізнення на рівні схеми)."""

from dataclasses import dataclass

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


@dataclass(frozen=True)
class ComposedAlert:
    text: str
    is_stub: bool
    model: str | None  # None для стаба, назва провайдера/моделі — коли стане реальним


def compose_alert_text(
    level: str,
    location: tuple[str, ...],
    threat_type_evidence: str | None,
    transition_type: str,
    confirmation_count: int,
    contributing_channels: tuple[str, ...],
) -> ComposedAlert:
    emoji, level_label = _LEVEL_UA.get(level, ("⚪", level.upper()))
    transition_label = _TRANSITION_UA.get(transition_type, transition_type)
    location_str = ", ".join(location) if location else "локація не визначена"
    evidence_line = threat_type_evidence or "Джерело — лексичний тригер, без деталізації типу"
    channels_count = len(contributing_channels)
    text = (
        f"{emoji} {level_label} — {location_str}\n"
        f"{transition_label}. {evidence_line}\n"
        f"Підтверджено {confirmation_count} повідомленнями з {channels_count} "
        f"{'каналу' if channels_count == 1 else 'каналів'}."
    )
    return ComposedAlert(text=text, is_stub=True, model=None)


@dataclass(frozen=True)
class TieBreakResult:
    chosen_slot: int | None
    is_new_target: bool
    is_stub: bool


def resolve_ambiguous_slot(candidate_slots: list[tuple[int, dict]], new_trace) -> TieBreakResult:
    """СТАБ — та сама евристика "найновіший активний слот", що досі була
    інлайновою всередині channel_state.resolve() (рядок з max(...,
    key=lambda x: x[1]["updated_at"])), лише винесена за цей шов, щоб мати
    реальну точку виклику під роль (б), не тільки декларацію. Поведінка
    НЕ змінюється порівняно з попереднім inline-варіантом. `new_trace` поки
    не використовується стабом (сама евристика його не потребує) — лишений
    у сигнатурі, бо реальна LLM-версія читатиме текст нового повідомлення
    саме звідти для смислового зіставлення, не лише часової евристики."""
    if not candidate_slots:
        return TieBreakResult(chosen_slot=None, is_new_target=True, is_stub=True)
    slot_idx, _ = max(candidate_slots, key=lambda x: x[1]["updated_at"])
    return TieBreakResult(chosen_slot=slot_idx, is_new_target=False, is_stub=True)
