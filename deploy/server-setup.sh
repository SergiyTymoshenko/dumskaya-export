#!/usr/bin/env bash
# Настройка сервера под сайт dumskaya-design.com. Запускается автоматически из scripts/deploy.sh
# (спросит пароль sudo) или вручную:  sudo bash ~/dumskaya/deploy/server-setup.sh preview|live
#
#   preview — сайт доступен только с самого сервера на 127.0.0.1:8088 (смотреть через SSH-туннель),
#             домен и сертификаты не трогаются;
#   live    — сайт отвечает на dumskaya-design.com, Caddy сам получает HTTPS-сертификат
#             (включать после того, как DNS домена указывает на этот сервер).
#
# Что делает: папка /var/www/dumskaya, файл сайта в /etc/caddy/sites/ + строка «import sites/*.caddy»
# в основном Caddyfile, сервис приёма заявок. Перед перезагрузкой Caddy конфиг проверяется;
# если проверка не прошла — всё возвращается как было, другие сайты не затрагиваются.
set -euo pipefail

MODE="${1:-preview}"
[ "$MODE" = preview ] || [ "$MODE" = live ] || { echo "Режим: preview или live"; exit 1; }
[ "$(id -u)" -eq 0 ] || { echo "Запустите через sudo"; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${SUDO_USER:-deploy}"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
APP="$HOME_DIR/dumskaya"
CADDYFILE=/etc/caddy/Caddyfile
TS="$(date +%Y%m%d-%H%M%S)"

command -v caddy >/dev/null || { echo "Caddy не найден"; exit 1; }
[ -f "$CADDYFILE" ] || { echo "Нет $CADDYFILE — Caddy настроен иначе, остановка"; exit 1; }
echo "Caddy: $(caddy version | cut -d' ' -f1), режим: $MODE, пользователь: $USER_NAME"

# 1. Папки
install -d -o "$USER_NAME" -g "$USER_NAME" -m 755 /var/www/dumskaya /var/www/dumskaya/site
install -d -o "$USER_NAME" -g "$USER_NAME" -m 750 "$APP"
install -d -m 755 /etc/caddy/sites
# Caddy работает от своего пользователя: журнал сайта должен принадлежать ему,
# иначе Caddy не сможет его открыть и не примет новый конфиг
CU="$(systemctl show caddy -p User --value 2>/dev/null)"; CU="${CU:-root}"
as_caddy() { if [ "$CU" = root ]; then "$@"; else sudo -u "$CU" -H "$@"; fi; }
install -d -o "$CU" -g "$CU" -m 755 /var/log/caddy
[ -f /var/log/caddy/dumskaya.log ] || install -o "$CU" -g "$CU" -m 640 /dev/null /var/log/caddy/dumskaya.log
chown "$CU":"$CU" /var/log/caddy/dumskaya.log*

# 2. Caddy
if [ "$MODE" = live ]; then
  SITE="dumskaya-design.com"
  WWW="www.dumskaya-design.com {\n\tredir https://dumskaya-design.com{uri} 301\n}"
  BIND=""
else
  SITE="http://:8088"
  WWW=""
  BIND="bind 127.0.0.1"
fi
sed -e "s#__SITE__#$SITE#" -e "s#__WWW_BLOCK__#$WWW#" -e "s#__BIND__#$BIND#" "$HERE/caddy/dumskaya.caddy.template" > /etc/caddy/sites/dumskaya.caddy.new
cp "$HERE/caddy/dumskaya-redirects.snippet" /etc/caddy/sites/dumskaya-redirects.snippet.new

cp -a "$CADDYFILE" "$CADDYFILE.bak-$TS"
for f in dumskaya.caddy dumskaya-redirects.snippet; do
  [ -f "/etc/caddy/sites/$f" ] && cp -a "/etc/caddy/sites/$f" "/etc/caddy/sites/$f.bak-$TS"
  mv "/etc/caddy/sites/$f.new" "/etc/caddy/sites/$f"
done
# В основной Caddyfile добавляется одна строка — импорт только файла этого сайта. Caddyfile принадлежит
# EuroExchange (его выкладка перезаписывает файл): если в нём уже есть «import sites/*.caddy», ничего не добавляется.
IMPORT_RE='^[[:space:]]*import[[:space:]]+sites/(\*|dumskaya)\.caddy[[:space:]]*$'
grep -qE "$IMPORT_RE" "$CADDYFILE" || printf '\n# dumskaya-design.com (~/dumskaya/deploy/server-setup.sh)\nimport sites/dumskaya.caddy\n' >> "$CADDYFILE"

restore() {
  echo "$1 — возвращаю как было."
  cp -a "$CADDYFILE.bak-$TS" "$CADDYFILE"
  for f in dumskaya.caddy dumskaya-redirects.snippet; do
    if [ -f "/etc/caddy/sites/$f.bak-$TS" ]; then mv "/etc/caddy/sites/$f.bak-$TS" "/etc/caddy/sites/$f"; else rm -f "/etc/caddy/sites/$f"; fi
  done
}
# проверка от имени пользователя Caddy — так же, как конфиг будет загружаться на самом деле
if ! as_caddy caddy validate --config "$CADDYFILE" --adapter caddyfile >/tmp/dumskaya-caddy-validate.log 2>&1; then
  tail -5 /tmp/dumskaya-caddy-validate.log | cut -c1-400 || true
  restore "Проверка конфига не прошла"
  exit 1
fi
if ! systemctl reload caddy; then
  journalctl -u caddy -n 8 --no-pager -o cat | grep -iE 'error|fail|denied|address' | tail -4 | cut -c1-400 || true
  restore "Caddy не принял новый конфиг"
  systemctl reload caddy 2>/dev/null || true
  systemctl is-active --quiet caddy || systemctl restart caddy
  echo "Caddy: $(systemctl is-active caddy), прежние настройки на месте."
  exit 1
fi
echo "Caddy перезагружен."
find /etc/caddy -name '*.bak-*' -mtime +30 -delete 2>/dev/null || true

# 3. Сервис заявок
if [ ! -f "$APP/lead.env" ]; then
  install -o "$USER_NAME" -g "$USER_NAME" -m 600 "$HERE/lead.env.example" "$APP/lead.env"
  echo "Создан $APP/lead.env — впишите туда токен Telegram и пароль почты."
fi
sed -e "s#^User=.*#User=$USER_NAME#" -e "s#/home/deploy#$HOME_DIR#g" "$HERE/dumskaya-lead.service" > /etc/systemd/system/dumskaya-lead.service
systemctl daemon-reload
systemctl enable dumskaya-lead >/dev/null 2>&1
systemctl restart dumskaya-lead
sleep 1
systemctl is-active --quiet dumskaya-lead && echo "Сервис заявок работает." || { echo "Сервис заявок не запустился:"; journalctl -u dumskaya-lead -n 20 --no-pager; }

echo "$MODE" > "$APP/mode"; chown "$USER_NAME":"$USER_NAME" "$APP/mode"
sha256sum "$HERE/lead_service.py" "$HERE/bot.py" "$HERE/site_monitor.py" "$HERE/caddy/"* "$HERE/dumskaya-lead.service" > "$APP/installed.sha256"
chown "$USER_NAME":"$USER_NAME" "$APP/installed.sha256"
echo "Готово."
