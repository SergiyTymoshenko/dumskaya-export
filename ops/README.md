# Заявки помощнику выкладки на Маке

`request.json` — что Мак выполнит сам (scripts/mac_agent.sh, раз в 2 минуты): `{"id": "…", "do": [...]}`.
Новый `id` — новая заявка. Действия: `deploy`, `deploy-home`, `dl:<фабрика>`, `status`; ничего другого помощник
не запускает. Вывод — ветка `agent-log`, файл `last.log`:
`git fetch -q origin agent-log && git show FETCH_HEAD:last.log`.
