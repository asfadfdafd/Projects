#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Альтернативная точка входа на FastAPI.

Нужна, если понадобится OpenAPI-схема, встроенная валидация запросов или
интеграция в существующий сервис на FastAPI. Логика не дублируется:
используются те же функции из app.py, которые, в свою очередь, вызывают
core/. Это и есть смысл разделения — веб-фреймворк заменяем.

Основной способ запуска демо — app.py: он не требует зависимостей.

    pip install fastapi "uvicorn[standard]"
    uvicorn app_fastapi:app --host 127.0.0.1 --port 8000
"""
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import app as core_app

ROOT = os.path.dirname(os.path.abspath(__file__))

api = FastAPI(
    title="AI-помощник по гражданским делам (демо)",
    description="Демонстрационный прототип. Оценки ориентировочные, "
                "рассчитаны на синтетических данных и не являются "
                "юридической консультацией.",
    version="demo-1.0.0",
)


class Document(BaseModel):
    name: str = "документ"
    text: str
    side: str = "claimant"


class CaseRequest(BaseModel):
    documents: list[Document] = []
    demo_case_id: str | None = None
    title: str | None = None


class FeaturesRequest(BaseModel):
    features: dict


@api.get("/api/demo-cases")
def demo_cases():
    return core_app.api_demo_cases({})


@api.get("/api/reference")
def reference():
    return core_app.api_reference({})


@api.get("/api/model-info")
def model_info():
    return core_app.api_model_info({})


@api.post("/api/citizen/assess")
def citizen_assess(req: CaseRequest):
    return core_app.api_citizen_assess(req.model_dump())


@api.post("/api/citizen/recalculate")
def citizen_recalculate(req: FeaturesRequest):
    return core_app.api_citizen_recalculate(req.model_dump())


@api.post("/api/judge/analyze")
def judge_analyze(req: CaseRequest):
    return core_app.api_judge_analyze(req.model_dump())


@api.get("/")
def index():
    return FileResponse(os.path.join(ROOT, "web", "index.html"))


api.mount("/", StaticFiles(directory=os.path.join(ROOT, "web"), html=True),
          name="web")

app = api
