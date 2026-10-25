#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Список товаров магазина для бота заявок: deploy/shop-products.json (артикул → название, страница, партнёр).

Кнопка «Узнать цену» на товаре передаёт в форму артикул (TDD-001 и т. п.). По этому списку бот на сервере
понимает, чей товар: если у товара указан партнёр (поле "partner": <номер партнёра из бота> в
content/pages/ru/shop/<товар>.json), заявка уходит людям этого партнёра, а разработчику и дизайнеру —
уведомление. Без поля "partner" товар студии — заявка как обычно.
Товары партнёрских фабрик из content/shop/catalog/<фабрика>.json (ещё до выкладки их страниц) тоже попадают
в список: партнёр — название компании из content/shop/manufacturers.json, плюс подсказка для студии и партнёра —
изготовитель, его артикул и коллекция, а для дизайнера — где у фабрики скачать 2D/3D модели изделия
(«models»: сами файлы не качаем; клиент этого не видит).
Запускается при выкладке (scripts/deploy.sh); файл не хранится в git.
   python3 scripts/build_shop.py"""
import glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out, errs = {}, []
for f in sorted(glob.glob(os.path.join(ROOT, "content/pages/ru/shop/*.json"))):
    p = json.load(open(f, encoding="utf-8"))
    m = re.search(r"\((TDD-[\w-]+|[A-Z]{2,5}-[A-Z]?\d+)\)", p.get("title", ""))
    if not m:
        continue
    code = m.group(1).upper()
    name = re.sub(r"\s*\|\s*DUMSKAYA DESIGN\s*$", "", p["title"])
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name)
    partner = p.get("partner")
    if partner is not None and not str(partner).isdigit():
        errs.append(f"{p['path']}: partner должен быть номером партнёра из бота, сейчас {partner!r}")
    if code in out:
        errs.append(f"артикул {code} повторяется: {out[code]['path']} и {p['path']}")
    out[code] = {"name": name, "path": p["path"], "partner": int(partner) if str(partner or "").isdigit() else None}
# каталоги фабрик (content/shop/manufacturers.json): партнёрских и тех, за кем партнёр пока не закреплён
TYPE_RU = {"suspension": "Подвесной светильник", "ceiling": "Потолочный светильник", "wall": "Бра",
           "table": "Настольная лампа", "floor": "Торшер", "spot": "Спот"}
def catalog_ref(it, sources):
    """Где товар в каталоге фабрики: {catalog, url, pages: [[страница PDF, номер в каталоге, что на ней]]}.
    Номера в каталоге — как напечатаны (у разворотов Novelties 2025 — «22–23»), ссылка ведёт на страницу PDF."""
    src = sources.get(it.get("catalog"))
    if not src:
        return None
    tech = (it.get("tech") or {}).get("source", {}).get("page")
    nums = sorted(set(it.get("catalog_pages") or []) | ({tech} if tech else set()))
    label = (lambda n: f"{2 * n - 2}–{2 * n - 1}") if src.get("spreads") else str
    index = set(src.get("index_pages") or [])
    pages = [[n, label(n), "чертёж и свет" if n == tech else "указатель" if n in index else "фото"] for n in nums]
    return {"catalog": src["id"], "url": src.get("url"), "pages": pages}


def sheet_ref(it, mf):
    """Техкарта изделия (PDF у фабрики): ссылка и страницы с чертежами — для фабрик, где товар = страница изделия."""
    sh = (it.get("sheets") or [None])[0]
    if not sh or not sh.get("url"):
        return None
    pages = sorted({d["source"]["page"] for d in it.get("drawings") or [] if d.get("source", {}).get("sheet") == sh["file"]})
    return {"label": "Техкарта", "catalog": mf["name"], "url": sh["url"],
            "pages": [[n, str(n), "чертёж"] for n in pages] or [[1, "1", None]]}


FMT = re.compile(r"\b(DWG|DXF|3DM|FBX|MAX|SKP|OBJ|3DS|RFA|IFC|STEP|STP|PDF)\b", re.I)


def models_ref(it):
    """2D/3D модели изделия. Сами файлы в базу не качаем — дизайнеру подсказка: что есть, где скачать и нужен ли вход.
    [{"what": "2D/3D", "formats": ["DWG", "SKP"], "url": страница или файл у фабрики, "how": как получить}]"""
    links, out = it.get("links") or {}, []
    gated = list(dict.fromkeys(m.upper() for f in it.get("files_after_login") or [] for m in FMT.findall(f.get("title") or "")))
    for key, what in (("files_2d3d", "2D/3D"), ("bim", "BIM"), ("files_2d", "2D"), ("model_3d", "3D")):
        v = links.get(key)
        if not v:
            continue
        url, _, note = v.partition("  (")
        if "после формы" in note:
            how = "один раз заполнить форму на сайте фабрики"
        elif "после входа" in note:
            how = "нужен вход на сайте фабрики"
        else:
            how = "скачивается сразу"
        ext = re.search(r"\.([a-z0-9]{2,4})$", url, re.I)
        formats = gated if key == "files_2d3d" else [ext.group(1).upper()] if ext and ext.group(1).lower() != "html" else []
        out.append({"what": what, "formats": formats, "url": url.strip(), "how": how})
    return out


mfrs = json.load(open(os.path.join(ROOT, "content/shop/manufacturers.json"), encoding="utf-8"))
# товары, уже выложенные на dumskaya-home.com: их страница — там (адреса закреплены при выкладке фабрики)
_home = os.path.join(ROOT, "content/home")
_pub = json.load(open(os.path.join(_home, "publish.json"), encoding="utf-8")).get("factories", {}) if os.path.exists(os.path.join(_home, "publish.json")) else {}
_frozen = json.load(open(os.path.join(_home, "frozen.json"), encoding="utf-8")) if os.path.exists(os.path.join(_home, "frozen.json")) else {}
for key, mf in mfrs.items():
    if not os.path.exists(os.path.join(ROOT, mf["catalog"])):
        print(f"  · {mf['name']}: каталога {mf['catalog']} ещё нет — пропуск")
        continue
    cat = json.load(open(os.path.join(ROOT, mf["catalog"]), encoding="utf-8"))
    cols = cat["collections"]
    sources = {s["id"]: s for s in cat.get("sources", []) if s.get("id")}
    for it in cat["products"]:
        code = it["sku"].upper()
        if code in out:
            errs.append(f"артикул {code} повторяется: {out[code].get('path') or 'каталог'} и каталог {key}")
            continue
        col = cols.get(it["collection"], {}).get("name", it["collection"])
        name = (it.get("name") or {}).get("ru") or f"{TYPE_RU.get(it['type'], 'Светильник')} {col}"
        home = _frozen.get(it["sku"]) if key in _pub else None
        out[code] = {"name": name, "path": ("https://dumskaya-home.com" + home["path"]["en"]) if home else it.get("path"), "partner": mf.get("partner"),
                     "mfr": f"{mf['name']} ({mf['country']})", "mfr_code": it.get("mfr_code"), "collection": col}
        if (it.get("links") or {}).get("page"):
            out[code]["mfr_url"] = it["links"]["page"]
        ref = catalog_ref(it, sources) or sheet_ref(it, mf)
        if ref:
            out[code]["catalog"] = ref
        models = models_ref(it)
        if models:
            out[code]["models"] = models
dst = os.path.join(ROOT, "deploy", "shop-products.json")
json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
own = sum(1 for v in out.values() if v["partner"])
print(f"товары для бота: {len(out)} (партнёрских: {own})")
for e in errs:
    print("  ✗", e)
sys.exit(1 if errs else 0)
