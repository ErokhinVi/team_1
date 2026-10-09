#!/bin/bash
# Release: make `main` (live bank + judge) match `dev`.
# Safe only if every commit on main is already in dev (by content);
# otherwise it stops so teammates' work on main is never lost.
set -e
cd "$(dirname "$0")/.."
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Сначала сохраните работу: bash backend/save_to_team.sh"; exit 1
fi
START="$(git rev-parse --abbrev-ref HEAD)"
git fetch -q origin
# Every non-merge commit on main must already be in dev by content (patch-id).
DEV_IDS="$(git log -p --no-merges origin/dev | git patch-id --stable | cut -d' ' -f1 | sort -u)"
MISSING=""
for c in $(git rev-list --no-merges origin/dev..origin/main); do
  id="$(git show "$c" | git patch-id --stable | cut -d' ' -f1)"
  echo "$DEV_IDS" | grep -qx "$id" || MISSING="$MISSING $c"
done
if [ -n "$MISSING" ]; then
  echo "СТОП: в main есть работа, которой нет в dev:"
  for c in $MISSING; do git log --oneline -1 "$c"; done
  echo "Ничего не изменено. Позовите Claude или модератора."; exit 1
fi
git switch -q main 2>/dev/null || git switch -q -c main origin/main
git reset -q --hard origin/main
git merge -q --no-commit -s ours origin/dev
git read-tree -u --reset origin/dev
git commit -q -m "release: dev -> main"
git push -q origin HEAD:main
git switch -q "$START"
echo ""
echo "Выпущено! main = dev. Через 2-4 минуты банк обновится в интернете."
