#!/usr/bin/env bash
# Состояние сервиса бота на сервере — для помощника выкладки (scripts/mac_agent.sh, действие server-check):
#   ssh eurox 'bash -s' < scripts/server_check.sh
# Только читает: сервис, открытые файлы и потоки процесса, нагрузку, журнал, ответы изнутри сервера. Ничего не меняет.
set -u
S=dumskaya-lead
echo "== сервис"
systemctl show "$S" -p ActiveState -p SubState -p MainPID -p NRestarts -p ExecMainStartTimestamp -p MemoryCurrent -p TasksCurrent --no-pager
PID="$(systemctl show -p MainPID --value "$S")"
if [ -n "$PID" ] && [ "$PID" != 0 ] && [ -d "/proc/$PID" ]; then
  echo "открыто файлов: $(ls /proc/$PID/fd 2>/dev/null | wc -l) · $(grep -i 'open files' /proc/$PID/limits)"
  echo "потоков: $(ls /proc/$PID/task | wc -l)"
  echo "== открытое по видам"
  ls -l "/proc/$PID/fd" 2>/dev/null | awk 'NR>1{print $NF}' | sed -E 's/[0-9]+/N/g' | sort | uniq -c | sort -rn | head -15
  echo "== потоки (процессор, состояние)"
  ps -L -o tid=,pcpu=,stat=,comm= -p "$PID" | sort -k2 -rn | head -15
fi
echo "== соединения с сервисом (порт 8095)"
ss -tan 2>/dev/null | awk '$4 ~ /:8095$/ || $5 ~ /:8095$/ {print $1}' | sort | uniq -c
echo "== нагрузка"
uptime; free -m; df -h ~ | tail -1
top -b -n1 -o %CPU 2>/dev/null | sed -n '7,14p'
echo "== журнал сервиса (последние строки)"
journalctl -u "$S" -n 150 --no-pager -o short-iso 2>&1 | cut -c1-400 | tail -150
echo "== выкладка"
tail -8 ~/dumskaya/autodeploy.log 2>/dev/null
echo "== страницы мини-приложений"
ls -la ~/dumskaya/deploy/*.html 2>&1
echo "== ответы изнутри сервера"
for p in /api/lead/health /api/crm/app /api/stats/app /api/portal/app; do
  curl -s -m 10 -o /dev/null -w "$p %{http_code} %{time_total} с\n" "http://127.0.0.1:8095$p" || echo "$p нет ответа"
done
