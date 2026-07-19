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
    event_type VARCHAR(10) NOT NULL DEFAULT 'new', -- 'new' | 'edit'
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    regex_matched_level VARCHAR(10),
    llm_response JSONB,
    dedup_hash VARCHAR(64),
    confirmation_count INT DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_events_log_detected_at ON events_log (detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_log_source_message ON events_log (source_channel, telegram_message_id);
