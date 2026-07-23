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
    dedup_hash VARCHAR(64),
    confirmation_count INT DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_events_log_detected_at ON events_log (detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_log_source_message ON events_log (source_channel, telegram_message_id);
