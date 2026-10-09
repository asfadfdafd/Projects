# -*- coding: utf-8 -*-
"""
Сквозная проверка демо: поднимает сервер, прогоняет оба сценария
на всех демо-делах и проверяет, что результат осмысленный.

Проверяются не только коды ответов, но и содержательные инварианты:
  * вероятность лежит в допустимом диапазоне и согласована с диапазоном оценки;
  * сильное дело оценивается выше слабого (иначе демо разваливается на показе);
  * дело с пропущенным сроком получает критическое предупреждение;
  * каждый показанный фактор имеет человекочитаемую формулировку;
  * модуль судьи не возвращает вероятность исхода;
  * рекомендации не противоречат категории спора.

Запуск:  python3 scripts/smoke_test.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

BASE = "http://127.0.0.1:8011"
FAILURES = []
CHECKS = [0]


def check(condition, message):
    CHECKS[0] += 1
    if condition:
        print("  ok   %s" % message)
    else:
        print("  FAIL %s" % message)
        FAILURES.append(message)


def _has_probability_value(node):
    """Есть ли где-нибудь в ответе поле с оценкой вероятности исхода.

    Проверяется именно наличие поля со значением, а не подстроки: слово
    probability законно встречается в имени поля-пояснения о том, почему
    вероятность судье не показывается.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("probability", "probability_pct", "assessment",
                       "band_label") and value is not None:
                return True
            if _has_probability_value(value):
                return True
    elif isinstance(node, list):
        return any(_has_probability_value(x) for x in node)
    return False


def call(path, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    env = dict(os.environ, PORT="8011")
    server = subprocess.Popen([sys.executable, os.path.join(ROOT, "app.py")],
                              cwd=ROOT, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(BASE + "/api/demo-cases", timeout=1)
                break
            except (urllib.error.URLError, OSError):
                time.sleep(0.25)
        else:
            print("Сервер не поднялся")
            print(server.stderr.read().decode("utf-8", "replace")[:2000])
            return 1

        print("\n[1] Статические страницы")
        for page in ("/", "/citizen.html", "/judge.html", "/model.html",
                     "/style.css", "/common.js"):
            with urllib.request.urlopen(BASE + page, timeout=10) as r:
                check(r.status == 200 and len(r.read()) > 200,
                      "страница %s отдаётся" % page)

        print("\n[2] Справочники и модель")
        info = call("/api/model-info")
        check(info["quality"]["roc_auc"] > 0.72,
              "ROC-AUC %.3f выше порога полезности" % info["quality"]["roc_auc"])
        check(info["quality"]["roc_auc"] < 0.97,
              "ROC-AUC не подозрительно высокий (нет утечки целевой переменной)")
        check(len(info["calibration"]) >= 6, "калибровочная таблица заполнена")
        check(0 < info["uncertainty_band_pp"] < 20,
              "диапазон неопределённости правдоподобен (%s п.п.)"
              % info["uncertainty_band_pp"])
        check(info["recovery_check"]["corr_pred_vs_true_probability"] > 0.9,
              "модель восстановила заложенную причинную структуру")

        print("\n[3] Модуль гражданина на демо-делах")
        cases = call("/api/demo-cases")["cases"]
        check(len(cases) == 3, "доступны 3 демо-дела")
        probs = {}
        for c in cases:
            res = call("/api/citizen/assess", {"demo_case_id": c["id"]})
            a = res["assessment"]
            probs[c["id"]] = a["probability_pct"]
            print("  — %s: %d%%" % (c["title"][:46], a["probability_pct"]))
            check(2 <= a["probability_pct"] <= 98,
                  "  вероятность в допустимых границах")
            check(a["range_pct"][0] <= a["probability_pct"] <= a["range_pct"][1],
                  "  оценка внутри своего диапазона")
            check(all(f.get("text") and f.get("effect_text")
                      for f in a["positive_factors"] + a["negative_factors"]),
                  "  все факторы имеют формулировку для пользователя")
            check(bool(a["disclaimer"]), "  дисклеймер присутствует")

        check(probs["case_01_postavka"] > probs["case_02_zaliv"] >
              probs["case_03_trud"],
              "сильное дело оценено выше среднего, среднее — выше слабого")
        check(probs["case_01_postavka"] - probs["case_03_trud"] > 40,
              "разрыв между сильным и слабым делом заметен на показе")

        print("\n[4] Критические предупреждения и применимость советов")
        trud = call("/api/citizen/assess", {"demo_case_id": "case_03_trud"})
        check(any(i["feature"] == "limitation_period_ok"
                  for i in trud["assessment"]["critical_issues"]),
              "по делу с пропущенным сроком выдано предупреждение о давности")
        check(trud["features"]["has_written_contract"] == 0,
              "фраза «договор мне не выдавался» распознана как отсутствие договора")

        zaliv = call("/api/citizen/assess", {"demo_case_id": "case_02_zaliv"})
        advice = [r["feature"] for r in zaliv["assessment"]["recommendations"]]
        check("has_written_contract" not in advice,
              "по делу о заливе не советуют приложить договор")
        check(all("Договор" not in f["label"] for f in
                  zaliv["assessment"]["negative_factors"]),
              "по делу о заливе договор не показан как слабое место")

        print("\n[5] Пересчёт после правки пользователем")
        base = zaliv["assessment"]["probability_pct"]
        edited = dict(zaliv["features"])
        edited["pretrial_claim_sent"] = 1
        edited["doc_completeness"] = min(1.0, edited["doc_completeness"] + 1 / 7.0)
        after = call("/api/citizen/recalculate",
                     {"features": edited})["assessment"]["probability_pct"]
        check(after > base,
              "исправление признака меняет оценку в ожидаемую сторону "
              "(%d%% -> %d%%)" % (base, after))

        print("\n[6] Модуль судьи")
        for c in cases:
            a = call("/api/judge/analyze", {"demo_case_id": c["id"]})
            print("  — %s: спорных точек %d, вопросов %d, событий %d"
                  % (c["title"][:40], len(a["issues"]), len(a["questions"]),
                     len(a["timeline"])))
            check(len(a["issues"]) >= 3, "  найдены спорные точки")
            check(len(a["questions"]) >= 5, "  сформированы вопросы сторонам")
            check(len(a["timeline"]) >= 3, "  построена хронология")
            check(a["overview"]["claim_amount"] != "—", "  определена цена иска")
            check(not _has_probability_value(a),
                  "  вероятность исхода судье не показывается")
            dates = [t["date"] for t in a["timeline"]]
            check(dates == sorted(dates), "  хронология упорядочена по датам")
            check(len(dates) == len(set(dates)), "  даты в хронологии не дублируются")

        postavka = call("/api/judge/analyze", {"demo_case_id": "case_01_postavka"})
        check(any(i["id"] == "quality_defect" and i["contested"]
                  for i in postavka["issues"]),
              "спор о качестве товара распознан как расхождение позиций")
        check(len(postavka["respondent_arguments"]) >= 3,
              "доводы ответчика разобраны по пунктам")

        trud_j = call("/api/judge/analyze", {"demo_case_id": "case_03_trud"})
        check(any(i["id"] == "limitation" for i in trud_j["issues"]),
              "по трудовому делу поднят вопрос исковой давности")
        check(any(c["status"] == "warn" and
                  "давност" in (c["item"] + " " + c["note"]).lower()
                  for c in trud_j["checklist"]),
              "чек-лист отмечает риск по сроку давности")

        zaliv_j = call("/api/judge/analyze", {"demo_case_id": "case_02_zaliv"})
        check(not any(i["id"] == "quality_defect" for i in zaliv_j["issues"]),
              "по делу о заливе не поднимается вопрос приёмки товара")
        check(any(i["id"] == "expertise_motion" for i in zaliv_j["issues"]),
              "ходатайство о судебной экспертизе замечено")

        print("\n[7] Ожидаемая сумма взыскания")
        for case_id in ("case_01_postavka", "case_02_zaliv"):
            res = call("/api/citizen/assess", {"demo_case_id": case_id})
            award = res["assessment"]["expected_award"]
            claim = award["claim_amount"]
            print("  — %s: иск %s тг, ожидаемое взыскание %s тг (%d %%)"
                  % (case_id, "{:,.0f}".format(claim).replace(",", " "),
                     "{:,.0f}".format(award["expected_award"]).replace(",", " "),
                     award["expected_share_pct"]))
            check(0 < award["award_if_won"] <= claim,
                  "  присуждаемая сумма не превышает заявленную")
            check(award["expected_award"] <= award["award_if_won"],
                  "  оценка с учётом вероятности не выше суммы при выигрыше")
            check(15 <= award["expected_share_pct"] <= 100,
                  "  доля удовлетворения в допустимых границах")

        print("\n[8] Похожие дела")
        for case_id in ("case_01_postavka", "case_03_trud"):
            res = call("/api/citizen/assess", {"demo_case_id": case_id})
            similar = res["similar"]
            model_pct = res["assessment"]["probability_pct"]
            neighbours_pct = similar["win_rate"] * 100
            print("  — %s: модель %d %%, похожие дела %.0f %% (из %d)"
                  % (case_id, model_pct, neighbours_pct, similar["n"]))
            check(similar["n"] >= 20, "  подборка достаточного размера")
            check(similar["examples"], "  показаны конкретные дела")
            check(abs(model_pct - neighbours_pct) <= 25,
                  "  оценка модели согласуется с исходами похожих дел")

        print("\n[9] Расхождения между материалами сторон")
        postavka = call("/api/judge/analyze", {"demo_case_id": "case_01_postavka"})
        debt = next((d for d in postavka["contradictions"]
                     if d["title"] == "Размер задолженности"), None)
        check(debt is not None, "спор о размере задолженности найден")
        if debt:
            print("     истец %s против ответчика %s"
                  % (debt["claimant"]["value"], debt["respondent"]["value"]))
            check("4 850 000" in debt["claimant"]["value"]
                  and "3 100 000" in debt["respondent"]["value"],
                  "суммы извлечены верно, без склейки с датами")
            check(debt["claimant"]["quote"] and debt["respondent"]["quote"],
                  "обе позиции подтверждены цитатами")

        trud = call("/api/judge/analyze", {"demo_case_id": "case_03_trud"})
        wage = next((d for d in trud["contradictions"]
                     if d["title"] == "Размер оплаты труда"), None)
        check(wage is not None and "210 000" in wage["respondent"]["value"],
              "взята сумма, ближайшая к предмету спора, а не наибольшая")
        check(any(d["type"] == "fact" for d in trud["contradictions"]),
              "найдено расхождение по факту (утверждение против отрицания)")
        check(any("Расхождения" in q["issue"] for q in trud["questions"][:3]),
              "вопросы по расхождениям идут первыми")

        zaliv = call("/api/judge/analyze", {"demo_case_id": "case_02_zaliv"})
        check(isinstance(zaliv["contradictions"], list),
              "отсутствие расхождений не ломает разбор")

        print("\n[10] Загрузка файлов разных форматов")
        import base64
        import io as _io
        import zipfile as _zip
        with open(os.path.join(ROOT, "demo_cases", "case_03_trud",
                               "01_iskovoe_zayavlenie.txt"), encoding="utf-8") as fh:
            source = fh.read()
        buffer = _io.BytesIO()
        with _zip.ZipFile(buffer, "w", _zip.ZIP_DEFLATED) as archive:
            body = "".join(
                '<w:p><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>'
                % line.replace("&", "&amp;").replace("<", "&lt;")
                for line in source.split("\n"))
            archive.writestr(
                "word/document.xml",
                '<?xml version="1.0"?><w:document xmlns:w="http://schemas.'
                'openxmlformats.org/wordprocessingml/2006/main"><w:body>%s'
                '</w:body></w:document>' % body)
        docx = call("/api/citizen/assess", {"documents": [{
            "name": "иск.docx",
            "data_base64": base64.b64encode(buffer.getvalue()).decode()}]})
        check(not docx.get("error"), "docx принят сервером")
        check(docx["features"]["claim_amount_kzt"] == 2340000.0,
              "сумма требований извлечена из docx")
        check(docx["assessment"]["probability_pct"] <= 10,
              "оценка по docx совпадает по смыслу с разбором txt")
        check(any("извлечён" in w for w in docx["extraction"]["warnings"]),
              "пользователю сообщается, каким способом получен текст")

        broken = call("/api/citizen/assess", {"documents": [{
            "name": "скан.pdf", "data_base64": base64.b64encode(
                b"%PDF-1.4\n" + b"\x00" * 400).decode()}]})
        check(broken.get("error") and "PDF" in broken["error"],
              "нечитаемый PDF даёт понятное сообщение, а не сбой")

        print("\n[11] Обработка ошибок")
        check(call("/api/citizen/assess", {"documents": []}).get("error"),
              "пустой запрос отклоняется с понятной ошибкой")

        print("\n" + "=" * 62)
        print("Проверок выполнено: %d, провалено: %d" % (CHECKS[0], len(FAILURES)))
        if FAILURES:
            for f in FAILURES:
                print("  FAIL %s" % f)
            return 1
        print("Все проверки пройдены.")
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    sys.exit(main())
