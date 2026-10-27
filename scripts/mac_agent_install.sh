#!/usr/bin/env bash
# Поставить помощника выкладки на Мак (scripts/mac_agent.sh) — один раз:
#   cd ~/dumskaya-site && git pull && bash scripts/mac_agent_install.sh
# Убрать:  bash scripts/mac_agent_install.sh --remove
# Ставит задачу launchd «com.dumskaya.agent»: раз в 2 минуты, пока вы вошли в систему и Мак не спит. Запоминает
# нынешние пути (node, npm, python3), чтобы выкладка работала так же, как из вашего Терминала. Проверяет, что Мак
# может отправлять вывод в GitHub (ветка agent-log) и заходить на сервер без пароля.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.dumskaya.agent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ "${1:-}" = "--remove" ]; then
  rm -f "$PLIST"; echo "Помощник выкладки убран."; exit 0
fi
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DIR/scripts/mac_agent.sh</string></array>
  <key>StartInterval</key><integer>120</integer>
  <key>RunAtLoad</key><true/>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>$PATH</string>
    <key>HOME</key><string>$HOME</string>
    <key>LANG</key><string>${LANG:-ru_RU.UTF-8}</string>
    <key>EXPORT_DIR</key><string>${EXPORT_DIR:-$HOME/Documents/dumskaya-export}</string>
  </dict>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/dumskaya-agent.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/dumskaya-agent.log</string>
</dict></plist>
EOF
echo "▸ Проверка доступа"
cd "$DIR"
if GIT_TERMINAL_PROMPT=0 git push -q --dry-run origin HEAD:refs/heads/agent-log 2>/dev/null; then echo "  GitHub: отправлять вывод можно ✓"
else echo "  GitHub: ✗ Мак не может отправлять в репозиторий — пришлите Claude этот вывод"; fi
if ssh -o BatchMode=yes -o ConnectTimeout=10 eurox true 2>/dev/null; then echo "  сервер eurox: вход без пароля ✓"
else echo "  сервер eurox: ✗ без пароля не пускает — выкладка из помощника не пройдёт, пришлите Claude этот вывод"; fi
command -v node >/dev/null && echo "  node $(node -v) ✓" || echo "  node: ✗ не найден"
rm -f "$HOME/.dumskaya-agent/last-id"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Готово: помощник выкладки работает (раз в 2 минуты смотрит заявки Claude). Убрать: bash scripts/mac_agent_install.sh --remove"
