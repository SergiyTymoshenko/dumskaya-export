#!/usr/bin/env bash
# Настройка заявок с сайта (Telegram и почта) — запуск с Mac:  npm run leads
# Копирует на сервер мастер настройки и запускает его там: он спросит токен бота, пароль приложения Gmail,
# всё проверит, перезапустит сервис заявок (пароль sudo) и отправит пробную заявку.
set -euo pipefail
cd "$(dirname "$0")/.."
HOST="${DEPLOY_HOST:-eurox}"
ssh "$HOST" 'mkdir -p ~/dumskaya/deploy'
rsync -az deploy/lead_setup.py deploy/lead.env.example "$HOST:dumskaya/deploy/"
ssh -t "$HOST" 'python3 ~/dumskaya/deploy/lead_setup.py'
