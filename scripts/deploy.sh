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

[ -d "$IMAGES_DIR" ] || { echo "Не найдена папка с оригиналами фото: $IMAGES_DIR"; exit 1; }
[ -d node_modules ] || npm install

echo "▸ 1/5 Фото"
node scripts/images.mjs
echo "▸ 2/5 Сборка"
PUBLIC_ANALYTICS=1 npx astro build >/dev/null
echo "▸ 3/5 Проверка"
python3 scripts/check_site.py | head -3
python3 scripts/build_caddy.py

echo "▸ 4/5 Выкладка на $HOST"
ssh "$HOST" 'mkdir -p ~/dumskaya/deploy'
rsync -az --delete --exclude '.DS_Store' deploy/ "$HOST:dumskaya/deploy/"
if ! ssh "$HOST" 'test -d /var/www/dumskaya/site'; then
  echo "  Первая выкладка: настраиваю сервер (нужен пароль sudo)…"
  ssh -t "$HOST" 'sudo bash ~/dumskaya/deploy/server-setup.sh preview'
fi
rsync -az --delete --delay-updates --exclude '.DS_Store' dist/ "$HOST:/var/www/dumskaya/site/"

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
