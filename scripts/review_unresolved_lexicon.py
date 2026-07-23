"""Періодичний інспекційний скрипт: дамп "нерозв'язаного" кошика Рівня 1
(app/common/lexicon.py) для ручного перегляду — той самий метод, яким
знайдено "балістичн"/"італмас"/"оптиці" тощо (сесії 2026-07-22, 2026-07-23).
Read-only, нічого не змінює. Обґрунтування регулярності — ADR-0014.

Категорії (та сама логіка, що app/common/events_query.py::count_unresolved,
дедуплікація до останньої версії кожного повідомлення):
  - без тексту: медіа без підпису — нема що ловити, не показуємо
  - локація без рівня: газетир щось знайшов, але жодного тригер-слова —
    найвищий пріоритет перегляду, саме тут знайшлись "шахів"/"кружля"/"оптиці"
  - взагалі нічого: ні рівня, ні локації, ні статусу — переважно шум,
    але перевіряти варто (звідси знайдено "балістичн"/"впердол"/"влуп")

Використання: python scripts/review_unresolved_lexicon.py > review.txt
(перенаправлення в файл — Windows-консоль (cp1251) падає на кирилиці/емодзі)
"""

import asyncio
import os
import sys

import asyncpg
from dotenv import load_dotenv

load_dotenv()

# Консоль Windows (cp1251) падає на кирилиці/емодзі — примусово UTF-8 для
# stdout незалежно від того, з якого середовища запущено скрипт.
sys.stdout.reconfigure(encoding="utf-8")

_QUERY = (
    "SELECT t.id, t.source_channel, t.matched_locations, t.raw_text FROM ("
    "  SELECT DISTINCT ON (e.source_channel, e.telegram_message_id) "
    "    e.id, e.source_channel, e.raw_text, e.matched_locations, "
    "    e.regex_matched_level, e.matched_status "
    "  FROM events_log e "
    "  ORDER BY e.source_channel, e.telegram_message_id, e.detected_at DESC"
    ") t "
    "WHERE t.regex_matched_level IS NULL AND t.matched_status IS NULL "
    "ORDER BY t.id"
)


async def main() -> None:
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)
    async with pool.acquire() as conn:
        rows = await conn.fetch(_QUERY)

    no_text, with_location, nothing = [], [], []
    for row in rows:
        text = (row["raw_text"] or "").strip()
        if not text:
            no_text.append(row)
        elif row["matched_locations"]:
            with_location.append(row)
        else:
            nothing.append(row)

    print(f"# Нерозв'язано всього: {len(rows)}")
    print(f"# Без тексту (медіа без підпису): {len(no_text)} — пропущено, нема що ловити")
    print(f"# Локація без рівня: {len(with_location)} — ПЕРЕГЛЯНУТИ ПЕРШИМИ")
    print(f"# Взагалі нічого не зловлено: {len(nothing)}")
    print()

    print("=" * 70)
    print(f"ЛОКАЦІЯ БЕЗ РІВНЯ ({len(with_location)})")
    print("=" * 70)
    for row in with_location:
        loc = ",".join(row["matched_locations"])
        text = (row["raw_text"] or "").replace("\n", " ")[:200]
        print(f"{row['id']}|{row['source_channel']}|{loc}|{text}")

    print()
    print("=" * 70)
    print(f"ВЗАГАЛІ НІЧОГО НЕ ЗЛОВЛЕНО ({len(nothing)})")
    print("=" * 70)
    for row in nothing:
        text = (row["raw_text"] or "").replace("\n", " ")[:200]
        print(f"{row['id']}|{row['source_channel']}|{text}")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
