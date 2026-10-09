# -*- coding: utf-8 -*-
"""Загрузка демонстрационных дел «из коробки»."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DIR = os.path.join(ROOT, "demo_cases")


def _manifest():
    with open(os.path.join(DEMO_DIR, "manifest.json"), encoding="utf-8") as fh:
        return json.load(fh)


def list_cases():
    return [{k: c[k] for k in ("id", "title", "short", "expectation")}
            for c in _manifest()["cases"]]


def load_case(case_id, side="all"):
    """side: 'claimant' — только документы истца (модуль гражданина),
             'all'      — все материалы дела (модуль судьи)."""
    case = next((c for c in _manifest()["cases"] if c["id"] == case_id), None)
    if case is None:
        raise KeyError(case_id)
    docs = []
    for d in case["documents"]:
        if side == "claimant" and d["side"] != "claimant":
            continue
        path = os.path.join(DEMO_DIR, case_id, d["file"])
        with open(path, encoding="utf-8") as fh:
            docs.append({"name": d["title"], "text": fh.read(), "side": d["side"]})
    return {"id": case["id"], "title": case["title"], "documents": docs}
