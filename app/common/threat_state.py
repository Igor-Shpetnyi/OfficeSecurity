"""Дедуплікація + каскадна стейт-машина (ТЗ §9+§10), план "Сповіщення"
2026-07-23. Кілька одночасних відкритих цілей за локацією (не один
глобальний рядок, не один на канал) — той самий принцип, що вже двічі
підтверджений у цьому проєкті: Рівень 2 (app/common/channel_state.py, до 3
слотів на канал) і DecisionTrace.location (кортеж, не одне значення).
Матчинг нового сигналу до відкритого рядка threat_state — перетин множин
локацій, як channel_state._write_explicit, лише міжканально.

Дві половини:
- record_signal() — подієва, викликається з app/userbot/handlers.py після
  channel_state.resolve() на кожному повідомленні з рівнем/статусом.
- cascade_tick() — періодична (app/admin/main.py, фоновий asyncio-тік),
  застосовує заплановані зниження й "локаційно втрачену ціль" (20 хв тиші).

Обидві пишуть у threat_notifications (append-only стрічка "Сповіщення")
лише на РЕАЛЬНІ переходи (нова ціль/ескалація/зниження/відбій) — мовчазні
підтвердження того самого рівня НЕ породжують запис, інакше стрічка
захлинеться тим самим шумом, що дедуплікація мала прибрати."""

import hashlib
from datetime import datetime, timedelta, timezone

from app.common import lexicon, llm

_LEVEL_RANK = {"yellow": 1, "orange": 2, "red": 3}
_CASCADE_NEXT = {"red": "orange", "orange": "yellow", "yellow": "green"}
# Затримка до НАСТУПНОГО кроку після щойного переходу — не дельта від "зараз"
# щоразу, а фіксовані інтервали ТЗ §10 (T+1хв/T+6хв/T+21хв від моменту
# підтвердженої нейтралізації): red→orange за +1хв, тоді orange→yellow за
# ще +5хв (разом T+6), тоді yellow→green за ще +15хв (разом T+21).
_FIRST_STEP_DELAY = timedelta(minutes=1)
_CASCADE_STEP_DELTA = {"orange": timedelta(minutes=5), "yellow": timedelta(minutes=15)}
_DEDUP_TTL_SECONDS = 30
# Та сама константа, що TTL слота Рівня 2 (channel_state._TTL_SECONDS) —
# не нова довільна цифра, той самий сенс "ціль втрачена без підтвердження".
_LOCATIONALLY_LOST_SECONDS = 1200


def _combine_evidence(level_evidence: str | None, direction_evidence: str | None) -> str | None:
    """Ціль (level_evidence) + напрямок (direction_evidence) одним рядком —
    той самий шлях, що вже threat_type_evidence, до llm.py й у стаб-текст
    (_stub_alert_text), без нових полів/колонок (запит користувача 2026-07-24)."""
    if not direction_evidence:
        return level_evidence
    if not level_evidence:
        return f"напрямок: {direction_evidence}"
    return f"{level_evidence}; напрямок: {direction_evidence}"


def _dedup_key(normalized_text: str, level: str, locations: tuple[str, ...]) -> str:
    payload = normalized_text + "|" + level + "|" + ",".join(sorted(locations))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"dedup:{digest}"


def _find_open_row_for_level(rows, locations: tuple[str, ...], source_channel: str):
    if locations:
        wanted = set(locations)
        for row in rows:
            if wanted & set(row["location"] or ()):
                return row
        return None
    for row in rows:
        if source_channel in (row["contributing_channels"] or ()):
            return row
    return None


def _find_open_row_for_status(rows, locations: tuple[str, ...]):
    if locations:
        wanted = set(locations)
        for row in rows:
            if wanted & set(row["location"] or ()):
                return row
    if len(rows) == 1:
        return rows[0]
    return None


async def _write_notification(
    conn, state_row, transition_type: str, level: str, location: tuple[str, ...],
    confirmation_count: int, contributing_channels: list[str], source_event_log_id: int | None,
    threat_type_evidence: str | None, contributing_event_ids: list[int],
) -> None:
    # threat_type_evidence передається окремим параметром, а не читається з
    # state_row — при ескалації state_row усе ще старий знімок ДО UPDATE
    # (перевірено власним ізольованим тестом: без цього текст сповіщення
    # показував evidence СТАРОГО рівня, не того слова, що спричинило ескалацію).
    alert = await llm.compose_alert_text(
        level=level,
        location=tuple(location),
        threat_type_evidence=threat_type_evidence,
        transition_type=transition_type,
        confirmation_count=confirmation_count,
        contributing_channels=tuple(contributing_channels),
    )
    await conn.execute(
        "INSERT INTO threat_notifications "
        "(threat_state_id, transition_type, level, location, composed_text, composed_by, "
        "confirmation_count, contributing_channels, source_event_log_id, contributing_event_ids) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
        state_row["id"], transition_type, level, list(location), alert.text,
        "template_stub" if alert.is_stub else "llm",
        confirmation_count, contributing_channels, source_event_log_id, contributing_event_ids,
    )


async def record_signal(
    pool, redis, trace, source_channel: str, event_log_id: int, normalized_text: str
) -> None:
    """Викликається з app/userbot/handlers.py::_store_event, одразу після
    channel_state.resolve() — trace тут уже після Рівня 1+2 (може мати
    рівень, статус, локацію — або нічого, тоді сюди взагалі не заходимо)."""
    if trace.status is not None:
        await _record_status(pool, trace, source_channel, event_log_id)
        return
    if trace.level is not None:
        # Гео-фільтр релевантності для Сум (запит користувача 2026-07-24):
        # локації лише tier=source (Крим/Бєлгород/Брянськ/Курськ/Харківщина/
        # Чернігівщина — джерела загрози, не цілі) без фрази напрямку в
        # тексті — далеко, можна не повідомляти. Статус-сигнали (_record_status)
        # гейта не потребують — торкаються лише вже відкритих рядків, які
        # пройшли цей гейт при створенні.
        if not lexicon.is_geo_relevant(trace.location, trace.direction_evidence):
            return
        await _record_level(pool, redis, trace, source_channel, event_log_id, normalized_text)


async def _record_status(pool, trace, source_channel: str, event_log_id: int) -> None:
    async with pool.acquire() as conn, conn.transaction():
        rows = await conn.fetch("SELECT * FROM threat_state WHERE status = 'open' FOR UPDATE")
        row = _find_open_row_for_status(rows, trace.location)
        if row is None:
            return

        confirming = list(row["status_confirming_channels"] or [])
        if source_channel not in confirming:
            confirming.append(source_channel)
        event_ids = list(row["contributing_event_ids"] or [])
        event_ids.append(event_log_id)

        # ТЗ §9: 2+ РІЗНИХ джерела підтвердження — лише тоді запускаємо
        # каскад (ТЗ §10). Одне джерело саме по собі не гасить ціль
        # негайно — 20-хвилинний "локаційно втрачена" фолбек у cascade_tick
        # все одно рано чи пізно знизить рівень, навіть без другого підтвердження.
        if len(confirming) >= 2 and row["downgrade_scheduled_at"] is None:
            scheduled_at = datetime.now(timezone.utc) + _FIRST_STEP_DELAY
            await conn.execute(
                "UPDATE threat_state SET status_confirming_channels = $1, downgrade_scheduled_at = $2, "
                "contributing_event_ids = $3 WHERE id = $4",
                confirming, scheduled_at, event_ids, row["id"],
            )
        else:
            await conn.execute(
                "UPDATE threat_state SET status_confirming_channels = $1, contributing_event_ids = $2 "
                "WHERE id = $3",
                confirming, event_ids, row["id"],
            )


async def _record_level(pool, redis, trace, source_channel: str, event_log_id: int, normalized_text: str) -> None:
    dedup_key = _dedup_key(normalized_text, trace.level, trace.location)
    # nx=True: ключ ставиться, лише якщо його ще нема — set() повертає
    # falsy, якщо ключ уже існував (справжній дубль за останні 30с).
    is_dup = not await redis.set(dedup_key, "1", ex=_DEDUP_TTL_SECONDS, nx=True)

    evidence = _combine_evidence(trace.level_evidence, trace.direction_evidence)

    async with pool.acquire() as conn, conn.transaction():
        rows = await conn.fetch("SELECT * FROM threat_state WHERE status = 'open' FOR UPDATE")
        row = _find_open_row_for_level(rows, trace.location, source_channel)

        if row is None:
            new_row = await conn.fetchrow(
                "INSERT INTO threat_state "
                "(current_level, location, threat_type_evidence, contributing_channels, "
                "origin_event_log_id, contributing_event_ids) "
                "VALUES ($1, $2, $3, $4, $5, $6) RETURNING *",
                trace.level, list(trace.location), evidence, [source_channel], event_log_id,
                [event_log_id],
            )
            if not is_dup:
                await _write_notification(
                    conn, new_row, "new", trace.level, trace.location, 1, [source_channel], event_log_id,
                    evidence, [event_log_id],
                )
            return

        channels = list(row["contributing_channels"] or [])
        if source_channel not in channels:
            channels.append(source_channel)
        new_count = row["confirmation_count"] + 1
        location = tuple(trace.location) if trace.location else tuple(row["location"] or ())
        event_ids = list(row["contributing_event_ids"] or [])
        event_ids.append(event_log_id)

        if _LEVEL_RANK[trace.level] > _LEVEL_RANK[row["current_level"]]:
            # ТЗ §10 "абсолютне правило переривання" — новий вищий рівень
            # скидає будь-який запланований каскад/неоднозначну "втрату".
            await conn.execute(
                "UPDATE threat_state SET current_level = $1, location = $2, threat_type_evidence = $3, "
                "last_signal_at = now(), downgrade_scheduled_at = NULL, is_locationally_lost = FALSE, "
                "lost_since = NULL, status_confirming_channels = '{}', contributing_channels = $4, "
                "confirmation_count = $5, contributing_event_ids = $6 WHERE id = $7",
                trace.level, list(location), evidence, channels, new_count, event_ids, row["id"],
            )
            if not is_dup:
                await _write_notification(
                    conn, row, "escalated", trace.level, location, new_count, channels, event_log_id,
                    evidence, event_ids,
                )
        else:
            # Мовчазне підтвердження — рівень не змінюється, жодного запису
            # в threat_notifications (інакше кожен збіг каналу+рівня стає
            # окремою карткою в стрічці, саме той шум, що дедуплікація мала прибрати).
            await conn.execute(
                "UPDATE threat_state SET last_signal_at = now(), contributing_channels = $1, "
                "confirmation_count = $2, is_locationally_lost = FALSE, lost_since = NULL, "
                "contributing_event_ids = $3 WHERE id = $4",
                channels, new_count, event_ids, row["id"],
            )


async def _apply_downgrade(conn, row, forced: bool) -> None:
    current = row["current_level"]
    next_level = _CASCADE_NEXT[current]
    channels = list(row["contributing_channels"] or [])

    if next_level == "green":
        await conn.execute(
            "UPDATE threat_state SET current_level = 'green', status = 'closed', "
            "downgrade_scheduled_at = NULL WHERE id = $1",
            row["id"],
        )
        transition_type = "cleared"
    else:
        next_delay = _CASCADE_STEP_DELTA.get(next_level)
        scheduled_at = (datetime.now(timezone.utc) + next_delay) if (next_delay and not forced) else None
        if forced:
            # Примусовий крок через тишу (ТЗ §10 "локаційно втрачена ціль")
            # — не заплановано наступний крок наперед, лишень перезапускаємо
            # 20-хвилинний лічильник тиші для наступного можливого кроку.
            await conn.execute(
                "UPDATE threat_state SET current_level = $1, downgrade_scheduled_at = NULL, "
                "last_signal_at = now() WHERE id = $2",
                next_level, row["id"],
            )
        else:
            await conn.execute(
                "UPDATE threat_state SET current_level = $1, downgrade_scheduled_at = $2 WHERE id = $3",
                next_level, scheduled_at, row["id"],
            )
        transition_type = "downgraded"

    await _write_notification(
        conn, row, transition_type, next_level, tuple(row["location"] or ()),
        row["confirmation_count"], channels, None, row["threat_type_evidence"],
        list(row["contributing_event_ids"] or []),
    )


async def cascade_tick(pool) -> None:
    """Періодичний тік (app/admin/main.py::lifespan, кожні 5-10с) —
    застосовує заплановані каскадні зниження й примусові зниження через
    "локаційно втрачену ціль" (20 хв без жодного сигналу)."""
    async with pool.acquire() as conn, conn.transaction():
        rows = await conn.fetch("SELECT * FROM threat_state WHERE status = 'open' FOR UPDATE")
        now = datetime.now(timezone.utc)
        for row in rows:
            if row["downgrade_scheduled_at"] is not None and now >= row["downgrade_scheduled_at"]:
                await _apply_downgrade(conn, row, forced=False)
            elif row["downgrade_scheduled_at"] is None and (
                now - row["last_signal_at"]
            ).total_seconds() >= _LOCATIONALLY_LOST_SECONDS:
                await conn.execute(
                    "UPDATE threat_state SET is_locationally_lost = TRUE, "
                    "lost_since = COALESCE(lost_since, now()) WHERE id = $1",
                    row["id"],
                )
                await _apply_downgrade(conn, row, forced=True)
