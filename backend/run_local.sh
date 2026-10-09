#!/bin/bash
# Run the backend block locally on http://localhost:8003 without Docker.
# Usage: bash backend/run_local.sh   (from anywhere)
set -e
cd "$(dirname "$0")"

VENV="$HOME/.raif-workshop/backend-venv"
DEPS=("fastapi>=0.111" "uvicorn[standard]>=0.30" "pydantic>=2.7")

if ! "$VENV/bin/python" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "Первый запуск: готовлю всё нужное (1-3 минуты)..."
  mkdir -p "$HOME/.raif-workshop"
  rm -rf "$VENV"
  PY=""
  for c in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1 && \
       "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  done
  if [ -n "$PY" ]; then
    "$PY" -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet "${DEPS[@]}"
  else
    echo "Python на ноутбуке устарел, скачиваю свежий (только для этой папки)..."
    python3 -m pip install --user --quiet uv
    UV="$(python3 -m site --user-base)/bin/uv"
    "$UV" venv --python 3.12 "$VENV"
    "$UV" pip install --quiet --python "$VENV/bin/python" "${DEPS[@]}"
  fi
fi

echo ""
echo "Готово. Ядро данных работает: http://localhost:8003/docs"
echo "Чтобы остановить — нажмите Control+C или закройте это окно."
echo ""
exec "$VENV/bin/python" -m uvicorn src.main:app --host 127.0.0.1 --port 8003 --reload
