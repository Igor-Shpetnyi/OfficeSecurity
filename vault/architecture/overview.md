---
title: Архітектура — огляд
updated: 2026-07-21
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

## Реалізовано (Етап 0/1, інжест каналів + адмін-панель)

- `app/userbot/` — Telethon-клієнт: приєднання до каналів + title/аватарка/колір (`channels.py`), запис вхідних повідомлень у `events_log` з дедупом no-op edit-ів і `reply_to_message_id` (`handlers.py`), головний цикл (`main.py`)
- `app/admin/` — FastAPI: CRUD каналів (`routers/channels.py`), стрічка подій з live-refresh (`routers/events.py`), дашборд (`routers/dashboard.py`), Basic Auth (`common/auth.py`)
- Синхронізація списку каналів між панеллю і юзерботом — Redis pub/sub + periodic poll, див. [ADR-0004](../decisions/0004-redis-pubsub-channel-sync.md)
- Схема БД: `app/db/schema.sql` (`monitoring_channels` — тепер з `title`/`avatar_color`; `events_log` — тепер з `reply_to_message_id`)
- `regex_matched_level`/`llm_response` в `events_log` поки NULL — RegEx-двигун і LLM-шар ще не реалізовані (наступні етапи)

## Адмін-панель: збагачення даних каналу/подій

Три спільні модулі в `app/common/`, що комбінують сирі дані з `events_log`/`monitoring_channels` у готове для UI:

- `channels_query.py` / `events_query.py` — єдина точка завантаження списків каналів і подій, використовується і `routers/dashboard.py`, і `routers/channels.py`/`routers/events.py` (уникає дублювання SQL)
- `avatars.py` — `avatar_url()` (шлях до завантаженого фото, `None` якщо немає), `extract_avg_color()`/`fallback_color()` — див. [ADR-0009](../decisions/0009-avatar-color-hue-only.md)
- `channel_display.py` — ініціали каналу з назви (2 літери, фільтр не-alnum символів на випадок емодзі на початку назви)
- `formatting.py` — `relative_time()` ("5 хв тому"), `to_kyiv()` — див. [ADR-0008](../decisions/0008-kyiv-time-python-side-conversion.md)

**Стрічка подій** (`events_query.py::load_recent_events`) для кожного `(source_channel, telegram_message_id)` показує лише останню версію тексту (`DISTINCT ON ... ORDER BY detected_at DESC`), з:
- **Історією редагувань** — усі версії того самого повідомлення, зібрані `json_agg(...) OVER (PARTITION BY ...)` (window function; `ORDER BY` всередині такого `json_agg` Postgres не підтримує — сортування перенесено в Python)
- **Ланцюжком reply** — не лише безпосередній "батько", а весь ланцюжок вгору по `reply_to_message_id` (`_load_reply_chains`, батчевий BFS: один SQL-запит на рівень глибини для ВСІХ подій одразу, а не запит на кожен крок кожної події; захист від циклів — `_MAX_CHAIN_DEPTH=12`)
- Повний текст завжди, без обрізання/розгортання (раніше — `<details>` для текстів довших за 400 символів, прибрано за проханням користувача)
- **Diff між версіями** — word-level `difflib.SequenceMatcher` між кожною послідовною версією тексту (додане/видалене — `<ins>`/`<del>`, стилізовано токенами `--positive`/`--negative`), і в поточному тексті картки (проти попередньої версії), і в кожному пункті "Історії редагувань". Бейдж "ред. ×N" показує `version_count - 1` (реальну кількість редагувань, не кількість версій у БД — раніше завищував на 1)

**Live-refresh** (`static/js/live-refresh.js`) — `fetch()` кожні 5с підміняє `#events-content`/`#dashboard-content` HTML-фрагментом. Зберігає стан відкритих `<details data-key="...">` (довгий текст раніше, історія редагувань, ланцюжок reply) через заміну — інакше будь-яке розгорнуте користувачем `<details>` миттєво згорталось би на наступному циклі оновлення.

**Cache-busting статики** — `app/config.py::STATIC_VERSION` (timestamp старту процесу) додається як `?v=` до посилань на CSS/JS у `base.html`; без цього браузер тримав застарілий `theme.css` навіть після редагування файлу на диску.

## Адаптивний дизайн (dashboard-grid)

Дашборд — одна CSS Grid-сітка на 3 колонки (`.dashboard-grid`, не два окремі grid з різними пропорціями), картка "Останні події" — `grid-column: span 2`, "Канали" — `span 1`: гарантує пікселем точний збіг меж карток другого ряду з першим (два окремі grid з `2fr 1fr` не давали точного збігу). Сайдбар — off-canvas на `<=768px` (`sidebar.js` + CSS `transform`), таблиці обгорнуті в `.table-scroll` (класична пастка CSS Grid — `min-width: auto` за замовчуванням не дає елементу стиснутись нижче вмісту, виправлено `.grid > * { min-width: 0 }`).

## Модель прослуховування каналів

Транспорт — MTProto (власний бінарний протокол Telegram) поверх постійного TCP-з'єднання, не веб-сокет-стандарт, але той самий push-принцип: сервер сам надсилає події, клієнт не полить.

**Одне з'єднання на весь акаунт, не одне на канал.** Одна `TelegramClient`-сесія отримує єдиний мультиплексований потік Update-подій з усіх каналів, де акаунт є учасником. Фільтрація `e.chat_id in active_ids` — клієнтська (в `app/userbot/handlers.py`): Telegram і так шле апдейти з усіх каналів-учасників, ми просто ігноруємо ті, що не в `active_ids`.

**Реальні вузькі місця при масштабуванні на багато каналів — не прослуховування:**
1. Приєднання (join) лімітоване `FloodWaitError`, тому черга з затримкою (ADR-0004) — саме слухання ліміту не має
2. `TelegramClient(sequential_updates=True)` — update'и обробляються по черзі, не паралельними asyncio-тасками. Раніше (за замовчуванням Telethon) паралельна обробка ламала дедуп-перевірку no-op edit-ів через check-then-act race — див. [ADR-0010](../decisions/0010-sequential-updates-race-fix.md). Компроміс: пропускна здатність обмежена одним update за раз, прийнятно для очікуваних обсягів (кілька повідомлень/сек з 9 каналів)
3. `asyncpg`-пул (`min_size=1, max_size=10`) — з запасом для реалістичних обсягів

## Повне видалення каналів (не лише "вимкнути")

`monitoring_channels.pending_delete BOOLEAN` — `POST /channels/{id}/delete` лише позначає рядок (`is_active=false, pending_delete=true`), не видаляє одразу. Нова `sync_pending_deletes()` (`app/userbot/channels.py`) обробляє чергу: якщо канал ще `join_status='joined'` — спершу виходить з нього (`LeaveChannelRequest`, той самий принцип, що й `sync_pending_leaves`), потім видаляє рядок незалежно від результату виходу. `sync_pending_leaves()` виключає `pending_delete=TRUE` зі свого запиту, щоб два обробники не змагались за один рядок. `events_log` не чіпається — не має FK на `monitoring_channels` (`source_channel` — текстове поле з marked ID), історія подій лишається і після видалення картки каналу.
