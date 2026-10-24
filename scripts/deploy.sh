#!/usr/bin/env bash
# Сборка и выкладка сайта с Mac на сервер:   npm run deploy
#
# 1) готовит фото (только новые), 2) собирает сайт, 3) проверяет его,
# 4) копирует на сервер только изменённые файлы, 5) если менялись настройки сервера
#    (редиректы, сервис заявок) — один раз спросит пароль sudo и применит их.
# Сервер: ssh-алиас «eurox» (можно поменять: DEPLOY_HOST=... npm run deploy).
set -euo pipefail
cd "$(dirname "$0")/.."
HOST="${DEPLOY_HOST:-eurox}"
export IMAGES_DIR="${IMAGES_DIR:-$HOME/Documents/dumskaya-export/images}"

if ! node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>22||(a===22&&b>=19)?0:1)' 2>/dev/null; then
  echo "Нужен Node.js 22.19 или новее, сейчас: $(node -v 2>/dev/null || echo 'не установлен')."
  echo "Поставьте версию LTS с https://nodejs.org (или: brew upgrade node / nvm install --lts) и запустите снова."
  exit 1
fi
[ -d "$IMAGES_DIR" ] || { echo "Не найдена папка с оригиналами фото: $IMAGES_DIR"; exit 1; }
# пакеты ставятся заново, если их нет, если обновился package-lock.json или сменилась версия Node
STAMP="$(node -v) $(shasum package-lock.json 2>/dev/null || sha1sum package-lock.json)"
if [ ! -d node_modules ] || [ "$(cat node_modules/.dd-stamp 2>/dev/null)" != "$STAMP" ]; then
  echo "▸ Установка пакетов"
  npm ci --no-audit --no-fund --loglevel=error
  echo "$STAMP" > node_modules/.dd-stamp
fi

echo "▸ 1/5 Фото"
node scripts/images.mjs
echo "▸ 2/5 Сборка"
PUBLIC_ANALYTICS=1 npx astro build >/dev/null
echo "▸ 3/5 Проверка"
CHECK="$(mktemp)"
if ! python3 scripts/check_site.py >"$CHECK"; then
  cat "$CHECK"; rm -f "$CHECK"
  echo "Проверка нашла ошибки — выкладка остановлена. Пришлите Claude этот вывод."; exit 1
fi
grep -E '^(страниц|ошибок)|заглушк' "$CHECK"; rm -f "$CHECK"
python3 scripts/build_caddy.py
python3 scripts/build_shop.py

echo "▸ 4/5 Выкладка на $HOST"
# версия бота и «Студии» — мелко внизу мини-приложения: коммит · когда · откуда («+ правки» — были незакоммиченные изменения)
V="$(git rev-parse --short HEAD 2>/dev/null || echo '—')"
git diff --quiet HEAD -- deploy 2>/dev/null || V="$V + правки"
printf '%s · %s · Мак\n' "$V" "$(date '+%d.%m.%Y %H:%M')" > deploy/VERSION
ssh "$HOST" 'mkdir -p ~/dumskaya/deploy'
rsync -az --delete --exclude '.DS_Store' deploy/ "$HOST:dumskaya/deploy/"
if ! ssh "$HOST" 'test -d /var/www/dumskaya/site'; then
  echo "  Первая выкладка: настраиваю сервер (нужен пароль sudo)…"
  ssh -t "$HOST" 'sudo bash ~/dumskaya/deploy/server-setup.sh preview'
fi
# --delay-updates (подмена файлов в самом конце) есть не во всех версиях rsync на macOS
DELAY=""; case "$(rsync --help 2>&1)" in *--delay-updates*) DELAY="--delay-updates" ;; esac
rsync -az --delete $DELAY --exclude '.DS_Store' dist/ "$HOST:/var/www/dumskaya/site/"

echo "▸ 5/5 Настройки сервера"
# changed — менялись редиректы, файлы сервисов или приём выкладки (нужен sudo); unlinked — в основном Caddyfile нет
# строки, подключающей сайт (его перезаписала выкладка другого проекта на этом сервере); code — изменился только код
# бота и «Студии»: его применяет перезапуск сервиса без пароля (autodeploy restart, «звонок» ставит server-setup.sh)
# (переводы кабинета deploy/i18n/*.json — тоже код: их отпечаток в ~/dumskaya/running-i18n.sha256)
STATE="$(ssh "$HOST" 'cd ~/dumskaya/deploy; sha256sum -c --quiet ~/dumskaya/installed.sha256 >/dev/null 2>&1 || echo changed; [ -x /usr/local/lib/dumskaya/autodeploy ] || echo changed; grep -qE "^[[:space:]]*import[[:space:]]+sites/(\*|dumskaya)\.caddy[[:space:]]*$" /etc/caddy/Caddyfile || echo unlinked; sha256sum -c --quiet ~/dumskaya/running.sha256 >/dev/null 2>&1 || echo code; sha256sum -c --quiet ~/dumskaya/running-i18n.sha256 >/dev/null 2>&1 || echo code')"
case "$STATE" in
  *unlinked*) echo "  сайт отключён от Caddy (основной Caddyfile перезаписан) — подключаю снова (нужен пароль sudo)…" ;;
  *changed*)  echo "  изменились редиректы или настройки сервиса — применяю (нужен пароль sudo)…" ;;
  *code*)     echo "  изменился код бота — перезапускаю сервис (без пароля)…" ;;
  *)          echo "  без изменений" ;;
esac
case "$STATE" in
  *unlinked*|*changed*)
    ssh -t "$HOST" 'sudo bash ~/dumskaya/deploy/server-setup.sh "$(cat ~/dumskaya/mode 2>/dev/null || echo preview)"' ;;
  *code*)
    ssh "$HOST" /usr/local/lib/dumskaya/autodeploy restart \
      || { echo "  сервис не ответил после перезапуска. Журнал: ssh $HOST 'tail -20 ~/dumskaya/autodeploy.log; sudo journalctl -u dumskaya-lead -n 30'"; exit 1; } ;;
esac
# отпечаток переводов запущенного кода (после перезапуска любым путём)
case "$STATE" in
  *unlinked*|*changed*|*code*) ssh "$HOST" 'cd ~/dumskaya/deploy && sha256sum -- i18n/*.json > ~/dumskaya/running-i18n.sha256 2>/dev/null' || true ;;
esac
MODE="$(ssh "$HOST" 'cat ~/dumskaya/mode 2>/dev/null || echo preview')"
if [ "$MODE" = live ]; then
  # проверка с этого Мака, как у посетителя: сайт должен ответить 200 по HTTPS
  CODE=000
  for _ in 1 2 3 4 5; do
    CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 https://dumskaya-design.com/ || true)"
    [ "$CODE" = 200 ] && break; sleep 3
  done
  if [ "$CODE" = 200 ]; then
    echo "Готово: https://dumskaya-design.com — сайт отвечает."
  else
    echo "ВНИМАНИЕ: файлы выложены, но https://dumskaya-design.com не отвечает (код $CODE)."
    echo "Подключить сайт к Caddy заново:  ssh -t $HOST 'sudo bash ~/dumskaya/deploy/server-setup.sh live'"
    echo "Если не помогло — пришлите Claude этот вывод."
    exit 1
  fi
else
  echo "Готово. Сайт пока в режиме просмотра. Посмотреть:  npm run tunnel  и откройте http://localhost:8088"
fi
