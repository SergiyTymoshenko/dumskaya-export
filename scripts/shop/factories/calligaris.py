#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Calligaris (calligaris.com): сбор с открытых страниц сайта — без входа, robots.txt соблюдается (запрещены только
сортировка, фильтры и поиск — их не трогаем), один запрос в секунду. Страницы кешируются в cache/calligaris/.

   python3 calligaris.py crawl      # разделы каталога (все страницы списка) и страницы изделий → cache/
   python3 calligaris.py build      # → calligaris.json (изделия) и calligaris-images.json (что за фото)
   python3 calligaris.py sizes      # размеры фото на белом: первые 64 КБ каждого снимка → calligaris-sizes.json
   python3 calligaris.py sources    # → content/shop/sources/calligaris/{site,files}.json (для factories_import.py и dl.py)

Данные — из JSON страницы (Next.js, __NEXT_DATA__), версия en-RW (международная, цены в евро):
  • список раздела (/en-RW/products/<раздел>?page=N): карточки — код (CS5156-C), семейство, короткое описание,
    раздел, фото изделия на белом фоне (cloudfront), новинка;
  • страница изделия (/en-RW/products/<код>-<семейство>): описание, размеры (высота, ширина, глубина),
    розничная цена в евро (для подсказки студии, на сайт не идёт), дизайнер, интерьерные фото (Contentful),
    ссылки на файлы OBJ / DWG / SKP и инструкцию по сборке — сами файлы не качаем.
Внутренний API сайта (/api/…, b2c-api) не используем — только то, что видно на странице."""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "calligaris")
BASE = "https://www.calligaris.com"
LOC = "en-RW"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36 DumskayaCatalog/1.0"
TOP = ["chairs", "armchairs", "sofas", "tables", "occasional-furniture", "stools", "beds", "bedroom-furniture",
       "cabinets-sideboards-wall-uni", "objects", "rugs"]
_last = [0.0]


def get(url, binary=False, headers=None):
    """Страница с сайта (из кеша, если уже была); None — нет страницы (404)."""
    key = re.sub(r"[^A-Za-z0-9._-]+", "_", url.replace(BASE, ""))[:180]
    path = os.path.join(CACHE, key + (".bin" if binary else ".html"))
    if os.path.exists(path):
        data = open(path, "rb").read()
        return None if data == b"404" else data if binary else data.decode("utf-8", "replace")
    wait = 1.0 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(urllib.parse.quote(url, safe=":/?=&%"), headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            os.makedirs(CACHE, exist_ok=True)
            open(path, "wb").write(b"404")
            return None
        if e.code == 206:
            data = e.read()
        else:
            raise
    os.makedirs(CACHE, exist_ok=True)
    open(path, "wb").write(data)
    return data if binary else data.decode("utf-8", "replace")


def next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html or "", re.S)
    return json.loads(m.group(1))["props"]["pageProps"] if m else {}


def listing(cat):
    """Все карточки раздела: [{sku, slug, family, description, category, image, brand, isNew}]."""
    out, page, pages = [], 1, 1
    while page <= pages:
        html = get(f"{BASE}/{LOC}/products/{cat}" + (f"?page={page}" if page > 1 else ""))
        p = next_data(html).get("products") or {}
        pages = (p.get("paginationInfo") or {}).get("pagesCount") or 1
        out += p.get("items") or []
        page += 1
    return out


def product_urls():
    xml = get(f"{BASE}/{LOC}/site-maps/sitemap-products.xml")
    return sorted(set(re.findall(r"<loc>([^<]+)</loc>", xml or "")))


def crawl():
    cards = {}
    for c in TOP:
        items = listing(c)
        for it in items:
            cards.setdefault(it["slug"].split("/")[-1].lower(), it)
        print(f"раздел {c}: {len(items)} карточек", flush=True)
    urls = product_urls()
    # страница изделия: адрес из карты сайта; карточки, которых в карте нет, — по коду и семейству из списка
    by_slug = {u.rsplit("/", 1)[-1].lower(): u for u in urls}
    for s in cards:
        by_slug.setdefault(s, f"{BASE}/{LOC}/products/{s}")
    ok = 0
    for i, (s, u) in enumerate(sorted(by_slug.items()), 1):
        ok += get(u) is not None
        if i % 50 == 0:
            print(f"  страниц изделий: {i} из {len(by_slug)}", flush=True)
    json.dump({"cards": cards, "pages": by_slug}, open(os.path.join(CACHE, "_index.json"), "w"), ensure_ascii=False)
    print(f"карточек {len(cards)}, страниц изделий {len(by_slug)}: открылось {ok}, нет страницы {len(by_slug) - ok}")


def https(u):
    return ("https:" + u) if (u or "").startswith("//") else u


def text_of(node):
    """Текст из Contentful rich text."""
    if isinstance(node, dict):
        if node.get("nodeType") == "text":
            return node.get("value") or ""
        parts = [text_of(x) for x in node.get("content") or []]
        sep = "\n\n" if node.get("nodeType") == "document" else ""
        return sep.join(p for p in parts if p).strip() if sep else "".join(parts)
    return ""


def images_in(o, out):
    """Все снимки Contentful на странице изделия (desktop): адрес, размеры, вес, подпись."""
    if isinstance(o, dict):
        f = o.get("file") if isinstance(o.get("file"), dict) else None
        if f and (f.get("contentType") or "").startswith("image/") and f.get("url"):
            d = (f.get("details") or {}).get("image") or {}
            out.append({"url": https(f["url"]), "width": d.get("width"), "height": d.get("height"),
                        "bytes": (f.get("details") or {}).get("size"), "title": o.get("title") or "", "name": f.get("fileName")})
        for k, v in o.items():
            if k != "mobile":
                images_in(v, out)
    elif isinstance(o, list):
        for v in o:
            images_in(v, out)


def page_info(html):
    pp = next_data(html)
    p = pp.get("product") or {}
    d = p.get("product_details") or {}
    cms = p.get("cms_data") or {}
    if not d:
        return None
    designer, imgs = None, []
    for e in cms.get("editorialContent") or []:
        data = e.get("data") or {}
        if e.get("type") == "imageWithText" and "designer" in (data.get("internalName") or "").lower():
            t = (((data.get("content") or {}).get("data") or {}).get("title") or {}).get("data", {}).get("content")
            designer = designer or (t or "").strip() or None
        if e.get("type") in ("hero", "gallery", "imageGallery", "images", "imageCarousel"):
            images_in(e, imgs)
    images_in(cms.get("heading") or {}, imgs)
    meas = {}
    for m in d.get("measures") or []:
        for k, v in m.items():
            if k.startswith("misura_") and v:
                meas[k[len("misura_"):]] = v
    seen, pics = set(), []
    for im in imgs:
        if im["url"] not in seen and im.get("width"):
            seen.add(im["url"])
            pics.append(im)
    return {"version": d.get("version"), "family": d.get("family"), "macro": d.get("macrocategory"),
            "text": (d.get("consumer_description") or "").strip() or None, "measures": meas or None,
            "price_eur": (d.get("base_price") or {}).get("amount"), "configurable": d.get("configurable"),
            "downloads": [{"type": x.get("file_type"), "url": x.get("file_url")} for x in d.get("downloads") or [] if x.get("file_url")],
            "designer": designer, "images": pics, "seo_title": (cms.get("SEO") or {}).get("title"),
            "related": next((e["data"].get("skuList") for e in cms.get("editorialContent") or [] if e.get("type") == "relatedProducts"), None)}


def build():
    idx = json.load(open(os.path.join(CACHE, "_index.json"), encoding="utf-8"))
    cards = idx["cards"]
    out = []
    for s, u in sorted(idx["pages"].items()):
        html = get(u)
        if html is None:
            continue
        info = page_info(html)
        if not info:
            continue
        c = cards.get(s) or {}
        out.append({"url": u, "slug": s, "code": (info["version"] or c.get("sku") or "").upper(), "family": info["family"] or c.get("family"),
                    "short": c.get("description"), "category": c.get("category"), "line": c.get("brand"), "new": bool(c.get("isNew")),
                    "packshot": c.get("image"), **{k: v for k, v in info.items() if k not in ("version", "family")}})
    json.dump(out, open(os.path.join(HERE, "calligaris.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"изделий (страниц) {len(out)}, с фото на белом {sum(1 for x in out if x['packshot'])}, "
          f"с интерьерными фото {sum(1 for x in out if x['images'])}, с 2D/3D {sum(1 for x in out if any(d['type'] in ('dwg', 'obj', 'skp') for d in x['downloads']))}")


def sizes():
    """Размеры и вес фото на белом фоне (cloudfront): первые 64 КБ снимка — по ним PIL читает размер."""
    from io import BytesIO
    from PIL import Image
    items = json.load(open(os.path.join(HERE, "calligaris.json"), encoding="utf-8"))
    dst = os.path.join(HERE, "calligaris-sizes.json")
    have = json.load(open(dst, encoding="utf-8")) if os.path.exists(dst) else {}
    urls = sorted({x["packshot"] for x in items if x.get("packshot")} - set(have))
    for i, u in enumerate(urls, 1):
        req = urllib.request.Request(u, headers={"User-Agent": UA, "Range": "bytes=0-65535"})
        wait = 0.5 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                head, ctype = r.read(), r.headers.get("Content-Type", "")
                total = r.headers.get("Content-Range", "").rpartition("/")[2] or r.headers.get("Content-Length")
        except urllib.error.HTTPError as e:
            have[u] = {"error": e.code}
            continue
        try:
            im = Image.open(BytesIO(head))
            have[u] = {"width": im.width, "height": im.height, "format": im.format, "type": ctype,
                       "bytes": int(total) if str(total).isdigit() else None}
        except Exception as e:  # noqa: BLE001
            have[u] = {"error": str(e)[:80], "type": ctype}
        if i % 100 == 0:
            json.dump(have, open(dst, "w"), indent=0)
            print(f"  {i} из {len(urls)}", flush=True)
    json.dump(have, open(dst, "w"), indent=0)
    print(f"размеры фото: {sum(1 for v in have.values() if 'width' in v)} из {len(have)}")


def fname(s):
    """Имя файла в выгрузке: латиница, цифры, «-», «_», «.»; без пробелов."""
    s = re.sub(r"\s+", "-", (s or "").strip())
    return re.sub(r"[^A-Za-z0-9._-]+", "", s) or "foto"


def fslug(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


CF_MAX = 2400            # фото Contentful берём не больше 2400 px по ширине (оригиналы бывают по 25 МБ) — их сервис уменьшает сам


def sources():
    """→ content/shop/sources/calligaris/site.json (страницы изделий) и files.json (адрес → файл в выгрузке, размеры)."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    items = json.load(open(os.path.join(HERE, "calligaris.json"), encoding="utf-8"))
    sz = json.load(open(os.path.join(HERE, "calligaris-sizes.json"), encoding="utf-8"))
    EXT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "MPO": "jpg"}
    files, taken = {}, {}

    def add(url, folder, name, w, h, b):
        if url in files:
            return url
        base, ext = os.path.splitext(name)
        n, k = f"{base}{ext}", 1
        while (folder, n.lower()) in taken:
            k += 1
            n = f"{base}-{k}{ext}"
        taken[(folder, n.lower())] = 1
        files[url] = {"file": f"images/shop/calligaris/{folder}/{n}", "width": w, "height": h, "bytes": b or 0}
        return url

    site = []
    for x in items:
        folder = fslug(x["family"]) or "other"
        pics = []
        ps = x.get("packshot")
        info = sz.get(ps) if ps else None
        if info and info.get("width"):
            pics.append(add(ps, folder, f"{fslug(x['code'])}-{folder}.{EXT.get(info.get('format'), 'jpg')}",
                            info["width"], info["height"], info.get("bytes")))
        for im in x.get("images") or []:
            W, H = im["width"], im["height"]
            ext = "png" if (im.get("name") or "").lower().endswith(".png") else "jpg"
            w = min(W, CF_MAX)
            h = round(H * w / W)
            url = f"{im['url']}?w={w}&q=85" + ("&fm=jpg" if ext == "jpg" else "")
            nm = fname(os.path.splitext(im.get("name") or "foto")[0])[:80] + "." + ext
            pics.append(add(url, folder, nm, w, h, im.get("bytes") if w == W else 0))
        site.append({**{k: v for k, v in x.items() if k not in ("images", "packshot")}, "images": pics})
    dst = os.path.join(root, "content/shop/sources/calligaris")
    os.makedirs(dst, exist_ok=True)
    json.dump(site, open(os.path.join(dst, "site.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"files": files, "sheets": {}}, open(os.path.join(dst, "files.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"страниц изделий {len(site)}, фото {len(files)} → content/shop/sources/calligaris/")


if __name__ == "__main__":
    {"crawl": crawl, "build": build, "sizes": sizes, "sources": sources}[sys.argv[1] if len(sys.argv) > 1 else "crawl"]()
