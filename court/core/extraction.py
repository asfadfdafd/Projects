# -*- coding: utf-8 -*-
"""
Извлечение структурированных признаков дела из текста документов.

АРХИТЕКТУРНОЕ РЕШЕНИЕ
---------------------
Извлечение спрятано за интерфейсом `Extractor`. В демо работает
`RuleBasedExtractor` — полностью офлайн, без обращения к внешним сервисам:
материалы дела не покидают контур. `LLMExtractor` реализует тот же
интерфейс и подключается заменой одной строки в конфигурации, когда
появится развёрнутая локально языковая модель.

Каждый извлечённый признак сопровождается «сигналом»: из какого документа
и по какому фрагменту текста он получен. Это делает извлечение
проверяемым — пользователь видит основание, а не только результат.
"""
import datetime
import re

from core.schema import CATEGORIES

# ---------------------------------------------------------------------------
# Вспомогательное
# ---------------------------------------------------------------------------
MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11,
    "декабря": 12,
}

RE_DATE_NUM = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b")
RE_DATE_TEXT = re.compile(
    r"[«\"]?(\d{1,2})[»\"]?\s+(" + "|".join(MONTHS) + r")\s+(\d{4})")
# Разряды в сумме разделяются ОДНИМ пробелом. Допускать произвольные
# пробельные последовательности нельзя: в таблицах («…от 30.06.2025
# <много пробелов> 4 850 000 тенге») это склеивает дату с суммой и даёт
# числа в тысячи раз больше настоящих.
RE_AMOUNT = re.compile(
    r"(?<!\d)(\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,2})?"
    r"|\d{4,12}(?:[.,]\d{1,2})?)\s*(?:тенге|тг\.?|kzt|₸)", re.I)


def normalize(text):
    return text.lower().replace("ё", "е").replace(" ", " ")


def _snippet(text, pos, width=90):
    start = max(0, pos - width // 2)
    end = min(len(text), pos + width // 2)
    return ("…" if start else "") + text[start:end].strip().replace("\n", " ") + \
           ("…" if end < len(text) else "")


def parse_dates(text):
    out = []
    for m in RE_DATE_NUM.finditer(text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            out.append((datetime.date(y, mo, d), m.start()))
        except ValueError:
            pass
    for m in RE_DATE_TEXT.finditer(normalize(text)):
        d, mo, y = int(m.group(1)), MONTHS[m.group(2)], int(m.group(3))
        try:
            out.append((datetime.date(y, mo, d), m.start()))
        except ValueError:
            pass
    # сортируем по дате, а внутри даты — по позиции в документе: описание
    # события в основном тексте идёт раньше, чем строка в списке приложений
    return sorted(out, key=lambda t: (t[0], t[1]))


def parse_amount(raw):
    cleaned = raw.replace(" ", "").replace(" ", "")
    if "," in cleaned and cleaned.rfind(",") >= len(cleaned) - 3:
        cleaned = cleaned[:cleaned.rfind(",")]
    cleaned = cleaned.replace(",", "").replace(".", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Словари правил
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS = {
    "debt_contract": [
        ("задолженност", 3), ("основной долг", 3), ("договор займа", 4),
        ("расписк", 3), ("поставк", 2), ("неустойк", 1), ("возврат займа", 4),
        ("не оплатил", 2), ("оплата по договору", 2),
    ],
    "labor": [
        ("трудов", 4), ("увольнен", 4), ("заработной плат", 4), ("зарплат", 3),
        ("работодател", 3), ("восстановлении на работе", 5), ("приказ", 1),
        ("компенсация за неиспользованный отпуск", 4), ("табел", 2),
    ],
    "consumer": [
        ("потребител", 4), ("ненадлежащего качества", 4), ("возврат товара", 4),
        ("гарантийн", 3), ("продавец", 2), ("магазин", 2), ("кассовый чек", 2),
        ("недостатки товара", 4),
    ],
    "insurance": [
        ("страхов", 4), ("полис", 3), ("огпо", 4), ("каско", 4),
        ("страховой случай", 5), ("страховая выплата", 5), ("страховщик", 4),
    ],
    "construction": [
        ("подряд", 5), ("строительн", 3), ("смет", 3),
        ("акт выполненных работ", 3), ("недостатки работ", 4),
        ("ремонтн", 2), ("субподряд", 3),
    ],
    "housing_rent": [
        ("аренд", 4), ("наймодател", 4), ("найма жилого", 5), ("арендатор", 4),
        ("выселен", 4), ("коммунальн", 2), ("квартир", 1),
    ],
    "damage": [
        ("ущерб", 3), ("дтп", 5), ("залив", 5), ("повреждени", 2),
        ("вред имуществу", 4), ("виновник", 3), ("столкновени", 3),
    ],
    "family_property": [
        ("раздел имущества", 5), ("совместно нажит", 5), ("супруг", 4),
        ("расторжении брака", 4), ("алимент", 4), ("брачн", 3),
    ],
}

DOC_KINDS = [
    ("claim", ["исковое заявление", "иск о взыскании", "прошу взыскать"]),
    ("counterclaim", ["встречное исковое", "встречный иск"]),
    ("response", ["возражение на иск", "отзыв на исковое", "возражения ответчика"]),
    ("contract", ["договор №", "договор no", "договор аренды", "договор займа",
                  "договор подряда", "трудовой договор", "договор поставки"]),
    ("act", ["акт приема-передачи", "акт приемки", "акт выполненных работ",
             "накладная", "акт сверки"]),
    ("payment", ["платежное поручение", "квитанция", "кассовый чек",
                 "выписка по счету", "чек о переводе", "приходный кассовый ордер"]),
    ("pretrial", ["претензия", "досудебная претензия", "требование об оплате"]),
    ("correspondence", ["переписка", "whatsapp", "электронной почте",
                        "скриншот переписки", "телеграм"]),
    ("expert", ["заключение эксперта", "заключение специалиста", "экспертиз",
                "отчет об оценке", "оценочный отчет"]),
    ("witness", ["показания свидетел", "свидетельские показания",
                 "объяснение свидетеля"]),
    ("power_of_attorney", ["доверенность"]),
]

ORG_MARKERS = ["тоо ", "ао ", "оао", "зао", "товарищество с ограниченной",
               "акционерное общество", "ооо "]
IE_MARKERS = ["ип ", "индивидуальный предприниматель"]

# Отрицания. Без их учёта экстрактор принимает фразу «трудовой договор мне
# не выдавался» за наличие договора — то есть завышает оценку шансов.
# Ложноположительное срабатывание здесь опаснее пропуска, поэтому
# проверка отрицаний обязательна для всех признаков-доказательств.
NEGATIONS = [
    "не выдавал", "не выдан", "отсутству", "не заключал", "не составлял",
    "не сохранил", "не имеется", "не представлен", "не приложен",
    "не оформлял", "не вручал", "не направлял", "не обращал",
    "не подтвержда", "не могу", "не составлялась", "не выдавались",
    "не заключался", "у меня нет", "не располагаю",
    "не произвед", "не был произвед", "не выплач", "не оплач", "не выплатил",
]

RE_FIO = re.compile(r"\b([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ])\.\s*([А-ЯЁ])\.")


# ---------------------------------------------------------------------------
# Результат
# ---------------------------------------------------------------------------
class ExtractionResult(object):
    def __init__(self):
        self.features = {}
        self.signals = []      # [{feature, value, document, snippet, rule}]
        self.documents = []    # [{name, kind, kind_label, chars, dates}]
        self.timeline = []     # [{date, event, document}]
        self.warnings = []
        self.extractor = None

    def add(self, feature, value, document=None, snippet=None, rule=None):
        self.features[feature] = value
        self.signals.append({
            "feature": feature, "value": value, "document": document,
            "snippet": snippet, "rule": rule,
        })

    def as_dict(self):
        return {
            "features": self.features,
            "signals": self.signals,
            "documents": self.documents,
            "timeline": self.timeline,
            "warnings": self.warnings,
            "extractor": self.extractor,
        }


KIND_LABELS = {
    "claim": "Исковое заявление", "counterclaim": "Встречный иск",
    "response": "Возражение / отзыв ответчика", "contract": "Договор",
    "act": "Акт / накладная", "payment": "Платёжный документ",
    "pretrial": "Досудебная претензия", "correspondence": "Переписка сторон",
    "expert": "Заключение эксперта / оценка", "witness": "Показания свидетеля",
    "power_of_attorney": "Доверенность", "other": "Прочий документ",
}


# ---------------------------------------------------------------------------
# Правиловый экстрактор
# ---------------------------------------------------------------------------
class RuleBasedExtractor(object):
    """Офлайн-извлечение признаков. Никаких сетевых вызовов."""

    name = "rule_based_offline"
    display_name = "Правиловый экстрактор (офлайн)"

    def extract(self, documents, today=None):
        today = today or datetime.date.today()
        res = ExtractionResult()
        res.extractor = self.display_name

        joined_raw = "\n\n".join(d.get("text", "") for d in documents)
        joined = normalize(joined_raw)

        kinds = set()
        for doc in documents:
            raw = doc.get("text", "")
            norm = normalize(raw)
            name = doc.get("name", "документ")
            kind = self._detect_kind(name, norm)
            kinds.add(kind)
            dates = [d.isoformat() for d, _ in parse_dates(raw)]
            res.documents.append({
                "name": name, "kind": kind, "kind_label": KIND_LABELS[kind],
                "chars": len(raw), "dates": dates[:6],
            })

        self._category(res, joined, joined_raw)
        self._amount(res, joined, joined_raw)
        self._parties(res, joined, joined_raw)
        self._instance(res, joined, joined_raw)
        self._evidence_flags(res, joined, joined_raw, kinds, documents)
        self._process_flags(res, joined, joined_raw, kinds)
        self._timeline_and_limitation(res, documents, today)
        self._aggregates(res, documents)

        return res

    # -- отдельные группы правил -------------------------------------------
    def _find(self, norm, raw, needles):
        for n in needles:
            pos = norm.find(n)
            if pos >= 0:
                return pos, _snippet(raw, pos)
        return -1, None

    def _detect_kind(self, name, norm):
        head = normalize(name) + " " + norm[:600]
        for kind, needles in DOC_KINDS:
            if any(n in head for n in needles):
                return kind
        for kind, needles in DOC_KINDS:
            if any(n in norm for n in needles):
                return kind
        return "other"

    def _category(self, res, norm, raw):
        scores, best_hit = {}, {}
        for cat, kws in CATEGORY_KEYWORDS.items():
            score, hit = 0, None
            for kw, weight in kws:
                cnt = norm.count(kw)
                if cnt:
                    score += weight * min(cnt, 4)
                    if hit is None:
                        hit = _snippet(raw, norm.find(kw))
            scores[cat] = score
            best_hit[cat] = hit
        cat = max(scores, key=lambda c: scores[c])
        if scores[cat] == 0:
            cat = "debt_contract"
            res.warnings.append(
                "Категория спора не определена по тексту — использована "
                "категория по умолчанию. Проверьте и при необходимости измените её.")
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        res.add("dispute_category", cat, rule="ключевые слова категории",
                snippet=best_hit.get(cat))
        res.features["_category_scores"] = [
            {"category": c, "label": CATEGORIES[c], "score": s}
            for c, s in ranked if s > 0][:4]

    def _amount(self, res, norm, raw):
        anchors = ["прошу взыскать", "цена иска", "взыскать с ответчика",
                   "сумма задолженности", "общая сумма", "итого"]
        best = None
        for anchor in anchors:
            pos = norm.find(anchor)
            if pos < 0:
                continue
            window = raw[pos:pos + 400]
            m = RE_AMOUNT.search(window)
            if m:
                val = parse_amount(m.group(1))
                if val and val >= 1000:
                    best = (val, _snippet(raw, pos, 140))
                    break
        if best is None:
            candidates = [parse_amount(m.group(1)) for m in RE_AMOUNT.finditer(raw)]
            candidates = [c for c in candidates if c and c >= 1000]
            if candidates:
                best = (max(candidates), None)
                res.warnings.append(
                    "Сумма требований определена как наибольшая сумма в тексте — "
                    "проверьте значение.")
        if best is None:
            res.add("claim_amount_kzt", 500_000.0,
                    rule="значение по умолчанию (сумма не найдена)")
            res.warnings.append("Сумма требований в документах не найдена.")
        else:
            res.add("claim_amount_kzt", best[0], rule="сумма рядом с формулировкой "
                    "требования", snippet=best[1])

    def _party_type(self, fragment):
        f = normalize(fragment)
        if any(m in f for m in ORG_MARKERS):
            return "legal_entity"
        if any(m in f for m in IE_MARKERS):
            return "entrepreneur"
        return "individual"

    def _parties(self, res, norm, raw):
        def grab(labels):
            """Берём фрагмент от метки стороны, обрезая его перед меткой
            другой стороны — иначе «ИСТЕЦ: Иванов ... ОТВЕТЧИК: ТОО ...»
            приводит к тому, что истец определяется как юридическое лицо."""
            for lab in labels:
                pos = norm.find(lab)
                if pos < 0:
                    continue
                frag = raw[pos:pos + 200]
                tail = normalize(frag)[len(lab):]
                cut = min([c for c in (tail.find("ответчик"), tail.find("истец"),
                                       tail.find("\n\n"))
                           if c >= 0] or [len(tail)])
                return frag[:len(lab) + cut], pos
            return "", -1

        c_frag, c_pos = grab(["истец:", "истец ", "взыскатель:"])
        r_frag, r_pos = grab(["ответчик:", "ответчик ", "должник:"])
        res.add("claimant_type", self._party_type(c_frag),
                rule="организационная форма истца",
                snippet=_snippet(raw, c_pos) if c_pos >= 0 else None)
        res.add("respondent_type", self._party_type(r_frag),
                rule="организационная форма ответчика",
                snippet=_snippet(raw, r_pos) if r_pos >= 0 else None)

    def _instance(self, res, norm, raw):
        pos, snip = self._find(norm, raw, ["апелляционн", "апелляционная жалоба"])
        res.add("court_instance", "appeal" if pos >= 0 else "first",
                rule="упоминание апелляции", snippet=snip)

    @staticmethod
    def _sentence_at(raw, pos, max_len=250):
        """Предложение, в котором встретилась дата (а не обрывок текста).

        Учитывает две особенности судебных документов: текст жёстко разбит
        по ширине строки (одиночный перенос не заканчивает предложение) и
        насыщен инициалами («Жумабаев Б. К.»), где точка не является концом
        предложения.
        """
        lo, hi = max(0, pos - 320), min(len(raw), pos + 320)
        rel = pos - lo
        # одиночные переносы -> пробелы (длина сохраняется, позиции не плывут)
        flat = re.sub(r"(?<!\n)\n(?!\n)", " ", raw[lo:hi])

        bounds = [m.start() for m in
                  re.finditer(r"(?<![А-ЯЁA-Z])[.;]\s|\n\n", flat)]
        left = max([b + 2 for b in bounds if b + 2 <= rel] or [0])
        right = min([b + 1 for b in bounds if b >= rel] or
                    [min(len(flat), rel + max_len)])
        return " ".join(flat[left:right].split())[:max_len].strip(" .;")

    def _scan(self, norm, raw, needles, exclusions=()):
        """Считает упоминания признака, отделяя утверждения от отрицаний.

        Возвращает (утверждений, отрицаний, фрагмент_утверждения,
        фрагмент_отрицания).
        """
        pos_cnt = neg_cnt = 0
        pos_snip = neg_snip = None
        for needle in needles:
            start = 0
            while True:
                p = norm.find(needle, start)
                if p < 0:
                    break
                start = p + len(needle)
                if any(x in norm[max(0, p - 10):p + len(needle) + 50]
                       for x in exclusions):
                    continue
                window = norm[max(0, p - 130):p + len(needle) + 130]
                if any(g in window for g in NEGATIONS):
                    neg_cnt += 1
                    if neg_snip is None:
                        neg_snip = _snippet(raw, p, 130)
                else:
                    pos_cnt += 1
                    if pos_snip is None:
                        pos_snip = _snippet(raw, p)
        return pos_cnt, neg_cnt, pos_snip, neg_snip

    def _evidence_flags(self, res, norm, raw, kinds, documents):
        def flag(feature, needles, kind=None, exclusions=()):
            if kind and kind in kinds:
                doc = next(d["name"] for d in res.documents if d["kind"] == kind)
                res.add(feature, 1, document=doc,
                        rule="в деле есть документ типа «%s»" % KIND_LABELS[kind])
                return
            pos_cnt, neg_cnt, pos_snip, neg_snip = self._scan(
                norm, raw, needles, exclusions)
            if pos_cnt:
                res.add(feature, 1, snippet=pos_snip, rule="упоминание в тексте")
            elif neg_cnt:
                res.add(feature, 0, snippet=neg_snip,
                        rule="в тексте прямо указано на отсутствие документа")
            else:
                res.add(feature, 0, rule="упоминаний в материалах не найдено")

        flag("has_written_contract",
             ["договор №", "заключен договор", "по договору", "трудовой договор",
              "договором"],
             kind="contract")
        flag("has_payment_documents",
             ["платежное поручение", "квитанц", "кассовый чек", "выписка по счет",
              "перевод на сумму", "оплатил"], kind="payment",
             exclusions=["государственной пошлины", "госпошлин"])
        flag("has_acceptance_act",
             ["акт приема-передачи", "акт выполненных работ", "накладная",
              "акт сверки"], kind="act")
        flag("has_correspondence",
             ["переписк", "whatsapp", "электронной почте", "письмо от"],
             kind="correspondence")
        flag("has_expert_opinion",
             ["заключение эксперт", "экспертиз", "отчет об оценке",
              "заключение специалиста", "оценщик"], kind="expert",
             exclusions=["назначить", "ходатайств", "провести судебн"])

        # подписи в договоре
        if res.features.get("has_written_contract"):
            pos, snip = self._find(norm, raw, [
                "подписан обеими сторонами", "подписи сторон",
                "стороны подписали", "подпись заказчика", "подписан сторонами"])
            if pos >= 0:
                res.add("contract_signed_both", 1, snippet=snip,
                        rule="прямое указание на подписи сторон")
            else:
                unsigned, snip2 = self._find(norm, raw, [
                    "не подписан", "отсутствует подпись", "без подписи"])
                if unsigned >= 0:
                    res.add("contract_signed_both", 0, snippet=snip2,
                            rule="указание на отсутствие подписи")
                else:
                    res.add("contract_signed_both", 1,
                            rule="договор приложен, признаков отсутствия подписи нет")
        else:
            res.add("contract_signed_both", 0, rule="письменного договора нет")

        # свидетели: считаем уникальные ФИО рядом с упоминанием свидетеля,
        # а не число самих упоминаний (иначе один свидетель, названный
        # трижды, превращается в трёх)
        surnames, snip = set(), None
        for m in re.finditer(r"свидетел|показани|очевидц", norm):
            if snip is None:
                snip = _snippet(raw, m.start(), 130)
            for fio in RE_FIO.finditer(raw[m.start():m.start() + 220]):
                surnames.add(fio.group(1)[:5].lower())
        if surnames:
            witnesses = len(surnames)
        else:
            witnesses = 1 if snip else 0
        res.add("witness_count", min(witnesses, 5), snippet=snip,
                rule="уникальные ФИО рядом с упоминанием свидетелей")

    def _process_flags(self, res, norm, raw, kinds):
        pos, snip = self._find(norm, raw, ["претензи", "требование об оплате"])
        sent = pos >= 0 and any(
            w in norm for w in ["направлен", "вручен", "отправлен", "получена"])
        res.add("pretrial_claim_sent", 1 if (sent or "pretrial" in kinds) else 0,
                snippet=snip, rule="упоминание направленной претензии")

        pos, snip = self._find(norm, raw, ["доверенност", "представитель истца",
                                           "адвокат истца"])
        res.add("claimant_has_lawyer", 1 if pos >= 0 else 0, snippet=snip,
                rule="упоминание представителя истца")

        pos, snip = self._find(norm, raw, ["представитель ответчика",
                                           "адвокат ответчика",
                                           "юрист ответчика"])
        res.add("respondent_has_lawyer", 1 if pos >= 0 else 0, snippet=snip,
                rule="упоминание представителя ответчика")

        absent, snip_a = self._find(norm, raw, [
            "не явился", "не явилась", "извещен надлежаще, не явился",
            "уклоняется от участия"])
        appeared = ("response" in kinds or "counterclaim" in kinds
                    or self._find(norm, raw, ["возражени", "отзыв на иск"])[0] >= 0)
        res.add("respondent_appeared", 0 if (absent >= 0 and not appeared) else
                (1 if appeared else 1), snippet=snip_a,
                rule="участие ответчика по материалам дела")

        pos, snip = self._find(norm, raw, [
            "частично признает", "признает частично", "признает требования в части",
            "согласен частично", "признал долг в размере"])
        res.add("respondent_admits_partially", 1 if pos >= 0 else 0, snippet=snip,
                rule="признание требований ответчиком")

        pos, snip = self._find(norm, raw, ["встречный иск", "встречное исковое"])
        res.add("counterclaim_filed",
                1 if (pos >= 0 or "counterclaim" in kinds) else 0, snippet=snip,
                rule="наличие встречного иска")

    def _timeline_and_limitation(self, res, documents, today):
        # Одна и та же дата упоминается в нескольких документах. Показывать
        # её несколько раз бессмысленно: для каждой даты берём одно наиболее
        # информативное предложение и указываем, сколько документов её
        # подтверждают.
        by_date = {}
        for doc in documents:
            raw = doc.get("text", "")
            for d, pos in parse_dates(raw):
                if d > today + datetime.timedelta(days=1):
                    continue
                sentence = self._sentence_at(raw, pos)
                entry = by_date.setdefault(d.isoformat(), {
                    "date": d.isoformat(), "event": sentence,
                    "document": doc.get("name", "документ"), "sources": set()})
                entry["sources"].add(doc.get("name", "документ"))
                # оставляем первое содержательное описание события: документы
                # идут в порядке от искового заявления, и его формулировка
                # информативнее, чем строка из списка приложений
                if len(entry["event"]) < 60 < len(sentence):
                    entry["event"] = sentence
                    entry["document"] = doc.get("name", "документ")

        timeline = []
        for e in sorted(by_date.values(), key=lambda x: x["date"]):
            e["mentioned_in"] = len(e.pop("sources"))
            timeline.append(e)
        res.timeline = timeline[:14]

        if timeline:
            first = datetime.date.fromisoformat(timeline[0]["date"])
            months = max(1, int((today - first).days / 30.4))
        else:
            months = 6
            res.warnings.append(
                "В документах не найдено дат — давность обращения оценена условно.")
        res.add("months_since_breach", min(months, 240),
                rule="от самой ранней даты в материалах до текущей даты",
                snippet=timeline[0]["event"] if timeline else None)

        interrupted = bool(res.features.get("pretrial_claim_sent")) or \
            bool(res.features.get("respondent_admits_partially"))
        if months >= 36 and not interrupted:
            res.add("limitation_period_ok", 0,
                    rule="прошло более 3 лет (общий срок исковой давности), "
                         "признаков перерыва срока не найдено")
        else:
            res.add("limitation_period_ok", 1,
                    rule="срок исковой давности, по имеющимся данным, соблюдён")

    def _aggregates(self, res, documents):
        f = res.features
        doc_flags = [f.get("has_written_contract", 0), f.get("has_payment_documents", 0),
                     f.get("has_acceptance_act", 0), f.get("has_correspondence", 0),
                     f.get("has_expert_opinion", 0), f.get("pretrial_claim_sent", 0),
                     f.get("contract_signed_both", 0)]
        res.add("doc_completeness", round(sum(doc_flags) / len(doc_flags), 3),
                rule="доля присутствующих типов подтверждающих документов")

        attachments = 0
        for doc in documents:
            norm = normalize(doc.get("text", ""))
            pos = norm.find("приложени")
            if pos >= 0:
                attachments += len(re.findall(r"^\s*\d+[).]", doc["text"][pos:],
                                              re.M))
        count = max(len(documents), attachments, 1) + f.get("witness_count", 0)
        res.add("evidence_count", min(int(count), 40),
                rule="документы в деле и позиции в списке приложений")


# ---------------------------------------------------------------------------
# LLM-экстрактор (интерфейс на будущее)
# ---------------------------------------------------------------------------
class LLMExtractor(object):
    """Тот же интерфейс, но признаки извлекает языковая модель.

    Не используется в демо: выбран полностью офлайн-режим. Подключается
    заменой EXTRACTOR в core/config.py, когда в контуре будет развёрнута
    локальная модель (llama.cpp / Ollama / vLLM). Ожидаемый контракт:
    модель возвращает строгий JSON по схеме core.schema.FEATURES, после
    чего результат проходит ту же валидацию, что и правиловый вывод.
    """

    name = "llm"
    display_name = "LLM-экстрактор (не активен в демо)"

    def __init__(self, client=None):
        self.client = client

    def extract(self, documents, today=None):
        raise NotImplementedError(
            "LLM-экстрактор отключён: демо работает в офлайн-режиме. "
            "Схема признаков и валидация переиспользуются без изменений.")


def get_extractor(name="rule_based_offline"):
    return {"rule_based_offline": RuleBasedExtractor, "llm": LLMExtractor}[name]()
