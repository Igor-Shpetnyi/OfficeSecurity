# Безпека Офісу — Суми

Telegram-система ситуаційної обізнаності: моніторинг публічних Telegram-каналів Сумщини, автоматичне визначення рівня загрози та сповіщення співробітників офісу з мінімальною затримкою.

Повне технічне завдання — [`TZ_bezpeka_ofisu_sumy.md`](TZ_bezpeka_ofisu_sumy.md). Хід розробки, архітектурні рішення та їхнє обґрунтування — у [`vault/`](vault/INDEX.md) (див. [`CLAUDE.md`](CLAUDE.md) щодо принципів роботи з ним).

## Поточний стан (Етап 0/1 з 6 за ТЗ)

Реалізовано інжест повідомлень з моніторинг-каналів і адмін-панель керування ними. **RegEx-двигун, LLM-шар і каскадна стейт-машина (Етапи 1-3) ще не реалізовані** — це наступний крок.

- **Юзербот** (Telethon) — слухає моніторинг-канали одним MTProto-з'єднанням, пише сирі повідомлення в `events_log`, підтягує назву/аватарку/колір каналу, відстежує reply-ланцюжки та історію редагувань
- **Адмін-панель** (FastAPI) — Дашборд, керування каналами (додати/вимкнути), стрічка подій із live-refresh, dark/light тема, адаптивний layout
- Синхронізація списку каналів між панеллю і юзерботом — Redis pub/sub + periodic poll (запобіжна сітка)

Детальніше — [`vault/architecture/overview.md`](vault/architecture/overview.md).

## Стек

| Компонент | Технологія |
|---|---|
| Юзербот | Python 3.12+, [Telethon](https://docs.telethon.dev/) |
| Адмін-панель | FastAPI, Jinja2, ванільний JS (без фронтенд-фреймворків) |
| БД | PostgreSQL |
| Черга/pub-sub | Redis |
| Обробка зображень | Pillow (середній колір аватарки каналу) |

## Структура

```
app/
  admin/          — FastAPI адмін-панель (routers/, templates/, static/)
  userbot/         — Telethon-клієнт: приєднання до каналів, обробка подій
  common/          — спільна логіка: БД-запити, часові пояси, аватарки/кольори
  db/              — pool.py, schema.sql
  config.py        — читання .env, налаштування
scripts/           — одноразові утиліти (генерація сесії, інспекція каналів)
vault/             — зовнішня пам'ять проєкту: архітектура, рішення (ADR), журнал, backlog
TZ_bezpeka_ofisu_sumy.md — технічне завдання
docker-compose.yml — Postgres + Redis для локальної розробки
```

## Запуск (локальна розробка)

### 1. Інфраструктура

```bash
docker compose up -d
```

Піднімає Postgres і Redis; схема (`app/db/schema.sql`) застосовується автоматично при першому старті.

### 2. Залежності

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt   # Windows
# .venv/bin/python -m pip install -r requirements.txt         # Linux/macOS
```

### 3. Конфігурація

Скопіюйте `.env.example` → `.env` і заповніть:

```bash
cp .env.example .env
```

- `DATABASE_URL` / `REDIS_URL` — уже відповідають `docker-compose.yml`, змінювати не треба
- `ADMIN_BASIC_AUTH_USER` / `ADMIN_BASIC_AUTH_PASSWORD` — логін для адмін-панелі
- `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` — зареєструвати застосунок на [my.telegram.org](https://my.telegram.org)
- `TELEGRAM_SESSION_STRING` — генерується окремо (крок 4), вимагає інтерактивного логіну особистим Telegram-акаунтом

### 4. Сесія юзербота

```bash
.venv\Scripts\python.exe scripts\generate_session.py
```

Запит номера телефону й коду підтвердження — виконується один раз, вручну, в інтерактивному терміналі (не автоматизується навмисно). Виведений рядок вставити в `TELEGRAM_SESSION_STRING` у `.env`.

### 5. Запуск

```bash
# адмін-панель
.venv\Scripts\python.exe -m uvicorn app.admin.main:app --reload --port 8010

# юзербот (окремий процес)
.venv\Scripts\python.exe -m app.userbot.main
```

Адмін-панель — http://localhost:8010/dashboard (Basic Auth з `.env`).

## Допоміжні скрипти

Усі — в [`scripts/`](scripts/), одноразові/діагностичні, не частина основного застосунку:

| Скрипт | Призначення |
|---|---|
| `generate_session.py` | Генерація `TELEGRAM_SESSION_STRING` |
| `list_channels.py` | Список каналів, на які вже підписаний акаунт юзербота |
| `inspect_channels.py` | Деталі конкретних каналів (тип, кількість учасників, опис) перед додаванням |
| `create_test_channel.py`, `set_test_channel_username.py`, `send_test_event.py` | Створення й наповнення тестового каналу для перевірки пайплайну подій |

## Документація

- [`vault/INDEX.md`](vault/INDEX.md) — точка входу в архітектуру й історію рішень проєкту
- [`vault/decisions/`](vault/decisions/) — ADR: чому обрано саме такі рішення (одне рішення — один файл)
- [`vault/progress/`](vault/progress/) — хронологічний журнал сесій розробки
- [`vault/backlog/open-questions.md`](vault/backlog/open-questions.md) — відкриті питання й TODO
