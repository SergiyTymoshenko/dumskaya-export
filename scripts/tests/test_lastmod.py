"""Проверка честных дат <lastmod> (scripts/lastmod.py) на временном репозитории: отпечаток не видит шапку, меню, подвал,
формы, кнопки и оформление; фото и заглушка без фото — одинаково; содержимое не менялось — дата прежняя; правка шаблона —
дата прежняя; изменился файл страницы — дата его коммита; незакоммиченная правка — сегодня; новая страница — дата её
коммита; у каталога — дата по данным самого товара (правка другого товара в том же каталоге её не двигает), не раньше
выкладки фабрики; индекс карт сайта — самая поздняя дата его файла; файл дат при apply не меняется.
   python3 scripts/tests/test_lastmod.py      — в конце «OK: N проверок»"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import lastmod as L  # noqa: E402

ok = 0


def check(cond, what):
    global ok
    if not cond:
        raise AssertionError(what)
    ok += 1


# --- отпечаток
def page(text, header="Меню", css="a1", img='<img src="/img/x-960.webp" alt="Гостиная">', extra=""):
    return (f'<html><head><title>T {css}</title><link href="/_astro/{css}.css"></head><body><header>{header}</header>'
            f'<main><nav class="crumbs"><a href="/">Главная</a></nav><h1 class="h-{css}">Заголовок</h1><p data-astro-cid-{css}>{text}</p>{img}'
            f'<form><label>Имя<input></label><button>Отправить</button></form><a class="btn" href="#lead">Узнать цену</a>{extra}'
            f'<script>var t={css!r}</script></main><footer>© {css}</footer></body></html>')


base = L.fingerprint(page("текст"))
check(L.fingerprint(page("текст", header="Меню и Каталог", css="b2")) == base, "шапка, меню, подвал, оформление, скрипты — не изменение")
check(L.fingerprint(page("текст", img='<span class="ph" role="img" aria-label="Гостиная"></span>')) == base,
      "фото и заглушка без фото (сборка без оригиналов) — одинаково")
check(L.fingerprint(page("новый текст")) != base, "текст изменился — отпечаток другой")
check(L.fingerprint(page("текст", img='<img src="/img/x.webp" alt="Спальня">')) != base, "другое фото (подпись) — изменение")
check(L.fingerprint(page("текст", extra='<div data-nohash><p>Каталог фабрик</p></div>')) == base, "блок шаблона data-nohash не считается")

# --- временный репозиторий
TMP = tempfile.mkdtemp(prefix="lastmod-test-")
L.ROOT = TMP
env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


def sh(*a, day=None):
    e = dict(env)
    if day:
        e["GIT_AUTHOR_DATE"] = e["GIT_COMMITTER_DATE"] = f"{day}T12:00:00+02:00"
    subprocess.run(a, cwd=TMP, env=e, check=True, capture_output=True)


def write(rel, data):
    f = os.path.join(TMP, rel)
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, "w", encoding="utf-8") as fh:
        fh.write(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False))


def commit(day, msg="x"):
    sh("git", "add", "-A")
    sh("git", "commit", "-q", "-m", msg, day=day)


SITE = "https://dumskaya-design.com"


def build(texts):
    """«Сборка» сайта студии: страницы и sitemap.xml без дат."""
    for path, t in texts.items():
        write("dist/" + ("index" if path == "/" else path.strip("/")) + ".html", page(t))
    write("dist/sitemap.xml", '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          + "".join(f"<url><loc>{SITE}{p}</loc><xhtml:link/></url>" for p in texts) + "</urlset>")


def dates(site="studio"):
    return {p: d for p, (_, d, _) in L.compute(site)[4].items()}


sh("git", "init", "-q")
write("content/pages/ru/a.json", {"path": "/a", "type": "service", "h1": "A", "sections": [1]})
write("content/pages/ru/b.json", {"path": "/b", "type": "service", "h1": "B", "sections": [1]})
commit("2026-10-15")
write("content/pages/ru/b.json", {"path": "/b", "type": "service", "h1": "B", "sections": [2]})
commit("2026-10-20")
write("content/pages/ru/a.json", {"path": "/a", "type": "service", "h1": "A", "sections": [1], "alternates": {"en": "/en/a"}})
commit("2026-10-22", "только языковые ссылки")
build({"/a": "текст A", "/b": "текст B"})

days = L.init_studio()
check(days["content/pages/ru/a.json"] == "2026-10-15", "начальная дата: последний коммит, изменивший содержимое (не языковые ссылки)")
check(days["content/pages/ru/b.json"] == "2026-10-20", "начальная дата: правка содержимого")
sys.argv = ["lastmod.py", "init", "studio"]
L.main()
st = L.load_state("studio")
check(st["/a"][1] == "2026-10-15" and st["/b"][1] == "2026-10-20", "init записал отпечатки и даты в файл дат")
commit("2026-10-23", "даты")

check(dates() == {"/a": "2026-10-15", "/b": "2026-10-20"}, "содержимое не менялось — даты прежние")
build({"/a": "текст A (новый шаблон)", "/b": "текст B"})
check(dates()["/a"] == "2026-10-15", "изменился текст шаблона, файл страницы не менялся — дата прежняя")
write("content/pages/ru/a.json", {"path": "/a", "type": "service", "h1": "A", "sections": [3], "alternates": {"en": "/en/a"}})
commit("2026-10-24")
build({"/a": "текст A2", "/b": "текст B"})
check(dates()["/a"] == "2026-10-24", "изменилась страница — дата коммита её файла")
write("content/pages/ru/b.json", {"path": "/b", "type": "service", "h1": "B", "sections": [9]})
build({"/a": "текст A2", "/b": "текст B9"})
check(dates()["/b"] == L.today(), "незакоммиченная правка страницы — сегодня")
commit("2026-10-25")
write("content/pages/ru/c.json", {"path": "/c", "type": "service", "h1": "C", "sections": [1]})
commit("2026-10-25")
build({"/a": "текст A2", "/b": "текст B9", "/c": "текст C"})
check(dates()["/c"] == "2026-10-25", "новая страница — дата её коммита")
before = open(os.path.join(TMP, "content/sitemap-lastmod.json"), encoding="utf-8").read()
sys.argv = ["lastmod.py", "apply", "studio"]
L.main()
xml = open(os.path.join(TMP, "dist/sitemap.xml"), encoding="utf-8").read()
check(f"<loc>{SITE}/a</loc><lastmod>2026-10-24</lastmod>" in xml and xml.count("<lastmod>") == 3, "apply вписал <lastmod> сразу после <loc>")
L.main()
check(open(os.path.join(TMP, "dist/sitemap.xml"), encoding="utf-8").read().count("<lastmod>") == 3, "повторный apply не дублирует даты")
check(open(os.path.join(TMP, "content/sitemap-lastmod.json"), encoding="utf-8").read() == before, "apply не меняет файл дат (дерево на Маке чистое)")
sys.argv = ["lastmod.py", "save", "studio"]
L.main()
st = L.load_state("studio")
check(st["/a"][1] == "2026-10-24" and "/c" in st, "save сохраняет новые отпечатки и даты")

# --- каталог: дата по данным самого товара, индекс карт сайта
H = "https://dumskaya-home.com"
write("content/shop/catalog/fab.json", {"products": [{"sku": "DF-1", "name": "Sofa"}, {"sku": "DF-2", "name": "Chair"}]})
commit("2026-10-16")
write("content/shop/catalog/fab.json", {"products": [{"sku": "DF-1", "name": "Sofa"}, {"sku": "DF-2", "name": "Chair v2"}]})
commit("2026-10-18")
write("content/home/publish.json", {"factories": {"fab": {"since": "2026-10-17"}}})
write("home/data/catalog.json", {"brands": {"fab": {"slug": "fab", "published": {"since": "2026-10-17"}}}, "taxonomy": {},
                                 "products": [{"sku": "DF-1", "factory": "fab", "published": True, "path": {"en": "/fab/sofa"}},
                                              {"sku": "DF-2", "factory": "fab", "published": True, "path": {"en": "/fab/chair"}}]})
write("home/src/lib/i18n.ts", "// тексты")
commit("2026-10-19")
for p, t in (("/fab/sofa", "Sofa"), ("/fab/chair", "Chair"), ("/fab", "Fab")):
    write("home/dist/" + p.strip("/") + ".html", page(t))
write("home/dist/sitemap-products-fab.xml", '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
      + "".join(f"<url><loc>{H}{p}</loc></url>" for p in ("/fab/sofa", "/fab/chair")) + "</urlset>")
write("home/dist/sitemap-categories.xml", f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{H}/fab</loc></url></urlset>')
write("home/dist/sitemap.xml", '<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
      + "".join(f"<sitemap><loc>{H}/{n}</loc></sitemap>" for n in ("sitemap-categories.xml", "sitemap-products-fab.xml")) + "</sitemapindex>")
d = dates("home")
check(d["/fab/sofa"] == "2026-10-17", "товар: данные не менялись с 16-го, фабрика выложена 17-го — дата выкладки")
check(d["/fab/chair"] == "2026-10-18", "товар: дата правки его данных; правка соседнего товара дату не двигает")
check(d["/fab"] == "2026-10-18", "страница фабрики — самая поздняя дата её товаров")
sys.argv = ["lastmod.py", "apply", "home"]
L.main()
idx = open(os.path.join(TMP, "home/dist/sitemap.xml"), encoding="utf-8").read()
check(f"<loc>{H}/sitemap-products-fab.xml</loc><lastmod>2026-10-18</lastmod>" in idx, "индекс: у файла — самая поздняя дата его адресов")
import sitemap_check as SC  # noqa: E402
errs = []
sm = SC.check_sitemaps(os.path.join(TMP, "home/dist"), H, {"/fab/sofa", "/fab/chair", "/fab"}, errs)
check(not errs and sm["/fab/chair"] == "2026-10-18", "проверка карты сайта: индекс, файлы, даты W3C")
errs = []
SC.check_sitemaps(os.path.join(TMP, "home/dist"), H, {"/fab/sofa"}, errs)
check(any("нет страницы" in e for e in errs), "проверка карты сайта: адрес без страницы — ошибка")

print(f"OK: {ok} проверок")
