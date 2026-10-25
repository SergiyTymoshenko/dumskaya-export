#!/usr/bin/env bash
# Сборка и выкладка каталога фабрик dumskaya-home.com с Mac:   npm run deploy:home
#
# 1) каталог: товары из content/shop/catalog/ + структура и правки (scripts/shop/catalog_index.py),
# 2) фото: WebP с описательными именами из папки выгрузки (только новые; scripts/home_images.mjs),
# 3) сборка (home/, Astro), 4) проверка (scripts/check_home.py), 5) копирование на сервер только изменённого.
#
# Пока сайт в режиме просмотра (preview: смотреть через npm run tunnel:home), собираются все фабрики —
# чтобы посмотреть каталог целиком (только некоторые: HOME_FACTORIES=poliform,minotti npm run deploy:home).
# На домене (live) — только выложенные фабрики (content/home/publish.json; выложить: catalog_index.py --publish <фабрика>).
# Сервер под сайт настраивает обычная выкладка студии (npm run deploy) — она же обновляет бот, принимающий заявки.
set -euo pipefail
cd "$(dirname "$0")/.."
HOST="${DEPLOY_HOST:-eurox}"
export EXPORT_DIR="${EXPORT_DIR:-$HOME/Documents/dumskaya-export}"

if ! node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>22||(a===22&&b>=19)?0:1)' 2>/dev/null; then
  echo "Нужен Node.js 22.19 или новее, сейчас: $(node -v 2>/dev/null || echo 'не установлен')."; exit 1
fi
[ -d "$EXPORT_DIR/images/shop" ] || { echo "Не найдена папка с фото фабрик: $EXPORT_DIR/images/shop"; exit 1; }
STAMP="$(node -v) $(shasum package-lock.json 2>/dev/null || sha1sum package-lock.json)"
if [ ! -d node_modules ] || [ "$(cat node_modules/.dd-stamp 2>/dev/null)" != "$STAMP" ]; then
  echo "▸ Установка пакетов"; npm ci --no-audit --no-fund --loglevel=error; echo "$STAMP" > node_modules/.dd-stamp
fi
if ! ssh "$HOST" 'test -d /var/www/dumskaya-home/site'; then
  echo "Сервер ещё не настроен под dumskaya-home.com. Сначала выложите сайт студии: npm run deploy (один раз спросит пароль sudo)."
  exit 1
fi
MODE="$(ssh "$HOST" 'cat ~/dumskaya/home-mode 2>/dev/null || echo preview')"
if [ "$MODE" = preview ]; then export HOME_ALL=1; else unset HOME_ALL HOME_FACTORIES; fi

echo "▸ 1/5 Каталог ($([ "$MODE" = preview ] && echo "просмотр: все фабрики${HOME_FACTORIES:+ — $HOME_FACTORIES}" || echo "на домене: выложенные фабрики"))"
python3 scripts/shop/catalog_index.py --write --quiet
echo "▸ 2/5 Фото (первый раз долго: тысячи снимков)"
node scripts/home_images.mjs
echo "▸ 3/5 Сборка"
npx astro build --root home >/dev/null
echo "▸ 4/5 Проверка"
CHECK="$(mktemp)"
if ! python3 scripts/check_home.py >"$CHECK"; then
  cat "$CHECK"; rm -f "$CHECK"; echo "Проверка нашла ошибки — выкладка остановлена. Пришлите Claude этот вывод."; exit 1
fi
head -2 "$CHECK"; rm -f "$CHECK"
echo "▸ 5/5 Выкладка на $HOST"
# На сервере есть и другие сайты: место проверяем заранее — после выкладки должно оставаться не меньше 3 ГБ.
# Считается только то, чего на сервере ещё нет (то, что уже выложено, заменится).
NEED_KB="$(du -sk home/dist home/img | awk '{s += $1} END {print s}')"
read -r FREE_KB HAVE_KB < <(ssh "$HOST" 'echo "$(df -Pk /var/www | awk "NR==2 {print \$4}") $(du -sk /var/www/dumskaya-home/site 2>/dev/null | cut -f1)"')
HAVE_KB="${HAVE_KB:-0}"
case "$FREE_KB" in ''|*[!0-9]*) echo "Не получилось узнать свободное место на сервере — выкладка остановлена. Пришлите Claude этот вывод."; exit 1 ;; esac
LEFT_KB=$(( FREE_KB + HAVE_KB - NEED_KB ))
echo "  каталог: $(( NEED_KB / 1024 )) МБ, на сервере свободно $(( FREE_KB / 1024 )) МБ"
if [ "$LEFT_KB" -lt $(( 3 * 1024 * 1024 )) ]; then
  echo "На сервере мало места: после выкладки осталось бы $(( LEFT_KB / 1024 )) МБ, а другим сайтам нужен запас 3 ГБ."
  echo "Выкладка остановлена. Пришлите Claude этот вывод — можно выложить только часть фабрик (HOME_FACTORIES=…)."
  exit 1
fi
DELAY=""; case "$(rsync --help 2>&1)" in *--delay-updates*) DELAY="--delay-updates" ;; esac
# сначала фото (новые имена — новые файлы), потом страницы; старые файлы удаляются только из папки этого сайта
rsync -az --exclude '.DS_Store' home/img/ "$HOST:/var/www/dumskaya-home/site/img/"
rsync -az --delete $DELAY --exclude '.DS_Store' --exclude '/img/' home/dist/ "$HOST:/var/www/dumskaya-home/site/"
rsync -az --delete --exclude '.DS_Store' home/img/ "$HOST:/var/www/dumskaya-home/site/img/"
if [ "$MODE" = live ]; then
  CODE=000
  for _ in 1 2 3 4 5; do CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 https://dumskaya-home.com/ || true)"; [ "$CODE" = 200 ] && break; sleep 3; done
  [ "$CODE" = 200 ] && echo "Готово: https://dumskaya-home.com — сайт отвечает." || { echo "ВНИМАНИЕ: файлы выложены, но https://dumskaya-home.com не отвечает (код $CODE). Пришлите Claude этот вывод."; exit 1; }
else
  echo "Готово. Сайт пока в режиме просмотра. Посмотреть:  npm run tunnel:home  и откройте http://localhost:8089"
fi
