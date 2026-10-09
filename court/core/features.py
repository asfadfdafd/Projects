# -*- coding: utf-8 -*-
"""
Преобразование карточки дела в вектор признаков.

Один и тот же код используется при обучении и при инференсе — это
устраняет самый частый класс ошибок в ML-системах (train/serve skew).
Модуль написан на чистом Python без внешних зависимостей, поэтому
рантайм демо не требует ни numpy, ни scikit-learn.
"""
import math

from core.schema import (BINARY_FEATURES, CATEGORIES, INSTANCES, PARTY_TYPES)

# Человекочитаемые названия для объяснения предсказания
DERIVED_LABELS = {
    "log_claim_amount": "Размер требований",
    "log_evidence_count": "Объём приложенных документов",
    "doc_completeness": "Полнота пакета документов",
    "witness_count": "Свидетели",
    "months_since_breach": "Давность обращения в суд",
    "resp_lawyer_x_weak_docs": "Юрист у ответчика при слабом пакете документов",
    "expert_x_large_claim": "Экспертиза в деле с крупной суммой",
}


def _one_hot(prefix, value, allowed):
    return [("%s=%s" % (prefix, a), 1.0 if value == a else 0.0) for a in allowed]


def build_feature_vector(case):
    """dict карточки дела -> (список_имён, список_значений).

    Порядок признаков детерминирован и является частью контракта модели:
    он сохраняется в model.json и проверяется при загрузке.
    """
    pairs = []

    # --- категориальные (one-hot) ------------------------------------------
    pairs += _one_hot("category", case.get("dispute_category"), list(CATEGORIES))
    pairs += _one_hot("claimant", case.get("claimant_type"), list(PARTY_TYPES))
    pairs += _one_hot("respondent", case.get("respondent_type"), list(PARTY_TYPES))
    pairs += _one_hot("instance", case.get("court_instance"), list(INSTANCES))

    # --- числовые (сглаженные преобразования) ------------------------------
    amount = float(case.get("claim_amount_kzt") or 0.0)
    log_amount = math.log(max(amount, 1.0))
    evidence = float(case.get("evidence_count") or 0)
    months = min(float(case.get("months_since_breach") or 0), 60.0)
    doc_completeness = float(case.get("doc_completeness") or 0.0)
    witnesses = min(float(case.get("witness_count") or 0), 5.0)

    pairs.append(("log_claim_amount", log_amount))
    pairs.append(("log_evidence_count", math.log1p(evidence)))
    pairs.append(("doc_completeness", doc_completeness))
    pairs.append(("witness_count", witnesses))
    pairs.append(("months_since_breach", months))

    # --- бинарные ----------------------------------------------------------
    for name in BINARY_FEATURES:
        pairs.append((name, float(case.get(name) or 0)))

    # --- взаимодействия ----------------------------------------------------
    # Юрист у ответчика особенно опасен, когда документов мало.
    resp_lawyer = float(case.get("respondent_has_lawyer") or 0)
    pairs.append(("resp_lawyer_x_weak_docs", resp_lawyer * (1.0 - doc_completeness)))
    # Экспертиза критична, когда взыскивается крупная сумма.
    amount_z = (log_amount - 14.2) / 1.15
    pairs.append(("expert_x_large_claim",
                  float(case.get("has_expert_opinion") or 0) * max(0.0, amount_z)))

    names = [p[0] for p in pairs]
    values = [p[1] for p in pairs]
    return names, values


def feature_names():
    """Имена признаков в каноническом порядке."""
    stub = {
        "dispute_category": None, "claimant_type": None, "respondent_type": None,
        "court_instance": None, "claim_amount_kzt": 1.0, "evidence_count": 0,
        "months_since_breach": 0, "doc_completeness": 0.0, "witness_count": 0,
    }
    names, _ = build_feature_vector(stub)
    return names


def humanize(feature_name):
    """Название признака для показа пользователю."""
    from core.schema import FEATURE_BY_NAME

    if feature_name in DERIVED_LABELS:
        return DERIVED_LABELS[feature_name]
    if feature_name in FEATURE_BY_NAME:
        return FEATURE_BY_NAME[feature_name]["label"]
    if "=" in feature_name:
        prefix, value = feature_name.split("=", 1)
        mapping = {
            "category": (CATEGORIES, "Категория спора"),
            "claimant": (PARTY_TYPES, "Истец"),
            "respondent": (PARTY_TYPES, "Ответчик"),
            "instance": (INSTANCES, "Инстанция"),
        }
        if prefix in mapping:
            table, title = mapping[prefix]
            return "%s: %s" % (title, table.get(value, value))
    return feature_name
