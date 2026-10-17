#!/usr/bin/env bash
# Докачка файлов по списку «путь<TAB>адрес» в папку выгрузки; уже скачанные пропускает. Бюджет времени — $2 секунд.
LIST="$1"; BUDGET="${2:-160}"
# папка выгрузки: по умолчанию — на уровень выше этого скрипта (он лежит в <выгрузка>/_work/)
ROOT="${EXPORT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
end=$(( $(date +%s) + BUDGET ))
todo=$(mktemp)
while IFS=$'\t' read -r dst url; do [ -s "$ROOT/$dst" ] || printf '%s\t%s\n' "$dst" "$url"; done < "$LIST" > "$todo"
echo "осталось: $(wc -l < "$todo")"
fetch() { dst="$1"; url="$2"; [ "$(date +%s)" -lt "$END" ] || exit 0; mkdir -p "$(dirname "$ROOT/$dst")"; curl -sfL --retry 2 --max-time 60 -A 'Mozilla/5.0 DumskayaCatalog/1.0' -o "$ROOT/$dst.part$BASHPID" "$url" && mv "$ROOT/$dst.part$BASHPID" "$ROOT/$dst" || { mkdir -p "$ROOT/_work/trash"; mv "$ROOT/$dst.part$BASHPID" "$ROOT/_work/trash/" 2>/dev/null; echo "FAIL $url"; }; }
export -f fetch; export ROOT; export END=$end
tr '\t' '\n' < "$todo" | xargs -d '\n' -n 2 -P 8 bash -c 'fetch "$0" "$1"'
left=0; while IFS=$'\t' read -r dst url; do [ -s "$ROOT/$dst" ] || left=$((left+1)); done < "$LIST"; echo "не скачано: $left из $(wc -l < "$LIST")"
