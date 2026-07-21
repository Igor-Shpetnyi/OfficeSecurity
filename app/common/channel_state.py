import json
from datetime import datetime, timezone

from app.common.lexicon import DecisionTrace

_SLOTS = 3
# 20 хв — та сама константа, що "локаційно втрачена ціль" в ТЗ §10, не нова
# довільна цифра. Redis TTL на кожен запис слота, оновлюється (sliding
# window) при кожному успадкуванні — доки канал живий по темі, слот живе.
_TTL_SECONDS = 1200


def _key(channel_id: str, slot: int) -> str:
    return f"channel_state:{channel_id}:{slot}"


async def _get_slot(redis, channel_id: str, slot: int) -> dict | None:
    raw = await redis.get(_key(channel_id, slot))
    return json.loads(raw) if raw else None


async def _set_slot(redis, channel_id: str, slot: int, data: dict) -> None:
    await redis.set(_key(channel_id, slot), json.dumps(data), ex=_TTL_SECONDS)


async def _active_slots(redis, channel_id: str) -> list[tuple[int, dict]]:
    result = []
    for slot in range(_SLOTS):
        data = await _get_slot(redis, channel_id, slot)
        if data:
            result.append((slot, data))
    return result


async def _write_explicit(redis, channel_id: str, trace: DecisionTrace, source_message_id: int) -> None:
    """Рівень 1 щось явно зловив — записати/оновити слот. Пріоритет вибору
    слота: (1) уже активний слот з тою самою локацією (та сама ціль, що
    розвивається), (2) вільний слот, (3) якщо всі 3 зайняті — витісняється
    найстаріший (новий явний сигнал важливіший за застарілий)."""
    slots = await _active_slots(redis, channel_id)

    target_slot = None
    if trace.location:
        for slot_idx, data in slots:
            if data.get("location") == trace.location:
                target_slot = slot_idx
                break
    if target_slot is None:
        used = {s for s, _ in slots}
        free = [s for s in range(_SLOTS) if s not in used]
        target_slot = free[0] if free else min(slots, key=lambda x: x[1]["updated_at"])[0]

    await _set_slot(redis, channel_id, target_slot, {
        "level": trace.level,
        "location": trace.location,
        "source_message_id": source_message_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


async def _clear_matching_slot(redis, channel_id: str, location: str | None) -> None:
    """Повідомлення саме є status-сигналом (відбій/знищено/...) — закрити
    активний слот, якого це стосується, а не чекати TTL. Якщо в
    повідомленні є локація — шукаємо слот саме з нею; якщо активний слот
    рівно один (найчастіший випадок) — закриваємо його, бо "відбій" явно
    про нього; якщо кілька одночасних і локація не вказана — не вгадуємо
    який саме, лишаємо TTL/Етап 4 (LLM tie-break) розібратись."""
    slots = await _active_slots(redis, channel_id)
    if not slots:
        return
    target = None
    if location:
        for slot_idx, data in slots:
            if data.get("location") == location:
                target = slot_idx
                break
    if target is None and len(slots) == 1:
        target = slots[0][0]
    if target is not None:
        await redis.delete(_key(channel_id, target))


async def resolve(redis, channel_id: str, lex_trace: DecisionTrace, source_message_id: int) -> DecisionTrace:
    """Рівень 2 конвеєра виявлення (ADR-0012). Якщо повідомлення саме є
    status-сигналом (відбій/знищено/...) — закриває відповідний активний
    слот і повертає trace як є, НЕ успадковуючи рівень (інакше "Відбій..."
    показало б рівень активної цілі — той самий клас бага, що вже
    виправлений у Рівні 1 через resolve_level(), знайдено повторно власним
    ізольованим тестом при розробці Рівня 2). Якщо Рівень 1 дав рівень —
    записує/оновлює стан каналу і повертає trace як є. Якщо ні — дивиться
    на активні "цілі" каналу (Redis, TTL 20 хв): 0 активних → лишається
    нерозв'язаним (повертає lex_trace без змін, чесно); 1 активна —
    успадковує її рівень, оновлює локацію, якщо в повідомленні з'явився
    новий топонім; 2-3 одночасно → неоднозначно, поки що береться
    найновіша (точне зіставлення — LLM tie-break, Етап 4, ще не
    реалізовано)."""
    if lex_trace.status is not None:
        await _clear_matching_slot(redis, channel_id, lex_trace.location)
        return lex_trace

    if lex_trace.level is not None:
        await _write_explicit(redis, channel_id, lex_trace, source_message_id)
        return lex_trace

    slots = await _active_slots(redis, channel_id)
    if not slots:
        return lex_trace

    if len(slots) == 1:
        slot_idx, data = slots[0]
        location = lex_trace.location or data.get("location")
        await _set_slot(redis, channel_id, slot_idx, {
            "level": data["level"],
            "location": location,
            "source_message_id": data["source_message_id"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        level_evidence = (
            f'успадковано рівень "{data["level"]}" від активної цілі каналу '
            f'(джерело — повідомлення #{data["source_message_id"]})'
        )
        location_evidence = lex_trace.location_evidence or (
            f'успадковано разом із рівнем від повідомлення #{data["source_message_id"]}' if location else None
        )
        return DecisionTrace(
            layer="channel_state",
            level=data["level"], level_evidence=level_evidence,
            status=lex_trace.status, status_evidence=lex_trace.status_evidence,
            location=location, location_evidence=location_evidence,
        )

    slot_idx, data = max(slots, key=lambda x: x[1]["updated_at"])
    level_evidence = (
        f'{len(slots)} активні цілі в каналі одночасно — обрано найновішу '
        f'(рівень "{data["level"]}", повідомлення #{data["source_message_id"]}); '
        f'точне зіставлення чекає LLM tie-break (Етап 4, ще не реалізовано)'
    )
    return DecisionTrace(
        layer="channel_state_ambiguous",
        level=data["level"], level_evidence=level_evidence,
        status=lex_trace.status, status_evidence=lex_trace.status_evidence,
        location=lex_trace.location or data.get("location"), location_evidence=lex_trace.location_evidence,
    )


async def all_active_slots(redis) -> list[dict]:
    """Усі активні записи по всіх каналах — для адмін-панелі /channels/state."""
    result = []
    async for key in redis.scan_iter(match="channel_state:*"):
        raw = await redis.get(key)
        if not raw:
            continue
        ttl = await redis.ttl(key)
        data = json.loads(raw)
        _, channel_id, slot = key.split(":")
        result.append({"channel_id": channel_id, "slot": int(slot), "ttl": ttl, **data})
    return result
