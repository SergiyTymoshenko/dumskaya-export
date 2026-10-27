#!/usr/bin/env bash
# Помощник выкладки на Маке (решено 27.10.2026): Claude оставляет заявку в репозитории — Мак выполняет её сам.
#
# Запускается launchd раз в 2 минуты (ставит scripts/mac_agent_install.sh). Берёт из GitHub свежую версию и смотрит
# ops/request.json: {"id": "…", "do": ["deploy", "deploy-home", "dl:lago"]}. Новая заявка (id ещё не выполнялся) —
# выполняет по порядку ТОЛЬКО разрешённые действия:
#   deploy        — npm run deploy        (сайт студии и сервис на сервере)
#   deploy-home   — npm run deploy:home   (каталог dumskaya-home.com)
#   dl:<фабрика>  — scripts/shop/factories/dl.py <фабрика> (фото и техкарты в папку выгрузки)
#   status        — только версия и место на диске (проверка, что помощник жив)
#   gsc-now, gsc-status, gsc-sitemaps — индекс Google на сервере: проверить сейчас / что известно / отправить карты сайта
# Ничего другого не запускает. Вывод — в ветку agent-log репозитория (файл last.log; Claude читает его оттуда),
# рабочую папку и ветку main не трогает. Пароль sudo помощник не вводит: если выкладке он нужен (меняются настройки
# сервера), шаг остановится с сообщением — тогда эту команду владелец запускает в Терминале сам.
# Мак спит или выключен — заявка выполнится, когда он проснётся.
set -uo pipefail
export GIT_TERMINAL_PROMPT=0          # без Терминала git не должен ждать логина и пароля — просто ошибка
DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$HOME/.dumskaya-agent"
mkdir -p "$STATE"
LOCK="$STATE/lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  # прошлый запуск ещё идёт (выкладка — до получаса); зависший замок старше 3 часов — снять
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +180 2>/dev/null)" ]; then rm -rf "$LOCK"; mkdir "$LOCK" || exit 0; else exit 0; fi
fi
trap 'rm -rf "$LOCK"' EXIT
cd "$DIR" || exit 0
git fetch -q origin main 2>/dev/null || exit 0
# свежая версия помощника: если изменился он сам — перезапуститься ею, чтобы заявку выполнили уже новые правила
SELF="$(git hash-object "$0" 2>/dev/null)"
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ] && git pull -q --ff-only origin main >/dev/null 2>&1 \
   && [ "$(git hash-object "$0" 2>/dev/null)" != "$SELF" ] && [ -z "${AGENT_RESTARTED:-}" ]; then
  rm -rf "$LOCK"; trap - EXIT
  AGENT_RESTARTED=1 exec /bin/bash "$0"
fi
REQ="$(git show origin/main:ops/request.json 2>/dev/null)" || exit 0
ID="$(printf '%s' "$REQ" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))' 2>/dev/null)"
case "$ID" in ''|*[!A-Za-z0-9._:-]*) exit 0 ;; esac
[ "$(cat "$STATE/last-id" 2>/dev/null)" = "$ID" ] && exit 0
echo "$ID" > "$STATE/last-id"
LOG="$STATE/run.log"
publish() {   # вывод — в ветку agent-log (отдельный коммит, рабочая папка не меняется)
  local blob tree commit
  blob="$(git hash-object -w "$LOG")" && tree="$(printf '100644 blob %s\tlast.log\n' "$blob" | git mktree)" \
    && commit="$(GIT_AUTHOR_NAME="Mac agent" GIT_AUTHOR_EMAIL=agent@dumskaya-design.com GIT_COMMITTER_NAME="Mac agent" \
       GIT_COMMITTER_EMAIL=agent@dumskaya-design.com git commit-tree "$tree" -m "agent: $ID")" && git push -q -f origin "$commit:refs/heads/agent-log" 2>>"$STATE/push.err"
}
{
  echo "заявка: $ID"
  echo "начало: $(date '+%d.%m.%Y %H:%M:%S') · Мак: $(scutil --get ComputerName 2>/dev/null || hostname)"
  echo "идёт…"
} > "$LOG"
publish
STEPS="$(printf '%s' "$REQ" | python3 -c 'import json,sys; print("\n".join(json.load(sys.stdin).get("do") or []))' 2>/dev/null)"
RC=0
if ! git pull -q --ff-only origin main >>"$LOG" 2>&1; then
  echo "✗ не получилось взять свежую версию (git pull): в папке сайта на Маке есть свои изменения — нужен Claude" >>"$LOG"
  RC=1
else
  echo "версия: $(git rev-parse --short HEAD)" >>"$LOG"
  while IFS= read -r step; do
    [ -z "$step" ] && continue
    echo "" >>"$LOG"; echo "▶ $step — $(date '+%H:%M:%S')" >>"$LOG"
    case "$step" in
      deploy)      caffeinate -i npm run deploy </dev/null >>"$LOG" 2>&1 ;;
      deploy-home) caffeinate -i npm run deploy:home </dev/null >>"$LOG" 2>&1 ;;
      dl:*)        f="${step#dl:}"
                   if [[ "$f" =~ ^[a-z0-9]+$ ]] && [ -d "content/shop/sources/$f" ]; then
                     caffeinate -i python3 scripts/shop/factories/dl.py "$f" </dev/null >>"$LOG" 2>&1
                   else echo "нет такой фабрики: $f" >>"$LOG"; false; fi ;;
      status)      { node -v; df -h "$HOME" | tail -1; } >>"$LOG" 2>&1 ;;
      gsc-now)     ssh -o BatchMode=yes eurox 'python3 ~/dumskaya/deploy/gsc_index.py --now' </dev/null >>"$LOG" 2>&1 ;;
      gsc-status)  ssh -o BatchMode=yes eurox 'python3 ~/dumskaya/deploy/gsc_index.py --status' </dev/null >>"$LOG" 2>&1 ;;
      gsc-sitemaps) ssh -o BatchMode=yes eurox 'python3 ~/dumskaya/deploy/gsc_index.py --sitemaps' </dev/null >>"$LOG" 2>&1 ;;
      *)           echo "неизвестное действие — не выполняю" >>"$LOG"; false ;;
    esac
    r=$?
    echo "◀ $step: $([ $r = 0 ] && echo готово || echo "ошибка (код $r)")" >>"$LOG"
    if [ $r != 0 ]; then RC=$r; break; fi
  done <<< "$STEPS"
fi
sed -i '' 's/^идёт…$//' "$LOG" 2>/dev/null || true
echo "" >>"$LOG"; echo "конец: $(date '+%d.%m.%Y %H:%M:%S') · $([ $RC = 0 ] && echo 'ВСЁ ГОТОВО' || echo "ОСТАНОВЛЕНО (код $RC)")" >>"$LOG"
# вывод выкладки длинный (сотни строк сборки) — в ветку только последние 400 строк
tail -400 "$LOG" > "$LOG.tail" && mv "$LOG.tail" "$LOG"
publish
exit 0
