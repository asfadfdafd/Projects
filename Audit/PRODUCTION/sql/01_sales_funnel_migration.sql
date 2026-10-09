-- ============================================================
-- MVP Sales Bot — миграция схемы CRM (Фаза 0, раздел 5 плана)
-- Запустить ОДИН РАЗ в той же базе, что NNN_CRM_schema.sql
-- (креденшл "Social Automation DB"). Идемпотентно.
-- ВНИМАНИЕ: цены/коэффициенты в сидах — ПЛЕЙСХОЛДЕРЫ из
-- Sample_Price_List_and_Logic.md. Заменить реальными цифрами аудитора.
-- ============================================================

-- ---------- 1. Расширяем nnn_leads под воронку продаж ----------
ALTER TABLE nnn_leads
  ADD COLUMN IF NOT EXISTS channel       TEXT,                       -- 'telegram' | 'instagram'
  ADD COLUMN IF NOT EXISTS state         TEXT NOT NULL DEFAULT 'greeting',
  -- greeting|faq|order_intent|awaiting_questionnaire|pricing|proposal_sent|negotiating|contract_sent|signed|handoff
  ADD COLUMN IF NOT EXISTS phone         TEXT,
  ADD COLUMN IF NOT EXISTS company_name  TEXT,
  ADD COLUMN IF NOT EXISTS contact_name  TEXT;

-- Бэкфилл: у лидов, созданных старым ботом, channel был NULL —
-- без этого новый бот завёл бы существующим клиентам дубликаты.
UPDATE nnn_leads SET channel = source WHERE channel IS NULL AND source = 'telegram';

CREATE INDEX IF NOT EXISTS idx_leads_channel_chat ON nnn_leads(channel, channel_id);
CREATE INDEX IF NOT EXISTS idx_leads_state        ON nnn_leads(state);

-- ---------- 2. Каталог услуг (база знаний для FAQ + база цены) ----------
CREATE TABLE IF NOT EXISTS nnn_services (
  id           BIGSERIAL PRIMARY KEY,
  code         TEXT UNIQUE NOT NULL,     -- 'statutory'|'voluntary'|'subsoil'|'tax'|'due_diligence'
  name_ru      TEXT NOT NULL,
  description  TEXT,                     -- текст для FAQ-консультанта
  base_price   NUMERIC NOT NULL,         -- базовая цена, ₸ (ПЛЕЙСХОЛДЕР)
  currency     TEXT NOT NULL DEFAULT 'KZT',
  is_active    BOOLEAN NOT NULL DEFAULT TRUE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO nnn_services (code, name_ru, description, base_price) VALUES
  ('voluntary',     'Инициативный аудит',  'Добровольный аудит финансовой отчётности по инициативе собственника или руководства.', 300000),
  ('tax',           'Налоговый аудит',     'Проверка корректности исчисления и уплаты налогов, выявление налоговых рисков.', 400000),
  ('statutory',     'Обязательный аудит',  'Аудит финансовой отчётности, обязательный по законодательству РК для отдельных категорий организаций.', 500000),
  ('due_diligence', 'Due diligence / спецзадание', 'Проверка для сделок M&A, инвесторов и специальных целей.', 700000),
  ('subsoil',       'Аудит недропользователя', 'Аудит компаний-недропользователей. Требуется специальная лицензия — у компании она есть.', 1000000)
ON CONFLICT (code) DO NOTHING;

-- ---------- 3. Правила ценообразования ----------
-- Движок цены читает эту таблицу; число всегда считают ПРАВИЛА, не LLM.
CREATE TABLE IF NOT EXISTS nnn_pricing_rules (
  id          BIGSERIAL PRIMARY KEY,
  rule_type   TEXT NOT NULL,   -- 'multiplier' | 'additive' | 'config'
  factor      TEXT NOT NULL,   -- 'revenue_band'|'employees'|'standard'|'urgency'|'extra_year'|'extra_entity'|'floor'|'review_threshold'|'round_to'
  condition   TEXT,            -- значение фактора из анкеты ('lt_100m', 'ifrs', ...) или NULL для config/additive
  value       NUMERIC NOT NULL,-- множитель, доля от базы или сумма
  note        TEXT,
  is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

-- сиды-ПЛЕЙСХОЛДЕРЫ (Sample_Price_List_and_Logic.md)
INSERT INTO nnn_pricing_rules (rule_type, factor, condition, value, note) VALUES
  ('multiplier','revenue_band','lt_100m', 1.0,  'выручка до ₸100 млн'),
  ('multiplier','revenue_band','100m_1b', 1.3,  '₸100 млн – 1 млрд'),
  ('multiplier','revenue_band','1b_10b',  1.7,  '₸1–10 млрд'),
  ('multiplier','revenue_band','gt_10b',  2.2,  'свыше ₸10 млрд'),
  ('multiplier','employees','lt_50',      1.0,  '<50 сотрудников'),
  ('multiplier','employees','50_250',     1.15, '50–250'),
  ('multiplier','employees','gt_250',     1.3,  '>250'),
  ('multiplier','standard','ifrs',        1.2,  'МСФО'),
  ('multiplier','standard','nsfo',        1.0,  'НСФО'),
  ('multiplier','urgency','urgent',       1.4,  'дедлайн < 30 дней'),
  ('multiplier','urgency','normal',       1.0,  'дедлайн ≥ 30 дней'),
  ('additive','extra_year',  NULL, 0.8,  '+80% базы за каждый доп. год'),
  ('additive','extra_entity',NULL, 0.2,  '+20% базы за каждое доп. юрлицо (cap 5)'),
  ('config','floor',            NULL, 300000,  'минимальная цена'),
  ('config','review_threshold', NULL, 5000000, 'цена выше — ручное одобрение аудитора до отправки КП'),
  ('config','round_to',         NULL, 50000,   'округление итога')
ON CONFLICT DO NOTHING;

-- ---------- 4. Ответы на анкету ----------
CREATE TABLE IF NOT EXISTS nnn_questionnaire_responses (
  id           BIGSERIAL PRIMARY KEY,
  lead_id      BIGINT REFERENCES nnn_leads(id) ON DELETE CASCADE,
  answers      JSONB NOT NULL DEFAULT '{}'::jsonb,  -- {field_id: value} по Sample_Audit_Questionnaire.md
  current_step INT  NOT NULL DEFAULT 0,             -- индекс текущего вопроса (пошаговая анкета)
  completed    BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_qr_lead ON nnn_questionnaire_responses(lead_id);

-- ---------- 5. Коммерческие предложения ----------
CREATE TABLE IF NOT EXISTS nnn_proposals (
  id             BIGSERIAL PRIMARY KEY,
  lead_id        BIGINT REFERENCES nnn_leads(id) ON DELETE CASCADE,
  service_code   TEXT,
  price          NUMERIC NOT NULL,
  currency       TEXT NOT NULL DEFAULT 'KZT',
  breakdown      JSONB,             -- расчёт: база, множители, добавки
  proposal_text  TEXT,              -- текст КП (LLM)
  needs_review   BOOLEAN NOT NULL DEFAULT FALSE, -- цена > review_threshold
  status         TEXT NOT NULL DEFAULT 'draft',  -- draft|sent|accepted|declined
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_proposals_lead ON nnn_proposals(lead_id);

-- ---------- 6. Договоры ----------
CREATE TABLE IF NOT EXISTS nnn_contracts (
  id              BIGSERIAL PRIMARY KEY,
  lead_id         BIGINT REFERENCES nnn_leads(id) ON DELETE CASCADE,
  proposal_id     BIGINT REFERENCES nnn_proposals(id) ON DELETE SET NULL,
  contract_number TEXT,
  file_url        TEXT,              -- ссылка на сгенерированный PDF
  sign_url        TEXT,              -- ссылка э-подписи (DocuSign/SignNow)
  external_id     TEXT,              -- id конверта у провайдера э-подписи
  status          TEXT NOT NULL DEFAULT 'draft', -- draft|sent|signed|declined
  signed_at       TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_contracts_lead ON nnn_contracts(lead_id);

-- ---------- 7. База знаний FAQ ----------
CREATE TABLE IF NOT EXISTS nnn_faq_kb (
  id         BIGSERIAL PRIMARY KEY,
  topic      TEXT NOT NULL,
  content    TEXT NOT NULL,   -- факт, который FAQ-консультант может использовать
  is_active  BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- сиды-ПЛЕЙСХОЛДЕРЫ — заменить фактами от аудитора
INSERT INTO nnn_faq_kb (topic, content)
SELECT * FROM (VALUES
  ('Лицензии', 'У компании есть генеральная лицензия на аудиторскую деятельность, включая аудит недропользователей. [ПЛЕЙСХОЛДЕР: № лицензии и дата выдачи]'),
  ('Цены', 'Стоимость зависит от вида аудита, выручки, численности персонала, стандарта отчётности (НСФО/МСФО) и срочности. Диапазон от ₸300 000. Точная цена — после короткой анкеты.'),
  ('Сроки', '[ПЛЕЙСХОЛДЕР] Типовой аудит занимает 4–8 недель с момента предоставления документов. Срочное выполнение (<30 дней) возможно с надбавкой.'),
  ('Процесс', 'Как заказать: ответьте «хочу заказать аудит» → заполните анкету → получите коммерческое предложение с ценой → при согласии подпишете договор электронно.')
) AS v(topic, content)
WHERE NOT EXISTS (SELECT 1 FROM nnn_faq_kb);

-- ---------- 8. Расширяем nnn_messages под мультиканальность ----------
ALTER TABLE nnn_messages
  ADD COLUMN IF NOT EXISTS channel TEXT DEFAULT 'telegram',
  ADD COLUMN IF NOT EXISTS lead_id BIGINT;
CREATE INDEX IF NOT EXISTS idx_messages_chat ON nnn_messages(chat_id, created_at);
