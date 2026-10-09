# Audit Firm Sales-Bot — MVP Improvement Plan (v2, EN)

**Date:** 2026-06-12
**Status:** for approval before development

---

## 0. Context

The boss reframed the product. What's in the folder today is an **NNN-lease overcharge analyzer** (a tenant tool that finds billing errors in documents). The new goal is a **sales-funnel chatbot for an audit firm**: it consults clients, collects a questionnaire, prices the service, sends a commercial proposal (КП), and gets the client to a signed contract. The audit itself is out of scope for the MVP.

This v2 reflects your latest decisions: I've generated placeholder versions of the questionnaire, price list, and contract (you had none), kept the build **Telegram-first**, and treated Instagram and e-signature as *foundations* rather than full MVP features.

## 1. MVP business process (boss's 7 steps)

1. **Entry** — client arrives from Instagram into the chatbot.
2. **Consultation (FAQ)** — bot answers price/audit-types/license questions (e.g. subsoil-user license).
3. **Order initiation** — client says "I want to order an audit."
4. **Questionnaire** — bot sends the brief and waits.
5. **Proposal (КП)** — system reads the returned questionnaire and computes the price.
6. **Closing** — on agreement, bot generates and sends the contract for signing.
7. **MVP boundary** — automation stops *before* the actual audit. Document upload and recommendations are later phases.

## 2. Decisions locked in

| Topic | Decision |
|---|---|
| Channels | **Telegram-first.** Instagram = foundation only (pluggable adapter, no Meta dependency yet). |
| Pricing (КП) | **Hybrid** — rules compute the number, LLM writes the proposal text. |
| Contract + signing | **Auto-generated PDF.** MVP = in-chat acceptance + PDF; e-sign integration left as a stubbed hook. |
| Questionnaire | **Generated placeholder** (`Sample_Audit_Questionnaire.md`) — swap in the real one later. |
| Price list | **Generated placeholder** (`Sample_Price_List_and_Logic.md`). |
| Contract | **Generated placeholder** (`Sample_Contract_Template.md`). |

## 3. Reuse / repurpose / park

**Reuse as-is:** Postgres + DB credential; the Telegram bot scaffold; the Groq credential (FAQ + КП text); Gmail nodes (team/client notifications); Cal.com webhook (optional consult booking).

**Repurpose (bricks stay, logic changes):** the `nnn_tg_intake` buffer → conversation **state machine** and questionnaire intake; the "Analysis Engine" (contract↔reconciliation) → **pricing engine** (questionnaire → price + КП text). Same Groq/Code nodes, new prompts and formulas.

**Park for Phase 3+ (this *is* the deferred "actual audit"):** the NNN overcharge logic, OCR, and dispute-letter generation. Not deleted — kept as the basis for the paid post-signing phase.

## 4. Target architecture

```
INSTAGRAM (foundation) ─┐                                   ┌─ Team email / alerts
                        ├─► [Channel adapter] ─► [Dialog core: state machine] ─┤
TELEGRAM (MVP)         ─┘                              │                       └─ CRM (Postgres)
                                                       │
        ┌───────────────────────────────────────────────┼───────────────────────────────────┐
        ▼                 ▼                  ▼                ▼                    ▼
   [FAQ / Groq]   [Order intent]    [Questionnaire]   [Pricing engine]    [Contract + sign hook]
   knowledge base detect intent     parse fields      rules + LLM КП       template → PDF
```

**Components:**

1. **Channel adapters.** Telegram (built now) and an Instagram adapter (foundation: same interface, implemented later via Meta Messaging API). Both normalize input to `{channel, user_id, text, attachments}` so the core is channel-agnostic.
2. **Dialog core (state machine).** State lives in the DB (like today's Telegram buffer), not memory. States: `greeting → faq → order_intent → awaiting_questionnaire → pricing → proposal_sent → negotiating → contract_sent → signed → handoff`.
3. **FAQ consultant.** Groq answers from a **services knowledge base** (filled from the auditor's materials, plus the sample price list), not free invention. Detects the "I want to order" intent → moves to `order_intent`.
4. **Questionnaire step.** Bot sends the brief, sets `awaiting_questionnaire`, waits, then parses returned fields (see `Sample_Audit_Questionnaire.md`).
5. **Pricing engine (hybrid).** A Code node computes price **deterministically** from the matrix in `Sample_Price_List_and_Logic.md`; Groq wraps the number in a human-readable КП. The price comes from rules, never the LLM.
6. **Contract + sign hook.** On agreement, fill `Sample_Contract_Template.md` → generate PDF. MVP: client accepts in chat, bot logs it and sends the PDF. A clearly-marked stub is left where an e-sign provider (DocuSign/SignNow) plugs in later via webhook.
7. **CRM / notifications.** Every step is written to Postgres; key events (new lead, КП accepted, contract sent) alert the team.

## 5. Data-model changes (Postgres)

Extend existing tables, add new ones:

- `leads` (from `nnn_leads`): add `channel`, `state`, contact fields.
- `messages` (from `nnn_messages`): per-channel history for FAQ context.
- `services` (new): audit types, descriptions, base prices.
- `pricing_rules` (new): multipliers / additive scope from the price-logic file.
- `questionnaire_responses` (new): parsed questionnaire fields per lead.
- `proposals` (new): computed price, КП text, status (sent/accepted/declined).
- `contracts` (new): PDF link, signing status, date, provider id (for later e-sign).
- `bookings` (`nnn_bookings`): kept for optional consult booking.

## 6. Phased delivery

**Phase 0 — Foundation.** DB migration (Section 5), dialog state machine, FAQ knowledge base, normalized message format, channel-adapter interface (with Instagram stub). Reuse existing Postgres nodes.

**Phase 1 — End-to-end Telegram MVP.** FAQ → order intent → questionnaire → price → КП → contract PDF → in-chat acceptance. This is a fully working product with no external approvals needed.

**Phase 2 — Optional once MVP is validated.** Implement the Instagram adapter (Meta Messaging API + app review) and swap the contract stub for real e-signature.

**Phase 3 — Deferred ("actual audit").** Client document upload, the parked NNN engine/OCR for real analysis, recommendations, pay-by-link, funnel dashboard.

## 7. Risks & mitigations

- **Instagram automation** needs Meta business approval — kept out of the MVP path (Telegram-first), foundation only.
- **Pricing accuracy** rests entirely on rules + questionnaire; LLM writes prose, not the number. A floor and a manual-review threshold guard edge cases. Tune constants with the auditor.
- **Contract legality** — the template is a placeholder; the auditor's lawyer must review before real use. КП and messages carry a disclaimer.
- **Untested VM workflows** (boss noted) — Phase 0 includes running each node, fixing mappings, and filling leftover placeholders (OCR key, team email, Cal.com URL).

## 8. What I'll do right after your "go"

1. Create/extend the Postgres schema (Section 5) as a SQL migration.
2. Build the dialog state machine + FAQ consultant on the existing Telegram bot.
3. Stand up the pricing engine using the sample price logic (real numbers swap in trivially later).
4. Wire questionnaire → КП → contract PDF end-to-end in Telegram.

When you're ready, just confirm and I'll start with Phase 0.

## Companion files
- `Sample_Audit_Questionnaire.md` — placeholder intake brief
- `Sample_Price_List_and_Logic.md` — placeholder services, prices, formula
- `Sample_Contract_Template.md` — placeholder agreement with merge fields
