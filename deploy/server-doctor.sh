#!/usr/bin/env bash
# Диагностика и безопасный откат настроек Caddy для dumskaya-design.com.
#   sudo bash ~/dumskaya/deploy/server-doctor.sh
#
# 1) показывает состояние Caddy и причину последней ошибки;
# 2) отключает сайт: убирает из /etc/caddy/Caddyfile строку, добавленную server-setup.sh, и переименовывает файл сайта;
# 3) проверяет, что Caddy работает и остальные сайты на сервере отвечают.
# Выход 0 — откат прошёл и причина ошибки известна (можно запускать выкладку снова), иначе 1.
set -uo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Запустите через sudo"; exit 1; }
CF=/etc/caddy/Caddyfile
SITES=/etc/caddy/sites
TS="$(date +%Y%m%d-%H%M%S)"
CU="$(systemctl show caddy -p User --value 2>/dev/null)"; CU="${CU:-root}"
as_caddy() { if [ "$CU" = root ]; then "$@"; else sudo -u "$CU" -H "$@"; fi; }
cut_() { cut -c1-400; }

echo "=== 1. Caddy"
echo "состояние: $(systemctl is-active caddy)   версия: $(caddy version | cut -d' ' -f1)   пользователь: $CU"
systemctl cat caddy 2>/dev/null | grep -E '^(ExecStart|ExecReload)=' | cut_

echo "=== 2. Ошибки Caddy за последние 2 часа"
journalctl -u caddy --since "-2 hours" --no-pager -o cat 2>/dev/null | grep -iE 'error|fail|denied|address already' | tail -8 | cut_

echo "=== 3. Порты 2019 (управление Caddy), 8088 (просмотр сайта), 8095 (заявки)"
ss -ltnp 2>/dev/null | grep -E ':(2019|8088|8095)\s' | cut -c1-200 || true
echo "--- настройки в основном Caddyfile:"
grep -nE '^\s*(admin|bind|import|storage)\b' "$CF" | cut_ || true

echo "=== 4. Проверка конфига от имени пользователя $CU (как при перезагрузке)"
ls -la /var/log/caddy/ 2>/dev/null | sed -n '2,20p'
CHECK="$(as_caddy caddy validate --config "$CF" --adapter caddyfile 2>&1 | tail -3)"
echo "$CHECK" | cut_
KNOWN=0
if echo "$CHECK" | grep -q 'dumskaya.log' && echo "$CHECK" | grep -qi 'permission denied'; then
  KNOWN=1
  echo ">>> Причина: файл журнала сайта создан от root, а Caddy работает от $CU и не может в него писать."
fi

echo "=== 5. Откат основного Caddyfile"
# Основной Caddyfile принадлежит проекту EuroExchange (его выкладка перезаписывает файл целиком):
# убирается только строка, которую добавил server-setup.sh. Общую строку «import sites/*.caddy»
# из файла EuroExchange не трогаем — сайт отключается переименованием своего файла ниже.
if grep -qE '^\s*import\s+sites/dumskaya\.caddy\s*$' "$CF"; then
  cp -a "$CF" "$CF.failed-$TS"
  sed -i -E '/^# dumskaya-design\.com \(~\/dumskaya\/deploy\/server-setup\.sh\)$/d; /^\s*import\s+sites\/dumskaya\.caddy\s*$/d' "$CF"
  echo "Из Caddyfile удалена строка import сайта (остальное не трогаю)."
else
  echo "Своей строки import в Caddyfile нет — в нём ничего не меняю."
fi
for f in dumskaya.caddy dumskaya-redirects.snippet; do
  [ -f "$SITES/$f" ] && mv "$SITES/$f" "$SITES/$f.off-$TS"
done
[ -f /var/log/caddy/dumskaya.log ] && chown "$CU":"$CU" /var/log/caddy/dumskaya.log 2>/dev/null

echo "=== 6. Проверка после отката"
OK=1
as_caddy caddy validate --config "$CF" --adapter caddyfile >/tmp/dd-validate.log 2>&1 \
  && echo "конфиг: в порядке" || { echo "конфиг: ОШИБКА"; tail -3 /tmp/dd-validate.log | cut_; OK=0; }
if systemctl is-active --quiet caddy; then
  if systemctl reload caddy 2>/dev/null; then echo "перезагрузка Caddy: работает"; else echo "перезагрузка Caddy: НЕ работает"; OK=0
    journalctl -u caddy -n 5 --no-pager -o cat | cut_; fi
else
  echo "Caddy не запущен — запускаю"; systemctl restart caddy; sleep 2
fi
echo "Caddy: $(systemctl is-active caddy)"; systemctl is-active --quiet caddy || OK=0

echo "--- сайты на этом сервере (запрос к локальному Caddy):"
grep -E '^[^#[:space:]({][^{]*\{[[:space:]]*$' "$CF" | sed 's/{.*//' | tr ',' ' ' | tr -s ' ' '\n' | grep -v '^$' | while read -r a; do
  case "$a" in :*|*\**) continue ;; http://*|https://*) u="$a" ;; *) u="https://$a" ;; esac
  printf '  %-45s %s\n' "$u" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 --connect-to ::127.0.0.1: "$u/" 2>/dev/null)"
done

echo "==="
if [ "$OK" = 1 ] && [ "$KNOWN" = 1 ]; then
  echo "Откат выполнен, Caddy и другие сайты работают. Причина найдена — можно выкладывать снова."
  exit 0
elif [ "$OK" = 1 ]; then
  echo "Откат выполнен, Caddy и другие сайты работают. Причину нужно разобрать — пришлите Claude этот вывод."
  exit 1
else
  echo "ВНИМАНИЕ: после отката есть проблема. Пришлите Claude этот вывод."
  exit 1
fi
