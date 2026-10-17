#!/usr/bin/env bash
# Настройка заявок с сайта (Telegram, почта, перевод на русский) — запуск с Mac:  npm run leads
# Только перевод сообщений заказчиков:  npm run translate  (то же с --translate)
# Копирует на сервер мастер настройки и запускает его там: он спросит токен бота, пароль приложения Gmail,
# ключ сервиса перевода, всё проверит, перезапустит сервис заявок (пароль sudo) и отправит пробную заявку.
set -euo pipefail
cd "$(dirname "$0")/.."
HOST="${DEPLOY_HOST:-eurox}"
ssh "$HOST" 'mkdir -p ~/dumskaya/deploy'
rsync -az deploy/lead_setup.py deploy/translate.py deploy/lead.env.example "$HOST:dumskaya/deploy/"
ssh -t "$HOST" "python3 ~/dumskaya/deploy/lead_setup.py $*"
