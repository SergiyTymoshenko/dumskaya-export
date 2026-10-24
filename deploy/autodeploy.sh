#!/usr/bin/env bash
# Выкладка бота и «Студии» без пароля sudo. server-setup.sh ставит этот файл в /usr/local/lib/dumskaya/autodeploy
# (владелец root: ни пользователь сервера, ни ключ GitHub изменить его не могут).
#
#   По ключу GitHub — в ~/.ssh/authorized_keys он записан с command="/usr/local/lib/dumskaya/autodeploy",restrict,
#   поэтому этим ключом нельзя ни войти в оболочку, ни выполнить что-то другое:
#       команда «<коммит> <тема коммита в base64>», на входе — tar с папкой deploy/ из репозитория.
#       Проверяет архив и код Python, кладёт файлы в ~/dumskaya/deploy (собранные при выкладке с Мака файлы
#       не трогает), перезапускает сервис заявок и ждёт, пока он ответит. Не ответил за 40 с — возвращает
#       прежнюю версию. EuroExchange, Caddy и другие папки не затрагиваются.
#   autodeploy restart — только перезапуск с проверкой (так npm run deploy с Мака применяет новый код без sudo).
#   autodeploy ping    — проверка ключа (мастер npm run autodeploy).
#
# Перезапуск — через «звонок»: запись в ~/dumskaya/run/restart; за файлом следит dumskaya-lead-restart.path (root),
# который умеет только перезапустить dumskaya-lead. Журнал — ~/dumskaya/autodeploy.log.
set -uo pipefail
umask 022
APP="${DUMSKAYA_APP:-$HOME/dumskaya}"
RUN="$APP/run"
LOG="$APP/autodeploy.log"
SERVICE="${DUMSKAYA_SERVICE:-dumskaya-lead}"
HEALTH="${DUMSKAYA_HEALTH:-http://127.0.0.1:8095/api/lead/health}"
WAIT="${DUMSKAYA_WAIT:-40}"
MAX_BYTES=$((40 * 1024 * 1024))
mkdir -p "$RUN"

say() { echo "$*"; echo "$(date '+%F %T') $*" >> "$LOG"; }
pid() { systemctl show -p MainPID --value "$SERVICE" 2>/dev/null || echo 0; }
healthy() { python3 -c 'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=3)' "$HEALTH" >/dev/null 2>&1; }

restart() {      # «звонок» и ожидание нового процесса, который отвечает; потом — отпечатки запущенного кода
  local before now i
  before="$(pid)"
  date +%s.%N > "$RUN/restart"
  for ((i = 0; i < WAIT; i++)); do
    sleep 1
    now="$(pid)"
    if [ -n "$now" ] && [ "$now" != 0 ] && [ "$now" != "$before" ] && healthy; then
      (cd "$APP/deploy" && sha256sum -- *.py *.html *.json > "$APP/running.sha256" 2>/dev/null)
      return 0
    fi
  done
  return 1
}

note() {         # что выложено — бот сообщит разработчику после перезапуска (bot.py: announce_deploy)
  python3 - "$RUN/deployed.json" "$SHA" "$SUBJ" "$1" "$2" <<'PY'
import base64, json, sys, time
path, sha, subj, status, setup = sys.argv[1:6]
try:
    subject = base64.b64decode(subj).decode("utf-8", "replace").strip()[:200]
except ValueError:
    subject = ""
with open(path, "w", encoding="utf-8") as fh:
    json.dump({"sha": sha, "subject": subject, "status": status, "setup_needed": setup == "1", "time": int(time.time())},
              fh, ensure_ascii=False)
PY
}

# команда: из аргументов (с Мака) или от ключа GitHub (SSH_ORIGINAL_COMMAND)
if [ $# -eq 0 ]; then
  read -r -a ARGS <<< "${SSH_ORIGINAL_COMMAND:-}"
  set -- "${ARGS[@]+"${ARGS[@]}"}"
fi
CMD="${1:-}"

if [ "$CMD" = ping ]; then
  echo "ok: приём выкладки на месте"
  exit 0
fi

exec 9>"$RUN/autodeploy.lock"
flock -w 180 9 || { say "занято: идёт другая выкладка"; exit 3; }

if [ "$CMD" = restart ]; then
  if restart; then say "сервис перезапущен (выкладка с Мака)"; exit 0; fi
  say "сервис не ответил за ${WAIT} с после перезапуска"
  exit 1
fi

SHA="$CMD"
SUBJ="${2:-}"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "неизвестная команда"; exit 2; }
[[ "$SUBJ" =~ ^[A-Za-z0-9+/=]{0,400}$ ]] || SUBJ=""
[ -d "$APP/deploy" ] || { say "нет $APP/deploy — сначала выкладка с Мака"; exit 4; }

STAGE="$(mktemp -d "$RUN/stage.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
if ! head -c "$MAX_BYTES" | tar -x -C "$STAGE" --no-same-owner --no-same-permissions -f - deploy 2> "$STAGE/tar.err"; then
  say "архив не принят ($(head -c 300 "$STAGE/tar.err" | tr '\n' ' '))"
  exit 5
fi
NEW="$STAGE/deploy"
if [ ! -f "$NEW/lead_service.py" ] || [ ! -f "$NEW/bot.py" ]; then say "в архиве нет кода бота"; exit 5; fi
if [ -n "$(find "$NEW" -type l -print -quit)" ]; then say "в архиве есть ссылки — не принимаю"; exit 5; fi
if ! python3 - "$NEW"/*.py <<'PY'
import ast, sys
for f in sys.argv[1:]:
    with open(f, encoding="utf-8") as fh:
        ast.parse(fh.read(), f)
PY
then
  say "код Python в ${SHA:0:7} с ошибкой — не выкладываю"
  exit 6
fi

rm -rf "$APP/deploy.prev"
cp -a "$APP/deploy" "$APP/deploy.prev"
cp -a "$NEW/." "$APP/deploy/"
# изменились настройки сервера (файл сервиса, Caddy, этот приём)? их применит только выкладка с Мака (sudo)
SETUP=0
sha256sum -c --quiet "$APP/installed.sha256" >/dev/null 2>&1 || SETUP=1
note ok "$SETUP"
if restart; then
  say "выложено ${SHA:0:7}$([ "$SETUP" = 1 ] && echo ' (настройки сервера — при выкладке с Мака)')"
  exit 0
fi

say "после выкладки ${SHA:0:7} сервис не ответил за ${WAIT} с — возвращаю прежнюю версию"
rm -rf "$APP/deploy.failed"
mv "$APP/deploy" "$APP/deploy.failed"
mv "$APP/deploy.prev" "$APP/deploy"
note rolled_back 0
if restart; then
  say "прежняя версия работает (неудачная — в $APP/deploy.failed)"
else
  say "сервис не отвечает и на прежней версии — нужна помощь: sudo journalctl -u $SERVICE -n 50"
fi
exit 1
