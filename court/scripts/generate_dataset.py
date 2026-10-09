# -*- coding: utf-8 -*-
"""
Генератор демонстрационного датасета гражданских дел (РК).

ВАЖНО: данные синтетические. Реальные судебные решения не использовались.
Генерация построена не на случайном шуме, а на ЯВНОЙ ПРИЧИННОЙ МОДЕЛИ:

    сила_позиции = сумма(вес_признака * значение) + взаимодействия + шум
    P(иск удовлетворён) = sigmoid(сила_позиции)

Благодаря этому:
  * важности признаков, которые выучит модель, осмысленны, а не артефакт шума;
  * есть «истинный» ответ, с которым можно сверить обученную модель
    (колонка true_probability используется только для валидации, в обучении
     не участвует);
  * заложены реалистичные корреляции и разная значимость признаков
    по категориям споров.

Запуск:  python3 scripts/generate_dataset.py
"""
import csv
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.schema import CATEGORIES, FEATURE_NAMES  # noqa: E402

SEED = 20260809
N_CASES = 4000
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


# ---------------------------------------------------------------------------
# Профили категорий: как часто встречаются те или иные документы
# и насколько силён «базовый» перевес истца в этой категории.
# ---------------------------------------------------------------------------
PROFILES = {
    "debt_contract": dict(
        share=0.22, base=0.75, amount_mu=14.4, amount_sigma=1.15,
        p_contract=0.93, p_payment=0.84, p_act=0.62, p_corr=0.66,
        p_expert=0.09, p_pretrial=0.80, witness_lambda=0.4,
        w_expert=0.15, w_act=0.55, w_payment=0.85, w_witness=0.10,
    ),
    "labor": dict(
        share=0.14, base=0.55, amount_mu=13.6, amount_sigma=0.85,
        p_contract=0.86, p_payment=0.55, p_act=0.25, p_corr=0.58,
        p_expert=0.06, p_pretrial=0.42, witness_lambda=1.4,
        w_expert=0.10, w_act=0.20, w_payment=0.60, w_witness=0.45,
    ),
    "consumer": dict(
        share=0.13, base=0.85, amount_mu=13.1, amount_sigma=0.95,
        p_contract=0.58, p_payment=0.78, p_act=0.40, p_corr=0.71,
        p_expert=0.34, p_pretrial=0.74, witness_lambda=0.5,
        w_expert=0.70, w_act=0.35, w_payment=0.75, w_witness=0.15,
    ),
    "insurance": dict(
        share=0.11, base=0.50, amount_mu=14.1, amount_sigma=0.90,
        p_contract=0.90, p_payment=0.66, p_act=0.30, p_corr=0.63,
        p_expert=0.58, p_pretrial=0.83, witness_lambda=0.3,
        w_expert=1.05, w_act=0.20, w_payment=0.50, w_witness=0.10,
    ),
    "construction": dict(
        share=0.10, base=0.35, amount_mu=15.0, amount_sigma=1.20,
        p_contract=0.82, p_payment=0.72, p_act=0.68, p_corr=0.60,
        p_expert=0.47, p_pretrial=0.66, witness_lambda=0.6,
        w_expert=1.15, w_act=0.90, w_payment=0.55, w_witness=0.20,
    ),
    "housing_rent": dict(
        share=0.09, base=0.45, amount_mu=13.9, amount_sigma=1.05,
        p_contract=0.71, p_payment=0.63, p_act=0.44, p_corr=0.57,
        p_expert=0.18, p_pretrial=0.58, witness_lambda=1.0,
        w_expert=0.35, w_act=0.45, w_payment=0.65, w_witness=0.35,
    ),
    "damage": dict(
        share=0.13, base=0.55, amount_mu=14.2, amount_sigma=1.10,
        p_contract=0.16, p_payment=0.36, p_act=0.22, p_corr=0.41,
        p_expert=0.69, p_pretrial=0.51, witness_lambda=1.6,
        w_expert=1.35, w_act=0.15, w_payment=0.25, w_witness=0.50,
    ),
    "family_property": dict(
        share=0.08, base=0.40, amount_mu=15.3, amount_sigma=1.00,
        p_contract=0.34, p_payment=0.58, p_act=0.20, p_corr=0.44,
        p_expert=0.40, p_pretrial=0.24, witness_lambda=1.1,
        w_expert=0.75, w_act=0.15, w_payment=0.70, w_witness=0.40,
    ),
}

# Глобальные веса (в логарифме шансов). Знак и величина заданы так,
# чтобы отражать общепринятую практику доказывания в гражданском процессе.
W = dict(
    contract=0.95,           # письменный договор
    contract_signed=0.70,    # + подписан обеими сторонами (только если договор есть)
    correspondence=0.30,
    doc_completeness=1.30,
    evidence_count=0.42,     # на log1p(count)
    pretrial=0.45,
    limitation=-2.40,        # пропуск срока исковой давности — почти приговор иску
    claimant_lawyer=0.55,
    respondent_lawyer=-0.60,
    respondent_absent=0.75,  # заочное рассмотрение чаще в пользу истца
    admits=1.05,
    counterclaim=-0.85,
    appeal=-0.35,
    amount_z=-0.22,          # крупные требования удовлетворяют осторожнее
    stale_months=-0.030,     # затягивание обращения
    legal_entity_claimant=0.25,
)

# Общий свободный член. Подобран так, чтобы доля удовлетворённых исков
# в датасете была правдоподобной (порядка 60–70 %), а не 50/50 и не 95 %.
# Значения `base` в профилях работают как отклонение категории от общего уровня.
GLOBAL_INTERCEPT = float(os.environ.get("COURT_DEMO_INTERCEPT", -3.60))

NOISE_SD = 1.05  # «неустранимая» неопределённость: усмотрение суда, устные пояснения


def sigmoid(x):
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def pick_category(rng):
    r = rng.random()
    acc = 0.0
    for name, prof in PROFILES.items():
        acc += prof["share"]
        if r <= acc:
            return name
    return list(PROFILES)[-1]


def generate_case(rng, idx):
    cat = pick_category(rng)
    p = PROFILES[cat]

    # --- стороны ----------------------------------------------------------
    if cat in ("labor", "consumer", "insurance"):
        claimant_type = "individual"
        respondent_type = "legal_entity"
    elif cat in ("damage", "family_property", "housing_rent"):
        claimant_type = rng.choices(
            ["individual", "entrepreneur", "legal_entity"], [0.78, 0.12, 0.10])[0]
        respondent_type = rng.choices(
            ["individual", "entrepreneur", "legal_entity"], [0.70, 0.14, 0.16])[0]
    else:
        claimant_type = rng.choices(
            ["individual", "entrepreneur", "legal_entity"], [0.34, 0.24, 0.42])[0]
        respondent_type = rng.choices(
            ["individual", "entrepreneur", "legal_entity"], [0.36, 0.22, 0.42])[0]

    court_instance = "appeal" if rng.random() < 0.17 else "first"

    # --- сумма требований -------------------------------------------------
    claim_amount = math.exp(rng.gauss(p["amount_mu"], p["amount_sigma"]))
    claim_amount = float(min(max(claim_amount, 120_000), 400_000_000))
    amount_z = (math.log(claim_amount) - 14.2) / 1.15
    big_case = amount_z > 0.6

    # --- организованность истца (латентная переменная, создаёт корреляции) --
    organized = rng.random()
    if claimant_type == "legal_entity":
        organized = min(1.0, organized + 0.22)
    if big_case:
        organized = min(1.0, organized + 0.12)

    def draw(base_p, boost=0.30):
        return 1 if rng.random() < min(0.98, base_p + boost * (organized - 0.5)) else 0

    has_written_contract = draw(p["p_contract"])
    contract_signed_both = has_written_contract and draw(0.86)
    has_payment_documents = draw(p["p_payment"])
    has_acceptance_act = draw(p["p_act"])
    has_correspondence = draw(p["p_corr"])
    has_expert_opinion = draw(p["p_expert"], boost=0.22)
    pretrial_claim_sent = draw(p["p_pretrial"])

    witness_count = min(5, int(rng.expovariate(1.0 / max(0.15, p["witness_lambda"]))))

    claimant_has_lawyer = 1 if rng.random() < min(
        0.95, 0.24 + 0.45 * organized + (0.22 if big_case else 0.0)) else 0
    respondent_has_lawyer = 1 if rng.random() < min(
        0.95, 0.20 + (0.30 if respondent_type == "legal_entity" else 0.0)
        + (0.20 if big_case else 0.0)) else 0

    respondent_appeared = 1 if rng.random() < (
        0.66 + 0.18 * respondent_has_lawyer) else 0
    respondent_admits_partially = (
        1 if respondent_appeared and rng.random() < 0.24 else 0)
    counterclaim_filed = (
        1 if respondent_appeared and rng.random() < (
            0.10 + 0.10 * respondent_has_lawyer) else 0)

    # Часть истцов обращается в суд спустя годы — именно там возникает
    # вопрос исковой давности (общий срок — 3 года).
    if rng.random() < 0.17:
        months_since_breach = max(1, int(rng.gammavariate(3.0, 16.0)))
    else:
        months_since_breach = max(1, int(rng.gammavariate(2.2, 5.0)))
    if months_since_breach >= 36:
        # течение срока могло прерываться претензией или признанием долга
        limitation_period_ok = 1 if rng.random() < 0.30 else 0
    else:
        limitation_period_ok = 1

    doc_flags = [has_written_contract, has_payment_documents, has_acceptance_act,
                 has_correspondence, has_expert_opinion, pretrial_claim_sent,
                 contract_signed_both]
    doc_completeness = round(
        min(1.0, max(0.0, sum(doc_flags) / len(doc_flags) + rng.gauss(0, 0.06))), 3)

    evidence_count = max(1, int(
        2 + 2.4 * sum(doc_flags) + witness_count + rng.gauss(0, 2.2)))

    # --- причинная модель исхода ------------------------------------------
    z = GLOBAL_INTERCEPT + p["base"]
    z += W["contract"] * has_written_contract
    z += W["contract_signed"] * contract_signed_both
    z += p["w_payment"] * has_payment_documents
    z += p["w_act"] * has_acceptance_act
    z += W["correspondence"] * has_correspondence
    z += p["w_expert"] * has_expert_opinion
    z += p["w_witness"] * min(witness_count, 3)
    z += W["evidence_count"] * math.log1p(evidence_count) * 0.5
    z += W["doc_completeness"] * doc_completeness
    z += W["pretrial"] * pretrial_claim_sent
    z += W["limitation"] * (1 - limitation_period_ok)
    z += W["claimant_lawyer"] * claimant_has_lawyer
    z += W["respondent_lawyer"] * respondent_has_lawyer
    z += W["respondent_absent"] * (1 - respondent_appeared)
    z += W["admits"] * respondent_admits_partially
    z += W["counterclaim"] * counterclaim_filed
    z += W["appeal"] * (1 if court_instance == "appeal" else 0)
    z += W["amount_z"] * amount_z
    z += W["stale_months"] * min(months_since_breach, 60)
    z += W["legal_entity_claimant"] * (1 if claimant_type == "legal_entity" else 0)

    # нелинейности: юрист у ответчика особенно опасен, когда пакет документов слабый
    z += -0.55 * respondent_has_lawyer * (1 - doc_completeness)
    # экспертиза критична в крупных делах о возмещении
    if cat in ("damage", "construction", "insurance"):
        z += 0.45 * has_expert_opinion * max(0.0, amount_z)

    z_noisy = z + rng.gauss(0, NOISE_SD)
    true_p = sigmoid(z)
    outcome_win = 1 if sigmoid(z_noisy) > rng.random() else 0

    # --- какая доля требований будет удовлетворена --------------------------
    # У доли своя причинная структура, а не просто «чем сильнее позиция, тем
    # больше присудят». Суд срезает ту часть требований, размер которой
    # документально не подтверждён: отсюда вес экспертизы, платёжных
    # документов и актов. Признание ответчиком части долга, наоборот,
    # фиксирует её как бесспорную.
    if outcome_win:
        share_z = (
            0.30
            + 0.62 * has_expert_opinion
            + 0.48 * has_payment_documents
            + 0.38 * has_acceptance_act
            + 0.55 * respondent_admits_partially
            + 0.28 * contract_signed_both
            + 0.85 * (doc_completeness - 0.5)
            - 0.52 * amount_z              # крупные суммы срезают чаще
            - 0.40 * counterclaim_filed    # встречные требования идут в зачёт
            + rng.gauss(0, 0.55)
        )
        share_core = sigmoid(share_z)
        if rng.random() < share_core ** 3.0:
            satisfied_share = 1.0          # требования удовлетворены полностью
        else:
            concentration = 6.0
            a = max(0.6, share_core * concentration)
            b = max(0.6, (1 - share_core) * concentration)
            satisfied_share = round(min(0.94, max(0.15, rng.betavariate(a, b))), 3)
    else:
        satisfied_share = 0.0

    if satisfied_share >= 0.95:
        label = "satisfied_full"
    elif satisfied_share > 0:
        label = "satisfied_partial"
    else:
        label = "denied"

    return {
        "case_id": "DEMO-%05d" % idx,
        "dispute_category": cat,
        "claimant_type": claimant_type,
        "respondent_type": respondent_type,
        "court_instance": court_instance,
        "claim_amount_kzt": round(claim_amount, 2),
        "months_since_breach": months_since_breach,
        "has_written_contract": has_written_contract,
        "contract_signed_both": int(contract_signed_both),
        "has_payment_documents": has_payment_documents,
        "has_acceptance_act": has_acceptance_act,
        "has_correspondence": has_correspondence,
        "has_expert_opinion": has_expert_opinion,
        "witness_count": witness_count,
        "evidence_count": evidence_count,
        "doc_completeness": doc_completeness,
        "pretrial_claim_sent": pretrial_claim_sent,
        "limitation_period_ok": limitation_period_ok,
        "claimant_has_lawyer": claimant_has_lawyer,
        "respondent_has_lawyer": respondent_has_lawyer,
        "respondent_appeared": respondent_appeared,
        "respondent_admits_partially": respondent_admits_partially,
        "counterclaim_filed": counterclaim_filed,
        "outcome_win": outcome_win,
        "satisfied_share": satisfied_share,
        "outcome_label": label,
        "true_probability": round(true_p, 4),
    }


def main():
    rng = random.Random(SEED)
    rows = [generate_case(rng, i + 1) for i in range(N_CASES)]

    os.makedirs(OUT_DIR, exist_ok=True)
    columns = (["case_id"] + FEATURE_NAMES
               + ["outcome_win", "satisfied_share", "outcome_label", "true_probability"])

    path = os.path.join(OUT_DIR, "cases.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r[c] for c in columns})

    # сводка для документации и проверки правдоподобия
    total = len(rows)
    wins = sum(r["outcome_win"] for r in rows)
    by_cat = {}
    for r in rows:
        c = r["dispute_category"]
        d = by_cat.setdefault(c, {"n": 0, "wins": 0, "amount": 0.0})
        d["n"] += 1
        d["wins"] += r["outcome_win"]
        d["amount"] += r["claim_amount_kzt"]

    summary = {
        "n_cases": total,
        "seed": SEED,
        "overall_win_rate": round(wins / total, 4),
        "outcome_distribution": {
            k: round(sum(1 for r in rows if r["outcome_label"] == k) / total, 4)
            for k in ("satisfied_full", "satisfied_partial", "denied")
        },
        "by_category": {
            CATEGORIES[c]: {
                "n": d["n"],
                "win_rate": round(d["wins"] / d["n"], 3),
                "median_claim_kzt": round(sorted(
                    r["claim_amount_kzt"] for r in rows
                    if r["dispute_category"] == c)[d["n"] // 2]),
            }
            for c, d in sorted(by_cat.items())
        },
    }
    with open(os.path.join(OUT_DIR, "dataset_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    print("Сохранено: %s (%d дел)" % (path, total))
    print("Доля удовлетворённых исков: %.1f%%" % (100 * wins / total))
    for name, d in summary["by_category"].items():
        print("  %-42s n=%4d  win=%.2f" % (name, d["n"], d["win_rate"]))


if __name__ == "__main__":
    main()
