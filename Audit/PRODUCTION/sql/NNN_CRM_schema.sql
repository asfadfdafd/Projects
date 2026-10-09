-- ============================================================
-- NNN Audit — схема CRM для Postgres
-- Запусти один раз в своей базе (тот же креденшл, что в Instagram-workflow).
-- ============================================================

-- Лиды/клиенты (одна строка на обращение)
CREATE TABLE IF NOT EXISTS nnn_leads (
  id              BIGSERIAL PRIMARY KEY,
  source          TEXT        NOT NULL DEFAULT 'web',   -- 'web' | 'telegram'
  channel_id      TEXT,                                  -- telegram chat_id или email
  email           TEXT,
  full_name       TEXT,
  property_name   TEXT,
  currency        TEXT        DEFAULT 'USD',
  status          TEXT        NOT NULL DEFAULT 'new',    -- new|analyzed|contacted|booked|in_audit|won|lost
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Результаты анализа (одна строка на проверку)
CREATE TABLE IF NOT EXISTS nnn_analyses (
  id                   BIGSERIAL PRIMARY KEY,
  lead_id              BIGINT REFERENCES nnn_leads(id) ON DELETE CASCADE,
  total_overcharge     TEXT,           -- человекочитаемая сумма, напр. '≈ 19 499 USD'
  total_overcharge_num NUMERIC,        -- число для аналитики
  high_count           INT DEFAULT 0,
  findings             JSONB,          -- массив находок
  tasks                JSONB,          -- массив задач
  summary              TEXT,
  dispute_letter       TEXT,           -- текст письма-претензии
  confidence           NUMERIC,
  source_type          TEXT,           -- 'text' | 'ocr'
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Записи на услугу (из Cal.com webhook)
CREATE TABLE IF NOT EXISTS nnn_bookings (
  id            BIGSERIAL PRIMARY KEY,
  lead_id       BIGINT REFERENCES nnn_leads(id) ON DELETE SET NULL,
  external_id   TEXT UNIQUE,            -- uid брони из Cal.com
  attendee_name TEXT,
  attendee_email TEXT,
  service       TEXT,                   -- тип услуги
  start_time    TIMESTAMPTZ,
  end_time      TIMESTAMPTZ,
  status        TEXT DEFAULT 'confirmed', -- confirmed|cancelled|rescheduled
  meeting_url   TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Буфер приёма документов в Telegram (накопление до 2 файлов на чат)
CREATE TABLE IF NOT EXISTS nnn_tg_intake (
  id          BIGSERIAL PRIMARY KEY,
  chat_id     TEXT NOT NULL,
  role        TEXT NOT NULL,            -- 'contract' | 'reconciliation'
  file_name   TEXT,
  doc_text    TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tg_intake_chat ON nnn_tg_intake(chat_id);

-- История сообщений чат-бота (опционально, для контекста/аналитики)
CREATE TABLE IF NOT EXISTS nnn_messages (
  id          BIGSERIAL PRIMARY KEY,
  chat_id     TEXT,
  direction   TEXT,                     -- 'in' | 'out'
  text        TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
