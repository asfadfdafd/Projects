# Price List & Pricing Logic (PLACEHOLDER)

> **Note:** All numbers are invented so the engine has something to run. Currency shown as ₸ (KZT) — configurable. Replace base prices and multipliers with the auditor's real figures. The bot's price is **always computed by these rules** (deterministic); the LLM only writes the explanation around the number.

## 1. Base price by audit type

| Audit type (`audit_type`) | Base price (₸) |
|---|---|
| Voluntary / initiative (`voluntary`) | 300,000 |
| Tax (`tax`) | 400,000 |
| Statutory financial (`statutory`) | 500,000 |
| Due diligence / special (`due_diligence`) | 700,000 |
| Subsoil user (`subsoil`) | 1,000,000 |

## 2. Multipliers

| Factor | Condition | Multiplier |
|---|---|---|
| Revenue (`revenue_band`) | up to ₸100M | ×1.0 |
| | ₸100M–1B | ×1.3 |
| | ₸1B–10B | ×1.7 |
| | over ₸10B | ×2.2 |
| Employees (`employees`) | <50 | ×1.0 |
| | 50–250 | ×1.15 |
| | >250 | ×1.3 |
| Standard (`standard`) | IFRS (МСФО) | ×1.2 |
| | National (НСФО) | ×1.0 |
| Urgency (`deadline_days`) | < 30 days | ×1.4 |
| | ≥ 30 days | ×1.0 |

## 3. Additive scope

- **Extra years** (`years` > 1): + 80% of base price per additional year.
- **Consolidation** (`entities` > 1): + 20% of base price per additional entity (cap +100%).

## 4. Formula

```
subtotal = base[audit_type]
         × revenue_mult × employee_mult × standard_mult × urgency_mult

scope_add = base × 0.8 × (years - 1)
          + base × 0.2 × min(entities - 1, 5)

price = round( subtotal + scope_add, to nearest 50,000 )
```

A configurable **floor** (e.g. ₸300,000) and **manual-review trigger** (e.g. price > ₸5,000,000 → flag for auditor approval before КП is sent) keep edge cases safe.

## 5. Worked examples

- **Small voluntary audit:** voluntary (300k) × rev<100M (1.0) × <50 emp (1.0) × НСФО (1.0) × not urgent (1.0), 1 year, 1 entity → **₸300,000**.
- **Mid statutory, IFRS:** statutory (500k) × ₸100M–1B (1.3) × 50–250 (1.15) × IFRS (1.2) → 897k → rounded **₸900,000**.
- **Subsoil user, large, 2 years, urgent:** subsoil (1.0M) × ₸1B–10B (1.7) × >250 (1.3) × НСФО (1.0) × urgent (1.4) = 3.094M; +1 extra year (0.8×1.0M = 800k) → 3.894M → **₸3,900,000** (over floor, under review threshold).

These illustrate the logic; tune the constants with the auditor.
