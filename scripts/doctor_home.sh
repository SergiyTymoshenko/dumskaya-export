#!/usr/bin/env bash
# Проверка выкладки каталога DUMSKAYA HOME — что есть на Маке и на сервере:  bash scripts/doctor_home.sh
# Ничего не меняет. Вывод целиком можно прислать Claude.
set -uo pipefail
cd "$(dirname "$0")/.."
HOST="${DEPLOY_HOST:-eurox}"
EXPORT_DIR="${EXPORT_DIR:-$HOME/Documents/dumskaya-export}"
LOG=".deploy-home.log"
ok() { echo "  ✓ $*"; }
no() { echo "  ✗ $*"; }

echo "▸ Мак"
echo "  код: $(git log --oneline -1 2>/dev/null) ($(git status -sb 2>/dev/null | head -1))"
v="$(node -v 2>/dev/null || echo нет)"
if node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>22||(a===22&&b>=19)?0:1)' 2>/dev/null; then ok "Node.js $v"; else no "Node.js $v — нужен 22.19 или новее"; fi
if [ -d "$EXPORT_DIR/images/shop" ]; then
  ok "фото фабрик: $EXPORT_DIR/images/shop"
  for d in "$EXPORT_DIR"/images/shop/*/; do
    [ -d "$d" ] && printf "      %-14s %6s файлов\n" "$(basename "$d")" "$(find "$d" -type f ! -name '.DS_Store' | wc -l | tr -d ' ')"
  done
else
  no "нет папки с фото фабрик: $EXPORT_DIR/images/shop"
fi
if [ -f home/data/catalog.json ]; then
  ok "каталог собран: $(python3 -c 'import json;d=json.load(open("home/data/catalog.json"));p=d.get("products",[]);from collections import Counter;c=Counter(x["brand"] for x in p);print(len(p),"товаров —",", ".join(f"{k} {v}" for k,v in c.most_common()))' 2>/dev/null)"
else
  no "каталог ещё не собирался (нет home/data/catalog.json)"
fi
if [ -d home/img ]; then ok "фото для сайта: $(find home/img -type f | wc -l | tr -d ' ') файлов, $(du -sh home/img | cut -f1)"; else no "фото для сайта ещё не готовились (нет home/img)"; fi
if [ -f home/dist/index.html ]; then ok "сборка есть: $(find home/dist -name '*.html' | wc -l | tr -d ' ') страниц, $(date -r home/dist/index.html '+%d.%m %H:%M' 2>/dev/null)"; else no "сборки нет (нет home/dist/index.html)"; fi
if [ -f "$LOG" ]; then
  echo "  последняя выкладка ($(date -r "$LOG" '+%d.%m %H:%M' 2>/dev/null)), конец вывода:"
  tail -n 12 "$LOG" | sed 's/^/      /'
else
  echo "  журнала прошлой выкладки нет (он пишется с этой версии: $LOG)"
fi

echo "▸ Сервер ($HOST)"
ssh -o ConnectTimeout=15 "$HOST" '
  ok() { echo "  ✓ $*"; }; no() { echo "  ✗ $*"; }
  echo "  режим сайта студии: $(cat ~/dumskaya/mode 2>/dev/null || echo нет), каталога: $(cat ~/dumskaya/home-mode 2>/dev/null || echo нет)"
  S=/var/www/dumskaya-home/site
  if [ -d "$S" ]; then
    n=$(find "$S" -type f -name "*.html" 2>/dev/null | wc -l); i=$(find "$S/img" -type f 2>/dev/null | wc -l)
    [ -f "$S/index.html" ] && ok "каталог на сервере: $n страниц, фото $i, $(du -sh "$S" 2>/dev/null | cut -f1)" || no "папка каталога есть, но каталога в ней нет (страниц $n, фото $i)"
  else no "нет папки $S — сервер не настроен (npm run deploy)"; fi
  [ -f /etc/caddy/sites/home/dumskaya-home.caddy ] && ok "файл Caddy каталога: $(grep -m1 -E "^(http|dumskaya)" /etc/caddy/sites/home/dumskaya-home.caddy)" || no "нет файла Caddy каталога"
  grep -q "sites/home" /etc/caddy/sites/dumskaya.caddy 2>/dev/null && ok "подключён из файла сайта студии" || no "файл сайта студии его не подключает"
  c=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8089/ 2>/dev/null); echo "  ответ на 127.0.0.1:8089: ${c:-нет}"
  echo "  свободно на диске: $(df -h /var/www | awk "NR==2 {print \$4}")"
' 2>&1 || no "не получилось подключиться к серверу по ssh"
