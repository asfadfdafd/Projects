# Audit Intake Questionnaire (PLACEHOLDER / анкета)

> **Note:** This is a made-up sample so we can build and test the flow. Replace with your real questionnaire later. Field IDs in `code` are what the bot stores and the pricing engine reads — keep them stable even if you reword the questions.

## Section A — Contact

1. Company name — `company_name`
2. Contact person (name, position) — `contact_name`
3. Email — `email`
4. Phone — `phone`

## Section B — What you need (drives audit type)

5. **Type of audit** — `audit_type` (single choice):
   - Statutory financial audit (обязательный) — `statutory`
   - Voluntary / initiative audit (инициативный) — `voluntary`
   - Subsoil user audit (недропользователь) — `subsoil`
   - Tax audit (налоговый) — `tax`
   - Due diligence / special purpose — `due_diligence`
6. Are you a subsoil user / недропользователь? — `is_subsoil` (yes/no)
7. Reporting standard — `standard`: National (НСФО) / IFRS (МСФО)
8. Periods to audit (how many years) — `years` (1, 2, 3+)
9. Desired completion deadline — `deadline_days` (e.g. 60 days; <30 = urgent)

## Section C — Company size (drives multipliers)

10. Annual revenue band — `revenue_band`:
    - up to ₸100M — `lt_100m`
    - ₸100M – ₸1B — `100m_1b`
    - ₸1B – ₸10B — `1b_10b`
    - over ₸10B — `gt_10b`
11. Number of employees — `employees`: <50 / 50–250 / >250
12. Number of legal entities to audit (group/consolidation) — `entities` (1, 2, 3+)
13. Accounting system — `accounting_system` (1C, SAP, other)
14. Number of branches / locations — `branches`

## Section D — History & logistics

15. Have you been audited before? — `prior_audit` (yes/no; first-time may add scope)
16. Preferred report language — `report_language` (KZ / RU / EN)
17. Anything else we should know — `notes` (free text)

---

### Mapping to pricing inputs

The engine reads: `audit_type`, `is_subsoil`, `standard`, `years`, `deadline_days`, `revenue_band`, `employees`, `entities`. Everything else is for context, the КП text, and the contract.
