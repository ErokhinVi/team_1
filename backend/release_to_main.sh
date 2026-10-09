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
if git cherry origin/dev origin/main | grep -q '^+'; then
  echo "СТОП: в main есть работа, которой нет в dev:"
  git log --oneline origin/dev..origin/main
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
