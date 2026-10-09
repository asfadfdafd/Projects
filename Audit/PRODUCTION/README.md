# PRODUCTION — конечная версия (MVP Sales Bot)

Здесь только то, что реально работает в n8n на текущий момент. Оригиналы файлов остались на своих местах в корне `Audit/` и в `MVP_Sales_Bot/` — это копии.

## workflows/

| Файл | Роль | Статус |
|---|---|---|
| `NNN Sales Bot — воронка продаж (Telegram).json` | Главный воркфлоу: state machine, FAQ (Groq + база знаний), анкета 12 вопросов, КП, генерация договора, алерты в Gmail. 36 узлов. | Active |
| `NNN Pricing Engine (под-воркфлоу).json` | Движок цены. Вызывается главным через Execute Workflow: расчёт по правилам из Postgres, Groq пишет только текст КП. | Active (импортировать первым) |
| `NNN Booking — приём брони из Cal.com v2.json` | Вебхук Cal.com → `nnn_bookings` → лид в `booked` → подтверждение клиенту в Telegram/email + алерт команде. | Active |

Порядок импорта: Pricing Engine → Sales Bot (привязать под-воркфлоу в узле «🧮 Движок цены (КП)») → Booking v2.

## sql/

- `NNN_CRM_schema.sql` — базовые таблицы: `nnn_leads`, `nnn_analyses`, `nnn_bookings`, `nnn_tg_intake`, `nnn_messages`
- `01_sales_funnel_migration.sql` — миграция воронки продаж (анкета, КП, договоры, правила цены)
- `faq_kb_update.sql` — наполнение базы знаний для FAQ-режима

Выполнять в этом порядке, креденшл `Social Automation DB`.

## docs/

- `INSTALLATION_GUIDE.md` — пошаговая установка Sales Bot
- `README.md` — описание MVP Sales Bot
- `CAL_COM_INTEGRATION.md` — настройка Cal.com v2

---

## Не входит в конечную версию

| Файл | Почему |
|---|---|
| `NNN Telegram Bot — приём документов и запись.json` | Конкурирует с Sales Bot за один Telegram-токен. Предписано перевести в Inactive (шаг 6 гайда). Возврат — Фаза 3. |
| `NNN Analysis Engine (под-воркфлоу).json` | Вызывался только тем ботом → простаивает вместе с ним. Роль в новой версии занял Pricing Engine. |
| `NNN Booking — приём брони из Cal.com.json` (v1) | Заменён на v2, деактивировать. |
| `NNN_Audit_Workflow.json` | Веб-форма v3, автономна, в контуре продаж не участвует. После 12 июня в документации не упоминается. |
