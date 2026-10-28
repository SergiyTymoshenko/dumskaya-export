#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""llms-full.txt — полный текст сайта одним Markdown-файлом для ИИ-ассистентов (решено 28.10.2026, как на usk.ua).

Собирается скриптом из ГОТОВЫХ страниц сборки, а не руками: адреса — из карты сайта (только опубликованные канонические
страницы), со страницы — заголовок, meta description, ld+json (хлебные крошки, бренд, вопросы и ответы) и текст из <main>
(абзацы, списки, таблицы размеров, «название: значение»). Формы, галереи, кнопки, похожие товары, кабинеты и /api/ не
попадают; ключей и персональных данных на публичных страницах нет. Пересобирается при каждой выкладке
(scripts/deploy_home.sh — после сборки и дат в карте сайта, до проверки check_home.py).

Структура: заголовок и справка → раздел → страница → адрес и адреса на других языках → описание → текст, характеристики,
вопросы и ответы. Текст — на основном языке сайта (у каталога — английский), у каждой страницы — ссылки на её версии на
остальных языках (тексты те же). Абзацы, повторяющиеся на многих страницах (условия цены и доставки), — один раз в начале.

   python3 scripts/llms_full.py home          — home/dist/llms-full.txt (dumskaya-home.com)
   python3 scripts/llms_full.py home --print  — то же, итог на экран
Только стандартная библиотека Python 3."""
import html
import json
import os
import re
import sys
from collections import Counter, OrderedDict
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITES = {
    "home": {
        "dist": os.path.join(ROOT, "home", "dist"), "base": "https://dumskaya-home.com", "lang": "en",
        "title": "DUMSKAYA HOME — full text of the catalog",
        "langs": {"ru": "Russian", "de": "German", "fr": "French", "es": "Spanish"},
        # что на странице не текст: галерея, чертежи, похожие товары, карточки товаров в списках, форма, кнопки
        "skip_class": {"crumbs", "pgal", "draws", "group", "grid", "pc", "btn", "plead", "lead", "ph", "filters", "chips",
                       "sort", "pager", "cards", "tiles", "tile", "hero__img", "brandbar"},
        "main_section": "Main pages",
    },
}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SKIP_TAGS = {"script", "style", "svg", "form", "nav", "button", "noscript", "template", "picture", "img", "iframe",
             "select", "textarea", "input", "label", "video", "audio", "canvas", "dialog"}
BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "aside", "figure", "figcaption", "blockquote",
         "ul", "ol", "li", "table", "thead", "tbody", "tr", "dl", "dt", "dd", "details", "summary",
         "h1", "h2", "h3", "h4", "h5", "h6", "address", "hr"}
REPEAT_MIN = 20            # абзац на стольких страницах — общий: один раз в начале файла


class Node:
    __slots__ = ("tag", "attrs", "kids")

    def __init__(self, tag, attrs):
        self.tag, self.attrs, self.kids = tag, attrs, []

    def cls(self):
        return set((self.attrs.get("class") or "").split())


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        n = Node(tag, {k: (v or "") for k, v in attrs})
        self.stack[-1].kids.append(n)
        if tag not in VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].kids.append(Node(tag, {k: (v or "") for k, v in attrs}))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].kids.append(data)


def find(n, pred):
    if isinstance(n, str):
        return None
    if pred(n):
        return n
    for k in n.kids:
        r = find(k, pred)
        if r is not None:
            return r
    return None


def find_all(n, pred, out=None):
    out = [] if out is None else out
    if isinstance(n, Node):
        if pred(n):
            out.append(n)
        for k in n.kids:
            find_all(k, pred, out)
    return out


def ws(s):
    return re.sub(r"\s+", " ", s).strip()


class Render:
    """Текст <main> → блоки Markdown."""

    def __init__(self, cfg):
        self.skip_class = cfg["skip_class"]

    def skip(self, n):
        if n.tag in SKIP_TAGS or n.attrs.get("aria-hidden") == "true" or n.attrs.get("hidden") is not None \
                or n.attrs.get("role") == "img":
            return True
        return bool(n.cls() & self.skip_class)

    def inline(self, n):
        if isinstance(n, str):
            return n
        if self.skip(n):
            return ""
        if n.tag == "br":
            return " "
        t = "".join(self.inline(k) for k in n.kids)
        if n.tag in ("strong", "b") and ws(t):
            return f"**{ws(t)}**"
        return t

    def has_block(self, n):
        return any(isinstance(k, Node) and not self.skip(k) and (k.tag in BLOCK or self.has_block(k)) for k in n.kids)

    def blocks(self, n, out):
        if isinstance(n, str) or self.skip(n):
            return out
        t = n.tag
        if t in ("h1",):
            return out
        if t in ("h2", "h3", "h4", "h5", "h6"):
            s = ws(self.inline(n))
            if s:
                out.append(("h", int(t[1]), s))
            return out
        if t in ("ul", "ol"):
            items = [ws(self.inline(li)) for li in n.kids if isinstance(li, Node) and li.tag == "li" and not self.skip(li)]
            items = [i for i in items if i]
            if items:
                out.append(("list", items))
            return out
        if t == "table":
            rows = []
            for tr in find_all(n, lambda x: x.tag == "tr"):
                cells = [ws(self.inline(c)).replace("|", "/") for c in tr.kids if isinstance(c, Node) and c.tag in ("td", "th")]
                if any(cells):
                    rows.append(cells)
            if rows:
                out.append(("table", rows))
            return out
        if t == "dl":
            pairs, key = [], None
            for d in find_all(n, lambda x: x.tag in ("dt", "dd")):
                if d.tag == "dt":
                    key = ws(self.inline(d))
                elif key is not None:
                    pairs.append((key, ws(self.inline(d))))
                    key = None
            if pairs:
                out.append(("facts", pairs))
            return out
        if t == "details":
            summ = find(n, lambda x: x.tag == "summary")
            q = ws(self.inline(summ)) if summ else ""
            rest = Node("div", {})
            rest.kids = [k for k in n.kids if k is not summ]
            a = ws(self.inline(rest))
            if q and a:
                out.append(("qa", q, a))
            return out
        if t == "p" or not self.has_block(n):
            s = ws(self.inline(n))
            if s:
                out.append(("p", s))
            return out
        buf = []
        for k in n.kids:                     # вперемешку текст и блоки: текст между блоками — отдельным абзацем
            if isinstance(k, str) or (isinstance(k, Node) and k.tag not in BLOCK and not self.has_block(k)):
                buf.append(self.inline(k))
                continue
            if ws("".join(buf)):
                out.append(("p", ws("".join(buf))))
            buf = []
            self.blocks(k, out)
        if ws("".join(buf)):
            out.append(("p", ws("".join(buf))))
        return out


def md(blocks, shared):
    out = []
    for b in blocks:
        if b[0] == "h":
            out.append("#" * min(6, b[1] + 2) + " " + b[2])
        elif b[0] == "p":
            if b[1] not in shared:
                out.append(b[1])
        elif b[0] == "list":
            out.append("\n".join(f"- {i}" for i in b[1]))
        elif b[0] == "facts":
            out.append("\n".join(f"- {k}: {v}" for k, v in b[1]))
        elif b[0] == "table":
            rows = b[1]
            w = max(len(r) for r in rows)
            rows = [r + [""] * (w - len(r)) for r in rows]
            out.append("\n".join(["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * w] + ["| " + " | ".join(r) + " |" for r in rows[1:]]))
        elif b[0] == "qa":
            out.append(f"- Question: {b[1]}\n  Answer: {b[2]}")
    # заголовок раздела без текста под ним (был только у галереи или формы) — не нужен
    clean = []
    for i, s in enumerate(out):
        if s.startswith("#") and (i + 1 == len(out) or out[i + 1].startswith("#")):
            continue
        clean.append(s)
    return "\n\n".join(clean)


def sitemap_urls(dist, base):
    """Адреса из карты сайта (индекс → части), по порядку."""
    seen, out = set(), []

    def read(name):
        p = os.path.join(dist, name)
        if not os.path.exists(p):
            return
        x = open(p, encoding="utf-8").read()
        for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", x):
            loc = html.unescape(loc)
            if not loc.startswith(base):
                continue
            path = urlsplit(loc).path or "/"
            if re.search(r"/sitemap[\w-]*\.xml$", path):
                read(path.lstrip("/"))
            elif path not in seen:
                seen.add(path)
                out.append(path)
    read("sitemap.xml")
    return out


def page_file(dist, path):
    if path == "/":
        return os.path.join(dist, "index.html")
    for f in (path.strip("/") + ".html", path.strip("/") + "/index.html"):
        if os.path.exists(os.path.join(dist, f)):
            return os.path.join(dist, f)
    return None


def ld_items(h):
    out = []
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        for x in (d.get("@graph") or [d]) if isinstance(d, dict) else d:
            if isinstance(x, dict):
                out.append(x)
    return out


def meta(h, name):
    m = re.search(r'<meta\s+name="' + name + r'"\s+content="([^"]*)"', h) or re.search(r'<meta\s+content="([^"]*)"\s+name="' + name + '"', h)
    return ws(html.unescape(m.group(1))) if m else ""


def parse_page(cfg, path, f, render):
    h = open(f, encoding="utf-8").read()
    lang = (re.search(r'<html[^>]*\blang="([^"]+)"', h) or [None, ""])[1]
    if lang != cfg["lang"] or re.search(r'<meta\s+name="robots"\s+content="[^"]*noindex', h):
        return None
    ld = ld_items(h)
    crumbs = next(([i.get("name") for i in x.get("itemListElement") or []] for x in ld if x.get("@type") == "BreadcrumbList"), [])
    types = [x.get("@type") for x in ld if x.get("@type") not in ("WebSite", "Organization", "BreadcrumbList")]
    page = next((x for x in ld if x.get("@type") in ("ItemPage", "Product", "CollectionPage", "WebPage", "AboutPage", "ContactPage")), {})
    orgs = {x.get("@id"): x for x in ld if x.get("@type") == "Organization"}
    brand = orgs.get(((page.get("about") or {}) if isinstance(page.get("about"), dict) else {}).get("@id")) if page else None
    faq = [(ws(q.get("name", "")), ws(re.sub(r"<[^>]+>", " ", (q.get("acceptedAnswer") or {}).get("text", ""))))
           for x in ld if x.get("@type") == "FAQPage" for q in x.get("mainEntity") or []]
    alts = OrderedDict()
    for l, u in re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)"', h):
        if l in cfg["langs"]:
            alts[l] = urlsplit(html.unescape(u)).path or "/"
    t = Tree()
    t.feed(h)
    main = find(t.root, lambda n: n.tag == "main") or find(t.root, lambda n: n.tag == "body") or t.root
    h1n = find(main, lambda n: n.tag == "h1")
    h1 = ws(render.inline(h1n)) if h1n else ""
    title = ws(html.unescape((re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1]))
    blocks = render.blocks(main, [])
    return {"path": path, "h1": h1 or re.sub(r"\s*\|.*$", "", title), "title": title, "desc": meta(h, "description"),
            "crumbs": crumbs, "types": types, "brand": brand, "faq": faq, "alts": alts, "blocks": blocks}


def section_of(cfg, p, roots):
    if "ItemPage" in p["types"] or "Product" in p["types"]:
        b = (p["brand"] or {}).get("name") or (p["crumbs"][-2] if len(p["crumbs"]) >= 3 else "")
        return f"Products — {b}" if b else "Products"
    c = p["crumbs"]
    if len(c) >= 3:
        return f"Catalog — {c[1]}" if c[1] not in roots.get("brands", ()) else c[1]
    if len(c) == 2 and roots["children"].get(c[1]):
        return c[1] if c[1] in roots.get("brands", ()) else f"Catalog — {c[1]}"
    return cfg["main_section"]


def build(site, show=False):
    cfg = SITES[site]
    dist, base = cfg["dist"], cfg["base"]
    urls = sitemap_urls(dist, base)
    published = set(urls)
    render = Render(cfg)
    pages = []
    for path in urls:
        f = page_file(dist, path)
        if not f:
            continue
        p = parse_page(cfg, path, f, render)
        if p:
            pages.append(p)
    # разделы: у каких верхних пунктов крошек есть страницы ниже; «Бренды» — раздел брендов (страница брендов и фабрик)
    children = Counter(p["crumbs"][1] for p in pages if len(p["crumbs"]) >= 3)
    brand_names = {(p["brand"] or {}).get("name") for p in pages if "ItemPage" in p["types"]} - {None}
    brands = {p["crumbs"][1] for p in pages if len(p["crumbs"]) == 3 and p["crumbs"][2] in brand_names and "CollectionPage" in p["types"]}
    roots = {"children": children, "brands": brands}
    # общие абзацы (на многих страницах одинаковые) — один раз в начале
    cnt = Counter(b[1] for p in pages for b in set(x for x in p["blocks"] if x[0] == "p"))
    shared = {s for s, n in cnt.items() if n >= REPEAT_MIN}
    by = OrderedDict()
    for p in pages:
        by.setdefault(section_of(cfg, p, roots), []).append(p)
    main_s = cfg["main_section"]
    order = [main_s] + [k for k in by if k.startswith("Catalog")] + [k for k in by if k in brands] + \
            sorted(k for k in by if k.startswith("Products")) + [k for k in by if k not in (main_s,) and not k.startswith(("Catalog", "Products")) and k not in brands]
    llms = open(os.path.join(dist, "llms.txt"), encoding="utf-8").read() if os.path.exists(os.path.join(dist, "llms.txt")) else ""
    quote = (re.search(r"^> (.+)$", llms, re.M) or [None, ""])[1]
    L = [f"# {cfg['title']}", ""]
    if quote:
        L += [f"> {quote}", ""]
    names = cfg["langs"]
    L.append(f"Pages: {len(pages)} — the {'English' if cfg['lang'] == 'en' else cfg['lang']} version of every published page, each with the addresses "
             f"of its {', '.join(names.values())} versions (the texts are the same). Updated: {date.today().isoformat()}.")
    L += ["", f"- Summary with links: {base}/llms.txt · Sitemap: {base}/sitemap.xml"]
    if shared:
        common = [s for s in sorted(shared, key=lambda s: -cnt[s]) if len(s) >= 40]   # короткие (название бренда) — и так в «Brand:»
        if common:
            L += ["", "Repeated on many pages:", ""] + [f"- {s}" for s in common]
    L.append("")
    for k in [k for k in order if k in by]:
        ps = by[k]
        if k.startswith("Products"):
            ps = sorted(ps, key=lambda p: ((p["crumbs"][1] if len(p["crumbs"]) > 2 else ""), p["h1"].lower()))
        L += [f"## {k}", ""]
        for p in ps:
            L += [f"### {p['h1']}", "", f"- Page: {base}{p['path']}"]
            alts = [f"{names[l]}: {base}{u}" for l, u in p["alts"].items() if u in published and u != p["path"]]
            if alts:
                L.append(f"- Other languages: {' · '.join(alts)}")
            if p["brand"] and ("ItemPage" in p["types"] or "Product" in p["types"]):
                b = p["brand"]
                extra = ", ".join(x for x in (b.get("legalName"), b.get("url")) if x)
                cat = p["crumbs"][1] if len(p["crumbs"]) > 2 else ""
                L.append(f"- Brand: {b.get('name')}{f' ({extra})' if extra else ''}{f' · Category: {cat}' if cat else ''}")
            if p["desc"]:
                L.append(f"- Description: {p['desc']}")
            body = md(p["blocks"], shared)
            if body:
                L += ["", body]
            if p["faq"] and not any(b[0] == "qa" for b in p["blocks"]):
                L += ["", "#### Questions and answers", ""] + [f"- Question: {q}\n  Answer: {a}" for q, a in p["faq"] if q and a]
            L.append("")
    text = "\n".join(L).rstrip() + "\n"
    out = os.path.join(dist, "llms-full.txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    if show:
        print(text)
    print(f"llms-full.txt: {len(pages)} страниц, {len(text.encode('utf-8')) / 1024:.0f} КБ, разделов {len(by)}")
    return len(pages), len(text.encode("utf-8"))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in SITES:
        sys.exit("python3 scripts/llms_full.py home [--print]")
    build(sys.argv[1], "--print" in sys.argv)
