"""Проверка IndexNow (deploy/indexnow.py): первый раз — все страницы, потом только новые, изменённые и удалённые;
правка оформления, меню и подвала не считается изменением; каталог в режиме просмотра ждёт; не больше BATCH адресов
за час; ошибка — повтор и одно сообщение в бот через сутки. Сайт — временная папка, поисковики и сеть подменены.

   python3 scripts/tests/test_indexnow.py      — в конце «OK: N проверок»"""
import os
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="indexnow-test-")
os.environ["HOME"] = TMP                                  # ~/dumskaya → временная папка (режимы сайтов, состояние)
os.environ["SITE_DIR"] = os.path.join(TMP, "site")
os.environ["HOME_SITE_DIR"] = os.path.join(TMP, "home-site")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "deploy"))
import indexnow as I  # noqa: E402

ok = 0


def check(cond, what):
    global ok
    if not cond:
        raise AssertionError(what)
    ok += 1


HOST, KEY = "dumskaya-design.com", "0123456789abcdef0123456789abcdef"
ROOT = os.environ["SITE_DIR"]
APP = os.path.join(TMP, "dumskaya")
os.makedirs(ROOT)
os.makedirs(APP)
CALLS, MODE, ONLINE, MSGS = [], {"code": 202}, {"ok": True}, []


def fake_post(api, host, key, urls):
    CALLS.append((api, host, key, list(urls)))
    code = MODE.get(api.split("/")[2], MODE["code"])        # можно задать ответ одного поисковика: MODE["www.bing.com"]
    return code, "" if code in (200, 202) else "ключ не принят"


class FakeBot:
    def notify_owner(self, text):
        MSGS.append(text)


I.post = fake_post
I.key_online = lambda host, key: (True, "") if ONLINE["ok"] else (False, "сайт не открывается на домене (URLError)")
I.BOT = FakeBot()
LOG = []


def page(title, text, css="Base.AbC123", menu="Меню", year="2026"):
    return (f'<!DOCTYPE html><html><head><title>{title}</title><meta name="description" content="{title} — описание">'
            f'<link rel="stylesheet" href="/_astro/{css}.css"><link rel="canonical" href="https://{HOST}/x">'
            f'<style>.a{{color:red}}</style><script type="application/ld+json">{{"name":"{title}"}}</script></head>'
            f'<body><header data-astro-cid-abc123><nav>{menu}</nav></header>'
            f'<main id="main"><h1 data-astro-cid-{css[-6:].lower()}>{title}</h1><p>{text}</p>'
            f'<img src="/_astro/pic.{css}.webp"><script>var t={time.time()}</script></main>'
            f'<footer>© {year} DUMSKAYA DESIGN</footer></body></html>')


PATHS = ["/"] + [f"/p{i}" for i in range(1, 12)] + ["/ua/p1"]
URL = {p: f"https://{HOST}{p}" for p in PATHS}


CHANGED = set()


def write_site(paths=PATHS, change=None, **kw):
    """Собрать «сайт»: страницы и sitemap.xml; change — страница с новым текстом (правки копятся, как на настоящем сайте).
    Время файлов — как после новой сборки."""
    if change:
        CHANGED.add(change)
    for p in PATHS:
        f = os.path.join(ROOT, "index.html" if p == "/" else p.strip("/") + ".html")
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(page(p, "текст " + p + (" (новое)" if p in CHANGED else ""), **kw))
        t = time.time() + len(CALLS) + 1
        os.utime(f, (t, t))
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0"?><urlset>' + "".join(
            f"<url><loc>{URL[p]}</loc><image:image><image:loc>https://{HOST}/img/a.webp</image:loc></image:image></url>"
            for p in paths) + "</urlset>")


def run():
    CALLS.clear()
    outs = I.run_all(log=LOG.append)
    return {o["host"]: o for o in outs}


def sent_urls():
    return sorted({u for c in CALLS for u in c[3]})


# --- сайт ещё не открыт (режим preview) или нет ключа
write_site()
with open(os.path.join(APP, "mode"), "w") as f:
    f.write("preview")
r = run()
check(r[HOST]["status"] == "preview" and not CALLS, "preview: ничего не отправляем")
check(r["dumskaya-home.com"]["status"] == "preview", "каталог без файла режима — режим просмотра")
with open(os.path.join(APP, "mode"), "w") as f:
    f.write("live")
r = run()
check(r[HOST]["status"] == "nokey" and not CALLS, "нет файла ключа — не отправляем")
with open(os.path.join(ROOT, KEY + ".txt"), "w") as f:
    f.write(KEY)
with open(os.path.join(ROOT, "ffffffffffffffffffffffffffffffff.txt"), "w") as f:
    f.write("не ключ")
check(I.find_key(ROOT) == KEY, "ключ — файл, внутри которого он сам")

# --- первый раз: все страницы, во все три поисковика, с ключом
r = run()
check(r[HOST]["status"] == "ok" and len(r[HOST]["new"]) == len(PATHS), "первый раз — все страницы новые")
check(len(CALLS) == 3 and {c[0] for c in CALLS} == {a for _, a in I.ENGINES}, "отправка в Bing, Яндекс и Seznam")
check(sent_urls() == sorted(URL.values()), "отправлены ровно адреса из карты сайта (без фото)")
check(all(c[1] == HOST and c[2] == KEY for c in CALLS), "домен и ключ в запросе")
s = {x["host"]: x for x in I.status()}[HOST]
check(s["status"] == "ok" and s["last_count"] == len(PATHS) and s["total"] == len(PATHS) and s["pending"] == 0, "сводка после отправки")
check(s["results"]["Bing"][0] == 202, "ответы поисковиков в сводке")

# --- повтор и новая сборка без изменений содержимого: оформление, меню, подвал, скрипты — не изменение
r = run()
check(not CALLS and r[HOST]["status"] == "ok", "повтор без изменений — ничего не отправляем")
write_site(css="Base.XyZ789", menu="Меню и Каталог", year="2027")
r = run()
check(not CALLS, "новое оформление, меню и подвал — не изменение страниц")

# --- изменилась одна страница
write_site(change="/p3")
r = run()
check(sent_urls() == [URL["/p3"]] and r[HOST]["changed"] == [URL["/p3"]], "изменилась одна страница — отправлена только она")

# --- страница удалена из карты сайта (и файла нет)
os.remove(os.path.join(ROOT, "p11.html"))
write_site(paths=[p for p in PATHS if p != "/p11"])
r = run()
check(sent_urls() == [URL["/p11"]] and r[HOST]["gone"] == [URL["/p11"]], "удалённая страница — отправлена (поисковик увидит 404)")
r = run()
check(not CALLS, "удалённая отправляется один раз")

# --- карта сайта почти пустая (выкладка в процессе) — ничего не отправляем и ничего не считаем удалённым
with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as fh:
    fh.write(f"<urlset><url><loc>{URL['/p1']}</loc></url></urlset>")
r = run()
check(r[HOST]["status"] == "wait" and not CALLS, "короткая карта сайта — ждём следующего часа")
write_site(paths=[p for p in PATHS if p != "/p11"])
r = run()
check(not CALLS, "после выкладки — снова без изменений")

# --- ошибки: поисковики не принимают, потом сутки, потом снова принимают
write_site(paths=[p for p in PATHS if p != "/p11"], change="/p5")
MODE["code"] = 403
r = run()
check(r[HOST]["status"] == "error" and "403" in r[HOST]["note"] and not MSGS, "не приняли — ошибка, сообщения пока нет")
r = run()
check(sent_urls() == [URL["/p5"]], "не принятое отправляется снова через час")
st = I.load(HOST)
st["fail_since"] = int(time.time()) - 25 * 3600
I.save(HOST, st)
run()
check(len(MSGS) == 1 and "IndexNow" in MSGS[0] and HOST in MSGS[0], "больше суток — одно сообщение разработчику")
run()
check(len(MSGS) == 1, "второго сообщения нет")
MODE["code"] = 200
r = run()
check(r[HOST]["status"] == "ok" and sent_urls() == [URL["/p5"]], "снова принимают — отправлено")
check(I.load(HOST).get("fail_since") is None and I.status()[0]["fail_since"] is None, "ошибка сброшена")
write_site(paths=[p for p in PATHS if p != "/p11"], change="/p6")
ONLINE["ok"] = False
r = run()
check(r[HOST]["status"] == "error" and not CALLS and "домене" in r[HOST]["note"], "ключ не открывается — не отправляем, причина видна")
ONLINE["ok"] = True
check(run()[HOST]["status"] == "ok", "ключ снова открывается — отправлено")

# --- не больше BATCH адресов за час
I.BATCH = 5
r = I.run_all(log=LOG.append, resend=True)
st = I.load(HOST)
check(st["last_count"] == 5 and st["pending"] == len(PATHS) - 1 - 5, "за час — не больше BATCH адресов, остальное ждёт")
n = 0
while I.load(HOST)["pending"] and n < 5:
    run()
    n += 1
check(I.load(HOST)["pending"] == 0 and n == 2, "остальное доотправлено в следующие часы")
I.BATCH = 10000

# --- один поисковик не принял (другие приняли) — ему одному повтор через час; принял — повторов больше нет
BING = "https://www.bing.com/indexnow"
write_site(paths=[p for p in PATHS if p != "/p11"], change="/p9")
MODE["www.bing.com"] = 403
r = run()
check(r[HOST]["status"] == "ok" and "Bing" in r[HOST]["note"] and "повторим" in r[HOST]["note"], "Bing не принял — видно в сводке")
check(I.load(HOST)["retry"]["Bing"]["urls"] == [URL["/p9"]], "адрес отложен для Bing")
r = run()
check([c[0] for c in CALLS] == [BING] and CALLS[0][3] == [URL["/p9"]], "через час — повтор только для Bing и только отложенное")
check(I.load(HOST)["retry"].get("Bing"), "Bing снова не принял — адрес остаётся отложенным")
write_site(paths=[p for p in PATHS if p != "/p11"], change="/p10")
r = run()
bing = [c for c in CALLS if c[0] == BING]
check(len(CALLS) == 3 and sorted(bing[0][3]) == sorted([URL["/p9"], URL["/p10"]]), "Bing получает отложенное вместе с новым, другие — только новое")
MODE.pop("www.bing.com")
r = run()
check([c[0] for c in CALLS] == [BING] and r[HOST]["status"] == "ok", "Bing принял отложенные")
check(not I.load(HOST)["retry"] and I.status()[0]["results"]["Bing"][0] in (200, 202), "отложенных больше нет, в сводке Bing принял")
r = run()
check(not CALLS, "дальше — тишина, пока нет изменений")
MODE["www.bing.com"] = 403
write_site(paths=[p for p in PATHS if p != "/p11"], change="/p1")
run()
st = I.load(HOST)
st["retry"]["Bing"]["since"] = int(time.time()) - 4 * 86400
I.save(HOST, st)
run()
check(not I.load(HOST)["retry"] and any("больше не повторяем" in m for m in LOG), "больше 3 дней — повторять перестаём")
MODE.pop("www.bing.com")

# --- dry-run ничего не отправляет и не меняет
write_site(paths=[p for p in PATHS if p != "/p11"], change="/p7")
CALLS.clear()
before = open(I.state_path(HOST), encoding="utf-8").read()
r = {o["host"]: o for o in I.run_all(log=LOG.append, dry=True)}
check(r[HOST]["status"] == "dry" and URL["/p7"] in r[HOST]["changed"] and not CALLS, "dry-run показывает изменения")
check(open(I.state_path(HOST), encoding="utf-8").read() == before, "dry-run не меняет состояние")

# --- раз в час, в своём потоке
I._last = 0.0
I.tick(log=LOG.append)
for _ in range(50):
    if not I._lock.locked() and any(c for c in CALLS):
        break
    time.sleep(0.1)
check(URL["/p7"] in sent_urls(), "tick запускает проверку")
CALLS.clear()
write_site(paths=[p for p in PATHS if p != "/p11"], change="/p8")
I.tick(log=LOG.append)
time.sleep(0.3)
check(not CALLS, "второй tick в течение часа ничего не делает")

# --- отпечаток: файл страницы по адресу, без выхода за папку сайта
check(I.page_file(ROOT, f"https://{HOST}/") and I.page_file(ROOT, URL["/ua/p1"]).endswith("ua/p1.html"), "адрес → файл .html")
check(I.page_file(ROOT, f"https://{HOST}/../../etc/passwd") is None, "адрес не выходит за папку сайта")

# --- даты <lastmod> в карте сайта (решено 25.10.2026): изменённая — та, у которой сменилась дата
LM = {p: "2026-10-23" for p in PATHS if p != "/p11"}


def write_lastmod(change_text=None, index=False):
    """Карта сайта с датами; index — как у каталога: sitemap.xml — индекс из двух файлов."""
    if change_text:
        CHANGED.add(change_text)
    for p in [x for x in PATHS if x != "/p11"]:
        f = os.path.join(ROOT, "index.html" if p == "/" else p.strip("/") + ".html")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(page(p, "текст " + p + (" (новое)" if p in CHANGED else "")))
        t = time.time() + len(CALLS) + 7
        os.utime(f, (t, t))
    rows = [f"<url><loc>{URL[p]}</loc><lastmod>{d}</lastmod></url>" for p, d in LM.items()]
    for n in os.listdir(ROOT):
        if n.startswith("sitemap"):
            os.remove(os.path.join(ROOT, n))
    if not index:
        with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as fh:
            fh.write('<?xml version="1.0"?><urlset>' + "".join(rows) + "</urlset>")
        return
    half = len(rows) // 2
    for name, part in (("sitemap-pages.xml", rows[:half]), ("sitemap-products-x.xml", rows[half:])):
        with open(os.path.join(ROOT, name), "w", encoding="utf-8") as fh:
            fh.write('<?xml version="1.0"?><urlset>' + "".join(part) + "</urlset>")
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0"?><sitemapindex>' + "".join(
            f"<sitemap><loc>https://{HOST}/{n}</loc><lastmod>2026-10-25</lastmod></sitemap>" for n in ("sitemap-pages.xml", "sitemap-products-x.xml"))
            + "</sitemapindex>")


LM["/p8"] = time.strftime("%Y-%m-%d")                  # /p8 изменилась после последней отправки — дата сегодняшняя
write_lastmod()
r = run()
check(sent_urls() == [URL["/p8"]], "появились даты: страницы, изменённые до последней отправки, заново не отправляем — "
      "только /p8 с датой не раньше дня отправки (переход со старых отпечатков)")
check(all(str(v).startswith("lastmod:") for v in I.load(HOST)["sent"].values()), "запомнены даты страниц")
LM["/p4"] = "2026-10-25"
write_lastmod()
r = run()
check(sent_urls() == [URL["/p4"]], "сменилась дата одной страницы — отправлена только она")
write_lastmod(change_text="/p5")
r = run()
check(not CALLS, "текст страницы изменился, а дата нет (например, правка шаблона) — не отправляем: решает дата")
LM["/p6"] = "2026-10-26"
write_lastmod(index=True)
check(len(I.sitemap_entries(ROOT, HOST)) == len(LM) and ("https://dumskaya-design.com/p6", "2026-10-26") in I.sitemap_entries(ROOT, HOST),
      "индекс карт сайта: адреса и даты из всех его файлов")
r = run()
check(sent_urls() == [URL["/p6"]], "индекс карт сайта: отправлена только страница с новой датой")
os.remove(os.path.join(ROOT, "sitemap-products-x.xml"))
r = run()
check(r[HOST]["status"] == "wait" and not CALLS, "файл из индекса не выложен — ждём, ничего не удаляем")

# --- robots.txt закрывает сайт (каталог до запуска) — не отправляем
write_lastmod()
with open(os.path.join(ROOT, "robots.txt"), "w") as f:
    f.write("# not open yet\nUser-agent: *\nDisallow: /\n")
LM["/p2"] = "2026-10-27"
write_lastmod()
r = run()
check(r[HOST]["status"] == "closed" and not CALLS, "robots.txt: Disallow: / — поисковикам не отправляем")
with open(os.path.join(ROOT, "robots.txt"), "w") as f:
    f.write("User-agent: *\nAllow: /\nDisallow: /api/\n")
r = run()
check(sent_urls() == [URL["/p2"]], "сайт открыли — отправлено то, что изменилось")
check(not I.robots_closed(ROOT), "Disallow: /api/ — не закрыт")

print(f"OK: {ok} проверок")
