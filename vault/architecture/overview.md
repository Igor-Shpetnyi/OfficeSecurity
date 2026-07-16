---
title: Архітектура — огляд
updated: 2026-07-16
status: active
source: ../../TZ_bezpeka_ofisu_sumy.md#2-архітектура
---

# Архітектура — огляд

Ядро системи: RegEx-двигун і LLM працюють **паралельно**, не послідовно. RegEx ніколи не чекає LLM.

```
Telegram-канали → Userbot (Telethon, event handler)
    ├─ RegEx/keyword engine (0-100мс) → сирий сигнал → Notification Service → чат
    └─ Redis-черга → LLM Worker (async) → уточнення рівня → Notification Service
                            │
                            ▼
                     PostgreSQL (стан, лог, RLHF-датасет)
                            │
                            ▼
                     State Machine (каскадні таймери, TTL)
                            │
                            ▼
                     Admin Panel (FastAPI)
```

Компоненти й деталі кожного — див. ТЗ, розділи 2-4. Цей файл — навігаційна карта, не дублікат: при зміні реальної архітектури під час розробки править тут, а не перечитуй ТЗ заново.

## Реалізовано (Етап 0/1, інжест каналів)

- `app/userbot/` — Telethon-клієнт: приєднання до каналів (`channels.py`), запис вхідних повідомлень у `events_log` (`handlers.py`), головний цикл (`main.py`)
- `app/admin/` — FastAPI: CRUD каналів (`routers/channels.py`), стрічка сирих подій (`routers/events.py`), Basic Auth (`common/auth.py`)
- Синхронізація списку каналів між панеллю і юзерботом — Redis pub/sub + periodic poll, див. [ADR-0004](../decisions/0004-redis-pubsub-channel-sync.md)
- Схема БД: `app/db/schema.sql` (`monitoring_channels`, `events_log`)
- `regex_matched_level`/`llm_response` в `events_log` поки NULL — RegEx-двигун і LLM-шар ще не реалізовані (наступні етапи)

## Модель прослуховування каналів

Транспорт — MTProto (власний бінарний протокол Telegram) поверх постійного TCP-з'єднання, не веб-сокет-стандарт, але той самий push-принцип: сервер сам надсилає події, клієнт не полить.

**Одне з'єднання на весь акаунт, не одне на канал.** Одна `TelegramClient`-сесія отримує єдиний мультиплексований потік Update-подій з усіх каналів, де акаунт є учасником. Фільтрація `e.chat_id in active_ids` — клієнтська (в `app/userbot/handlers.py`): Telegram і так шле апдейти з усіх каналів-учасників, ми просто ігноруємо ті, що не в `active_ids`.

**Реальні вузькі місця при масштабуванні на багато каналів — не прослуховування:**
1. Приєднання (join) лімітоване `FloodWaitError`, тому черга з затримкою (ADR-0004) — саме слухання ліміту не має
2. Конкурентні asyncio-хендлери на швидкому потоці подій не гарантують порядок запису в `events_log` (див. backlog)
3. `asyncpg`-пул (`min_size=1, max_size=10`) — з запасом для реалістичних обсягів
