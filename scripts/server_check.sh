#!/usr/bin/env bash
# Состояние сервиса бота на сервере — для помощника выкладки (scripts/mac_agent.sh, действие server-check):
#   ssh eurox 'bash -s' < scripts/server_check.sh
# Только читает: сервис, открытые файлы и потоки процесса, нагрузку, журнал, ответы изнутри сервера. Ничего не меняет.
# Вывод короткий (помощник отправляет последние 400 строк): журнал — только строки ошибок, без повторов.
set -u
S=dumskaya-lead
echo "== сервис"
systemctl show "$S" -p ActiveState -p SubState -p MainPID -p NRestarts -p ExecMainStartTimestamp -p MemoryCurrent -p TasksCurrent --no-pager
echo "сейчас: $(date -u '+%F %T') UTC"
PID="$(systemctl show -p MainPID --value "$S")"
if [ -n "$PID" ] && [ "$PID" != 0 ] && [ -d "/proc/$PID" ]; then
  echo "открыто файлов: $(ls /proc/$PID/fd 2>/dev/null | wc -l) · $(grep -i 'open files' /proc/$PID/limits | tr -s ' ')"
  echo "потоков: $(ls /proc/$PID/task | wc -l)"
  echo "== открытое по видам"
  ls -l "/proc/$PID/fd" 2>/dev/null | awk 'NR>1{print $NF}' | sed -E 's/[0-9]+/N/g' | sort | uniq -c | sort -rn | head -12
  echo "== сетевые соединения процесса (состояние, куда)"
  ss -tanp 2>/dev/null | grep "pid=$PID," | awk '{split($5,a,":"); n=a[1]; if ($4 ~ /:8095$/) n="← к сервису (Caddy и др.)"; print $1, n}' \
    | sort | uniq -c | sort -rn | head -12
  echo "== потоки (процессор, состояние)"
  ps -L -o tid=,pcpu=,stat=,comm= -p "$PID" | sort -k2 -rn | head -8
fi
echo "== соединения с портом 8095"
ss -tan 2>/dev/null | awk '$4 ~ /:8095$/ || $5 ~ /:8095$/ {print $1}' | sort | uniq -c
echo "== нагрузка"
uptime; free -m | head -2; df -h ~ | tail -1
echo "== журнал сервиса за 3 часа: ошибки (сколько раз, первая и последняя)"
journalctl -u "$S" --since "-3 hours" --no-pager -o short-iso 2>&1 \
  | grep -E "Error|error|ошибка|Exception in thread|Too many|Killed|слушаю" | grep -v "During handling" \
  | awk '{t=$1; $1=""; $2=""; sub(/^ +[^ ]+ /,""); m=substr($0,1,220); if (!(m in c)) {o[++n]=m; f[m]=t}; c[m]++; l[m]=t}
         END {for (i=1;i<=n;i++) {m=o[i]; print c[m] "× " substr(f[m],12,8) "…" substr(l[m],12,8) " " m}}' | tail -40
echo "== выкладка"
tail -4 ~/dumskaya/autodeploy.log 2>/dev/null
echo "== ответы изнутри сервера"
for p in /api/lead/health /api/crm/app /api/stats/app /api/portal/app; do
  curl -s -m 10 -o /dev/null -w "$p %{http_code} %{time_total} с\n" "http://127.0.0.1:8095$p" || echo "$p нет ответа"
done
