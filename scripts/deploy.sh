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
python3 scripts/check_site.py | sed -n '1,2p'
python3 scripts/build_caddy.py

echo "▸ 4/5 Выкладка на $HOST"
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
if ssh "$HOST" 'cd ~/dumskaya/deploy && sha256sum -c --quiet ~/dumskaya/installed.sha256 >/dev/null 2>&1'; then
  echo "  без изменений"
else
  echo "  изменились редиректы или сервис заявок — применяю (нужен пароль sudo)…"
  ssh -t "$HOST" 'sudo bash ~/dumskaya/deploy/server-setup.sh "$(cat ~/dumskaya/mode 2>/dev/null || echo preview)"'
fi
MODE="$(ssh "$HOST" 'cat ~/dumskaya/mode 2>/dev/null || echo preview')"
if [ "$MODE" = live ]; then
  echo "Готово: https://dumskaya-design.com"
else
  echo "Готово. Сайт пока в режиме просмотра. Посмотреть:  npm run tunnel  и откройте http://localhost:8088"
fi
