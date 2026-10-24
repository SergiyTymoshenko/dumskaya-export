#!/usr/bin/env bash
# Копия учёта студии («Студия» в боте) на этот Мак:   npm run backup
#
# 1) на сервере — свежая копия баз (учёт проектов и бот; копии за 30 дней сервер хранит и сам, по одной в день),
# 2) скачивает копии баз и файлы проектов в ~/Documents/dumskaya-backups (db/ и files/; с Мака ничего не удаляется,
#    другая папка — STUDIO_BACKUP_DIR=... npm run backup),
# 3) отмечает на сервере дату: если копии на Маке больше 7 дней, бот напомнит разработчику.
# Запускается и сам в конце каждой выкладки (npm run deploy). Сервер: ssh-алиас «eurox» (DEPLOY_HOST=...).
set -uo pipefail
HOST="${DEPLOY_HOST:-eurox}"
BK="${STUDIO_BACKUP_DIR:-$HOME/Documents/dumskaya-backups}"
mkdir -p "$BK/db" "$BK/files"
if ! ssh "$HOST" 'test -f ~/dumskaya/deploy/crm.py' 2>/dev/null; then
  echo "  учёт студии на сервере ещё не установлен — копировать нечего"
  exit 0
fi
OUT="$(ssh "$HOST" 'python3 ~/dumskaya/deploy/crm.py --backup-now')" || { echo "  свежая копия на сервере не сделалась — проверьте связь с сервером"; exit 1; }
echo "  на сервере: $OUT"
rsync -az "$HOST:dumskaya/backups/" "$BK/db/" || { echo "  копии баз не скачались"; exit 1; }
if ssh "$HOST" 'test -d ~/dumskaya/crm/files'; then
  rsync -az "$HOST:dumskaya/crm/files/" "$BK/files/" || { echo "  файлы проектов не скачались"; exit 1; }
fi
ssh "$HOST" 'date -u +%Y-%m-%dT%H:%M:%S+00:00 > ~/dumskaya/mac-backup.txt'
echo "  копия учёта студии на Маке: $BK ($(du -sh "$BK" 2>/dev/null | cut -f1))"
