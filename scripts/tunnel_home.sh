#!/usr/bin/env bash
# Посмотреть каталог DUMSKAYA HOME в режиме просмотра (до включения домена):  npm run tunnel:home
# Сначала проверяет сервер — без этого браузер показывает просто белую страницу, если каталога там ещё нет;
# потом открывает туннель: http://localhost:8089 на Маке → 127.0.0.1:8089 на сервере. Ctrl+C — закрыть.
set -uo pipefail
HOST="${DEPLOY_HOST:-eurox}"
PORT=8089

STATE="$(ssh -o ConnectTimeout=15 "$HOST" '
  mode=$(cat ~/dumskaya/home-mode 2>/dev/null || echo none)
  dir=no; [ -d /var/www/dumskaya-home/site ] && dir=yes
  idx=no; [ -f /var/www/dumskaya-home/site/index.html ] && idx=yes
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:'"$PORT"'/ 2>/dev/null); [ -n "$code" ] || code=000
  echo "$mode $dir $idx $code"' 2>/dev/null)" || {
  echo "Не получилось подключиться к серверу ($HOST) по ssh. Проверьте интернет и попробуйте ещё раз."
  exit 1
}
read -r MODE DIR IDX CODE <<<"$STATE"

if [ "$DIR" != yes ] || [ "$MODE" = none ]; then
  echo "Сервер ещё не настроен под каталог. Сначала выложите сайт студии и каталог (в Терминале на Маке):"
  echo "  cd ~/dumskaya-site && git pull && npm run deploy && caffeinate -i npm run deploy:home && npm run tunnel:home"
  exit 1
fi
if [ "$MODE" = live ]; then
  echo "Каталог уже открыт на домене — туннель не нужен: https://dumskaya-home.com"
  command -v open >/dev/null && open https://dumskaya-home.com
  exit 0
fi
if [ "$IDX" != yes ]; then
  echo "Место под каталог на сервере есть, но сам каталог ещё не выложен. Выложите его (в Терминале на Маке; первый раз — долго):"
  echo "  cd ~/dumskaya-site && caffeinate -i npm run deploy:home && npm run tunnel:home"
  exit 1
fi
if [ "$CODE" != 200 ]; then
  echo "Каталог выложен, но сервер на порту $PORT не отвечает (код $CODE). Пришлите Claude этот вывод."
  exit 1
fi

echo "DUMSKAYA HOME: http://localhost:$PORT  (окно не закрывайте; Ctrl+C — закрыть)"
(sleep 2; command -v open >/dev/null && open "http://localhost:$PORT") &
exec ssh -N -o ExitOnForwardFailure=yes -L "$PORT:127.0.0.1:$PORT" "$HOST"
