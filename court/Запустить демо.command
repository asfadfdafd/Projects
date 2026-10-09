#!/bin/bash
# Двойной клик по этому файлу запускает демо и открывает браузер.
# Чтобы остановить — нажмите Ctrl+C в этом окне или просто закройте его.

cd "$(dirname "$0")" || exit 1

clear
echo "=============================================="
echo "  AI-помощник по гражданским делам — демо"
echo "=============================================="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 не найден."
  echo
  echo "Установите инструменты разработчика — это займёт пару минут:"
  echo "  1) в этом окне выполните:  xcode-select --install"
  echo "  2) подтвердите установку и дождитесь её окончания"
  echo "  3) снова запустите этот файл двойным кликом"
  echo
  read -r -p "Нажмите Enter, чтобы закрыть..."
  exit 1
fi

echo "Python: $(python3 --version)"

if [ ! -f models/model.json ] || [ ! -f data/cases.csv ]; then
  echo "Модель не найдена — обучаю заново (около 5 секунд)..."
  python3 scripts/generate_dataset.py >/dev/null && \
  python3 scripts/train_model.py >/dev/null || {
    echo "Не удалось подготовить модель. Нужен numpy: pip3 install numpy"
    read -r -p "Нажмите Enter, чтобы закрыть..."
    exit 1
  }
fi

echo "Запускаю сервер..."
python3 app.py &
SERVER_PID=$!

trap 'kill $SERVER_PID 2>/dev/null; exit 0' INT TERM

sleep 2

if kill -0 $SERVER_PID 2>/dev/null; then
  echo
  echo "Открываю браузер: http://127.0.0.1:8000"
  echo
  echo "----------------------------------------------"
  echo "  Чтобы остановить демо — нажмите Ctrl+C"
  echo "  или закройте это окно."
  echo "----------------------------------------------"
  open "http://127.0.0.1:8000"
else
  echo "Сервер не запустился. Проверьте, не занят ли порт 8000."
  read -r -p "Нажмите Enter, чтобы закрыть..."
  exit 1
fi

wait $SERVER_PID
