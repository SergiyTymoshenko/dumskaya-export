#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка собранного сайта (папка dist/) перед выкладкой:
  • все внутренние ссылки ведут на существующие страницы (не на редиректы и не в 404);
  • hreflang взаимные, у каждой страницы есть x-default и canonical на себя;
  • ровно один H1, есть title ≤ 60 и description ≤ 155;
  • JSON-LD парсится;
  • ни одна страница не попала в список редиректов (иначе она была бы недоступна);
  • Варшава/Москва не встречаются в видимом тексте страниц, кроме явно варшавских проектов;
  • хлебные крошки на каждой странице (кроме главных): начинаются с главной своего языка, кончаются
    текущей страницей (без ссылки), на языке страницы; разметка BreadcrumbList для Google с ними совпадает,
    у каждого звена, кроме последнего, есть ссылка на существующую страницу;
  • на словацких страницах — только словацкий телефон студии, на немецких — только австрийский
    (ссылки tel:, видимый текст, разметка); на них нет кириллицы, а ссылки из текста ведут на страницы того же языка;
  • карта сайта (scripts/sitemap_check.py): XML читается, в ней все страницы, у каждой — <lastmod> (вписывает
    scripts/lastmod.py после сборки); llms.txt и llms-full.txt ссылаются только на страницы из карты сайта (не на старые
    адреса), в llms.txt есть все услуги, цены и пакеты, проекты, советы, магазин, «О студии», контакты; нет старых
    номеров (+48 — Польша, +1 — США). Если отпечатки страниц не сохранены (lastmod.py save), — предупреждение.
  python3 scripts/check_site.py
"""
import glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sitemap_check as SC  # noqa: E402
from html.parser import HTMLParser
from urllib.parse import urlparse, unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
SITE = "https://dumskaya-design.com"


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.body_links = []   # ссылки в тексте страницы (без шапки, меню и подвала)
        self.links, self.h1, self.alts, self.canon, self.title, self.desc, self.ld = [], 0, {}, None, "", None, []
        self._t = self._ld = False
        self.text = []
        self._skip = 0
        self._depth, self._navstack = 0, []   # шапка, меню и подвал не считаются текстом страницы
        self.crumbs, self._cr, self._cri = [], None, None   # видимые хлебные крошки: [[текст, href, текущая]]

    VOID = {"img", "input", "br", "meta", "link", "hr", "source", "wbr"}

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag not in self.VOID:
            self._depth += 1
            if tag in ("header", "nav", "footer") or (a.get("class") or "").split()[:1] == ["menu"]:
                self._navstack.append(self._depth)
        if tag in ("script", "style"):
            self._skip += 1
            if tag == "script" and a.get("type") == "application/ld+json":
                self._ld = True
        if tag == "nav" and "crumbs" in (a.get("class") or "").split():
            self._cr = self._depth
            self.crumbs.append([])
        if self._cr is not None and tag in ("a", "span"):
            self.crumbs[-1].append(["", a.get("href") if tag == "a" else None, a.get("aria-current") == "page"])
            self._cri = self._depth
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
            if not self._navstack:
                self.body_links.append(a["href"])
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
        if tag == "img" and a.get("alt") is not None and not self._navstack:
            self.text.append(a.get("alt"))

    def handle_endtag(self, tag):
        if tag not in self.VOID:
            if self._cri == self._depth:
                self._cri = None
            if self._cr == self._depth:
                self._cr = None
            if self._navstack and self._navstack[-1] == self._depth:
                self._navstack.pop()
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
        elif not self._skip and not self._navstack:
            self.text.append(d)


SITE_JSON = json.load(open(os.path.join(ROOT, "content", "site.json"), encoding="utf-8"))
PHONES = {p["key"]: p for p in SITE_JSON["contacts"]["phones"]}
OWN_PHONE = {"sk": "sk", "de": "at"}   # на этих языках — только свой номер


def check_phones(u, html, errs):
    lang = lang_of(u)
    own = PHONES.get(OWN_PHONE.get(lang))
    if not own:
        return
    # мессенджеры студии (WhatsApp, Telegram) привязаны к своему номеру — это не телефон в тексте
    html = re.sub(r"https://(wa\.me|t\.me)/[^\"'\s<]*", "", html)
    for k, ph in PHONES.items():
        if ph is own:
            continue
        digits = ph["tel"].lstrip("+")
        if ph["tel"] in html or ph["text"] in html or re.search(r"\+\s?" + r"\s?".join(digits), html):
            errs.append(f"чужой телефон {ph['text']} на странице {lang}: {u}")
    if own["tel"] not in html:
        errs.append(f"нет телефона {own['text']}: {u}")


HOME = {"ru": "/", "ua": "/ua", "en": "/en", "sk": "/sk", "de": "/de"}
HOME_LABEL = {"ru": "Главная", "ua": "Головна", "en": "Home", "sk": "Domov", "de": "Startseite"}


def lang_of(u):
    for l in ("ua", "en", "sk", "de"):
        if u == "/" + l or u.startswith("/" + l + "/"):
            return l
    return "ru"


def check_crumbs(u, p, parsed, errs):
    """Хлебные крошки: видимые и в разметке BreadcrumbList (Google требует ссылку у каждого звена, кроме последнего)."""
    lang = lang_of(u)
    if u in HOME.values():
        return
    if len(p.crumbs) != 1:
        errs.append(f"крошки: {'нет' if not p.crumbs else 'несколько блоков'}: {u}")
        return
    vis = [[" ".join(t.split()), h, cur] for t, h, cur in p.crumbs[0]]
    if len(vis) < 2:
        errs.append(f"крошки: одно звено: {u}")
        return
    if vis[0][1] != HOME[lang] or vis[0][0] != HOME_LABEL[lang]:
        errs.append(f"крошки: первое звено не «{HOME_LABEL[lang]}» ({vis[0][0]} → {vis[0][1]}): {u}")
    last = vis[-1]
    if last[1] is not None or not last[2] or not last[0]:
        errs.append(f"крошки: последнее звено должно быть текущей страницей без ссылки ({last[0] or 'пусто'}): {u}")
    for t, h, cur in vis[1:-1]:
        if not t:
            errs.append(f"крошки: пустое звено: {u}")
    labels = " ".join(t for t, _, _ in vis)
    if (lang in ("en", "sk", "de") and re.search(r"[а-яёіїєґ]", labels, re.I)) or (lang == "ua" and re.search(r"[ыэъё]", labels, re.I)):
        errs.append(f"крошки не на языке страницы ({labels}): {u}")
    bl = []
    for block in p.ld:
        try:
            d = json.loads(block)
        except Exception:
            continue
        bl += [x for x in d.get("@graph", [d]) if x.get("@type") == "BreadcrumbList"]
    if len(bl) != 1:
        errs.append(f"крошки: в разметке BreadcrumbList {len(bl)} шт.: {u}")
        return
    items = bl[0].get("itemListElement", [])
    if [i.get("position") for i in items] != list(range(1, len(items) + 1)):
        errs.append(f"крошки: позиции в разметке не по порядку: {u}")
    for i in items[:-1]:
        if not i.get("item"):
            errs.append(f"крошки: в разметке звено без ссылки «{i.get('name')}»: {u}")
        elif (urlparse(i["item"]).path or "/") not in parsed:
            errs.append(f"крошки: в разметке ссылка на несуществующую страницу {i['item']}: {u}")
    if items and items[-1].get("item") and items[-1]["item"] != SITE + u:
        errs.append(f"крошки: последнее звено разметки ведёт не на эту страницу ({items[-1]['item']}): {u}")
    # разметка = видимые звенья со ссылкой + текущая страница
    want = [t for t, h, _ in vis[:-1] if h] + [last[0]]
    got = [" ".join(str(i.get("name", "")).split()) for i in items]
    if got != want:
        errs.append(f"крошки: разметка {got} не совпадает с видимыми {want}: {u}")


def url_of(f):
    rel = os.path.relpath(f, DIST)
    if rel == "index.html":
        return "/"
    return "/" + unquote(rel[:-5])


def check_page_seo(u, p, h, errs):
    """Полный набор SEO на каждой странице студии (правило владельца 26.10.2026, README «SEO страниц»): разметка Schema.org —
    организация, сайт, крошки и страница с описанием и главным фото; og:image с подписью; товар магазина — ItemPage, фото —
    ImageObject с правообладателем, og:type product и product:brand, без Product (цен нет); главное фото — сразу, у фото —
    width/height (CLS)."""
    bad, nodes = [], []
    for block in p.ld:
        try:
            o = json.loads(block)
            nodes += o.get("@graph") or [o]
        except Exception:
            pass
    types = {str(n.get("@type")) for n in nodes}
    for t in ("Organization", "WebSite", "BreadcrumbList"):
        if t not in types and not (t == "Organization" and "['ProfessionalService', 'HomeAndConstructionBusiness']" in types):
            bad.append(f"нет {t}")
    page = next((n for n in nodes if str(n.get("@type", "")).endswith("Page")), None)
    if not page or not page.get("description"):
        bad.append("нет страницы (WebPage …) с описанием в разметке")
    if 'property="og:image"' in h and 'property="og:image:alt"' not in h:
        bad.append("нет og:image:alt")
    ru = urlparse(p.alts.get("ru", "")).path or u           # товар — по русскому адресу (/shop/<товар>, не /shop/cat/…)
    shop_item = bool(re.match(r"^/shop/(?!cat/)[^/]+$", ru))
    if shop_item:
        if not page or page.get("@type") != "ItemPage":
            bad.append("товар магазина — не ItemPage")
        elif 'class="sgal' in h and "<img" in h.split('class="sgal', 1)[1][:400]:
            im = page.get("primaryImageOfPage") or {}
            if im.get("@type") != "ImageObject" or not im.get("copyrightNotice"):
                bad.append("главное фото товара — не ImageObject с правообладателем")
        if 'content="product"' not in h or 'property="product:brand"' not in h:
            bad.append("нет og:type product / product:brand")
    if "Product" in types:
        bad.append("разметка Product без цены — ошибка для Google")
    for tag in re.findall(r"<img\b[^>]*>", h):
        if "data-lb" not in tag and ("width=" not in tag or "height=" not in tag):
            bad.append("фото без width/height (CLS)")
            break
    for b in bad:
        errs.append(f"SEO страницы: {b} (README, правило 26.10.2026): {u}")


def main():
    files = [f for f in glob.glob(os.path.join(DIST, "**", "*.html"), recursive=True) if not f.endswith("404.html")]
    pages = {url_of(f): f for f in files}
    redirects = json.load(open(os.path.join(ROOT, "content", "redirects.json"), encoding="utf-8"))
    projects = json.load(open(os.path.join(ROOT, "content", "projects.json"), encoding="utf-8"))
    explicit = {v for p in projects if p.get("explicit_warsaw") for v in p["alternates"].values()}
    explicit |= {u for u in pages if re.search(r"warsaw|varshav|germany|germaniya|nimechch|deutschland", u)}
    errs, warn = [], []
    parsed, raw_html = {}, {}
    for u, f in pages.items():
        p = P()
        raw_html[u] = open(f, encoding="utf-8").read()
        p.feed(raw_html[u])
        parsed[u] = p
    for u, p in parsed.items():
        if p.h1 != 1:
            errs.append(f"H1 x{p.h1}: {u}")
        t = p.title.strip()
        if not t or len(t) > 60:
            errs.append(f"title {len(t)}: {u}")
        if not p.desc or len(p.desc) > 155:
            errs.append(f"description {len(p.desc or '')}: {u}")
        if p.canon != SITE + u and not (u == "/" and p.canon == SITE + "/"):
            errs.append(f"canonical {p.canon}: {u}")
        if "x-default" not in p.alts:
            errs.append(f"нет x-default: {u}")
        for lang, href in p.alts.items():
            v = urlparse(href).path or "/"
            if v not in parsed:
                errs.append(f"hreflang {lang} → нет страницы {v}: {u}")
            elif lang != "x-default" and SITE + u not in [h for h in parsed[v].alts.values()] and SITE + "/" != SITE + u:
                errs.append(f"hreflang не взаимный {u} ↔ {v}")
        for raw in p.links:
            if raw.startswith(("mailto:", "tel:", "#", "http://", "https://")) and not raw.startswith(SITE):
                continue
            v = urlparse(raw.replace(SITE, "")).path or "/"
            if v.startswith("/img/") or v.startswith("/_astro/") or v.startswith("/api/"):
                continue
            if v in redirects:
                errs.append(f"ссылка на старый адрес {v}: {u}")
            elif v not in parsed:
                errs.append(f"битая ссылка {v}: {u}")
        for block in p.ld:
            try:
                json.loads(block)
            except Exception as e:
                errs.append(f"JSON-LD не читается: {u}: {e}")
        check_crumbs(u, p, parsed, errs)
        check_page_seo(u, p, raw_html[u], errs)
        lang = lang_of(u)
        if lang in OWN_PHONE:
            check_phones(u, raw_html[u], errs)
            txt = " ".join(p.text)
            m = re.search(r"\w*[а-яёіїєґ]\w*", txt, re.I)
            if m:
                errs.append(f"кириллица на странице {lang} («{m.group(0)}»): {u}")
            for raw in p.body_links:
                v = urlparse(raw.replace(SITE, "")).path or "/"
                if raw.startswith("/") or raw.startswith(SITE):
                    if not v.startswith(("/img/", "/_astro/", "/api/")) and lang_of(v) != lang:
                        errs.append(f"ссылка из текста на другой язык {v}: {u}")
        if u not in explicit:
            txt = " ".join(p.text)
            m = re.search(r"\w*(Варшав|Warsaw|Warszaw|Varšav|Warschau|Москв|Moscow|Moskv|Moskau|Польш|Польщ|Poland|Poľsk|Polen)\w*", txt)
            if m:
                ctx = txt[max(0, m.start() - 60): m.end() + 30].replace("\n", " ")
                warn.append(f"гео в тексте {u}: …{ctx}…")
    # фото, которых не было при сборке (вместо них серая заглушка .ph): сборка на Mac из оригиналов должна давать 0
    PH = re.compile(r'class="ph[\s"]')          # заглушка <span class="ph …"> (не phero, ph2 — это блоки проекта)
    ph = [u for u, f in pages.items() if PH.search(open(f, encoding="utf-8").read())]
    if ph:
        warn.insert(0, f"страниц с заглушками вместо фото: {len(ph)} (нет оригиналов — проверьте вывод npm run images), например {ph[0]}")
    clash = [u for u in pages if u in redirects]
    for u in clash:
        errs.append(f"страница стоит в редиректах: {u}")
    for k, v in redirects.items():
        if v not in pages:
            errs.append(f"редирект ведёт в никуда: {k} → {v}")
    # ключ IndexNow (deploy/indexnow.py): ровно один файл <ключ>.txt в корне сайта, внутри — сам ключ
    keys = [n for n in os.listdir(DIST) if re.fullmatch(r"[0-9a-f]{32}\.txt", n)]
    if len(keys) != 1:
        errs.append(f"ключ IndexNow: в корне сайта должен быть ровно один файл <ключ>.txt (папка public/), сейчас {len(keys)}")
    elif open(os.path.join(DIST, keys[0]), encoding="utf-8").read().strip() != keys[0][:-4]:
        errs.append(f"ключ IndexNow: внутри {keys[0]} должен быть сам ключ")
    # карта сайта и справки для нейросетей
    sm = SC.check_sitemaps(DIST, SITE, set(pages), errs)
    if sm:
        for u in pages:
            if u not in sm and 'name="robots" content="noindex' not in raw_html[u]:
                errs.append(f"страница не в карте сайта: {u}")
    links = SC.check_llms(DIST, SITE, sm, set(redirects), errs)
    for name in links:
        text = open(os.path.join(DIST, name), encoding="utf-8").read()
        m = re.search(r"\+48[\s\d]|\+1[\s(-]\d", text)
        if m:
            errs.append(f"{name}: старый номер телефона ({m.group(0).strip()}…) — номеров Польши и США на сайте нет")
    must = {"service", "price", "project", "article", "about", "contact", "portfolio", "shop"}
    for f in glob.glob(os.path.join(ROOT, "content/pages/en/**/*.json"), recursive=True):
        pg = json.load(open(f, encoding="utf-8"))
        if pg.get("type") in must and pg["path"] in pages and pg["path"] not in links.get("llms.txt", set()):
            errs.append(f"llms.txt: нет страницы {pg['path']} ({pg['type']})")
    try:
        import lastmod as LM
        stale = [p for p, (_, _, how) in LM.compute("studio")[4].items() if how != "same"]
        if stale:
            warn.append(f"lastmod: у {len(stale)} страниц содержимое изменилось после сохранения дат — даты по истории git "
                        f"(сохранить: python3 scripts/lastmod.py save studio), например {stale[0]}")
    except Exception as e:  # noqa: BLE001
        warn.append(f"lastmod: не проверено ({type(e).__name__}: {e})")
    print(f"страниц: {len(pages)}, редиректов: {len(redirects)}, в карте сайта: {len(sm)}")
    print(f"ошибок: {len(errs)}, предупреждений: {len(warn)}")
    for e in sorted(set(errs))[:80]:
        print("  ✗", e)
    for w in warn[:40]:
        print("  ⚠", w)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
