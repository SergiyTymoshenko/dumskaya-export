#!/usr/bin/env bash
# Автовыкладка бота и «Студии» через GitHub — настройка один раз, с Мака:   npm run autodeploy
#
# 1) проверяет, что на сервере стоит приём выкладки (его ставит npm run deploy, один раз с паролем sudo);
# 2) GitHub CLI («gh»): если его нет — ставит через Homebrew; если не вошли — откроет вход в браузере;
# 3) создаёт отдельный ключ SSH только для выкладки и добавляет его на сервер в ~/.ssh/authorized_keys с ограничением
#    command="/usr/local/lib/dumskaya/autodeploy",restrict: этим ключом можно только передать папку deploy/ —
#    ни войти в оболочку, ни тронуть EuroExchange, Caddy и другие папки. Остальные ключи в файле не меняются;
# 4) кладёт ключ и адрес сервера в секрет репозитория DUMSKAYA_DEPLOY (напрямую в GitHub, в чат ничего не попадает),
#    на этом Маке ключ не остаётся;
# 5) запускает пробную выкладку и ждёт результат.
# Сайт по-прежнему выкладывается с Мака: npm run deploy.   Выключить автовыкладку: npm run autodeploy -- --off
set -euo pipefail
cd "$(dirname "$0")/.."
HOST="${DEPLOY_HOST:-eurox}"
REPO="${DEPLOY_REPO:-SergiyTymoshenko/dumskaya-export}"
NAME="dumskaya-autodeploy"
RECV="/usr/local/lib/dumskaya/autodeploy"
WORKFLOW="deploy-bot.yml"
step() { echo; echo "▸ $*"; }

ensure_gh() {
  if ! command -v gh >/dev/null; then
    if command -v brew >/dev/null; then
      echo "  ставлю GitHub CLI: brew install gh"
      brew install gh
    else
      echo "Нужен GitHub CLI: https://cli.github.com — поставьте его и запустите снова."; exit 1
    fi
  fi
  if ! gh auth status >/dev/null 2>&1; then
    echo "  войдите в GitHub — откроется браузер, подтвердите код:"
    gh auth login --hostname github.com --git-protocol https --web
  fi
  gh repo view "$REPO" --json name >/dev/null 2>&1 || { echo "Под этой учётной записью GitHub нет доступа к $REPO."; exit 1; }
}

if [ "${1:-}" = "--off" ]; then
  step "Выключаю автовыкладку"
  ensure_gh
  gh secret delete DUMSKAYA_DEPLOY -R "$REPO" 2>/dev/null && echo "  секрет в GitHub удалён" || echo "  секрета в GitHub не было"
  ssh "$HOST" "[ -f ~/.ssh/authorized_keys ] && sed -i '/ $NAME\$/d' ~/.ssh/authorized_keys; true"
  echo "  ключ выкладки на сервере удалён. Бот и «Студию» снова выкладывает только npm run deploy."
  exit 0
fi

step "1/5 Сервер"
ssh "$HOST" "test -x $RECV" || { echo "На сервере ещё нет приёма выкладки — сначала выложите с Мака: npm run deploy (один раз спросит пароль sudo)."; exit 1; }
CFG="$(ssh -G "$HOST")"
RH="$(awk '$1 == "hostname" {print $2; exit}' <<< "$CFG")"
RP="$(awk '$1 == "port" {print $2; exit}' <<< "$CFG")"
RU="$(awk '$1 == "user" {print $2; exit}' <<< "$CFG")"
if grep -qiE '^(proxyjump|proxycommand) ' <<< "$CFG" && ! grep -qiE '^(proxyjump|proxycommand) none$' <<< "$CFG"; then
  echo "К серверу подключение идёт через промежуточный сервер (ProxyJump) — GitHub так не подключится. Напишите Claude."; exit 1
fi
HOSTKEY="$(ssh "$HOST" 'cat /etc/ssh/ssh_host_ed25519_key.pub' | awk '{print $1" "$2}')"
[ -n "$HOSTKEY" ] || { echo "Не удалось прочитать ключ сервера (/etc/ssh/ssh_host_ed25519_key.pub)."; exit 1; }
if [ "${RP:-22}" = 22 ]; then KNOWN="$RH $HOSTKEY"; else KNOWN="[$RH]:$RP $HOSTKEY"; fi
echo "  сервер: $RU@$RH, порт ${RP:-22}"

step "2/5 GitHub"
ensure_gh
echo "  репозиторий: $REPO"

step "3/5 Ключ только для выкладки"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ssh-keygen -q -t ed25519 -N '' -C "$NAME" -f "$TMP/key"
LINE="command=\"$RECV\",restrict $(cut -d' ' -f1,2 "$TMP/key.pub") $NAME"
# прежний ключ выкладки (если был) заменяется; остальные строки файла — как были; копия — authorized_keys.bak-dumskaya
printf '%s\n' "$LINE" | ssh "$HOST" 'set -e; umask 077; mkdir -p ~/.ssh; f="$HOME/.ssh/authorized_keys"; touch "$f"; cp -p "$f" "$f.bak-dumskaya"
  sed -i "/ dumskaya-autodeploy\$/d" "$f"
  if [ -s "$f" ] && [ -n "$(tail -c1 "$f")" ]; then echo >> "$f"; fi
  cat >> "$f"' 
ssh "$HOST" true || { echo "Вход на сервер с этого Мака перестал работать — верните копию: ~/.ssh/authorized_keys.bak-dumskaya"; exit 1; }
printf '%s\n' "$KNOWN" > "$TMP/known"
K=(-i "$TMP/key" -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$TMP/known" -p "${RP:-22}")
OUT="$(ssh "${K[@]}" "$RU@$RH" ping 2>&1)" || { echo "Ключ выкладки не работает: $OUT"; exit 1; }
echo "  ключ работает: $OUT"
SHELL_TRY="$(ssh "${K[@]}" "$RU@$RH" 'echo shell-open' 2>&1 || true)"
if grep -q shell-open <<< "$SHELL_TRY"; then echo "Ключ открывает оболочку — так быть не должно. Остановлено, напишите Claude."; exit 1; fi
echo "  оболочку этот ключ не открывает — только приём выкладки"

step "4/5 Секрет в GitHub"
{
  echo "HOST=$RH"; echo "PORT=${RP:-22}"; echo "USER=$RU"
  echo "KNOWN=$(printf '%s\n' "$KNOWN" | base64 | tr -d '\n')"
  echo "KEY=$(base64 < "$TMP/key" | tr -d '\n')"
} | base64 | tr -d '\n' | gh secret set DUMSKAYA_DEPLOY -R "$REPO"
echo "  секрет DUMSKAYA_DEPLOY сохранён; на этом Маке ключа не осталось"

step "5/5 Пробная выкладка"
START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
gh workflow run "$WORKFLOW" -R "$REPO" --ref main
RID=""
for _ in $(seq 1 20); do
  sleep 3
  RID="$(gh run list -R "$REPO" --workflow "$WORKFLOW" --event workflow_dispatch --limit 1 --json databaseId,createdAt \
    -q ".[] | select(.createdAt >= \"$START\") | .databaseId")"
  [ -n "$RID" ] && break
done
[ -n "$RID" ] || { echo "GitHub не запустил выкладку — посмотрите вкладку Actions в репозитории."; exit 1; }
echo "  GitHub выкладывает, жду результат (обычно до минуты)…"
if gh run watch "$RID" -R "$REPO" --exit-status >/dev/null 2>&1; then
  echo
  echo "Готово: автовыкладка работает. После каждого изменения бота и «Студии» они сами выложатся на сервер,"
  echo "а вам в бот придёт тихое сообщение «🔄 Выложено автоматически». Сайт — по-прежнему: npm run deploy."
else
  echo "Пробная выкладка не прошла. Что ответил сервер:"
  gh run view "$RID" -R "$REPO" --log-failed | tail -15 | cut -c1-300
  echo "Пришлите Claude этот вывод. Частая причина — сервер не принимает SSH-подключения извне (брандмауэр Hetzner)."
  exit 1
fi
