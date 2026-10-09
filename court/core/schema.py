# -*- coding: utf-8 -*-
"""
Единая схема признаков дела. Используется генератором датасета,
обучением модели, экстрактором признаков из документов и веб-интерфейсом.

Один источник правды: если признак добавляется — он добавляется здесь.
"""

# ---------------------------------------------------------------------------
# Категории гражданских споров (РК)
# ---------------------------------------------------------------------------

CATEGORIES = {
    "debt_contract": "Взыскание задолженности по договору",
    "labor": "Трудовой спор (зарплата, увольнение)",
    "consumer": "Защита прав потребителей",
    "insurance": "Страховой спор (выплата)",
    "construction": "Договор подряда / качество работ",
    "housing_rent": "Жилищный спор / аренда",
    "damage": "Возмещение ущерба (ДТП, залив, порча)",
    "family_property": "Раздел имущества супругов",
}

PARTY_TYPES = {
    "individual": "Физическое лицо",
    "entrepreneur": "Индивидуальный предприниматель",
    "legal_entity": "Юридическое лицо",
}

INSTANCES = {
    "first": "Первая инстанция",
    "appeal": "Апелляционная инстанция",
}

# ---------------------------------------------------------------------------
# Признаки
#   kind: cat | bin | num
#   group: используется для группировки в интерфейсе
#   label: человекочитаемое название (без юридического жаргона)
# ---------------------------------------------------------------------------

FEATURES = [
    # --- Параметры дела -----------------------------------------------------
    dict(name="dispute_category", kind="cat", group="case", values=list(CATEGORIES),
         label="Категория спора"),
    dict(name="claimant_type", kind="cat", group="case", values=list(PARTY_TYPES),
         label="Кто подаёт иск"),
    dict(name="respondent_type", kind="cat", group="case", values=list(PARTY_TYPES),
         label="Кто отвечает по иску"),
    dict(name="court_instance", kind="cat", group="case", values=list(INSTANCES),
         label="Инстанция"),
    dict(name="claim_amount_kzt", kind="num", group="case",
         label="Сумма требований, тг"),
    dict(name="months_since_breach", kind="num", group="case",
         label="Месяцев с момента нарушения"),

    # --- Документы и доказательства ----------------------------------------
    dict(name="has_written_contract", kind="bin", group="evidence",
         label="Есть письменный договор",
         pos="Договор оформлен письменно",
         neg="Письменного договора нет — отношения придётся доказывать иначе"),
    dict(name="contract_signed_both", kind="bin", group="evidence",
         label="Договор подписан обеими сторонами",
         pos="Договор подписан обеими сторонами",
         neg="В договоре нет подписи второй стороны"),
    dict(name="has_payment_documents", kind="bin", group="evidence",
         label="Есть платёжные документы",
         pos="Есть платёжные документы (переводы, квитанции, выписки)",
         neg="Нет платёжных документов, подтверждающих расчёты"),
    dict(name="has_acceptance_act", kind="bin", group="evidence",
         label="Есть акты приёма-передачи",
         pos="Есть акты приёма-передачи / накладные",
         neg="Нет актов приёма-передачи выполненного"),
    dict(name="has_correspondence", kind="bin", group="evidence",
         label="Есть письменная переписка",
         pos="Есть переписка сторон (письма, мессенджеры)",
         neg="Переписка сторон не приложена"),
    dict(name="has_expert_opinion", kind="bin", group="evidence",
         label="Есть заключение эксперта",
         pos="Есть заключение эксперта / оценка",
         neg="Нет экспертизы, подтверждающей размер требований"),
    dict(name="witness_count", kind="num", group="evidence",
         label="Количество свидетелей"),
    dict(name="evidence_count", kind="num", group="evidence",
         label="Всего документов в деле"),
    dict(name="doc_completeness", kind="num", group="evidence",
         label="Полнота пакета документов (0–1)"),

    # --- Процессуальные факторы --------------------------------------------
    dict(name="pretrial_claim_sent", kind="bin", group="process",
         label="Направлена досудебная претензия",
         pos="Досудебная претензия направлена",
         neg="Досудебная претензия не направлена"),
    dict(name="limitation_period_ok", kind="bin", group="process",
         label="Срок исковой давности не истёк",
         pos="Срок исковой давности соблюдён",
         neg="Срок исковой давности, вероятно, истёк"),
    dict(name="claimant_has_lawyer", kind="bin", group="process",
         label="У истца есть представитель",
         pos="Интересы истца представляет юрист",
         neg="Истец действует без юриста"),
    dict(name="respondent_has_lawyer", kind="bin", group="process",
         label="У ответчика есть представитель",
         pos="У ответчика есть юрист",
         neg="Ответчик без юриста"),
    dict(name="respondent_appeared", kind="bin", group="process",
         label="Ответчик участвует в процессе",
         pos="Ответчик участвует в процессе",
         neg="Ответчик не является в суд"),
    dict(name="respondent_admits_partially", kind="bin", group="process",
         label="Ответчик частично признаёт требования",
         pos="Ответчик частично признаёт требования",
         neg="Ответчик полностью отрицает требования"),
    dict(name="counterclaim_filed", kind="bin", group="process",
         label="Подан встречный иск",
         pos="Ответчик подал встречный иск",
         neg="Встречный иск не подан"),
]

FEATURE_NAMES = [f["name"] for f in FEATURES]
FEATURE_BY_NAME = {f["name"]: f for f in FEATURES}

BINARY_FEATURES = [f["name"] for f in FEATURES if f["kind"] == "bin"]
NUMERIC_FEATURES = [f["name"] for f in FEATURES if f["kind"] == "num"]
CATEGORICAL_FEATURES = [f["name"] for f in FEATURES if f["kind"] == "cat"]

TARGET = "outcome_win"
TARGET_SHARE = "satisfied_share"

DISCLAIMER = (
    "Оценка носит ориентировочный характер и рассчитана на демонстрационных "
    "(синтетических) данных. Это не юридическая консультация и не прогноз "
    "решения суда по конкретному делу."
)
