# -*- coding: utf-8 -*-
"""
Инференс модели вероятности + объяснение предсказания.

Чистый Python, без внешних зависимостей: модель загружается из
models/model.json. Это позволяет разворачивать демо в закрытом контуре,
где установка пакетов невозможна или нежелательна.

Объяснение считается ТОЧНО, а не аппроксимируется:
    z = intercept + Σ coef_i * (x_i - mean_i) / std_i
    вклад признака i = coef_i * (x_i - mean_i) / std_i   [в логарифме шансов]
Для показа пользователю вклад переводится в процентные пункты:
    «насколько изменилась бы вероятность, если бы этот признак
     был на среднем для датасета уровне».
"""
import json
import math
import os

from core.features import build_feature_vector, humanize
from core.schema import BINARY_FEATURES, DISCLAIMER, FEATURE_BY_NAME

MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "model.json")

# Признаки, которые заявитель может реально изменить до подачи/заседания.
# Используются для формирования рекомендаций.
ACTIONABLE = {
    "has_written_contract": "Найти и приложить письменный договор",
    "contract_signed_both": "Приложить экземпляр договора с подписями обеих сторон",
    "has_payment_documents": "Приложить платёжные документы: чеки, квитанции, "
                             "выписки по счёту, подтверждения переводов",
    "has_acceptance_act": "Приложить акты приёма-передачи, накладные или "
                          "акты выполненных работ",
    "has_correspondence": "Приложить переписку с другой стороной: письма, "
                          "сообщения в мессенджерах, электронную почту",
    "has_expert_opinion": "Получить заключение эксперта или отчёт об оценке, "
                          "подтверждающий заявленную сумму",
    "pretrial_claim_sent": "Направить досудебную претензию и сохранить "
                           "подтверждение отправки",
    "claimant_has_lawyer": "Привлечь юриста для подготовки позиции по делу",
}

# Признаки, неприменимые к категории спора. Модель обучена на всём датасете
# и формально может «посоветовать» приложить договор по делу о заливе
# квартиры. Такой совет бессмысленен и подрывает доверие к системе,
# поэтому неприменимые признаки скрываются и из факторов, и из рекомендаций.
NOT_APPLICABLE = {
    "damage": {"has_written_contract", "contract_signed_both",
               "has_acceptance_act"},
    "family_property": {"has_acceptance_act"},
    "insurance": {"has_acceptance_act"},
    "labor": {"has_acceptance_act", "has_expert_opinion"},
    "debt_contract": {"has_expert_opinion"},
    "housing_rent": {"has_expert_opinion"},
}

_MODEL = None


def sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-min(z, 35)))
    e = math.exp(max(z, -35))
    return e / (1.0 + e)


def load_model(path=MODEL_PATH):
    global _MODEL
    if _MODEL is None:
        with open(path, encoding="utf-8") as fh:
            _MODEL = json.load(fh)
    return _MODEL


def _raw_z(model, case):
    names, values = build_feature_vector(case)
    if names != model["feature_names"]:
        raise ValueError(
            "Набор признаков не совпадает с обученной моделью. "
            "Переобучите модель: python3 scripts/train_model.py")
    contributions = []
    z = model["intercept"]
    for name, x, mu, sd, w in zip(names, values, model["mean"],
                                  model["std"], model["coef"]):
        c = w * (x - mu) / (sd if sd else 1.0)
        z += c
        contributions.append((name, x, c))
    return z, contributions


def _expected_award(model, case, probability):
    """Сколько истец, вероятно, получит по итогу.

        ожидаемое взыскание = P(иск удовлетворён)
                              × E[доля удовлетворённых требований | удовлетворён]
                              × заявленная сумма

    Для истца это более полезная величина, чем вероятность выигрыша:
    выиграть дело и получить треть заявленного — распространённый исход,
    и планировать нужно исходя из него.
    """
    share_model = model.get("share_model")
    amount = float(case.get("claim_amount_kzt") or 0)
    if not share_model or amount <= 0:
        return None

    names, values = build_feature_vector(case)
    z = share_model["intercept"]
    for x, mu, sd, w in zip(values, model["mean"], model["std"],
                            share_model["coef"]):
        z += w * (x - mu) / (sd if sd else 1.0)
    lo, hi = share_model.get("clip", [0.15, 1.0])
    share = min(hi, max(lo, z))

    mae = float(share_model.get("metrics", {}).get("mae", 0.14))
    return {
        "claim_amount": round(amount),
        "expected_share": round(share, 3),
        "expected_share_pct": int(round(share * 100)),
        "share_range_pct": [max(0, int(round((share - mae) * 100))),
                            min(100, int(round((share + mae) * 100)))],
        "expected_award": round(probability * share * amount),
        "award_if_won": round(share * amount),
        "model_mae": round(mae, 3),
    }


def _band_label(p):
    if p < 0.30:
        return "низкие"
    if p < 0.50:
        return "ниже средних"
    if p < 0.70:
        return "умеренные"
    if p < 0.85:
        return "хорошие"
    return "высокие"


def predict(case, top_factors=6, max_recommendations=4):
    """Возвращает вероятность, объяснение и рекомендации."""
    model = load_model()
    z, contributions = _raw_z(model, case)
    p = sigmoid(z)

    hidden = set(NOT_APPLICABLE.get(case.get("dispute_category"), set()))
    if not float(case.get("has_written_contract") or 0):
        # без договора отдельный факт «нет подписи в договоре» только путает
        hidden.add("contract_signed_both")

    # --- факторы -----------------------------------------------------------
    factors = []
    for name, value, c in contributions:
        if abs(c) < 1e-6 or name in hidden:
            continue
        # Ранжируем по вкладу в логарифм шансов, а не в процентные пункты:
        # у дел с вероятностью около 5 % или 95 % любой фактор даёт малый
        # сдвиг в процентах, и сортировка по п.п. скрыла бы главные причины.
        if abs(c) < 0.03:
            continue
        # эффект в процентных пунктах: разница с гипотетическим «средним» делом
        delta_pp = (p - sigmoid(z - c)) * 100.0
        meta = FEATURE_BY_NAME.get(name, {})
        if name in BINARY_FEATURES:
            text = meta.get("pos" if value >= 0.5 else "neg", humanize(name))
        else:
            text = humanize(name)
        factors.append({
            "feature": name,
            "label": humanize(name),
            "text": text,
            "value": value,
            "effect_pp": round(delta_pp, 1),
            # Когда вероятность близка к 0 или 100 %, любой фактор даёт сдвиг
            # меньше 0,1 п.п. Показывать «+0.0 п.п.» бессмысленно, поэтому
            # для таких случаев формулировка качественная.
            "effect_text": ("%+.1f п.п." % delta_pp if abs(delta_pp) >= 0.1
                            else ("влияет незначительно при текущей оценке")),
            "weight": round(abs(c), 4),
            "direction": "positive" if c > 0 else "negative",
        })
    factors.sort(key=lambda f: -f["weight"])

    positive = [f for f in factors if f["direction"] == "positive"][:top_factors]
    negative = [f for f in factors if f["direction"] == "negative"][:top_factors]

    # --- рекомендации ------------------------------------------------------
    # Для каждого отсутствующего действия считаем, какой была бы вероятность,
    # если бы признак появился. Это не гипотеза, а прямой пересчёт модели.
    recommendations = []
    for name, advice in ACTIONABLE.items():
        if float(case.get(name) or 0) >= 0.5 or name in hidden:
            continue
        if name == "contract_signed_both" and not case.get("has_written_contract"):
            continue
        improved = dict(case)
        improved[name] = 1
        if name in ("has_written_contract", "has_payment_documents",
                    "has_acceptance_act", "has_correspondence",
                    "has_expert_opinion"):
            improved["evidence_count"] = float(case.get("evidence_count") or 0) + 2
            improved["doc_completeness"] = min(
                1.0, float(case.get("doc_completeness") or 0) + 1.0 / 7.0)
        z2, _ = _raw_z(model, improved)
        if z2 - z > 0.05:
            recommendations.append({
                "feature": name,
                "action": advice,
                "gain_pp": round((sigmoid(z2) - p) * 100.0, 1),
                "gain_logodds": round(z2 - z, 3),
                "source": "model",
            })
    recommendations.sort(key=lambda r: -r["gain_logodds"])

    # Критические блокирующие обстоятельства. Это правила, а не вывод модели:
    # когда пропущен срок, «донести документы» — бесполезный совет, и он
    # не должен стоять первым.
    critical = []
    if not float(case.get("limitation_period_ok") or 0):
        critical.append({
            "feature": "limitation_period_ok",
            "action": "Ключевое препятствие — вероятный пропуск срока исковой "
                      "давности. До сбора остальных документов нужно найти "
                      "основания для перерыва или восстановления срока: "
                      "письменное признание долга, направленную претензию, "
                      "документы о болезни или иных уважительных причинах.",
            "gain_pp": None,
            "source": "rule",
        })
    if float(case.get("claim_amount_kzt") or 0) > 3_000_000 and \
            not float(case.get("has_expert_opinion") or 0) and \
            case.get("dispute_category") in ("damage", "construction",
                                             "insurance", "consumer"):
        critical.append({
            "feature": "has_expert_opinion",
            "action": "Заявленная сумма крупная и не подтверждена независимой "
                      "оценкой — это первое, что оспорит другая сторона.",
            "gain_pp": None,
            "source": "rule",
        })

    band = float(model.get("uncertainty_band_pp", 8.0))
    # Показываемую вероятность ограничиваем 2–98 %: на демо-данных модель
    # не имеет оснований заявлять о полной определённости исхода.
    shown = max(2, min(98, int(round(p * 100))))
    return {
        "probability": round(p, 4),
        "probability_pct": shown,
        "range_pct": [max(1, int(round(shown - band))),
                      min(99, int(round(shown + band)))],
        "band_label": _band_label(p),
        "expected_award": _expected_award(model, case, p),
        "critical_issues": critical,
        "positive_factors": positive,
        "negative_factors": negative,
        "recommendations": recommendations[:max_recommendations],
        "model_version": model.get("model_version"),
        "model_quality": model.get("metrics_summary"),
        "disclaimer": DISCLAIMER,
    }
