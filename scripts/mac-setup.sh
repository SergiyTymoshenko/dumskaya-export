#!/usr/bin/env bash
# Первый запуск на Mac одной командой (из папки ~/dumskaya-site):   bash scripts/mac-setup.sh
#
# 1) Если Node.js старее 22.19 — обновляет его тем же способом, каким он был установлен
#    (nvm, Homebrew или официальный установщик с nodejs.org).
# 2) Запускает выкладку сайта (npm run deploy) и не даёт Mac уснуть, пока она идёт.
set -euo pipefail
cd "$(dirname "$0")/.."

node_ok() {
  command -v node >/dev/null 2>&1 &&
    node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>22||(a===22&&b>=19)?0:1)'
}

if node_ok; then
  echo "▸ Node.js $(node -v) — подходит"
else
  CUR="$(command -v node 2>/dev/null || true)"
  LINK="$( [ -n "$CUR" ] && ls -l "$CUR" 2>/dev/null || true)"
  echo "▸ Node.js ${CUR:+$(node -v) }устарел — обновляю"
  if [[ "$CUR" == *"/.nvm/"* ]] && [ -s "$HOME/.nvm/nvm.sh" ]; then
    echo "  способ: nvm"
    set +eu
    . "$HOME/.nvm/nvm.sh"
    nvm install --lts && nvm alias default 'lts/*' && nvm use default >/dev/null
    set -eu
  elif [[ "$LINK" == *"/Cellar/"* ]] && command -v brew >/dev/null 2>&1; then
    echo "  способ: Homebrew"
    brew upgrade node || brew install node
  else
    echo "  способ: официальный установщик с nodejs.org"
    VER="$(curl -fsSL https://nodejs.org/dist/index.json |
      python3 -c 'import json,sys; print(next(r["version"] for r in json.load(sys.stdin) if r["lts"]))')"
    TMP="$(mktemp -d)"
    echo "  скачиваю node-$VER.pkg"
    curl -fL --progress-bar -o "$TMP/node-$VER.pkg" "https://nodejs.org/dist/$VER/node-$VER.pkg"
    (cd "$TMP" && curl -fsSL "https://nodejs.org/dist/$VER/SHASUMS256.txt" | grep " node-$VER.pkg\$" | shasum -a 256 -c - >/dev/null)
    echo
    echo "  Установка Node.js $VER."
    echo "  Введите пароль от этого Mac (при вводе символы не видны) и нажмите Enter:"
    sudo installer -pkg "$TMP/node-$VER.pkg" -target /
    rm -rf "$TMP"
    export PATH="/usr/local/bin:$PATH"
  fi
  hash -r
  if ! node_ok; then
    echo
    echo "Node.js не обновился. Пришлите Claude вывод команды:  which -a node; node -v"
    exit 1
  fi
  echo "  готово: Node.js $(node -v)"
fi

echo "▸ Выкладка сайта"
if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -i npm run deploy
else
  npm run deploy
fi
