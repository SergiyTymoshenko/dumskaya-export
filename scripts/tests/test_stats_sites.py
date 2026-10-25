"""Статистика двух сайтов: dumskaya-design.com и каталог dumskaya-home.com (deploy/site_stats.py, home()).

Проверяет на журналах Caddy, собранных здесь же: у каждого сайта свои посетители, роботы отсеиваются одинаково
(сканер, «пулемёт» страниц, программа без заголовков браузера), просмотр каталога через туннель не считается,
журнал каталога не попадает в статистику студии, заявки — каждая в статистике своего сайта, страна доставки
из формы каталога — первой строкой заявки, время на странице и нажатия каталога — в его файлы,
«Графики» отдают выбранный сайт, утренняя строка — с каталогом, когда он на домене.
Запуск: python3 scripts/tests/test_stats_sites.py"""
import gzip
import json
import os
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone

LOGS = tempfile.mkdtemp(prefix="dd-logs-")
os.environ["SITE_LOG_GLOB"] = os.path.join(LOGS, "dumskaya*.log*")
os.environ["HOME_LOG_GLOB"] = os.path.join(LOGS, "dumskaya-home*.log*")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402  (сервис заявок с ботом на временных базах; HOME — временная папка)
import site_stats as S  # noqa: E402

FAILS = []


def check(ok, what):
    print(("✓ " if ok else "✗ ") + what)
    if not ok:
        FAILS.append(what)


UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
UA2 = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
GBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
NOW = time.time()
BASE = max(S.day_bounds(S.today())[0] + 5, NOW - 1500)     # все записи — сегодня, за последние 25 минут


def entry(ts, host, uri, ip, ua=UA, status=200, nav=True, lang="ru-RU,ru;q=0.9", ref=None):
    h = {"User-Agent": [ua]}
    if lang:
        h["Accept-Language"] = [lang]
    if nav:
        h["Sec-Fetch-Mode"] = ["navigate"]
    if ref:
        h["Referer"] = [ref]
    return json.dumps({"level": "info", "ts": ts, "logger": "http.log.access", "msg": "handled request",
                       "request": {"remote_ip": ip, "client_ip": ip, "proto": "HTTP/2.0", "method": "GET", "host": host,
                                   "uri": uri, "headers": h}, "status": status})


home, studio = [], []
t = BASE
# каталог: человек из Google — две страницы, оформление и фото (время на странице пришлёт позже через /api/hit)
home += [entry(t, "dumskaya-home.com", "/ru", "5.5.5.5", ref="https://www.google.com/"),
         entry(t + 1, "dumskaya-home.com", "/_astro/home.css", "5.5.5.5", nav=False),
         entry(t + 2, "dumskaya-home.com", "/img/poliform-westside-sofa-01-960.webp", "5.5.5.5", nav=False),
         entry(t + 40, "dumskaya-home.com", "/ru/divany", "5.5.5.5", ref="https://dumskaya-home.com/ru")]
# второй человек — немецкая версия, с сайта студии
home += [entry(t + 50, "dumskaya-home.com", "/de", "8.8.4.4", ua=UA2, lang="de-AT,de;q=0.9", ref="https://dumskaya-design.com/de"),
         entry(t + 51, "dumskaya-home.com", "/_astro/home.css", "8.8.4.4", ua=UA2, nav=False)]
# просмотр через туннель с Мака (режим preview) — не посетитель
home += [entry(t + 60, "localhost:8089", "/", "127.0.0.1", ua=UA2), entry(t + 61, "localhost:8089", "/_astro/home.css", "127.0.0.1", ua=UA2, nav=False)]
# сканер: ищет вход в админку
home += [entry(t + 70, "dumskaya-home.com", "/", "9.9.9.9"), entry(t + 71, "dumskaya-home.com", "/wp-login.php", "9.9.9.9", status=404)]
# «пулемёт»: 12 страниц за 6 секунд
home += [entry(t + 80 + i * 0.5, "dumskaya-home.com", f"/ru/divany/model-{i}", "10.0.0.7") for i in range(12)]
home += [entry(t + 81, "dumskaya-home.com", "/_astro/home.css", "10.0.0.7", nav=False)]
# программа без заголовков браузера, без оформления и времени
home += [entry(t + 90, "dumskaya-home.com", "/fr", "11.0.0.8", nav=False)]
# робот Google: русская и немецкая страницы
home += [entry(t + 100, "dumskaya-home.com", "/ru/divany", "66.249.66.1", ua=GBOT, lang=None, nav=False),
         entry(t + 101, "dumskaya-home.com", "/de/sofas", "66.249.66.1", ua=GBOT, lang=None, nav=False)]
# сайт студии: один человек
studio += [entry(t + 5, "dumskaya-design.com", "/", "6.6.6.6", ref="https://www.instagram.com/"),
           entry(t + 6, "dumskaya-design.com", "/_astro/site.css", "6.6.6.6", nav=False),
           entry(t + 30, "dumskaya-design.com", "/en/contact", "6.6.6.6")]
with open(os.path.join(LOGS, "dumskaya.log"), "w") as fh:
    fh.write("\n".join(sorted(studio, key=lambda x: json.loads(x)["ts"])) + "\n")
with open(os.path.join(LOGS, "dumskaya-home.log"), "w") as fh:
    fh.write("\n".join(sorted(home, key=lambda x: json.loads(x)["ts"])) + "\n")
# старая сжатая часть журнала каталога (вчера) — тоже не должна попасть к студии
with gzip.open(os.path.join(LOGS, "dumskaya-home-2026-10-24T08-00-00.000.log.gz"), "wt") as fh:
    fh.write(entry(BASE - 86400, "dumskaya-home.com", "/es", "12.0.0.9") + "\n")
os.utime(os.path.join(LOGS, "dumskaya-home-2026-10-24T08-00-00.000.log.gz"), (BASE - 86000, BASE - 86000))

# заявки: со студии, с каталога (новая — с site, старая — только с полным адресом), проверка с сервера — не считается
iso = lambda ts: datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")  # noqa: E731
with open(os.environ["LEADS_FILE"], "w", encoding="utf-8") as fh:
    for x in ({"time": iso(t + 31), "name": "Anna", "page": "/en/contact", "site": "dumskaya-design.com", "ip": "6.6.6.6", "lang": "en"},
              {"time": iso(t + 45), "name": "Олег", "page": "https://dumskaya-home.com/ru/divany", "site": "dumskaya-home.com", "ip": "5.5.5.5", "lang": "ru"},
              {"time": iso(t + 52), "name": "Jonas", "page": "https://dumskaya-home.com/de", "ip": "8.8.4.4", "lang": "de"},
              {"time": iso(t + 53), "name": "Проверка", "page": "/contact", "ip": "127.0.0.1", "lang": "ru"}):
        fh.write(json.dumps(x, ensure_ascii=False) + "\n")

PORT = 18761
H.serve(PORT)
URL = f"http://127.0.0.1:{PORT}"


def req(path, data=None, headers=None):
    body = data if isinstance(data, bytes) or data is None else json.dumps(data).encode()
    r = urllib.request.Request(URL + path, data=body, headers=headers or {}, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw and resp.headers.get("Content-Type", "").startswith("application/json") else raw)
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# время на странице и нажатие на e-mail с каталога — через /api/hit с адресом каталога
hh = {"Host": "dumskaya-home.com", "X-Forwarded-Host": "dumskaya-home.com", "X-Forwarded-For": "5.5.5.5", "User-Agent": UA,
      "Content-Type": "text/plain"}
check(req("/api/hit", json.dumps({"t": "time", "p": "/ru/divany", "s": 75}).encode(), hh)[0] == 204, "каталог: время на странице принято")
check(req("/api/hit", json.dumps({"t": "mail", "p": "/ru/divany"}).encode(), hh)[0] == 204, "каталог: нажатие на e-mail принято")
hs = dict(hh, **{"Host": "dumskaya-design.com", "X-Forwarded-Host": "dumskaya-design.com", "X-Forwarded-For": "6.6.6.6"})
check(req("/api/hit", json.dumps({"t": "time", "p": "/en/contact", "s": 40}).encode(), hs)[0] == 204, "студия: время на странице принято")
HM = S.home()
read = lambda p: open(p, encoding="utf-8").read() if os.path.exists(p) else ""  # noqa: E731
check('"/ru/divany"' in read(HM.TIMES_FILE) and '"/ru/divany"' not in read(S.TIMES_FILE), "время каталога — в times-home.jsonl, не у студии")
check('"mail"' in read(HM.HITS_FILE) and not read(S.HITS_FILE), "нажатия каталога — в hits-home.jsonl")
check('"/en/contact"' in read(S.TIMES_FILE), "время студии — в times.jsonl")
check(HM is not S and HM.STATS_DIR != S.STATS_DIR and HM.EXCLUDE_FILE == S.EXCLUDE_FILE and HM.SECRET_FILE == S.SECRET_FILE,
      "у каталога свои итоги дней, а «свои» адреса и соль — общие")

# заявка с каталога со страной доставки
code, _ = req("/api/lead", {"name": "Max Muster", "contact": "max@example.de", "message": "Preis für Westside, 3-Sitzer?", "country": "Deutschland, München",
                            "page": "/de/sofas/poliform-westside", "model": "DF-S0001", "lang": "de"},
              {"Host": "dumskaya-home.com", "X-Forwarded-Host": "dumskaya-home.com", "X-Forwarded-For": "13.0.0.10", "Content-Type": "application/json"})
last = json.loads(open(os.environ["LEADS_FILE"], encoding="utf-8").read().strip().splitlines()[-1])
check(code in (200, 502) and last["message"].startswith("Lieferung nach: Deutschland, München\n\nPreis") and last["site"] == "dumskaya-home.com",
      "страна доставки — первой строкой заявки каталога")
check("country" not in last, "отдельного поля в файле заявок нет — всё в сообщении")

# сами цифры
st, hm = S.web("7"), HM.web("7")
ts_, th = st["total"], hm["total"]
check(st["host"] == "dumskaya-design.com" and hm["host"] == "dumskaya-home.com" and hm["site"] == "home", "у данных — какой это сайт")
check(ts_["visitors"] == 1 and ts_["views"] == 2, f"студия: 1 посетитель, 2 просмотра (есть {ts_['visitors']}, {ts_['views']})")
tr = hm["rows"][-1]
check(tr["visitors"] == 2 and tr["views"] == 3, f"каталог сегодня: 2 посетителя, 3 просмотра — туннель, сканер, «пулемёт» и программа отсеяны (есть {tr['visitors']}, {tr['views']})")
check(th["visitors"] == 3 and hm["rows"][-2]["visitors"] == 1, "каталог за 7 дней: ещё вчерашний посетитель из сжатой части журнала")
check(ts_["leads"] == 1 and th["leads"] == 3, f"заявки: студия 1, каталог 3 (есть {ts_['leads']}, {th['leads']})")
check(th["google"] == 2 and ts_["google"] == 0, "робот Google — только у каталога")
row = hm["rows"][-1]
check(row["glang"] == {"ru": 1, "de": 1, "fr": 0, "es": 0} and [k for k, _ in hm["google_split"]] == ["ru", "de", "fr", "es"],
      "робот Google по языкам каталога")
check(dict(th["langs"]) == {"RU": 1, "DE": 1, "ES": 1}, f"языки каталога: {th['langs']}")
check(dict(ts_["langs"]) == {"RU": 1, "EN": 1}, f"языки студии: {ts_['langs']}")
src = dict(th["sources"])
check(src.get("Google") == 1 and src.get("сайт студии") == 1, f"источники каталога: Google и сайт студии ({src})")
check(th["contacts"] == 1 and ts_["contacts"] == 0, "нажатие на e-mail — у каталога")
check(th["avg_time"] == 75 and ts_["avg_time"] == 40, f"время на сайте у каждого своё ({th['avg_time']}, {ts_['avg_time']})")
pages = [p for p, _ in th["leads_pages"]]
check(any("/ru/divany" in p or "divany" in p for p in pages) or len(pages) == 3, f"страницы заявок каталога — путь, а не полный адрес ({pages})")

# «1 час» и «24 часа»
lv = HM.web("1h")
check(lv["summary"]["visitors"] == 2 and lv["host"] == "dumskaya-home.com", f"каталог, «1 час»: 2 посетителя ({lv['summary']['visitors']})")
s1 = next((x for x in lv["sessions"] if x["pages"][0]["path"] == "/ru"), None)
check(bool(s1) and [p["path"] for p in s1["pages"]] == ["/ru", "/ru/divany"] and s1["source"] == "Google", "каталог, «1 час»: путь посетителя и откуда пришёл")
check(S.web("24h")["total"]["visitors"] == 1 and HM.web("24h")["total"]["visitors"] == 2, "«24 часа» — у каждого сайта своё")

# режим: каталог ещё в preview → live=False
open(os.path.join(H.TMP, "dumskaya", "home-mode"), "w").write("preview")
check(HM.web("7")["live"] is False, "каталог в режиме просмотра — live: false (в «Графиках» — пояснение)")
open(os.path.join(H.TMP, "dumskaya", "home-mode"), "w").write("live")
check(HM.web("7")["live"] is True, "каталог на домене — live: true")

# «Графики» через сервис: site=home — каталог, без — студия; только разработчику и дизайнеру
init = H.init_data(H.OWNER, "Sergiy")
c1, d1 = req("/api/stats/data?p=7&site=home", headers={"X-Telegram-Init-Data": init})
c2, d2 = req("/api/stats/data?p=7", headers={"X-Telegram-Init-Data": init})
check(c1 == 200 and d1["host"] == "dumskaya-home.com" and d1["total"]["visitors"] == 3, "«Графики»: ?site=home — каталог")
check(c2 == 200 and d2["host"] == "dumskaya-design.com" and d2["total"]["visitors"] == 1, "«Графики»: без site — студия")
check(req("/api/stats/data?p=7&site=home", headers={"X-Telegram-Init-Data": H.init_data(H.CLIENT)})[0] == 403, "заказчику — нет доступа")

# «Не считать нас»: адрес первого посетителя каталога — свой → у каталога пересчёт без него
S.exclude_add("5.5.5.5", "тест")
check(HM.web("7")["rows"][-1]["visitors"] == 1, "свой адрес из «Не считать нас» — не считается и в каталоге")
S.exclude_remove("5.5.5.5/32")
check(HM.web("7")["rows"][-1]["visitors"] == 2, "адрес убран — снова считается")

# утренняя строка: с каталогом, когда он на домене, и две кнопки
H.CALLS.clear()
H.bot.s.put("stats:daily", "")
clock = lambda: datetime.now(S.TZ).replace(hour=10, minute=0)  # noqa: E731
S.SiteStats(H.bot, live_fn=lambda: True, clock=clock, home_live_fn=lambda: True).tick()
msgs = [p for m, p in H.CALLS if m == "sendMessage"]
txt = msgs[0]["text"] if msgs else ""
kb = json.dumps(msgs[0].get("reply_markup") if msgs else {}, ensure_ascii=False)
check("📈 Сайт за" in txt and "🛋 Магазин dumskaya-home.com" in txt, "утром: строка сайта и строка магазина")
check("site=home" in kb and "Магазин" in kb and "Студия" in kb, "утром: кнопки «Студия» и «Магазин»")
H.CALLS.clear()
H.bot.s.put("stats:daily", "")
S.SiteStats(H.bot, live_fn=lambda: True, clock=clock, home_live_fn=lambda: False).tick()
msgs = [p for m, p in H.CALLS if m == "sendMessage"]
check(bool(msgs) and "Магазин" not in msgs[0]["text"] and "site=home" not in json.dumps(msgs[0].get("reply_markup"), ensure_ascii=False),
      "каталог не на домене — утром только сайт студии")

# журнал каталога не попадает в студию и через сжатую часть
check(all("dumskaya-home" not in os.path.basename(f) for f in S._logs()) and len(HM._logs()) == 2, "части журнала разделены по сайтам")

# «Все»: оба сайта вместе — числа складываются по каждому периоду
for per in ("7", "24h", "30", "365", "all"):
    a_, b_, x = S.web(per), HM.web(per), S.web_all(per)
    ok_tot = all(x["total"][k] == a_["total"][k] + b_["total"][k] for k in ("visitors", "views", "leads", "google", "contacts"))
    sa = sum(r["visitors"] for r in a_["rows"]) + sum(r["visitors"] for r in b_["rows"])
    check(ok_tot and sum(r["visitors"] for r in x["rows"]) == sa and x["site"] == "all", f"«Все», {per}: итоги и строки — сумма двух сайтов")
x = S.web_all("7")
check(dict(x["total"]["langs"]).get("RU") == 2 and dict(x["total"]["langs"]).get("DE") == 1, f"«Все»: языки сложены ({x['total']['langs']})")
check(any(p[0].startswith("Магазин: ") for p in x["total"]["pages"]), "«Оба»: страницы магазина подписаны «Магазин:»")
check(x["total"]["avg_time"] is not None and 40 <= x["total"]["avg_time"] <= 75, f"«Все»: среднее время — между сайтами ({x['total']['avg_time']})")
lv = S.web_all("1h")
check(lv["summary"]["visitors"] == 3 and {s_["site"] for s_ in lv["sessions"]} == {"studio", "home"}, "«Все», «1 час»: заходы обоих сайтов, у каждого — сайт")
c3, d3 = req("/api/stats/data?p=7&site=all", headers={"X-Telegram-Init-Data": init})
check(c3 == 200 and d3["site"] == "all" and d3["total"]["visitors"] == 4, "«Графики»: ?site=all — оба сайта")

print("\n" + ("Всё в порядке" if not FAILS else f"Ошибок: {len(FAILS)}"))
sys.exit(1 if FAILS else 0)
