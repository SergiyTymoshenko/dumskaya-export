# dumskaya-design.com

Сайт студии DUMSKAYA DESIGN: статический сайт на [Astro](https://astro.build), три языка (ru / ua / en).
Тексты и настройки лежат в `content/`, шаблоны — в `src/`, всё для сервера — в `deploy/`.

## Повседневная работа

Правки вносит Claude в этом репозитории. Чтобы выложить их на сайт, на Mac:

```bash
cd ~/dumskaya-site      # папка с клоном репозитория
git pull
npm run deploy
```

`npm run deploy` готовит новые фото, собирает сайт, проверяет его (`npm run check`) и копирует
на сервер только изменённые файлы. Если поменялись редиректы или сервис заявок, один раз спросит пароль sudo.

Посмотреть сайт на сервере до переключения домена: `npm run tunnel` и открыть http://localhost:8088.

## Первый запуск на Mac

В Терминале на Mac (не на сервере):

```bash
cd ~/dumskaya-site && git fetch origin && git reset --hard origin/main && bash scripts/mac-setup.sh
```

`scripts/mac-setup.sh` при необходимости обновляет Node.js (нужен 22.19+) и запускает `npm run deploy`.
Первый раз фото обрабатываются долго (около 2 300 штук) и около 700 МБ уходит на сервер, потом — только новое.
Если клона ещё нет: `git clone https://github.com/SergiyTymoshenko/dumskaya-export.git ~/dumskaya-site`.

Нужны python3 и ssh-доступ `ssh eurox`.
Оригиналы фото берутся из `~/Documents/dumskaya-export/images` (другая папка: `IMAGES_DIR=... npm run deploy`).

## Заявки с сайта

Форма отправляет заявку на сервер (`deploy/lead_service.py`), он пишет её в `~/dumskaya/leads.jsonl`
и пересылает в Telegram и на почту. Настройки — в файле на сервере `~/dumskaya/lead.env`
(образец: `deploy/lead.env.example`). После правки: `sudo systemctl restart dumskaya-lead`.
Проверка: `python3 ~/dumskaya/deploy/lead_service.py --test` (с переменными из lead.env) или
`curl -s http://127.0.0.1:8095/api/lead/health`.

## Включение домена

Когда DNS домена указывает на сервер (A `62.238.124.237`, AAAA `2a01:4f9:c015:6ee0::1`, www → CNAME на домен):

```bash
ssh -t eurox 'sudo bash ~/dumskaya/deploy/server-setup.sh live'
```

Caddy сам получит HTTPS-сертификат. Затем в Search Console отправить `https://dumskaya-design.com/sitemap.xml`.

## Если на сервере что-то пошло не так

```bash
ssh -t eurox 'sudo bash ~/dumskaya/deploy/server-doctor.sh'
```

Показывает состояние Caddy и причину ошибки, возвращает основной Caddyfile к виду до установки сайта
и проверяет, что остальные сайты на сервере отвечают.

## Где что лежит

| Путь | Что внутри |
|---|---|
| `content/pages/{ru,ua,en}/` | Страницы: мета-теги, языковые пары, блоки текста и фото |
| `content/projects.json`, `projects-overrides.json` | Карточки проектов и факты для «штампа» |
| `content/redirects.json` | 344 постоянных редиректа со старых адресов |
| `content/home.json`, `site.json` | Главная; меню, контакты, счётчики |
| `content/images.json`, `image-names.json` | Сведения о фото и их имена файлов |
| `scripts/` | Импорт со старого сайта, SEO, фото, проверка, выкладка |
| `deploy/` | Caddy, сервис заявок, установщик сервера |
