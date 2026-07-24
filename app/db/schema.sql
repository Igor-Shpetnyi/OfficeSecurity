-- Етап 0/1: інжест повідомлень з моніторинг-каналів + керування списком каналів
-- events_log — схема з ТЗ, розділ 14 (без змін)

CREATE TABLE IF NOT EXISTS monitoring_channels (
    id SERIAL PRIMARY KEY,
    channel_identifier VARCHAR(255) NOT NULL UNIQUE, -- @username (публічний) або invite-hash (приватний)
    identifier_type VARCHAR(10) NOT NULL DEFAULT 'username', -- 'username' | 'invite'
    telegram_id BIGINT,
    title VARCHAR(255),
    avatar_color VARCHAR(7), -- '#rrggbb', середній колір завантаженої аватарки (app/common/avatars.py)
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    join_status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending | joined | failed | left
    join_error TEXT,
    pending_delete BOOLEAN NOT NULL DEFAULT FALSE, -- позначено на повне видалення з панелі (не лише "вимкнути")
    added_by BIGINT,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_message_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_monitoring_channels_active ON monitoring_channels (is_active);

CREATE TABLE IF NOT EXISTS events_log (
    id SERIAL PRIMARY KEY,
    raw_text TEXT,
    source_channel VARCHAR(100),
    telegram_message_id BIGINT, -- стабільний ID повідомлення в Telegram; той самий для 'new' і наступних 'edit' цього ж поста
    reply_to_message_id BIGINT, -- telegram_message_id повідомлення, на яке відповідають (той самий канал), NULL якщо не reply
    -- Тип вкладення (короткий код: photo | video | gif | sticker | voice | audio
    -- | poll | document | other), NULL якщо без медіа. Людський підпис/іконка —
    -- app/common/media.py, не дублюється тут. Заглушка на місці реального
    -- вкладення — далі шлях до завантаженого файлу піде окремою колонкою,
    -- цей код уже розрізняє тип, готовий під те розширення.
    media_type VARCHAR(20),
    grouped_id BIGINT, -- Telegram album/media-group ID; NULL якщо не частина альбому.
    -- Кілька фото одним постом з одним підписом — Telegram кладе підпис лише
    -- в ОДНЕ повідомлення групи, решта приходять з порожнім текстом (не наш
    -- баг захоплення). Поки що кожне фото — окрема картка в стрічці; grouped_id
    -- зберігається про запас під майбутнє об'єднання альбому в одну картку.
    event_type VARCHAR(10) NOT NULL DEFAULT 'new', -- 'new' | 'edit'
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Рівень 1 конвеєра виявлення (ADR-0012, app/common/lexicon.py):
    -- regex_matched_level — найвищий зловлений рівень загрози (red/orange/yellow),
    -- або успадкований з Рівня 2 (app/common/channel_state.py). matched_status —
    -- маркер зміни стану (відбій/втрата фіксації), окремо від рівня. matched_locations —
    -- МАСИВ канонічних назв топонімів з газетиру (не одна — реальні повідомлення,
    -- особливо "Повітряні Сили", часто називають маршрут через кілька топонімів
    -- одним реченням, знайдено на живих даних 2026-07-21). resolved_by —
    -- 'lexicon' | 'channel_state' | 'channel_state_ambiguous' | 'llm' | NULL
    -- (нічого не зловлено на жодному рівні).
    regex_matched_level VARCHAR(10),
    matched_status VARCHAR(20),
    matched_locations TEXT[],
    resolved_by VARCHAR(30),
    -- ЧЕРЕЗ ЩО ухвалено рішення вище (ADR-0013), не лише саме рішення:
    -- {"layer": "lexicon", "level_evidence": "зловлено слово \"каб\" (red)", ...}.
    -- Рівень, що ухвалив рішення (`layer`), пише власний trace за тим самим
    -- принципом — Рівень 2/3 не винаходять окрему структуру.
    decision_trace JSONB,
    llm_response JSONB,
    -- dedup_hash/confirmation_count: з оригінального ТЗ §14, ніколи не заповнювались
    -- кодом (перевірено grep, 2026-07-23) — замінені таблицями threat_state/
    -- threat_notifications нижче (своя дедуплікація/лічильник на рівні цілі,
    -- не окремого повідомлення). Лишені як є, не видалені — не заважають.
    dedup_hash VARCHAR(64),
    confirmation_count INT DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_events_log_detected_at ON events_log (detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_log_source_message ON events_log (source_channel, telegram_message_id);

-- Каскадна стейт-машина + дедуплікація (ТЗ §9+§10, план "Сповіщення" 2026-07-23).
-- Кілька одночасних відкритих цілей за локацією (не один глобальний рядок,
-- не один на канал) — той самий принцип, що вже двічі підтверджений у
-- цьому проєкті: Рівень 2 (channel_state.py, до 3 слотів на канал) і
-- DecisionTrace.location (кортеж, не одне значення). Матчинг нового сигналу
-- до відкритого рядка — перетин множин локацій, як channel_state._write_explicit.
CREATE TABLE IF NOT EXISTS threat_state (
    id SERIAL PRIMARY KEY,
    current_level VARCHAR(10) NOT NULL,
    location TEXT[] NOT NULL DEFAULT '{}',
    threat_type_evidence TEXT,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_signal_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    downgrade_scheduled_at TIMESTAMPTZ, -- NULL = каскад не заплановано
    last_update_source VARCHAR(30) NOT NULL DEFAULT 'auto', -- 'auto' зараз; 'manual:<id>' зарезервовано, не реалізовано
    is_locationally_lost BOOLEAN NOT NULL DEFAULT FALSE,
    lost_since TIMESTAMPTZ,
    confirmation_count INT NOT NULL DEFAULT 1,
    contributing_channels TEXT[] NOT NULL DEFAULT '{}',
    status_confirming_channels TEXT[] NOT NULL DEFAULT '{}', -- канали, що підтвердили "відбій" (ТЗ §9: 2+ гейтує каскад)
    status VARCHAR(10) NOT NULL DEFAULT 'open', -- 'open' | 'closed'
    origin_event_log_id INT REFERENCES events_log(id),
    -- Усі events_log.id, що торкнулись цього рядка (нова ціль/ескалація/
    -- мовчазне підтвердження/status-підтвердження) — повна доказова стрічка
    -- "на основі яких повідомлень" (запит користувача 2026-07-24).
    contributing_event_ids INT[] NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_threat_state_open ON threat_state (status) WHERE status = 'open';

-- Append-only стрічка переходів (той самий принцип, що events_log для
-- редагувань — threat_state сам живий/мутабельний, але стрічка "Сповіщення"
-- має показувати ІСТОРІЮ переходів, не один рядок, що тихо перезаписується.
CREATE TABLE IF NOT EXISTS threat_notifications (
    id SERIAL PRIMARY KEY,
    threat_state_id INT NOT NULL REFERENCES threat_state(id),
    transition_type VARCHAR(20) NOT NULL, -- 'new' | 'escalated' | 'downgraded' | 'cleared'
    level VARCHAR(10) NOT NULL,
    location TEXT[] NOT NULL DEFAULT '{}',
    composed_text TEXT NOT NULL,
    -- 'template_stub' зараз (app/common/llm.py — детермінований шаблон,
    -- жодного виклику LLM); 'llm' зарезервовано на майбутнє, коли Рівень 3
    -- отримає бюджет/API-ключ (ADR-0012) — навмисно різні значення, щоб
    -- стаб ніколи не сплутати з реальною відповіддю в БД/логах.
    composed_by VARCHAR(20) NOT NULL DEFAULT 'template_stub',
    confirmation_count INT NOT NULL DEFAULT 1,
    contributing_channels TEXT[] NOT NULL DEFAULT '{}',
    source_event_log_id INT REFERENCES events_log(id), -- саме ОДНЕ повідомлення, що спричинило ЦЕЙ перехід
    -- Знімок threat_state.contributing_event_ids на момент цього переходу —
    -- ПОВНА доказова стрічка (усі повідомлення, не лише те, що спричинило
    -- перехід), той самий принцип, що знімок confirmation_count/contributing_channels.
    contributing_event_ids INT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_threat_notifications_created_at ON threat_notifications (created_at DESC);
