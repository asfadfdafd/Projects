# -*- coding: utf-8 -*-
"""
Поиск похожих дел в базе.

Зачем это нужно. Число «49 %» само по себе абстрактно и вызывает вопрос
«откуда оно». Фраза «в базе 47 дел, похожих на ваше, из них удовлетворено
31» убеждает сильнее, потому что её можно проверить: рядом показываются
конкретные дела с их обстоятельствами и исходами.

Как считается близость. Дела сравниваются в том же пространстве признаков,
в котором работает модель, но каждая координата дополнительно взвешивается
модулем коэффициента модели. То есть похожими считаются дела, совпадающие
по тому, что на исход реально влияет, а не по случайным совпадениям вроде
одинакового числа страниц.

Чистый Python, без внешних зависимостей.
"""
import csv
import math
import os

from core.features import build_feature_vector
from core.predictor import load_model
from core.schema import CATEGORIES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "cases.csv")

NUMERIC = {"claim_amount_kzt", "months_since_breach", "witness_count",
           "evidence_count", "doc_completeness", "outcome_win",
           "satisfied_share"}

_INDEX = None

# Обстоятельства, которые стоит назвать в описании похожего дела
NOTABLE = [
    ("has_written_contract", "есть письменный договор", "договора нет"),
    ("has_expert_opinion", "есть экспертиза", None),
    ("has_payment_documents", "есть платёжные документы", None),
    ("limitation_period_ok", None, "срок исковой давности истёк"),
    ("respondent_admits_partially", "ответчик признал часть требований", None),
    ("counterclaim_filed", "подан встречный иск", None),
    ("claimant_has_lawyer", "истец с представителем", None),
]


def _money(value):
    value = float(value)
    if value >= 1_000_000:
        return "%.1f млн тг" % (value / 1_000_000)
    return "%.0f тыс. тг" % (value / 1000)


def _load_index():
    """Разово читает базу и готовит взвешенные векторы."""
    global _INDEX
    if _INDEX is not None:
        return _INDEX

    model = load_model()
    mean, std, coef = model["mean"], model["std"], model["coef"]
    # вес координаты — важность признака для модели
    weights = [abs(c) for c in coef]
    scale = max(weights) or 1.0
    weights = [w / scale for w in weights]

    rows, vectors = [], []
    with open(DATA_PATH, encoding="utf-8") as fh:
        for raw in csv.DictReader(fh):
            case = {}
            for key, value in raw.items():
                if key in NUMERIC:
                    case[key] = float(value) if value not in ("", None) else 0.0
                elif value in ("0", "1"):
                    case[key] = int(value)
                else:
                    case[key] = value
            _, values = build_feature_vector(case)
            vectors.append([
                w * (v - m) / (s if s else 1.0)
                for v, m, s, w in zip(values, mean, std, weights)])
            rows.append(case)

    _INDEX = {"rows": rows, "vectors": vectors, "mean": mean,
              "std": std, "weights": weights}
    return _INDEX


def _describe(case):
    notes = []
    for feature, if_yes, if_no in NOTABLE:
        value = float(case.get(feature) or 0)
        if value >= 0.5 and if_yes:
            notes.append(if_yes)
        elif value < 0.5 and if_no:
            notes.append(if_no)
    if float(case.get("witness_count") or 0) >= 2:
        notes.append("свидетелей: %d" % int(case["witness_count"]))

    share = float(case.get("satisfied_share") or 0)
    if share >= 0.95:
        outcome = "требования удовлетворены полностью"
    elif share > 0:
        outcome = "удовлетворено частично — %d %% от суммы иска" % round(share * 100)
    else:
        outcome = "в иске отказано"

    return {
        "case_id": case.get("case_id"),
        "category": CATEGORIES.get(case.get("dispute_category"), "—"),
        "amount": _money(case.get("claim_amount_kzt") or 0),
        "notes": notes[:4],
        "outcome": outcome,
        "won": int(float(case.get("outcome_win") or 0)),
        "satisfied_share": round(share, 3),
    }


def find_similar(case, k=60, examples=3):
    """Похожие дела и их исходы.

    k подобрано так, чтобы статистика была устойчивой, но выборка
    оставалась действительно близкой к делу пользователя.
    """
    index = _load_index()
    _, values = build_feature_vector(case)
    query = [w * (v - m) / (s if s else 1.0)
             for v, m, s, w in zip(values, index["mean"], index["std"],
                                   index["weights"])]

    scored = []
    for i, vector in enumerate(index["vectors"]):
        total = 0.0
        for a, b in zip(query, vector):
            diff = a - b
            total += diff * diff
        scored.append((total, i))
    scored.sort(key=lambda t: t[0])
    top = scored[:k]

    rows = [index["rows"][i] for _, i in top]
    wins = sum(1 for r in rows if float(r["outcome_win"]) > 0.5)
    won_rows = [r for r in rows if float(r["outcome_win"]) > 0.5]
    shares = sorted(float(r["satisfied_share"]) for r in won_rows)
    median_share = shares[len(shares) // 2] if shares else 0.0

    # для примеров берём самые близкие дела, но показываем и выигранные,
    # и проигранные — иначе подборка выглядит подогнанной
    won_examples = [r for r in rows if float(r["outcome_win"]) > 0.5][:examples - 1]
    lost_examples = [r for r in rows if float(r["outcome_win"]) <= 0.5][:1]
    shown = (won_examples + lost_examples)[:examples]

    return {
        "n": len(rows),
        "won": wins,
        "lost": len(rows) - wins,
        "win_rate": round(wins / len(rows), 3) if rows else 0.0,
        "median_satisfied_share": round(median_share, 3),
        "max_distance": round(math.sqrt(top[-1][0]), 3) if top else None,
        "examples": [_describe(r) for r in shown],
        "note": ("Дела из демонстрационной базы, близкие по обстоятельствам, "
                 "которые влияют на исход. База синтетическая — это иллюстрация "
                 "механики, а не статистика реальной практики."),
    }
