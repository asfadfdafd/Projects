# -*- coding: utf-8 -*-
"""
Поиск расхождений между материалами сторон.

Сверка того, что стороны говорят об одних и тех же обстоятельствах, —
механическая работа, на которую при подготовке к заседанию уходит время:
нужно держать в голове цифры из одного документа, читая другой. Здесь она
делается автоматически и полностью офлайн.

Ищутся расхождения двух видов:

1. ЧИСЛОВЫЕ — стороны называют разные суммы по одному и тому же предмету
   (задолженность, оплата труда, размер ущерба, произведённая оплата).

2. ФАКТИЧЕСКИЕ — одна сторона утверждает наличие обстоятельства, другая
   его прямо отрицает («приказ вручён под роспись» против «приказ мне
   не вручался»).

Система не решает, кто прав. Она показывает обе цитаты рядом и оставляет
оценку доказательств суду.
"""


from core.extraction import NEGATIONS, RE_AMOUNT, normalize, parse_amount

# ---------------------------------------------------------------------------
# Предметы, по которым сверяются суммы
# ---------------------------------------------------------------------------
AMOUNT_CONCEPTS = [
    ("debt", "Размер задолженности",
     ["задолженност", "основной долг", "сумма долга", "признаю задолженность",
      "долг в размере"]),
    ("wage", "Размер оплаты труда",
     ["заработная плат", "заработной плат", "должностной оклад", "оклад истца",
      "штатному расписанию", "зарплат"]),
    ("damage", "Размер ущерба",
     ["ущерб", "восстановительного ремонта", "стоимость ремонта",
      "размер ущерба"]),
    ("paid", "Сумма произведённой оплаты",
     ["оплачено", "частичная оплата", "платежным поручением",
      "окончательный расчет", "расчет произведен", "произвел оплату",
      "произвёл частичную оплату"]),
]

# ---------------------------------------------------------------------------
# Обстоятельства, по которым сверяется «есть / нет»
# ---------------------------------------------------------------------------
FACT_CONCEPTS = [
    ("contract", "Наличие письменного договора",
     ["трудовой договор", "договор №", "заключен договор", "по договору"]),
    ("order_served", "Вручение приказа стороне",
     ["приказ об увольнении", "приказ", "ознакомлен"]),
    ("pretrial", "Направление претензии",
     ["претензи", "требование об оплате"]),
    ("notified", "Извещение стороны об осмотре или составлении акта",
     ["извещ", "уведомлен о времени", "надлежаще извещ"]),
    ("act_signed", "Подписание акта стороной",
     ["акт подписан", "подписан обеими сторонами", "от подписания акта"]),
    ("settlement_docs", "Выдача расчётных документов",
     ["расчетные листки", "расчетный листок", "ведомост"]),
]

WINDOW = 220


def _money(value):
    return "{:,.0f}".format(value).replace(",", " ") + " тг"


def _quote(raw, pos, before=40, after=170):
    """Цитата, начинающаяся у самого упоминания, а не вокруг него."""
    start, end = max(0, pos - before), min(len(raw), pos + after)
    text = " ".join(raw[start:end].split())
    return ("…" if start else "") + text + ("…" if end < len(raw) else "")


def _amount_for(concept_keywords, norm, raw):
    """Сумма, названная ближе всего к упоминанию предмета спора.

    Именно ближайшая, а не наибольшая: в отзыве работодателя рядом стоят
    «оклад составлял 210 000 тенге, а не 780 000 тенге, как указано в иске».
    Максимум дал бы 780 000 — то есть позицию противоположной стороны,
    и расхождение исчезло бы.
    """
    best = None
    for keyword in concept_keywords:
        start = 0
        while True:
            pos = norm.find(keyword, start)
            if pos < 0:
                break
            start = pos + len(keyword)
            context = norm[max(0, pos - 140):pos + len(keyword) + 60]
            if any(marker in context for marker in NEGATIONS):
                continue      # «расчёт не был произведён» — это не сумма оплаты
            after = pos + len(keyword)
            window = raw[after:after + WINDOW]
            match = RE_AMOUNT.search(window)
            if not match:
                continue
            value = parse_amount(match.group(1))
            if not value or value < 10_000:
                continue
            distance = match.start()
            if best is None or distance < best[0]:
                best = (distance, value, _quote(raw, pos))
    return best


def _assertions_for(concept_keywords, norm, raw):
    """Сколько раз обстоятельство утверждается и сколько раз отрицается."""
    positive = negative = 0
    pos_quote = neg_quote = None
    for keyword in concept_keywords:
        start = 0
        while True:
            pos = norm.find(keyword, start)
            if pos < 0:
                break
            start = pos + len(keyword)
            window = norm[max(0, pos - 140):pos + len(keyword) + 140]
            if any(marker in window for marker in NEGATIONS):
                negative += 1
                if neg_quote is None:
                    neg_quote = _quote(raw, pos)
            else:
                positive += 1
                if pos_quote is None:
                    pos_quote = _quote(raw, pos)
    return positive, negative, pos_quote, neg_quote


def find_contradictions(claimant_docs, respondent_docs):
    """Возвращает список расхождений между материалами сторон."""
    if not claimant_docs or not respondent_docs:
        return []

    cl_raw = "\n\n".join(d.get("text", "") for d in claimant_docs)
    rs_raw = "\n\n".join(d.get("text", "") for d in respondent_docs)
    cl_norm, rs_norm = normalize(cl_raw), normalize(rs_raw)

    result = []

    # --- расхождения в суммах ---------------------------------------------
    for _, title, keywords in AMOUNT_CONCEPTS:
        cl_found = _amount_for(keywords, cl_norm, cl_raw)
        rs_found = _amount_for(keywords, rs_norm, rs_raw)
        if not cl_found or not rs_found:
            continue
        _, cl_value, cl_quote = cl_found
        _, rs_value, rs_quote = rs_found
        if cl_value == rs_value:
            continue
        # расхождение меньше 2 % — это округление, а не спор
        if abs(cl_value - rs_value) / max(cl_value, rs_value) < 0.02:
            continue
        result.append({
            "type": "amount",
            "title": title,
            "claimant": {"value": _money(cl_value), "quote": cl_quote},
            "respondent": {"value": _money(rs_value), "quote": rs_quote},
            "delta": _money(abs(cl_value - rs_value)),
            "note": "Стороны называют разные суммы по одному предмету. "
                    "Расхождение — %s." % _money(abs(cl_value - rs_value)),
        })

    # --- расхождения по факту ---------------------------------------------
    for _, title, keywords in FACT_CONCEPTS:
        cl_pos, cl_neg, cl_pq, cl_nq = _assertions_for(keywords, cl_norm, cl_raw)
        rs_pos, rs_neg, rs_pq, rs_nq = _assertions_for(keywords, rs_norm, rs_raw)

        # расхождение фиксируется только когда одна сторона обстоятельство
        # утверждает и не отрицает, а другая отрицает и не утверждает
        claimant_says_no = cl_neg > 0 and cl_pos == 0
        respondent_says_yes = rs_pos > 0 and rs_neg == 0
        claimant_says_yes = cl_pos > 0 and cl_neg == 0
        respondent_says_no = rs_neg > 0 and rs_pos == 0

        if claimant_says_no and respondent_says_yes:
            result.append({
                "type": "fact",
                "title": title,
                "claimant": {"value": "отрицает", "quote": cl_nq},
                "respondent": {"value": "утверждает", "quote": rs_pq},
                "note": "Стороны противоположно описывают одно обстоятельство. "
                        "Требуется установить, чем оно подтверждается.",
            })
        elif claimant_says_yes and respondent_says_no:
            result.append({
                "type": "fact",
                "title": title,
                "claimant": {"value": "утверждает", "quote": cl_pq},
                "respondent": {"value": "отрицает", "quote": rs_nq},
                "note": "Стороны противоположно описывают одно обстоятельство. "
                        "Требуется установить, чем оно подтверждается.",
            })

    # числовые расхождения показываем первыми: они конкретнее
    result.sort(key=lambda r: 0 if r["type"] == "amount" else 1)
    return result


def contradiction_questions(contradictions):
    """Вопросы сторонам, вытекающие из найденных расхождений."""
    questions = []
    for item in contradictions:
        if item["type"] == "amount":
            questions.append(
                "«%s»: истец указывает %s, ответчик — %s. Чем каждая сторона "
                "подтверждает свой расчёт?"
                % (item["title"], item["claimant"]["value"],
                   item["respondent"]["value"]))
        else:
            questions.append(
                "«%s»: позиции сторон прямо противоположны. Какими "
                "документами подтверждается каждая из них?" % item["title"])
    return questions
