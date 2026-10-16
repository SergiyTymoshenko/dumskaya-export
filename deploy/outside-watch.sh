#!/usr/bin/env bash
# Сторож сайта СНАРУЖИ — с другого сервера (например, эстонского). Нужен на случай, когда сервер сайта
# выключился целиком: тогда его собственный сторож (site_monitor.py) и бот молчат вместе с ним.
# Раз в минуту открывает https://dumskaya-design.com/; 5 неудач подряд — сообщение в бот студии
# (тот же бот, отправка от его имени; бот на сервере сайта это не мешает), когда сайт снова отвечает — тоже.
# Дополнительно смотрит, отвечает ли сервер сайта (ping, SSH, порт 80): так видно — лежит только сайт или весь сервер.
#
# Установка на другом сервере (Ubuntu/Debian, нужен sudo):
#   curl -fsSL https://raw.githubusercontent.com/SergiyTymoshenko/dumskaya-export/main/deploy/outside-watch.sh -o /tmp/outside-watch.sh && sudo bash /tmp/outside-watch.sh install
# Спросит токен бота (ввод не виден на экране, никуда не передаётся, хранится в /etc/dumskaya-watch.env, доступ только root),
# пришлёт в бот проверочное сообщение и поставит проверку раз в минуту (systemd-таймер dumskaya-watch).
# Проверить сейчас:  sudo dumskaya-outside-watch status      Удалить:  sudo bash /tmp/outside-watch.sh uninstall
set -uo pipefail
ENV="${DUMSKAYA_WATCH_ENV:-/etc/dumskaya-watch.env}"
BIN=/usr/local/bin/dumskaya-outside-watch
STATE="${DUMSKAYA_WATCH_STATE:-/var/lib/dumskaya-watch}"
TG_API="${TG_API:-https://api.telegram.org}"
URL_DEFAULT="https://dumskaya-design.com/"
SERVER_DEFAULT="62.238.124.237"
FAILS_TO_ALERT=5
REMIND_SEC=3600

tg() {   # tg "текст" — сообщение разработчику от имени бота студии
  curl -s --max-time 20 -o /dev/null -w '%{http_code}' "${TG_API}/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${BOT_OWNER_ID}" --data-urlencode "text=$1" -d parse_mode=HTML -d disable_web_page_preview=true
}

site_ok() {  # 0 — сайт ответил 200 и это наша страница
  local body code
  body="$(curl -s --max-time 20 -w '\n%{http_code}' -H 'Cache-Control: no-cache' -A 'dumskaya-outside-watch/1.0' "$URL" 2>/dev/null)"
  code="${body##*$'\n'}"
  WHY="ответ ${code}"
  [ "$code" = "000" ] && WHY="не открывается (нет соединения, тайм-аут или ошибка HTTPS)"
  [ "$code" = 200 ] || return 1
  grep -q DUMSKAYA <<<"$body" || { WHY="открывается чужая или пустая страница"; return 1; }
  return 0
}

server_alive() {   # сервер сайта жив: отвечает на ping, SSH или порт 80
  ping -c 1 -W 3 "$SERVER" >/dev/null 2>&1 && return 0
  local p; for p in 22 80; do timeout 5 bash -c "</dev/tcp/${SERVER}/${p}" 2>/dev/null && return 0; done
  return 1
}

minutes() { local m=$(( $1 / 60 )); [ $m -lt 120 ] && echo "${m} мин" || echo "$(( m / 60 )) ч $(( m % 60 )) мин"; }

run() {
  # shellcheck disable=SC1090
  . "$ENV"; URL="${SITE_URL:-$URL_DEFAULT}"; SERVER="${SITE_SERVER:-$SERVER_DEFAULT}"
  mkdir -p "$STATE"
  local now fails since alerted reminded
  now=$(date +%s)
  fails=$(cat "$STATE/fails" 2>/dev/null || echo 0)
  since=$(cat "$STATE/since" 2>/dev/null || echo "")
  alerted=$(cat "$STATE/alerted" 2>/dev/null || echo "")
  if site_ok || { sleep 10; site_ok; }; then
    if [ -n "$alerted" ]; then
      tg "🟢 <b>Сайт снова отвечает</b> (проверка со второго сервера) — не отвечал $(minutes $(( now - since )))." >/dev/null
    fi
    rm -f "$STATE/fails" "$STATE/since" "$STATE/alerted" "$STATE/reminded"
    return 0
  fi
  fails=$(( fails + 1 )); echo "$fails" > "$STATE/fails"
  [ -n "$since" ] || { since=$now; echo "$since" > "$STATE/since"; }
  local where
  if server_alive; then
    where="Сервер сайта при этом на связи — лежит сам сайт; от бота на сервере уже должно было прийти сообщение с причиной."
  else
    where="Сервер сайта не отвечает вообще (ни ping, ни SSH) — он выключен или недоступен по сети; бот на нём тоже молчит. Проверьте сервер в панели Hetzner: включён ли, нет ли сообщений о сбое."
  fi
  if [ -z "$alerted" ] && [ "$fails" -ge "$FAILS_TO_ALERT" ]; then
    echo "$now" > "$STATE/alerted"; echo "$now" > "$STATE/reminded"
    tg "🔴 <b>Сайт не отвечает</b> — проверка со второго сервера, ${fails} мин подряд.
${URL} — ${WHY}.

${where}" >/dev/null
  elif [ -n "$alerted" ]; then
    reminded=$(cat "$STATE/reminded" 2>/dev/null || echo "$now")
    if [ $(( now - reminded )) -ge $REMIND_SEC ]; then
      echo "$now" > "$STATE/reminded"
      tg "🔴 Сайт всё ещё не отвечает (проверка со второго сервера) — $(minutes $(( now - since ))): ${WHY}.
${where}" >/dev/null
    fi
  fi
}

status() {
  . "$ENV"; URL="${SITE_URL:-$URL_DEFAULT}"; SERVER="${SITE_SERVER:-$SERVER_DEFAULT}"
  if site_ok; then echo "сайт отвечает: $URL"; else echo "сайт НЕ отвечает: $URL — $WHY"; fi
  if server_alive; then echo "сервер сайта $SERVER на связи"; else echo "сервер сайта $SERVER не отвечает (ни ping, ни SSH, ни порт 80)"; fi
  echo "неудач подряд: $(cat "$STATE/fails" 2>/dev/null || echo 0)"
  systemctl list-timers dumskaya-watch.timer --no-pager 2>/dev/null | sed -n '1,2p'
}

install() {
  [ "$(id -u)" -eq 0 ] || { echo "Запустите через sudo"; exit 1; }
  command -v curl >/dev/null || { apt-get update -qq && apt-get install -y -qq curl; }
  local TOKEN OWNER
  if [ -f "$ENV" ]; then . "$ENV"; TOKEN="${TELEGRAM_BOT_TOKEN:-}"; OWNER="${BOT_OWNER_ID:-633722}"; fi
  if [ -z "${TOKEN:-}" ]; then
    echo "Токен бота студии (тот же, что в ~/dumskaya/lead.env на сервере сайта; у @BotFather: /mybots → бот → API Token)."
    read -rsp "Вставьте токен и нажмите Enter (на экране он не появится): " TOKEN; echo
  fi
  OWNER="${OWNER:-633722}"
  [ -n "$TOKEN" ] || { echo "Токен пустой — отменено."; exit 1; }
  if ! curl -s --max-time 20 "https://api.telegram.org/bot${TOKEN}/getMe" | grep -q '"ok":true'; then
    echo "Telegram не принял токен — проверьте и запустите установку снова."; exit 1
  fi
  umask 077
  printf 'TELEGRAM_BOT_TOKEN=%s\nBOT_OWNER_ID=%s\nSITE_URL=%s\nSITE_SERVER=%s\n' "$TOKEN" "$OWNER" "$URL_DEFAULT" "$SERVER_DEFAULT" > "$ENV"
  chmod 600 "$ENV"
  install -m 755 "$0" "$BIN"
  cat > /etc/systemd/system/dumskaya-watch.service <<EOF
[Unit]
Description=DUMSKAYA DESIGN — проверка сайта снаружи
After=network-online.target
[Service]
Type=oneshot
ExecStart=$BIN run
EOF
  cat > /etc/systemd/system/dumskaya-watch.timer <<EOF
[Unit]
Description=DUMSKAYA DESIGN — проверка сайта снаружи раз в минуту
[Timer]
OnBootSec=2min
OnUnitActiveSec=60s
AccuracySec=5s
[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now dumskaya-watch.timer >/dev/null
  . "$ENV"
  local code; code="$(tg "✅ Сторож сайта со второго сервера ($(hostname)) подключён: проверяет ${URL_DEFAULT} раз в минуту. Если сайт не ответит 5 минут подряд — придёт сообщение.")"
  [ "$code" = 200 ] && echo "Готово: проверка раз в минуту, проверочное сообщение отправлено в бот." \
                    || echo "Установлено, но сообщение в бот не ушло (код $code). Нажмите в боте «Старт», если ещё не нажимали."
  "$BIN" status
}

uninstall() {
  [ "$(id -u)" -eq 0 ] || { echo "Запустите через sudo"; exit 1; }
  systemctl disable --now dumskaya-watch.timer >/dev/null 2>&1
  rm -f /etc/systemd/system/dumskaya-watch.service /etc/systemd/system/dumskaya-watch.timer "$BIN" "$ENV"
  rm -rf "$STATE"; systemctl daemon-reload
  echo "Сторож снаружи удалён."
}

case "${1:-}" in
  run) run ;;
  status) status ;;
  install) install ;;
  uninstall) uninstall ;;
  *) echo "использование: $0 install | status | uninstall"; exit 1 ;;
esac
