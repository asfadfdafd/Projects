#!/usr/bin/env bash
# Полный запуск демо: данные -> модель -> проверка -> сервер.
set -e
cd "$(dirname "$0")"

PY=${PYTHON:-python3}

echo "== 1/4  Генерация демо-датасета =="
$PY scripts/generate_dataset.py

echo
echo "== 2/4  Обучение модели =="
$PY scripts/train_model.py

echo
echo "== 3/4  Сквозная проверка =="
$PY scripts/smoke_test.py

echo
echo "== 4/4  Запуск сервера =="
exec $PY app.py
