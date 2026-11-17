#!/usr/bin/env bash
# Dauerlauf fürs Posten (seit 17.11.2026). GitHub startet geplante Workflows oft nur alle paar Stunden,
# deshalb bleibt ein Lauf bis zu DAUER_MIN Minuten wach, schaut alle 5 Minuten nach fälligen Posts und
# Probe-Reels, sichert die Ergebnisse und startet sich am Ende selbst neu (Schritt im Workflow).
set -u
ENDE=$(( $(date +%s) + ${DAUER_MIN:-340} * 60 ))
git config user.name "BBH Automatik"; git config user.email "noreply@github.com"
while :; do
  git pull -q --rebase || echo "pull fehlgeschlagen"
  python3 scripts/posten.py || echo "posten.py mit Fehler beendet"
  if git fetch -q --depth 1 origin +hooktests:refs/remotes/origin/hooktests 2>/dev/null; then
    git worktree remove --force ht 2>/dev/null
    git worktree add -q --detach ht origin/hooktests
    python3 scripts/hooktest_posten.py || echo "hooktest_posten.py mit Fehler beendet"
    git worktree remove --force ht
  fi
  git add -A .
  if ! git diff --cached --quiet; then
    git commit -qm "Ergebnis $(date -u +%FT%H:%M)"
    for i in 1 2 3; do git pull -q --rebase && git push -q && break; sleep 10; done
  fi
  [ $(( $(date +%s) + 300 )) -gt "$ENDE" ] && break
  sleep 300
done
