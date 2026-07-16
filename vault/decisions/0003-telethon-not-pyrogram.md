---
title: "ADR-0003: Telethon, не Pyrogram"
updated: 2026-07-16
status: accepted
source: ../../TZ_bezpeka_ofisu_sumy.md#4-технологічний-стек
---

# ADR-0003: Telethon для юзербота

**Рішення:** Telethon замість Pyrogram.

**Чому:** кращий event-based API з коробки саме для моніторингу каналів, детальніша документація по FloodWait/reconnect — критично для вимоги ≥30 днів стабільної сесії без ручного втручання.

**Статус:** accepted.
