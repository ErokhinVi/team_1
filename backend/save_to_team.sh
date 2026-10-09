#!/bin/bash
# Lock in the backend block's work and send it to the team's shared branch.
# Usage: bash backend/save_to_team.sh "what was done"
set -e
cd "$(dirname "$0")/.."
MSG="${1:-backend: update}"
git add backend
if git diff --cached --quiet; then
  echo "Нечего сохранять: изменений нет."
else
  git commit -q -m "$MSG"
fi
echo "Забираю свежую работу соседей..."
git pull -q --rebase --autostash origin main
echo "Отправляю в общую копилку..."
git push -q origin HEAD:main
echo ""
echo "Готово! Работа в общей копилке. Через 2-4 минуты банк обновится."
