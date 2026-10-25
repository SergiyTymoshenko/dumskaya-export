#!/usr/bin/env python3
"""Честные даты изменения страниц — <lastmod> в sitemap.xml сайта студии и каталога (решено 25.10.2026).

Дата страницы — когда менялось её содержимое на этом языке, а не дата выкладки:
  • отпечаток страницы — только основная часть (<main>): текст, ссылки и подписи фото (фото без подписи — оформление).
    Шапка, меню, подвал,
    оформление, формы, кнопки и метки сборки не считаются — правка дизайна или меню дат не двигает;
  • даты и отпечатки хранятся в закоммиченном файле: content/sitemap-lastmod.json (студия),
    content/home/sitemap-lastmod.json (каталог) — {адрес: [отпечаток, дата]};
  • отпечаток совпал — дата прежняя. Изменился — дата последнего коммита источников страницы (свой файл страницы
    content/pages/…json; у портфолио, главной, цен, проекта — ещё content/projects.json и др.; у товара каталога — каталог
    фабрики, свои тексты, правки), если он новее сохранённой даты; если источники с тех пор не менялись — изменение пришло
    из шаблона, и дата остаётся прежней. Источники с незакоммиченными правками — сегодня;
  • у страниц фабрики каталога дата не раньше дня, когда фабрика выложена (content/home/publish.json).
Считается там, где есть история git, — на Маке при выкладке (scripts/deploy.sh, deploy_home.sh) и у Claude; на сервере
не считается. Выкладка файл дат не меняет (дерево на Маке остаётся чистым, git pull не мешает): даты на Маке
получаются те же — из файла и истории git. Сохраняет новые отпечатки Claude перед коммитом (save).

  python3 scripts/lastmod.py apply studio|home   — после сборки: вписать <lastmod> в sitemap сборки (файл дат не меняется)
  python3 scripts/lastmod.py save studio|home    — то же и сохранить отпечатки и даты в файл дат
  python3 scripts/lastmod.py check studio|home   — после сборки: есть ли страницы, чьи отпечатки не сохранены (код 1)
  python3 scripts/lastmod.py init studio         — начальные даты из истории git (содержимое файлов страниц по коммитам)
Только стандартная библиотека Python 3."""
import glob
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from urllib.parse import unquote, urlsplit

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bratislava")
except Exception:  # noqa: BLE001  pragma: no cover
    TZ = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITES = {
    "studio": {"base": "https://dumskaya-design.com", "dist": "dist", "state": "content/sitemap-lastmod.json"},
    "home": {"base": "https://dumskaya-home.com", "dist": "home/dist", "state": "content/home/sitemap-lastmod.json"},
}
# сайт студии: что ещё, кроме своего файла страницы, входит в её содержимое (по типу страницы)
STUDIO_EXTRA = {
    "portfolio": ["content/projects.json", "content/projects-order.json", "content/projects-overrides.json"],
    "home": ["content/home.json", "content/projects.json", "content/projects-order.json"],
    "price": ["content/projects.json"],
    "project": ["content/projects.json", "content/projects-overrides.json"],
    "contact": ["content/site.json"],
}
# каталог: контакты и политика (и главная, пока нет выложенных товаров) — тексты страниц
HOME_STATIC = ["home/src/lib/i18n.ts", "content/home/site.json"]


def today():
    return (datetime.now(TZ) if TZ else datetime.now()).date().isoformat()


def day_of(iso):
    """Дата коммита (%cI) → день по Братиславе."""
    d = datetime.fromisoformat(iso)
    return (d.astimezone(TZ) if TZ else d).date().isoformat()


# ---------- отпечаток основной части страницы ----------
_S = re.S | re.I
MAIN = re.compile(r"<main\b[^>]*>(.*)</main>", _S)
DROP = [re.compile(rf"<{t}\b.*?</{t}>", _S) for t in ("script", "style", "form", "nav", "noscript", "template", "dialog",
                                                         "svg", "button", "select", "textarea")]
NOHASH = re.compile(r"<(\w+)\b[^>]*\bdata-nohash\b[^>]*>.*?</\1>", _S)          # блок шаблона внутри <main>
BTN = re.compile(r'<a\b[^>]*class="[^"]*\bbtn\b[^"]*"[^>]*>.*?</a>', _S)          # кнопки-ссылки («Узнать цену»)
IMG = re.compile(r"<img\b[^>]*>", _S)
PH = re.compile(r'<span\b[^>]*class="[^"]*\bph\b[^"]*"[^>]*>\s*</span>', _S)     # заглушка вместо фото (сборка без фото)
ALT = re.compile(r'\balt="([^"]*)"')
ARIA = re.compile(r'\baria-label="([^"]*)"')
HREF = re.compile(r'<a\b[^>]*\bhref="([^"]*)"[^>]*>', _S)
TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")


def content_text(text):
    """Основная часть страницы как текст: слова, адреса ссылок и подписи фото (фото и заглушка — одинаково)."""
    m = MAIN.search(text)
    body = m.group(1) if m else ""
    body = NOHASH.sub(" ", body)
    for rx in DROP:
        body = rx.sub(" ", body)
    body = BTN.sub(" ", body)
    # фото — по подписи; без подписи (alt="") — оформление (размытый фон шапки, плитка с подписью рядом): не считается
    def pic(rx, x):
        m = rx.search(x.group(0))
        return f" [фото:{m.group(1)}] " if m and m.group(1).strip() else " "
    body = IMG.sub(lambda x: pic(ALT, x), body)
    body = PH.sub(lambda x: pic(ARIA, x), body)
    body = HREF.sub(lambda x: " [→%s] " % x.group(1), body)
    return SPACE.sub(" ", html.unescape(TAG.sub(" ", body))).strip()


def fingerprint(text):
    return hashlib.sha256(content_text(text).encode("utf-8")).hexdigest()[:16]


# ---------- sitemap сборки ----------
LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.S)
URL_RE = re.compile(r"<url>(.*?)</url>", re.S)
SM_RE = re.compile(r"<sitemap>(.*?)</sitemap>", re.S)
LASTMOD = re.compile(r"\s*<lastmod>.*?</lastmod>", re.S)


def sitemap_files(dist, base):
    """[(файл, xml)] — sitemap.xml, а если это индекс — файлы, на которые он ссылается."""
    top = os.path.join(dist, "sitemap.xml")
    xml = open(top, encoding="utf-8").read()
    if "<sitemapindex" not in xml:
        return top, None, [top]
    kids = []
    for m in SM_RE.finditer(xml):
        loc = html.unescape(LOC.search(m.group(1)).group(1))
        rel = urlsplit(loc).path.lstrip("/")
        kids.append(os.path.join(dist, rel))
    return top, xml, kids


def page_file(dist, url):
    path = unquote(urlsplit(url).path).strip("/")
    for rel in (("index.html",) if not path else (path + ".html", os.path.join(path, "index.html"))):
        f = os.path.join(dist, rel)
        if os.path.isfile(f):
            return f
    return None


# ---------- история git ----------
def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout


class Git:
    """Дата последнего коммита каждого файла (одним вызовом git log) и незакоммиченные правки."""

    def __init__(self, paths):
        self.dates = {}
        cur = None
        for line in git("log", "--format=%x01%cI", "--name-only", "--", *paths).splitlines():
            if line.startswith("\x01"):
                cur = day_of(line[1:])
            elif line.strip() and cur and line not in self.dates:
                self.dates[line] = cur
        self.dirty = {ln[3:].strip().strip('"') for ln in git("status", "--porcelain", "--", *paths).splitlines() if ln.strip()}

    def newest(self, sources):
        best = None
        for s in sources:
            pre = s.rstrip("/") + "/"
            if any(d == s or d.startswith(pre) for d in self.dirty):
                return today()
            for f, d in self.dates.items():
                if (f == s or f.startswith(pre)) and (best is None or d > best):
                    best = d
        return best


# ---------- источники страниц ----------
def studio_sources():
    """адрес → (файл страницы, тип) из content/pages/**/*.json."""
    out = {}
    for f in glob.glob(os.path.join(ROOT, "content/pages/**/*.json"), recursive=True):
        try:
            p = json.load(open(f, encoding="utf-8"))
        except ValueError:
            continue
        out[p["path"]] = (os.path.relpath(f, ROOT), p.get("type") or "")
    return out


def studio_date(path, ctx, gitinfo):
    """Сайт студии: день последнего изменения содержимого своего файла страницы (по истории git: коммит, который
    менял только языковые ссылки или описание, не считается) и последнего коммита общих файлов её типа."""
    if ctx.get("days") is None:
        ctx["days"] = init_studio()
    own = ctx["pages"].get(path)
    if not own:
        return gitinfo.newest(["content/pages"])
    ds = [ctx["days"].get(own[0]), gitinfo.newest(STUDIO_EXTRA.get(own[1], []))]
    ds = [d for d in ds if d]
    return max(ds) if ds else None


def file_versions(path):
    """[(день, текст)] — версии файла по коммитам, от старых к новым; рабочая копия с правками — «сегодня»."""
    rows = [ln.split(" ", 1) for ln in git("log", "--reverse", "--format=%H %cI", "--", path).splitlines() if ln.strip()]
    out = []
    if rows:
        proc = subprocess.run(["git", "cat-file", "--batch"], cwd=ROOT, input="".join(f"{sha}:{path}\n" for sha, _ in rows).encode(),
                              capture_output=True, check=False)
        buf, pos = proc.stdout, 0
        for sha, iso in rows:
            nl = buf.index(b"\n", pos)
            head = buf[pos:nl].decode()
            pos = nl + 1
            if head.endswith("missing"):
                continue
            size = int(head.split()[-1])
            out.append((day_of(iso), buf[pos:pos + size].decode("utf-8", "replace")))
            pos += size + 1
    try:
        cur = open(os.path.join(ROOT, path), encoding="utf-8").read()
        if not out or cur != out[-1][1]:
            out.append((today(), cur))
    except OSError:
        pass
    return out


def sku_dates():
    """Каталог: день последнего изменения данных каждого товара (по нашему артикулу) — по истории каталога фабрики
    (content/shop/catalog/<фабрика>.json), своих текстов (content/home/texts/<фабрика>.json) и правок
    (content/home/overrides.json). Изменение другого товара в том же файле дату не двигает."""
    files = sorted(glob.glob(os.path.join(ROOT, "content/shop/catalog/*.json"))) + sorted(glob.glob(os.path.join(ROOT, "content/home/texts/*.json")))
    files += [os.path.join(ROOT, "content/home/overrides.json")]
    dates = {}
    for f in files:
        rel = os.path.relpath(f, ROOT)
        prev, last = {}, {}
        for day, raw in file_versions(rel):
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            if rel.startswith("content/shop/catalog/"):
                ent = {x["sku"]: x for x in data.get("products", []) if isinstance(x, dict) and x.get("sku")}
            else:
                ent = {k: v for k, v in data.items() if not k.startswith("_")} if isinstance(data, dict) else {}
            cur = {k: hashlib.sha1(json.dumps(v, ensure_ascii=False, sort_keys=True).encode()).hexdigest() for k, v in ent.items()}
            for k, h in cur.items():
                if prev.get(k) != h:
                    last[k] = day
            prev = cur
        for k, d in last.items():
            if d > dates.get(k, ""):
                dates[k] = d
    return dates


def home_context():
    """Каталог: что за страница по адресу (товар, фабрика, раздел, категория, «Для улицы», главная, список фабрик,
    контакты и политика), товары, даты выкладки фабрик."""
    ctx = {"kind": {}, "products": [], "since": {}, "skud": None}
    try:
        cat = json.load(open(os.path.join(ROOT, "home/data/catalog.json"), encoding="utf-8"))
    except (OSError, ValueError):
        cat = {"products": [], "brands": {}, "taxonomy": {}}
    pre = lambda l: "" if l == "en" else "/" + l  # noqa: E731
    langs = ("en", "ru", "de", "fr", "es")
    ctx["products"] = [p for p in cat.get("products", []) if p.get("published")]
    for p in cat.get("products", []):
        for u in (p.get("path") or {}).values():
            ctx["kind"][u] = ("product", p)
    for fac, b in (cat.get("brands") or {}).items():
        for l in langs:
            ctx["kind"][f"{pre(l)}/{b.get('slug') or fac}"] = ("brand", fac)
    tax = cat.get("taxonomy") or {}
    for d in tax.get("departments") or []:
        for l in langs:
            ctx["kind"][f"{pre(l)}/{d['slug'][l]}"] = ("dept", d["id"])
    for c, v in (tax.get("categories") or {}).items():
        for l in langs:
            ctx["kind"][f"{pre(l)}/{v['slug'][l]}"] = ("cat", c)
    if tax.get("outdoor"):
        for l in langs:
            ctx["kind"][f"{pre(l)}/{tax['outdoor']['slug'][l]}"] = ("outdoor", None)
    for l in langs:
        ctx["kind"][pre(l) or "/"] = ("home", None)
    # список фабрик, контакты, политика — адреса из STATIC в home/src/lib/catalog.ts
    try:
        cat_ts = open(os.path.join(ROOT, "home/src/lib/catalog.ts"), encoding="utf-8").read()
    except OSError:
        cat_ts = ""
    m = re.search(r"const STATIC\b[^=]*=\s*\{(.*?)\n\};", cat_ts, re.S)
    for key in ("brands", "contact", "privacy"):
        mm = re.search(r"\b" + key + r"\s*:\s*\{([^}]*)\}", m.group(1)) if m else None
        for lang, slug in re.findall(r"(\w+)\s*:\s*'([^']+)'", mm.group(1) if mm else ""):
            ctx["kind"][f"{pre(lang)}/{slug}"] = ("brands" if key == "brands" else "static", None)
    try:
        pub = json.load(open(os.path.join(ROOT, "content/home/publish.json"), encoding="utf-8"))
        ctx["since"] = {f: (v or {}).get("since") for f, v in pub.get("factories", {}).items()}
    except (OSError, ValueError):
        pass
    return ctx


def home_date(path, ctx, gitinfo):
    """Каталог: день последнего изменения содержимого страницы по её данным — у товара по его артикулу (не раньше
    выкладки фабрики), у фабрики, раздела, категории, «Для улицы», главной и списка фабрик — самый поздний из её
    выложенных товаров; у контактов и политики (и пока нет товаров) — последний коммит их текстов."""
    if ctx["skud"] is None:
        ctx["skud"] = sku_dates()
    skud, since = ctx["skud"], ctx["since"]
    pd = lambda p: max(x for x in (skud.get(p["sku"]), since.get(p["factory"])) if x) if (skud.get(p["sku"]) or since.get(p["factory"])) else None  # noqa: E731
    kind, key = ctx["kind"].get(path, ("static", None))
    if kind == "product":
        return pd(key)
    pick = {"brand": lambda p: p["factory"] == key, "dept": lambda p: p.get("department") == key, "cat": lambda p: p.get("category") == key,
            "outdoor": lambda p: p.get("place") != "indoor", "home": lambda p: True, "brands": lambda p: True}.get(kind)
    ds = [d for d in (pd(p) for p in ctx["products"] if pick and pick(p)) if d]
    return max(ds) if ds else gitinfo.newest(HOME_STATIC)


# ---------- даты ----------
def load_state(site):
    try:
        return json.load(open(os.path.join(ROOT, SITES[site]["state"]), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(site, state):
    path = os.path.join(ROOT, SITES[site]["state"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = [f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}" for k, v in sorted(state.items())]
    with open(path, "w", encoding="utf-8") as f:     # одна строка на адрес — изменения хорошо видны в diff
        f.write("{\n" + ",\n".join(rows) + "\n}\n")


def compute(site):
    """{адрес: (отпечаток, дата, как)} для всех адресов sitemap сборки и список файлов sitemap."""
    cfg = SITES[site]
    dist = os.path.join(ROOT, cfg["dist"])
    top, index_xml, files = sitemap_files(dist, cfg["base"])
    state = load_state(site)
    ctx = {"pages": studio_sources()} if site == "studio" else home_context()
    gitinfo = Git(["content", "home/src/lib/i18n.ts", "home/src/lib/catalog.ts"])
    out, per_file = {}, {}
    for f in files:
        xml = open(f, encoding="utf-8").read()
        locs = []
        for m in URL_RE.finditer(xml):
            url = html.unescape(LOC.search(m.group(1)).group(1))
            path = urlsplit(url).path or "/"
            pf = page_file(dist, url)
            h = fingerprint(open(pf, encoding="utf-8", errors="replace").read()) if pf else ""
            st = state.get(path)
            if st and st[0] == h:
                d, how = st[1], "same"
            else:
                src = studio_date(path, ctx, gitinfo) if site == "studio" else home_date(path, ctx, gitinfo)
                if st and (src is None or src <= st[1]):
                    d, how = st[1], "template"            # изменилось не из источников страницы — шаблон, дата прежняя
                else:
                    d, how = (src or today()), ("changed" if st else "new")
            if site == "home":                       # страницы фабрики — не раньше дня её выкладки
                kind, key = ctx["kind"].get(path, ("", None))
                fac = key["factory"] if kind == "product" else key if kind == "brand" else None
                since = ctx["since"].get(fac) if fac else None
                if since and since > d:
                    d = since
            out[path] = (h, d, how)
            locs.append(path)
        per_file[f] = locs
    return cfg, top, index_xml, per_file, out


def inject(top, index_xml, per_file, out):
    """Вписать <lastmod> сразу после <loc> каждой записи; у индекса — самая поздняя дата его файла."""
    for f, locs in per_file.items():
        xml = open(f, encoding="utf-8").read()

        def one(m):
            inner = LASTMOD.sub("", m.group(1))
            url = html.unescape(LOC.search(inner).group(1))
            d = out[urlsplit(url).path or "/"][1]
            lm = LOC.search(inner)
            return "<url>" + inner[:lm.end()] + f"<lastmod>{d}</lastmod>" + inner[lm.end():] + "</url>"
        open(f, "w", encoding="utf-8").write(URL_RE.sub(one, xml))
    if index_xml is not None:
        newest = {os.path.basename(f): max((out[p][1] for p in locs), default=None) for f, locs in per_file.items()}

        def sm(m):
            inner = LASTMOD.sub("", m.group(1))
            lm = LOC.search(inner)
            name = os.path.basename(urlsplit(html.unescape(lm.group(1))).path)
            d = newest.get(name)
            return "<sitemap>" + inner[:lm.end()] + (f"<lastmod>{d}</lastmod>" if d else "") + inner[lm.end():] + "</sitemap>"
        open(top, "w", encoding="utf-8").write(SM_RE.sub(sm, index_xml))


# ---------- начальные даты: содержимое файлов страниц по истории git ----------
def page_content(raw):
    try:
        p = json.loads(raw)
    except ValueError:
        return None
    return hashlib.sha256(json.dumps([p.get("h1"), p.get("sections")], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def init_studio():
    """Для каждого файла страницы — день последнего коммита, в котором изменились её заголовок или содержимое
    (а не любой коммит файла: например, правка только языковых ссылок дату не двигает). Переименования учитываются."""
    log = git("log", "--reverse", "--format=%x01%H %cI", "--name-status", "-M", "--", "content/pages")
    commits, cur = [], None
    for line in log.splitlines():
        if line.startswith("\x01"):
            sha, iso = line[1:].split(" ", 1)
            cur = [sha, day_of(iso), []]
            commits.append(cur)
        elif line.strip() and cur:
            parts = line.split("\t")
            cur[2].append(parts)
    need = [(c[0], p[-1]) for c in commits for p in c[2] if p[0][0] in "AMR" and p[-1].endswith(".json")]
    blobs = {}
    if need:
        proc = subprocess.run(["git", "cat-file", "--batch"], cwd=ROOT, input="".join(f"{s}:{f}\n" for s, f in need).encode(),
                              capture_output=True, check=False)
        buf, pos = proc.stdout, 0
        for key in need:
            nl = buf.index(b"\n", pos)
            head = buf[pos:nl].decode()
            pos = nl + 1
            if head.endswith("missing"):
                continue
            size = int(head.split()[-1])
            blobs[key] = buf[pos:pos + size].decode("utf-8", "replace")
            pos += size + 1
    lineage = {}           # файл → [отпечаток содержимого, день изменения]
    for sha, day, changes in commits:
        for p in changes:
            st = p[0][0]
            if st == "D":
                lineage.pop(p[1], None)
                continue
            path = p[-1]
            prev = lineage.pop(p[1], None) if st == "R" else lineage.get(path)
            h = page_content(blobs.get((sha, path), "")) if path.endswith(".json") else None
            if prev and prev[0] == h:
                lineage[path] = prev
            else:
                lineage[path] = [h, day]
    # незакоммиченные правки содержимого — сегодня
    for f, v in lineage.items():
        try:
            if page_content(open(os.path.join(ROOT, f), encoding="utf-8").read()) != v[0]:
                v[1] = today()
        except OSError:
            pass
    for f in glob.glob(os.path.join(ROOT, "content/pages/**/*.json"), recursive=True):
        rel = os.path.relpath(f, ROOT)
        if rel not in lineage:                       # новый, ещё не закоммиченный файл
            lineage[rel] = [None, today()]
    return {f: v[1] for f, v in lineage.items()}


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("apply", "save", "check", "init") or sys.argv[2] not in SITES:
        print(__doc__)
        sys.exit(2)
    cmd, site = sys.argv[1], sys.argv[2]
    if git("rev-parse", "--is-shallow-repository").strip() == "true":
        print("⚠ lastmod: история git неполная (клон без истории) — даты по истории будут неточными; "
              "дополнить: git fetch --unshallow", file=sys.stderr)
    if cmd == "init":
        if site != "studio":
            sys.exit("init — только для сайта студии: у каталога даты сразу из истории его источников (apply/save)")
        days = init_studio()
        pages = studio_sources()
        gitinfo = Git(["content"])
        cfg, top, index_xml, per_file, out = compute(site)
        state = {}
        for path, (h, _, _) in out.items():
            own = pages.get(path)
            d = days.get(own[0]) if own else None
            extra = STUDIO_EXTRA.get(own[1], []) if own else []
            if own and own[1] in ("portfolio", "home"):          # их списки — из общих файлов проектов
                e = gitinfo.newest(extra)
                d = max(x for x in (d, e) if x) if (d or e) else None
            state[path] = [h, d or today()]
        save_state(site, state)
        print(f"lastmod {site}: начальные даты для {len(state)} адресов — в {cfg['state']}")
        return
    cfg, top, index_xml, per_file, out = compute(site)
    if cmd == "check":
        stale = [p for p, (h, d, how) in out.items() if how != "same"]
        if stale:
            print(f"lastmod {site}: у {len(stale)} адресов отпечаток не сохранён (например, {stale[0]}) — "
                  f"python3 scripts/lastmod.py save {site} и коммит")
            sys.exit(1)
        print(f"lastmod {site}: все {len(out)} отпечатков сохранены")
        return
    inject(top, index_xml, per_file, out)
    counts = {}
    for _, _, how in out.values():
        counts[how] = counts.get(how, 0) + 1
    days = sorted({d for _, d, _ in out.values()})
    print(f"lastmod {site}: {len(out)} адресов, даты {days[0] if days else '—'} … {days[-1] if days else '—'}"
          + "".join(f", {k}: {v}" for k, v in sorted(counts.items()) if k != "same"))
    if cmd == "save":
        state = load_state(site)
        live = {p: [h, d] for p, (h, d, _) in out.items()}
        # адреса, которых сейчас нет в sitemap (фабрика снята, сборка другого режима), не теряем
        state.update(live)
        save_state(site, state)
        print(f"lastmod {site}: сохранено в {cfg['state']}")


if __name__ == "__main__":
    main()
