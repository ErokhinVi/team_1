#!/bin/bash
# Lock in the backend block's work and send it to the team's `dev` branch.
# Usage: bash backend/save_to_team.sh "what was done"
# Note: Render deploys only from `main`; `dev` is NOT deployed automatically.
set -e
cd "$(dirname "$0")/.."
MSG="${*:-backend: R1-B4..B6 current-debt filter, salary flags, idempotency_key}"
BRANCH=dev

if [ "$(git rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]; then
  git switch "$BRANCH" 2>/dev/null || git switch -c "$BRANCH"
fi
git add backend
if git diff --cached --quiet; then
  echo "Нечего сохранять: изменений нет."
else
  git commit -q -m "$MSG"
fi
git fetch -q origin
if git rev-parse -q --verify "origin/$BRANCH" >/dev/null; then
  echo "Забираю свежие изменения из ветки $BRANCH..."
  git pull -q --rebase --autostash origin "$BRANCH"
fi
echo "Отправляю в ветку $BRANCH..."
git push -q -u origin "HEAD:$BRANCH"
echo ""
echo "Готово! Работа в ветке $BRANCH (на табло она попадёт только после переноса в main)."
