#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка сборки dumskaya-home.com (home/dist) перед выкладкой — по тем же правилам, что у сайта студии
(scripts/check_site.py):  python3 scripts/check_home.py

Ошибки (выкладка останавливается):
  • внутренние ссылки и фото ведут на существующие файлы;
  • hreflang на все 5 языков и x-default, взаимные; canonical на себя;
  • ровно один H1, title ≤ 60 и description ≤ 155, title не повторяется; JSON-LD читается;
  • хлебные крошки (кроме главных): начинаются с главной своего языка, кончаются текущей страницей без ссылки,
    на языке страницы; разметка BreadcrumbList совпадает с видимыми, у каждого звена, кроме последнего, — ссылка
    на существующую страницу;
  • телефоны студии и мессенджеры — только на русских страницах (решено 25.10.2026: на остальных языках связь через
    форму), e-mail — только адрес из content/home/site.json (пока пусто — ни одного); на всех, кроме русских, нет кириллицы;
  • в своих текстах (data-own, title, description) нет шаблонных оборотов (content/TEXT_STYLE.md, scripts/text_markers.py);
  • в тексте нет «undefined», «NaN», «[object Object]»;
  • карта сайта — индекс и его файлы (scripts/sitemap_check.py): XML читается, у каждого адреса <lastmod>, не больше
    50 000 адресов в файле, только опубликованное (товары и страницы выложенных фабрик); llms.txt ссылается только на
    страницы из карты сайта, в нём все выложенные фабрики и категории с их товарами;
  • robots.txt закрыт (Disallow: /), пока в content/home/site.json нет "indexing": true; открытый — с Sitemap и llms.txt.
  • страница товара — полный набор SEO (правило владельца 26.10.2026, README «SEO страницы товара»): ItemPage о фабрике
    и дизайнере, фото — ImageObject, без Product, og:image и product:brand, факты под названием, главное фото сразу и с местом.
Предупреждения: заглушки вместо фото (нет оригинала), товары выложенной фабрики без своего текста."""
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from html.parser import HTMLParser
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import text_markers as TM  # noqa: E402
import sitemap_check as SC  # noqa: E402

DIST = os.path.join(ROOT, "home/dist")
SITE = "https://dumskaya-home.com"
LANGS = ["en", "ru", "de", "fr", "es"]
HOME = {"en": "/", "ru": "/ru", "de": "/de", "fr": "/fr", "es": "/es"}
HOME_LABEL = {"en": "Home", "ru": "Главная", "de": "Startseite", "fr": "Accueil", "es": "Inicio"}
MARKERS = {"en": TM.EN, "ru": TM.RU, "de": TM.DE, "fr": TM.FR, "es": TM.ES}
SITE_JSON = json.load(open(os.path.join(ROOT, "content/site.json"), encoding="utf-8"))
PHONES = {p["key"]: p for p in SITE_JSON["contacts"]["phones"]}
HOME_EMAIL = (json.load(open(os.path.join(ROOT, "content/home/site.json"), encoding="utf-8")).get("email") or "").strip()
# названия моделей, коллекций и фабрик из каталога: в проверке штампов не считаются (с заглавной буквы — имя, а не оборот:
# «Sofá modular Oasis» — модель, «un oasis de calma» — штамп)
_CAT = json.load(open(os.path.join(ROOT, "home/data/catalog.json"), encoding="utf-8")) if os.path.exists(os.path.join(ROOT, "home/data/catalog.json")) else {"products": []}
_NAMES = sorted({str(x.get(k) or "").strip() for x in _CAT["products"] for k in ("model", "full_model", "collection_name", "brand")} - {""}, key=len, reverse=True)
NAMES = re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(n) for n in _NAMES) + r")(?![\w-])") if _NAMES else re.compile(r"(?!x)x")


def lang_of(u):
    for l in ("ru", "de", "fr", "es"):
        if u == "/" + l or u.startswith("/" + l + "/"):
            return l
    return "en"


class P(HTMLParser):
    VOID = {"img", "input", "br", "meta", "link", "hr", "source", "wbr"}

    def __init__(self):
        super().__init__()
        self.links, self.srcs, self.h1, self.alts, self.canon, self.title, self.desc, self.ld = [], [], 0, {}, None, "", None, []
        self.text, self.own = [], []
        self._t = self._ld = False
        self._skip = 0
        self._depth, self._own = 0, []
        self.crumbs, self._cr, self._cri = [], None, None

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag not in self.VOID:
            self._depth += 1
            if "data-own" in a:
                self._own.append(self._depth)
        if tag in ("script", "style"):
            self._skip += 1
            self._ld = tag == "script" and a.get("type") == "application/ld+json"
        if tag == "nav" and "crumbs" in (a.get("class") or "").split():
            self._cr = self._depth
            self.crumbs.append([])
        if self._cr is not None and tag in ("a", "span"):
            self.crumbs[-1].append(["", a.get("href") if tag == "a" else None, a.get("aria-current") == "page"])
            self._cri = self._depth
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in ("img", "link") and (a.get("src") or (tag == "link" and a.get("rel") in ("icon", "apple-touch-icon", "preload"))):
            self.srcs.append(a.get("src") or a.get("href"))
        if tag == "img" and a.get("srcset"):
            self.srcs += [x.strip().split(" ")[0] for x in a["srcset"].split(",")]
        for k in ("data-full",):
            if a.get(k):
                self.srcs.append(a[k])
        if tag == "h1":
            self.h1 += 1
        if tag == "title":
            self._t = True
        if tag == "link" and a.get("rel") == "canonical":
            self.canon = a.get("href")
        if tag == "link" and a.get("rel") == "alternate" and a.get("hreflang"):
            self.alts[a["hreflang"]] = a["href"]
        if tag == "meta" and a.get("name") == "description":
            self.desc = a.get("content")

    def handle_endtag(self, tag):
        if tag not in self.VOID:
            if self._cri == self._depth:
                self._cri = None
            if self._cr == self._depth:
                self._cr = None
            if self._own and self._own[-1] == self._depth:
                self._own.pop()
            self._depth -= 1
        if tag in ("script", "style"):
            self._skip -= 1
            self._ld = False
        if tag == "title":
            self._t = False

    def handle_data(self, d):
        if self._cri is not None and self.crumbs and self.crumbs[-1]:
            self.crumbs[-1][-1][0] += d
        if self._t:
            self.title += d
        if self._ld:
            self.ld.append(d)
        elif not self._skip:
            self.text.append(d)
            if self._own:
                self.own.append(d)


def url_of(f):
    rel = os.path.relpath(f, DIST)
    return "/" if rel == "index.html" else "/" + rel[:-5]


def check_crumbs(u, p, parsed, errs):
    l = lang_of(u)
    if u in HOME.values():
        return
    if len(p.crumbs) != 1:
        return errs.append(f"крошки: {'нет' if not p.crumbs else 'несколько блоков'}: {u}")
    vis = [[" ".join(t.split()), h, cur] for t, h, cur in p.crumbs[0]]
    if len(vis) < 2:
        return errs.append(f"крошки: одно звено: {u}")
    if vis[0][1] != HOME[l] or vis[0][0] != HOME_LABEL[l]:
        errs.append(f"крошки: первое звено не «{HOME_LABEL[l]}» ({vis[0][0]} → {vis[0][1]}): {u}")
    last = vis[-1]
    if last[1] is not None or not last[2] or not last[0]:
        errs.append(f"крошки: последнее звено должно быть текущей страницей без ссылки: {u}")
    labels = " ".join(t for t, _, _ in vis)
    if l != "ru" and re.search(r"[а-яё]", labels, re.I):
        errs.append(f"крошки не на языке страницы ({labels}): {u}")
    bl = []
    for block in p.ld:
        try:
            d = json.loads(block)
        except Exception:
            continue
        bl += [x for x in d.get("@graph", [d]) if x.get("@type") == "BreadcrumbList"]
    if len(bl) != 1:
        return errs.append(f"крошки: в разметке BreadcrumbList {len(bl)} шт.: {u}")
    items = bl[0].get("itemListElement", [])
    if [i.get("position") for i in items] != list(range(1, len(items) + 1)):
        errs.append(f"крошки: позиции в разметке не по порядку: {u}")
    for i in items[:-1]:
        if not i.get("item"):
            errs.append(f"крошки: в разметке звено без ссылки «{i.get('name')}»: {u}")
        elif (urlparse(i["item"]).path or "/") not in parsed:
            errs.append(f"крошки: в разметке ссылка на несуществующую страницу {i['item']}: {u}")
    want = [t for t, h, _ in vis[:-1] if h] + [last[0]]
    got = [" ".join(str(i.get("name", "")).split()) for i in items]
    if got != want:
        errs.append(f"крошки: разметка {got} не совпадает с видимыми {want}: {u}")


PRODUCT_SEO = "README, «SEO страницы товара» (правило 26.10.2026)"


def check_product_seo(u, h, errs):
    """Страница товара — полный набор SEO (правило владельца 26.10.2026, README «SEO страницы товара»):
    Schema.org ItemPage о фабрике (Organization с сайтом в sameAs) и дизайнере (Person), фото — ImageObject с правообладателем,
    организация магазина, без Product (нет цены); og:image + alt, product:brand; список фактов под названием и свой текст;
    главное фото — сразу (eager, fetchpriority=high) и с заранее занятым местом (--ar); у фото — width/height (CLS)."""
    bad = []
    nodes = []
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
        try:
            o = json.loads(block)
            nodes += o.get("@graph") or [o]
        except Exception:
            pass
    types = [n.get("@type") for n in nodes]
    page = next((n for n in nodes if n.get("@type") == "ItemPage"), None)
    if not page:
        bad.append("нет ItemPage")
    else:
        ids = {n.get("@id"): n for n in nodes}
        brand = ids.get((page.get("about") or {}).get("@id"))
        if not brand or brand.get("@type") != "Organization" or not brand.get("sameAs"):
            bad.append("ItemPage.about — не фабрика (Organization с sameAs)")
        if re.search(r"<dt>(Design|Дизайн|Diseño)</dt>", h) and not page.get("mentions"):
            bad.append("дизайнер есть на странице, но не в разметке (mentions → Person)")
        if re.search(r'class="pgal__i[^"]*"[^>]*>\s*<img', h):
            img = page.get("primaryImageOfPage")
            if not isinstance(img, dict) or img.get("@type") != "ImageObject" or not img.get("creditText") or not img.get("copyrightNotice"):
                bad.append("главное фото — не ImageObject с creditText и copyrightNotice")
        if page.get("publisher", {}).get("@id") not in ids:
            bad.append("нет организации магазина (publisher)")
    if "Product" in types:
        bad.append("разметка Product без цены — ошибка для Google")
    for m in ('property="og:image"', 'property="og:image:alt"', 'property="product:brand"'):
        if m not in h and not (m.startswith('property="og:image') and 'class="ph' in h.split('pgal', 1)[-1][:2000]):
            bad.append(f"нет {m}")
    if not re.search(r'<dl class="pinfo__meta">', h):
        bad.append("нет списка фактов под названием")
    main = re.search(r'<button[^>]*pgal__i--main[^>]*>\s*(<img[^>]*>)', h)
    if main:
        tag = main.group(1)
        if 'loading="eager"' not in tag or 'fetchpriority="high"' not in tag:
            bad.append("главное фото грузится не сразу (LCP)")
        if "--ar:" not in tag:
            bad.append("у главного фото не занято место до загрузки (CLS)")
    for tag in re.findall(r"<img\b[^>]*>", h):
        if "data-lb-img" not in tag and ("width=" not in tag or "height=" not in tag):
            bad.append("фото без width/height (CLS)")
            break
    for b in bad:
        errs.append(f"SEO товара: {b} ({PRODUCT_SEO}): {u}")


def main():
    errs, warns = [], []
    files = {"/" + os.path.relpath(f, DIST) for f in glob.glob(os.path.join(DIST, "**/*"), recursive=True) if os.path.isfile(f)}
    IMG = os.path.join(ROOT, "home/img")                    # фото лежат отдельно от сборки (на сервер — в /img/)
    files |= {"/img/" + n for n in (os.listdir(IMG) if os.path.isdir(IMG) else [])}
    pages, raw = {}, {}
    for f in glob.glob(os.path.join(DIST, "**/*.html"), recursive=True):
        u = url_of(f)
        if u == "/404":
            continue
        raw[u] = open(f, encoding="utf-8").read()
        p = P()
        p.feed(raw[u])
        pages[u] = p
    titles = Counter(p.title.strip() for p in pages.values())
    for u, p in pages.items():
        l = lang_of(u)
        t = p.title.strip()
        if not t or len(t) > 60:
            errs.append(f"title {len(t)}: {u} ({t})")
        if titles[t] > 1:
            errs.append(f"title повторяется: {t}: {u}")
        if not p.desc or len(p.desc) > 155:
            errs.append(f"description {len(p.desc or '')}: {u}")
        if p.h1 != 1:
            errs.append(f"H1 x{p.h1}: {u}")
        if p.canon != SITE + u:
            errs.append(f"canonical {p.canon}: {u}")
        if set(p.alts) != set(LANGS) | {"x-default"}:
            errs.append(f"языковые версии {sorted(p.alts)}: {u}")
        for lang, href in p.alts.items():
            v = urlparse(href).path or "/"
            if v not in pages:
                errs.append(f"hreflang {lang} → нет страницы {v}: {u}")
            elif lang != "x-default" and SITE + u not in pages[v].alts.values():
                errs.append(f"hreflang не взаимный {u} ↔ {v}")
        for href in p.links:
            if href.startswith(("mailto:", "tel:", "#", "http://", "https://")) and not href.startswith(SITE):
                continue
            v = urlparse(href.replace(SITE, "")).path or "/"
            if v.startswith("/api/"):
                continue
            if v not in pages and v not in files:
                errs.append(f"битая ссылка {v}: {u}")
        for s in p.srcs:
            if s and s.startswith("/") and urlparse(s).path not in files:
                errs.append(f"нет файла {s}: {u}")
        for block in p.ld:
            try:
                json.loads(block)
            except Exception as e:
                errs.append(f"JSON-LD не читается: {u}: {e}")
        check_crumbs(u, p, pages, errs)
        txt = " ".join(p.text)
        for bad in ("undefined", "NaN", "[object Object]"):
            if re.search(r"(?<![\w-])" + re.escape(bad) + r"(?![\w-])", txt):
                errs.append(f"в тексте «{bad}»: {u}")
        if l != "ru":
            m = re.search(r"\w*[а-яё]\w*", txt + " " + t + " " + (p.desc or ""), re.I)
            if m:
                errs.append(f"кириллица на странице {l} («{m.group(0)}»): {u}")
        # контакты — по видимой странице и разметке Schema: в скрипте статистики есть «tel:» и «mailto:» как образцы ссылок
        h = re.sub(r"<script(?![^>]*application/ld\+json)[^>]*>.*?</script>", "", raw[u], flags=re.S)
        has_tel = [ph["text"] for ph in PHONES.values() if ph["tel"] in h or ph["text"] in h or ph["tel"].lstrip("+") in h]
        if l != "ru":                                 # телефон и мессенджеры — только на русской версии
            if has_tel or re.search(r"""["'\s(]tel:""", h):     # не «Leuchtmittel: …» в тексте
                errs.append(f"телефон на странице {l} ({', '.join(has_tel) or 'tel:'}): {u}")
            if re.search(r"https://(wa\.me|t\.me)/", h):
                errs.append(f"мессенджер на странице {l}: {u}")
        elif not has_tel:
            errs.append(f"нет телефона на русской странице: {u}")
        for m in set(re.findall(r"mailto:([^\"'?]+)", h)) | set(re.findall(r"[\w.+-]+@dumskaya-(?:design|home)\.com", h)):
            if m != HOME_EMAIL:
                errs.append(f"e-mail {m} на странице (на сайте — только {HOME_EMAIL or 'форма, e-mail пока нет'}): {u}")
        own = " ".join([t, p.desc or ""] + p.own)
        hits = TM.scan(NAMES.sub(" ", own), MARKERS[l])     # названия моделей (Flexform «Oasis») — не штампы
        if hits:
            errs.append(f"шаблонные обороты ({l}): {', '.join(hits)}: {u}")
        if re.search(r'class="ph[\s"]', raw[u]):
            warns.append(f"заглушка вместо фото (нет оригинала): {u}")
        if 'property="og:type" content="product"' in raw[u]:
            check_product_seo(u, raw[u], errs)
    cat = json.load(open(os.path.join(ROOT, "home/data/catalog.json"), encoding="utf-8"))
    no_text = defaultdict(int)
    for pr in cat["products"]:
        if pr.get("published"):
            for l in LANGS:
                if not (pr.get("text") or {}).get(l):
                    no_text[pr["factory"]] += 1
    for f, n in no_text.items():
        warns.append(f"{f}: без своего текста — {n} (товар × язык)")
    ph = [w for w in warns if w.startswith("заглушка")]
    other = [w for w in warns if not w.startswith("заглушка")]
    # ключ IndexNow (deploy/indexnow.py): ровно один файл <ключ>.txt в корне сайта, внутри — сам ключ
    keys = [n for n in os.listdir(DIST) if re.fullmatch(r"[0-9a-f]{32}\.txt", n)]
    if len(keys) != 1:
        errs.append(f"ключ IndexNow: в корне сайта должен быть ровно один файл <ключ>.txt (папка home/public/), сейчас {len(keys)}")
    elif open(os.path.join(DIST, keys[0]), encoding="utf-8").read().strip() != keys[0][:-4]:
        errs.append(f"ключ IndexNow: внутри {keys[0]} должен быть сам ключ")
    # карта сайта: только опубликованное; llms.txt — только на страницы из неё; robots.txt — закрыт до запуска
    sm = SC.check_sitemaps(DIST, SITE, set(pages), errs)
    pub_paths = set()
    for pr in cat["products"]:
        for u in (pr.get("path") or {}).values():
            if u in sm and not pr.get("published"):
                errs.append(f"в карте сайта неопубликованный товар: {u}")
            if pr.get("published"):
                pub_paths.add(u)
    for f, b in (cat.get("brands") or {}).items():
        for l in LANGS:
            u = ("" if l == "en" else "/" + l) + "/" + b["slug"]
            if u in sm and not b.get("published"):
                errs.append(f"в карте сайта страница невыложенной фабрики: {u}")
    for u in pub_paths:
        if u in pages and u not in sm:
            errs.append(f"опубликованный товар не в карте сайта: {u}")
    links = SC.check_llms(DIST, SITE, sm, set(), errs)
    seen = links.get("llms.txt", set())
    tax = cat.get("taxonomy") or {}
    pubs = [pr for pr in cat["products"] if pr.get("published")]
    for f, b in (cat.get("brands") or {}).items():
        if b.get("published") and "/" + b["slug"] not in seen:
            errs.append(f"llms.txt: нет выложенной фабрики {b['name']}")
    for c in sorted({pr["category"] for pr in pubs}):
        u = "/" + tax["categories"][c]["slug"]["en"]
        if u not in seen:
            errs.append(f"llms.txt: нет категории {u}")
    robots = open(os.path.join(DIST, "robots.txt"), encoding="utf-8").read() if os.path.exists(os.path.join(DIST, "robots.txt")) else ""
    opened = json.load(open(os.path.join(ROOT, "content/home/site.json"), encoding="utf-8")).get("indexing") is True
    closed = re.search(r"(?im)^\s*user-agent:\s*\*\s*$(?:\n(?!\s*user-agent).*)*?^\s*disallow:\s*/\s*$", robots) is not None
    if not opened and not closed:
        errs.append("robots.txt должен быть закрыт (User-agent: * / Disallow: /), пока каталог не открыт (content/home/site.json → indexing)")
    if opened and (closed or f"Sitemap: {SITE}/sitemap.xml" not in robots or "Disallow: /api/" not in robots):
        errs.append("robots.txt открытого каталога: Allow, Disallow: /api/, Sitemap и ссылка на llms.txt")
    print(f"страниц: {len(pages)}, файлов: {len(files)}, в карте сайта: {len(sm)}, robots.txt: {'открыт' if opened else 'закрыт'}")
    print(f"ошибок: {len(errs)}, предупреждений: {len(warns)}")
    for e in sorted(set(errs))[:80]:
        print("  ✗", e)
    if ph:
        print(f"  ⚠ страниц с заглушками вместо фото: {len(ph)} (нет оригиналов — докачать фото фабрики), например {ph[0].split(': ', 1)[1]}")
    for w in other[:30]:
        print("  ⚠", w)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
