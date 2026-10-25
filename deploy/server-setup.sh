#!/usr/bin/env bash
# Настройка сервера под сайт dumskaya-design.com (и каталог фабрик dumskaya-home.com). Запускается автоматически
# из scripts/deploy.sh (спросит пароль sudo) или вручную:  sudo bash ~/dumskaya/deploy/server-setup.sh preview|live [home-preview|home-live]
#
# Второй аргумент — режим dumskaya-home.com (запоминается в ~/dumskaya/home-mode; без него — как был, сначала preview):
#   home-preview — каталог доступен только с сервера на 127.0.0.1:8089 (npm run tunnel:home), home-live — на домене.
#
#   preview — сайт доступен только с самого сервера на 127.0.0.1:8088 (смотреть через SSH-туннель),
#             домен и сертификаты не трогаются;
#   live    — сайт отвечает на dumskaya-design.com, Caddy сам получает HTTPS-сертификат
#             (включать после того, как DNS домена указывает на этот сервер).
#
# Что делает: папка /var/www/dumskaya, файл сайта в /etc/caddy/sites/ + строка «import sites/*.caddy»
# в основном Caddyfile, сервис приёма заявок, «звонок» для его перезапуска без sudo и приём выкладки бота
# (/usr/local/lib/dumskaya/autodeploy). Перед перезагрузкой Caddy конфиг проверяется;
# если проверка не прошла — всё возвращается как было, другие сайты не затрагиваются.
set -euo pipefail

MODE="${1:-preview}"
[ "$MODE" = preview ] || [ "$MODE" = live ] || { echo "Режим: preview или live"; exit 1; }
HOME_ARG="${2:-}"
[ -z "$HOME_ARG" ] || [ "$HOME_ARG" = home-preview ] || [ "$HOME_ARG" = home-live ] || { echo "Режим dumskaya-home.com: home-preview или home-live"; exit 1; }
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
install -d -m 755 /etc/caddy/sites /etc/caddy/sites/home
install -d -o "$USER_NAME" -g "$USER_NAME" -m 755 /var/www/dumskaya-home /var/www/dumskaya-home/site
# Caddy работает от своего пользователя: журнал сайта должен принадлежать ему,
# иначе Caddy не сможет его открыть и не примет новый конфиг
CU="$(systemctl show caddy -p User --value 2>/dev/null)"; CU="${CU:-root}"
as_caddy() { if [ "$CU" = root ]; then "$@"; else sudo -u "$CU" -H "$@"; fi; }
install -d -o "$CU" -g "$CU" -m 755 /var/log/caddy
[ -f /var/log/caddy/dumskaya.log ] || install -o "$CU" -g "$CU" -m 644 /dev/null /var/log/caddy/dumskaya.log
[ -f /var/log/caddy/dumskaya-home.log ] || install -o "$CU" -g "$CU" -m 644 /dev/null /var/log/caddy/dumskaya-home.log
chown "$CU":"$CU" /var/log/caddy/dumskaya.log* /var/log/caddy/dumskaya-home.log*
# журнал читает сервис статистики посетителей (от пользователя $USER_NAME); Caddy при ротации сохраняет эти права
chmod 644 /var/log/caddy/dumskaya*.log* 2>/dev/null || true

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
LOGMODE="mode 0644"   # права нового файла журнала (Caddy 2.8+); старый Caddy этой строки не знает — тогда без неё
gen_site() { sed -e "s#__SITE__#$SITE#" -e "s#__WWW_BLOCK__#$WWW#" -e "s#__BIND__#$BIND#" -e "s#__LOGMODE__#$LOGMODE#" "$HERE/caddy/dumskaya.caddy.template"; }
gen_site > /etc/caddy/sites/dumskaya.caddy.new
cp "$HERE/caddy/dumskaya-redirects.snippet" /etc/caddy/sites/dumskaya-redirects.snippet.new
# DUMSKAYA HOME: свой файл в /etc/caddy/sites/home/, подключается из файла сайта студии (import в его начале) —
# поэтому основной Caddyfile (он принадлежит EuroExchange) для него не меняется
HOME_MODE="${HOME_ARG#home-}"; [ -n "$HOME_MODE" ] || HOME_MODE="$(cat "$APP/home-mode" 2>/dev/null || echo preview)"
if [ "$HOME_MODE" = live ]; then
  HSITE="dumskaya-home.com"; HWWW="www.dumskaya-home.com {\n\tredir https://dumskaya-home.com{uri} 301\n}"; HBIND=""
else
  HSITE="http://:8089"; HWWW=""; HBIND="bind 127.0.0.1"
fi
gen_home() { sed -e "s#__SITE__#$HSITE#" -e "s#__WWW_BLOCK__#$HWWW#" -e "s#__BIND__#$HBIND#" -e "s#__LOGMODE__#$LOGMODE#" "$HERE/caddy/dumskaya-home.caddy.template"; }
gen_home > /etc/caddy/sites/home/dumskaya-home.caddy.new

cp -a "$CADDYFILE" "$CADDYFILE.bak-$TS"
for f in dumskaya.caddy dumskaya-redirects.snippet home/dumskaya-home.caddy; do
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
  for f in dumskaya.caddy dumskaya-redirects.snippet home/dumskaya-home.caddy; do
    if [ -f "/etc/caddy/sites/$f.bak-$TS" ]; then mv "/etc/caddy/sites/$f.bak-$TS" "/etc/caddy/sites/$f"; else rm -f "/etc/caddy/sites/$f"; fi
  done
}
# проверка от имени пользователя Caddy — так же, как конфиг будет загружаться на самом деле
validate() { as_caddy caddy validate --config "$CADDYFILE" --adapter caddyfile >/tmp/dumskaya-caddy-validate.log 2>&1; }
if ! validate && [ -n "$LOGMODE" ] && grep -q "mode" /tmp/dumskaya-caddy-validate.log; then
  LOGMODE=""            # эта версия Caddy не знает «mode» в журнале — права выставлены chmod выше
  gen_site > /etc/caddy/sites/dumskaya.caddy
  gen_home > /etc/caddy/sites/home/dumskaya-home.caddy
fi
if ! validate; then
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
# 4. Перезапуск сервиса заявок без sudo: «звонок» (файл ~/dumskaya/run/restart → systemd перезапускает только его)
#    и приём выкладки бота с GitHub и с Мака — файл root, изменить его без sudo нельзя
install -d -o "$USER_NAME" -g "$USER_NAME" -m 750 "$APP/run"
install -d -m 755 /usr/local/lib/dumskaya
install -o root -g root -m 755 "$HERE/autodeploy.sh" /usr/local/lib/dumskaya/autodeploy
sed -e "s#/home/deploy#$HOME_DIR#g" "$HERE/dumskaya-lead-restart.path" > /etc/systemd/system/dumskaya-lead-restart.path
sed -e "s#/usr/bin/systemctl#$(command -v systemctl)#" "$HERE/dumskaya-lead-restart.service" > /etc/systemd/system/dumskaya-lead-restart.service
systemctl daemon-reload
systemctl enable dumskaya-lead >/dev/null 2>&1
systemctl enable --now dumskaya-lead-restart.path >/dev/null 2>&1 || echo "«Звонок» перезапуска не включился — код бота применится только при выкладке с Мака с sudo."
systemctl restart dumskaya-lead
sleep 1
systemctl is-active --quiet dumskaya-lead && echo "Сервис заявок работает." || { echo "Сервис заявок не запустился:"; journalctl -u dumskaya-lead -n 20 --no-pager; }

echo "$MODE" > "$APP/mode"; echo "$HOME_MODE" > "$APP/home-mode"; chown "$USER_NAME":"$USER_NAME" "$APP/mode" "$APP/home-mode"
echo "dumskaya-home.com: режим $HOME_MODE"
# отпечатки: installed — то, что меняется только с sudo (Caddy, файлы сервисов, приём выкладки);
# running — код запущенного сервиса (новый код применяется перезапуском без sudo — autodeploy restart)
sha256sum "$HERE/caddy/"* "$HERE/dumskaya-lead.service" "$HERE/dumskaya-lead-restart.path" "$HERE/dumskaya-lead-restart.service" \
  "$HERE/autodeploy.sh" > "$APP/installed.sha256"
(cd "$HERE" && sha256sum -- *.py *.html *.json) > "$APP/running.sha256"
chown "$USER_NAME":"$USER_NAME" "$APP/installed.sha256" "$APP/running.sha256"
echo "Готово."
