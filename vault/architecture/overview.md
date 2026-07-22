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
- `regex_matched_level` — реалізовано, див. "Рівень 1 конвеєра виявлення" нижче. `llm_response` поки NULL — LLM-шар (Рівень 3, ADR-0012) ще не реалізований

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

## Рівень 1 конвеєра виявлення (лексика + газетир)

Перший з трьох рівнів з [ADR-0012](../decisions/0012-three-layer-detection-not-regex-then-llm.md) — реалізовано й працює на живому потоці з 2026-07-21. Деталі й обґрунтування — [`TZ_konveyer_analizu_zagroz.md`](../../TZ_konveyer_analizu_zagroz.md), тут лише карта коду.

- `app/common/normalize.py` — lowercase + згортання пробілів, без вирізання рекламних футерів (не заважають matching)
- `app/common/lexicon.py` — читає `app/common/data/triggers.yaml` (словник тригерів по рівнях + окремо status-маркери) і `toponyms.yaml` (газетир, canonical + відмінкові форми, fuzzy-fallback через `difflib` для одруківок), кешує через `lru_cache`. `match_level()`/`match_status()` — незалежні примітиви; `resolve_level()` — комбінатор, що гасить рівень, якщо в тому самому повідомленні є status-маркер (див. ADR-0012, "Уточнення 2026-07-21"). `match_locations()`/`_match_locations_explained()` повертають **усі** топоніми газетиру, знайдені в повідомленні (кортеж, не одне значення) — реальні повідомлення часто називають маршрут через кілька топонімів одним реченням, знайдено на живих даних 2026-07-21 (ADR-0012)
- `app/common/data/streets_sumy.yaml` — окремий газетир вулиць Сум (648 записів, офіційний реєстр міськради), навмисно **не підключений** до `match_locations()` — колізії з районними топонімами (Білопільська/Охтирська/Хотінська тощо) і звичайні слова у назвах вулиць вимагають окремої логіки матчингу (лише в парі з "вул."/"вулиця"), не голого підрядка
- `events_log`: `regex_matched_level`, `matched_status`, `matched_locations TEXT[]` (масив — не одна колонка, див. вище), `resolved_by` (`'lexicon'` | `'channel_state'` | `'channel_state_ambiguous'` — див. Рівень 2 нижче) — пишуться в `app/userbot/handlers.py::_store_event`
- UI: `_level_badge.html` (Jinja-макрос) — бейджі рівня/локації/статусу в `/events` і на дашборді; окрема сторінка `/lexicon` (`app/admin/routers/lexicon.py`) — візуалізація обох словників + газетиру вулиць з поясненням призначення й статусу (чернетка)
- **`decision_trace`** ([ADR-0013](../decisions/0013-decision-trace-every-layer.md)) — `lexicon.analyze()` повертає не лише рівень/статус/локацію, а й evidence-рядки людською мовою (яке слово/форма спрацювали, чи рівень приглушено). Зберігається в `events_log.decision_trace JSONB`, показується розгортним блоком "Чому?" (`decision_explanation()` в `_level_badge.html`) під бейджами в `/events`. Спільна форма для всіх рівнів конвеєра — Рівень 2/3 додадуть власний `layer`, не окрему структуру

**Готча: два процеси, один кеш кожен.** `app/common/data/*.yaml` читається через `lru_cache` і в юзерботі, і в адмін-панелі — це два окремі Python-процеси з окремою памʼяттю. Правка `triggers.yaml`/`toponyms.yaml` на диску не підхоплюється жодним із них, поки процес не перезапущений: **обидва**, не лише той, що щойно змінювали. Забутий перезапуск адмін-панелі після зміни словника — вже стався 2026-07-21 (панель `/lexicon` показувала старий розподіл рівнів, хоча юзербот уже писав за новим).

## Рівень 2 конвеєра виявлення (стан активної цілі на канал)

Другий з трьох рівнів з [ADR-0012](../decisions/0012-three-layer-detection-not-regex-then-llm.md) — реалізовано й підключено з 2026-07-21. Розв'язує еліптичні продовження без тригер-слова ("Впала", "Далі Х"), знайдені в дослідженні `TZ_konveyer_analizu_zagroz.md`.

- `app/common/channel_state.py::resolve()` — єдина точка входу, приймає `DecisionTrace` від Рівня 1 (`lexicon.analyze()`) і `source_message_id`:
  - status-маркер у повідомленні (відбій/знищено/...) → закриває відповідний активний слот (`_clear_matching_slot`), НЕ успадковує рівень — інакше "Відбій..." показало б рівень активної цілі (той самий клас бага, що вже виправлений на Рівні 1 через `resolve_level()`, знайдено повторно власним ізольованим тестом при розробці Рівня 2, до підключення в handlers.py)
  - Рівень 1 щось явно зловив → записує/оновлює слот (`_write_explicit`), повертає `lex_trace` як є
  - Немає активних слотів → лишається нерозв'язаним, чесно
  - Рівно 1 активний слот → успадковує його рівень, оновлює локації, якщо в повідомленні з'явились нові топоніми; `layer='channel_state'`
  - 2-3 одночасних слоти → неоднозначно, поки що береться найновіший; `layer='channel_state_ambiguous'` (точне зіставлення — LLM tie-break, Етап 4, ще не реалізовано)
- Redis-модель: `channel_state:{channel_id}:{slot}` (slot 0-2, до 3 одночасних цілей на канал), TTL 1200с (та сама константа "локаційно втраченої цілі", ТЗ §10), sliding — оновлюється при кожному успадкуванні. `location` у слоті — список (не одне значення, той самий принцип, що `matched_locations` вище)
- Вибір слота при явному сигналі: спершу існуючий слот з бодай ОДНІЄЮ спільною локацією (та сама ціль, що розвивається — повідомлення можуть називати кілька топонімів), інакше вільний, інакше витісняється найстаріший
- `app/userbot/handlers.py::_store_event` тепер приймає `redis_client` (прокинутий з `main.py`), викликає `channel_state.resolve()` замість голого `lexicon.analyze()`
- UI: `/channels/state` (`app/admin/routers/channel_state.py` + `channel_state.html`/`_channel_state_content.html`) — жива таблиця активних слотів по каналах (live-refresh, той самий патерн, що `/events`), пряме читання Redis (`SCAN`) + join з `monitoring_channels`. Бейджі подій розрізняють походження — `🔗 успадковано` / `❓ неоднозначно` (`origin_map` в `_level_badge.html`, закладений заздалегідь ще на Рівні 1)

## Етап 3 конвеєра виявлення (видимість нерозв'язаного)

Не рівень конвеєра (не додає нового `resolved_by`), а вимірювальна контрольна точка перед рішенням про Рівень 3/LLM — реалізовано 2026-07-22, план з `TZ_konveyer_analizu_zagroz.md`.

- `app/common/events_query.py::load_recent_events(pool, limit, unresolved_only=False)` — той самий `_QUERY_TEMPLATE`, підставляється `WHERE t.resolved_by IS NULL AND t.regex_matched_level IS NULL` для фільтра; `count_unresolved(pool)` — той самий DISTINCT ON (остання версія кожного повідомлення вирішує стан), без `LIMIT`, для лічильника на вкладці
- `app/admin/routers/events.py` — query-параметр `?filter=unresolved` на `/events/recent` і `/events/recent/fragment`; лічильник (`count_unresolved`) рахується лише на повному завантаженні сторінки, не на кожному 5с-циклі live-refresh — щоб не тримати зайвий запит на гарячому шляху
- UI: `.tab-switch`/`.tab-switch-item` (`theme.css`) — сегментований перемикач "Усі" / "Нерозв'язано (N)" над стрічкою подій, звичайні `<a href>` (повне перезавантаження сторінки, без нового JS — фільтр живе в URL)

**Перший вимір на живих даних (2026-07-22):** 236 нерозв'язаних повідомлень всього в `events_log` на момент реалізації — переважно рекламні/побутові пости каналів без жодного тригер-слова (напр. вакансії, фото без підпису). Це число — вхід для майбутнього рішення про бюджет Етапу 4 (LLM).

## Повне видалення каналів (не лише "вимкнути")

`monitoring_channels.pending_delete BOOLEAN` — `POST /channels/{id}/delete` лише позначає рядок (`is_active=false, pending_delete=true`), не видаляє одразу. Нова `sync_pending_deletes()` (`app/userbot/channels.py`) обробляє чергу: якщо канал ще `join_status='joined'` — спершу виходить з нього (`LeaveChannelRequest`, той самий принцип, що й `sync_pending_leaves`), потім видаляє рядок незалежно від результату виходу. `sync_pending_leaves()` виключає `pending_delete=TRUE` зі свого запиту, щоб два обробники не змагались за один рядок. `events_log` не чіпається — не має FK на `monitoring_channels` (`source_channel` — текстове поле з marked ID), історія подій лишається і після видалення картки каналу.
