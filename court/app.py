#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP-сервер демонстрационного прототипа.

Реализован на стандартной библиотеке Python: у рантайма нет ни одной
внешней зависимости. Для судебного контура это не компромисс, а
преимущество — разворачивание не требует доступа к репозиториям пакетов,
а поверхность атаки минимальна.

Переход на FastAPI, если он понадобится ради OpenAPI-схемы, затрагивает
только этот файл: вся логика лежит в core/ и от веб-фреймворка не зависит
(см. app_fastapi.py).

КОНФИДЕНЦИАЛЬНОСТЬ
  * сервер слушает только 127.0.0.1 — извне недоступен;
  * тексты документов не пишутся ни в лог, ни на диск, обрабатываются
    в памяти и удаляются вместе с запросом;
  * исходящих сетевых вызовов в коде нет вообще.

Запуск:  python3 app.py  →  http://127.0.0.1:8000
"""
import base64
import datetime
import json
import mimetypes
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core import demo_data                       # noqa: E402
from core.documents import (SUPPORTED_HINT, DocumentError,   # noqa: E402
                            extract_text)
from core.extraction import get_extractor        # noqa: E402
from core.similar_cases import find_similar      # noqa: E402
from core.judge_analysis import analyze_case     # noqa: E402
from core.predictor import load_model, predict   # noqa: E402
from core.schema import (CATEGORIES, DISCLAIMER, FEATURES,  # noqa: E402
                         INSTANCES, PARTY_TYPES)

WEB_DIR = os.path.join(ROOT, "web")
HOST, PORT = "127.0.0.1", int(os.environ.get("PORT", 8000))
MAX_BODY = 8 * 1024 * 1024

EXTRACTOR = get_extractor(os.environ.get("EXTRACTOR", "rule_based_offline"))


def _clean_features(features):
    """Убирает служебные поля перед передачей в модель."""
    return {k: v for k, v in features.items() if not k.startswith("_")}


def _documents_from_payload(payload, side="all"):
    """Документы из запроса. Возвращает (документы, заголовок, предупреждения).

    Файлы приходят либо готовым текстом, либо в base64 — тогда текст
    извлекается здесь, в памяти, без записи на диск.
    """
    if payload.get("demo_case_id"):
        case = demo_data.load_case(payload["demo_case_id"], side=side)
        return case["documents"], case["title"], []

    docs, notes = [], []
    for d in payload.get("documents", []):
        name = d.get("name") or "документ"
        text = (d.get("text") or "").strip()
        if not text and d.get("data_base64"):
            try:
                raw = base64.b64decode(d["data_base64"])
                text, method, warning = extract_text(name, raw)
                text = (text or "").strip()
                if warning:
                    notes.append("%s: %s" % (name, warning))
                if text:
                    notes.append("%s — текст извлечён (%s)." % (name, method))
            except DocumentError as exc:
                notes.append("%s: %s" % (name, exc))
                continue
            except Exception as exc:                      # noqa: BLE001
                notes.append("%s: не удалось прочитать файл (%s)." % (name, exc))
                continue
        if text:
            docs.append({"name": name, "text": text,
                         "side": d.get("side", "claimant")})
        else:
            notes.append("%s: файл пуст или текст не найден." % name)
    return docs, payload.get("title") or "Загруженные документы", notes


# ---------------------------------------------------------------------------
# Обработчики API
# ---------------------------------------------------------------------------
def api_demo_cases(_payload):
    return {"cases": demo_data.list_cases()}


def api_reference(_payload):
    return {
        "categories": CATEGORIES,
        "party_types": PARTY_TYPES,
        "instances": INSTANCES,
        "features": [{k: f.get(k) for k in ("name", "kind", "group", "label")}
                     for f in FEATURES],
        "disclaimer": DISCLAIMER,
    }


def api_model_info(_payload):
    model = load_model()
    path = os.path.join(ROOT, "models", "metrics.json")
    metrics = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            metrics = json.load(fh)
    return {
        "model_type": model.get("model_type"),
        "model_version": model.get("model_version"),
        "n_train": model.get("n_train"),
        "quality": model.get("metrics_summary"),
        "uncertainty_band_pp": model.get("uncertainty_band_pp"),
        "comparison": metrics.get("test", []),
        "calibration": metrics.get("calibration_logistic_test", []),
        "importance": metrics.get("permutation_importance_top15", []),
        "dataset": metrics.get("dataset", {}),
        "recovery_check": metrics.get("recovery_check", {}),
        "share_model": dict(metrics.get("share_model_test", {}),
                            n_train_used=(model.get("share_model") or {})
                            .get("n_train")),
        "extractor": EXTRACTOR.display_name,
        "supported_formats": SUPPORTED_HINT,
        "disclaimer": model.get("disclaimer"),
    }


def api_citizen_assess(payload):
    """Загруженные документы -> признаки -> вероятность и объяснение."""
    documents, title, notes = _documents_from_payload(payload, side="claimant")
    if not documents:
        return {"error": "Не удалось получить текст ни из одного файла. "
                         + " ".join(notes) + " " + SUPPORTED_HINT}
    extraction = EXTRACTOR.extract(documents, today=datetime.date.today())
    features = _clean_features(extraction.features)
    data = extraction.as_dict()
    data["warnings"] = list(data.get("warnings") or []) + notes
    return {
        "title": title,
        "extraction": data,
        "features": features,
        "assessment": predict(features),
        "similar": find_similar(features),
    }


def api_citizen_recalculate(payload):
    """Пересчёт после ручной правки признаков пользователем.

    Возможность поправить извлечённые данные принципиальна: автоматическое
    извлечение ошибается, и пользователь должен видеть, что оценка меняется
    вслед за исправлением, а не является «чёрным ящиком».
    """
    features = _clean_features(payload.get("features") or {})
    if not features:
        return {"error": "Не переданы признаки дела."}
    return {"features": features, "assessment": predict(features),
            "similar": find_similar(features)}


def api_judge_analyze(payload):
    documents, title, notes = _documents_from_payload(payload, side="all")
    if not documents:
        return {"error": "Не удалось получить текст ни из одного файла. "
                         + " ".join(notes) + " " + SUPPORTED_HINT}
    analysis = analyze_case(documents, today=datetime.date.today())
    analysis["title"] = title
    analysis["warnings"] = list(analysis.get("warnings") or []) + notes
    return analysis


ROUTES = {
    "/api/demo-cases": api_demo_cases,
    "/api/reference": api_reference,
    "/api/model-info": api_model_info,
    "/api/citizen/assess": api_citizen_assess,
    "/api/citizen/recalculate": api_citizen_recalculate,
    "/api/judge/analyze": api_judge_analyze,
}


# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "CourtAIDemo/1.0"

    def log_message(self, fmt, *args):
        # В лог попадают только метод и путь. Тексты документов не логируются.
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, code, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ROUTES:
            try:
                self._send(200, ROUTES[path]({}))
            except Exception as exc:                      # noqa: BLE001
                self._send(500, {"error": str(exc)})
            return
        self._serve_static(path)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        handler = ROUTES.get(path)
        if handler is None:
            self._send(404, {"error": "Неизвестный маршрут"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._send(413, {"error": "Слишком большой объём данных"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except ValueError:
            self._send(400, {"error": "Некорректный JSON"})
            return
        try:
            self._send(200, handler(payload))
        except KeyError as exc:
            self._send(404, {"error": "Не найдено: %s" % exc})
        except Exception as exc:                          # noqa: BLE001
            import traceback
            traceback.print_exc()
            self._send(500, {"error": str(exc)})

    def _serve_static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        target = os.path.normpath(os.path.join(WEB_DIR, path.lstrip("/")))
        if not target.startswith(WEB_DIR) or not os.path.isfile(target):
            self._send(404, "Не найдено", "text/plain; charset=utf-8")
            return
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/javascript":
            ctype += "; charset=utf-8"
        with open(target, "rb") as fh:
            self._send(200, fh.read(), ctype)


def main():
    for required in ("models/model.json", "data/cases.csv"):
        if not os.path.exists(os.path.join(ROOT, required)):
            print("Не найден файл %s.\nСначала выполните:\n"
                  "  python3 scripts/generate_dataset.py\n"
                  "  python3 scripts/train_model.py" % required)
            return 1
    print("Демо запущено:  http://%s:%d" % (HOST, PORT))
    print("Экстрактор:     %s" % EXTRACTOR.display_name)
    print("Остановка:      Ctrl+C\n")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
