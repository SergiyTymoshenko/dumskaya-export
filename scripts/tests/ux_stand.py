"""Стенд для проверки UI/UX мини-приложений бота (scripts/ux_apps.cjs): сервис заявок с ботом, учётом и кабинетами
на временных базах (harness.py — Telegram подменён, ничего никуда не уходит) и тестовыми данными: проект с заказчиками,
подрядчиками, работниками и сотрудником студии, разговоры, файлы, заявки с сайтов и посетители в журналах сайта.
Запуск: python3 scripts/tests/ux_stand.py [порт] — печатает одну строку JSON {"port", "init": {роль: initData}} и работает,
пока его не остановят."""
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone

LOGS = tempfile.mkdtemp(prefix="dd-ux-logs-")
os.environ["SITE_LOG_GLOB"] = os.path.join(LOGS, "dumskaya*.log*")
os.environ["HOME_LOG_GLOB"] = os.path.join(LOGS, "dumskaya-home*.log*")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18770
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
UA2 = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"


def entry(ts, host, uri, ip, ua=UA, nav=True, lang="ru-RU,ru;q=0.9", ref=None):
    h = {"User-Agent": [ua], "Accept-Language": [lang]}
    if nav:
        h["Sec-Fetch-Mode"] = ["navigate"]
    if ref:
        h["Referer"] = [ref]
    return json.dumps({"level": "info", "ts": ts, "logger": "http.log.access", "msg": "handled request",
                       "request": {"remote_ip": ip, "client_ip": ip, "proto": "HTTP/2.0", "method": "GET", "host": host, "uri": uri, "headers": h},
                       "status": 200})


# посетители: за последние часы и за прошлые дни (несколько человек на обоих сайтах)
now = time.time()
studio, home = [], []
pages = ["/", "/proekty-interior-design", "/interior-design-apartment-bratislava-127m", "/price-interior-design-bratislava-wien-praha",
         "/en", "/de/innenarchitekt-wien", "/sk", "/contact-studio-interior-design-bratislava-vienna"]
refs = ["https://www.google.com/", "https://www.instagram.com/", None, "https://www.google.sk/"]
for d in range(0, 9):
    for k in range(3 + d % 4):
        t = now - d * 86400 - k * 1800 - 600
        ip = f"5.{d}.{k}.9"
        ua = UA if k % 2 else UA2
        studio += [entry(t, "dumskaya-design.com", pages[(d + k) % len(pages)], ip, ua=ua, ref=refs[k % len(refs)],
                         lang=["ru-RU,ru;q=0.9", "de-AT,de;q=0.9", "sk-SK,sk;q=0.9", "en-GB,en;q=0.9"][k % 4]),
                   entry(t + 1, "dumskaya-design.com", "/_astro/site.css", ip, ua=ua, nav=False),
                   entry(t + 40, "dumskaya-design.com", pages[(d + k + 3) % len(pages)], ip, ua=ua)]
        if k < 2:
            home += [entry(t + 5, "dumskaya-home.com", "/ru/divany", ip, ua=ua, ref="https://www.google.com/"),
                     entry(t + 6, "dumskaya-home.com", "/_astro/home.css", ip, ua=ua, nav=False)]
for name, rows in (("dumskaya.log", studio), ("dumskaya-home.log", home)):
    with open(os.path.join(LOGS, name), "w") as fh:
        fh.write("\n".join(sorted(rows, key=lambda x: json.loads(x)["ts"])) + "\n")

env = H.seed(full=True)
H.link_people(env, team=True)
pid = env["pid"]
H.serve(PORT)
open(os.path.join(H.TMP, "dumskaya", "home-mode"), "w").write("live")

import urllib.request  # noqa: E402


def call(path, uid, body=None, lang="ru", host=None):
    data = json.dumps(body).encode() if body is not None else None
    hd = {"X-Telegram-Init-Data": H.init_data(uid, lang=lang), "Content-Type": "application/json"}
    if host:
        hd.update({"Host": host, "X-Forwarded-Host": host, "X-Forwarded-For": "8.8.8.8"})
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data, headers=hd)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


# сотрудник студии: добавлен, подключился по ссылке, назначен на проект
_, r = call("/api/crm/save", H.IRINA, {"entity": "assistant", "data": {"name": "Мария Петренко", "position": "визуализатор", "phone": "+421 900 000 111"}})
aid = r.get("saved_id")
if aid:
    _, inv = call("/api/crm/invite", H.IRINA, {"kind": "assistant", "ref_id": aid, "lang": "ru"})
    if inv.get("link"):
        H.update(H.ASSIST, "/start " + inv["link"].split("start=")[1], first="Мария", lang="ru")
        call("/api/crm/save", H.IRINA, {"entity": "passist", "data": {"project_id": pid, "assistant_id": aid, "on": True}})
# заявки с сайтов (как из формы): студия на трёх языках, каталог со страной доставки
for host, body in (
        ("dumskaya-design.com", {"name": "Jana Horváthová", "contact": "+421 905 123 456", "message": "Dobrý deň, potrebujeme návrh interiéru bytu 74 m² v Petržalke.",
                                 "page": "/sk/dizajn-interieru-bratislava", "lang": "sk"}),
        ("dumskaya-design.com", {"name": "Олег", "contact": "oleg@example.com", "message": "Добрый день! Интересует пакет «Базовый» для дома 160 м² под Веной.",
                                 "page": "/price-interior-design-bratislava-wien-praha", "lang": "ru"}),
        ("dumskaya-design.com", {"name": "Thomas Gruber", "contact": "t.gruber@example.at", "message": "Küche nach Maß, Wien 1190 — bitte um Rückruf.",
                                 "page": "/de/kueche-nach-mass-wien", "lang": "de"}),
        ("dumskaya-home.com", {"name": "Max Muster", "contact": "max@example.de", "message": "Preis für Westside, 3-Sitzer?", "country": "Deutschland, München",
                               "page": "/de/poliform/westside-sofa", "model": "DF-S0001", "lang": "de"})):
    call("/api/lead", H.OWNER, body, host=host)
    time.sleep(0.2)

ids = {"owner": H.OWNER, "irina": H.IRINA, "client": H.CLIENT, "crew": H.CREW, "crew2": H.CREW2, "worker": H.WORKER, "assistant": H.ASSIST}
print(json.dumps({"port": PORT, "pid": pid, "ids": ids, "init": {k: H.init_data(v, lang="ru") for k, v in ids.items()}}), flush=True)
while True:
    time.sleep(3600)
