#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сводный каталог DUMSKAYA HOME (dumskaya-home.com): все товары фабрик в одной структуре.

Берёт каталоги фабрик (content/shop/catalog/<фабрика>.json) и структуру каталога (content/shop/taxonomy.json):
раздел → категория → тип изделия, комнаты, «для улицы». Для каждого товара — название и адрес страницы на языках
сайта (en — основной, без префикса; ru, de, fr, es), описательные имена файлов фото и чертежей
(minotti-torii-sofa-01), повторы у фабрики (одно и то же изделие в двух разделах её сайта) — скрыты.

   python3 scripts/shop/catalog_index.py               # проверка и сводка по фабрикам и категориям
   python3 scripts/shop/catalog_index.py --write       # + home/data/catalog.json для сборки сайта (не в git)
   python3 scripts/shop/catalog_index.py --publish minotti   # выложить фабрику: адреса и имена фото её товаров
                                                       # закрепляются (content/home/frozen.json), дата — в publish.json

Адреса и имена фото выложенных фабрик больше не меняются (их знает Google), даже если поменяется название или тип
товара: тогда — редирект. У невыложенных фабрик всё считается заново при каждом запуске.
Свои тексты товаров — content/home/texts/<фабрика>.json ({артикул: {en, ru, de, fr, es}}), правки названий,
скрытие и уточнения — content/home/overrides.json ({артикул: {"variant": {...}, "hide": true, ...}})."""
import datetime
import glob
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TAX = json.load(open(os.path.join(ROOT, "content/shop/taxonomy.json"), encoding="utf-8"))
MFR = json.load(open(os.path.join(ROOT, "content/shop/manufacturers.json"), encoding="utf-8"))
HOME = os.path.join(ROOT, "content/home")
LANGS = TAX["langs"]
MODEL_FIRST = {"en", "de"}          # «Torii sofa», «Torii Sofa»; по-русски, по-французски, по-испански — «Диван Torii»


def jload(path, default):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


PUBLISH = jload(os.path.join(HOME, "publish.json"), {"factories": {}})
FROZEN = jload(os.path.join(HOME, "frozen.json"), {})
OVR = jload(os.path.join(HOME, "overrides.json"), {})
# подписи исполнений, чертежей и групп отделок, оставшиеся у фабрики по-итальянски или с опечатками: {«как у фабрики»: «как на сайте»}
RENAME = {k: v for k, v in (OVR.get("_rename") or {}).items() if not k.startswith("_")}


def rename(s):
    if not s or not RENAME:
        return s
    for a, b in RENAME.items():
        s = s.replace(a, b)
    return s

TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    "a b v g d e e zh z i y k l m n o p r s t u f h c ch sh shch _ y _ e yu ya".split()))


def slug(s, n=60):
    s = "".join(TRANSLIT.get(ch, ch) for ch in s.lower().replace("&", " and ").replace("+", " plus ").replace("ø", "o").replace("ß", "ss"))
    s = s.replace("_", "")                                   # ъ, ь
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.replace("-", " ")).strip("-")
    return s[:n].rstrip("-")


# тип → категория, категория → раздел
CAT_OF = {t: c for c, v in TAX["categories"].items() for t in v["types"]}
DEPT_OF = {c: d["id"] for d in TAX["departments"] for c in d["categories"]}
TYPE_WORDS = sorted({w for t in TAX["types"].values() for w in (t["en"], t["en"] + "s", t["en"] + "es")} |
                    {"lamp", "lamps", "light", "lights", "storage unit", "suspension lamp", "boiserie"}, key=len, reverse=True)
TAIL = re.compile(r"\s+(?:" + "|".join(map(re.escape, TYPE_WORDS)) + r")$", re.I)
# слова адреса у фабрики, которые не отличают изделия (разделы её сайта, языки, «open air»)
NOISE = set("""and e di the of open air openair outdoor indoor sofas armchairs tables coffee chairs sedie divani poltrone
tavoli tavolini letti beds carpets tappeti complementi accessories lighting illuminazione stand alone sectional sofa armchair
table chair bed rug rugs side lamp lamps light lights wall unit units night day systems system collection products product
new news en it ru""".split())


BRAND_SLUG = {"molteni": "molteni"}                   # Molteni&C → /molteni (а не molteni-and-c)

# уточнения к названию на языках сайта: {m} — модель
QUAL = {
    "sectional": {"en": "{m} sectional sofa", "ru": "Модульный диван {m}", "de": "{m} Modulsofa",
                  "fr": "Canapé modulable {m}", "es": "Sofá modular {m}"},
    "office": {"en": "{m} office chair", "ru": "Офисное кресло {m}", "de": "{m} Bürostuhl",
               "fr": "Chaise de bureau {m}", "es": "Silla de oficina {m}"},
    "vanity": {"en": "{m} vanity table", "ru": "Туалетный столик {m}", "de": "{m} Schminktisch",
               "fr": "Coiffeuse {m}", "es": "Tocador {m}"},
    "display": {"en": "{m} display cabinet", "ru": "Витрина {m}", "de": "{m} Vitrine",
                "fr": "Vitrine {m}", "es": "Vitrina {m}"},
    "fire_pit": {"en": "{m} fire pit", "ru": "Уличный очаг {m}", "de": "{m} Feuerstelle",
                 "fr": "Brasero {m}", "es": "Brasero {m}"},
    "dessert": {"en": "{m} dessert stand", "ru": "Подставка для десертов {m}", "de": "{m} Etagere",
                "fr": "Présentoir à desserts {m}", "es": "Soporte para postres {m}"},
    "walkin": {"en": "{m} walk-in closet", "ru": "Гардеробная {m}", "de": "{m} begehbarer Kleiderkasten",
               "fr": "Dressing {m}", "es": "Vestidor {m}"},
    "lantern": {"en": "{m} outdoor lantern", "ru": "Уличный фонарь {m}", "de": "{m} Outdoor-Laterne",
                "fr": "Lanterne d’extérieur {m}", "es": "Farol de exterior {m}"},
}


def clean_model(model, typ):
    m = re.sub(r"[\"“”«»]", "", model or "").replace("’", "'")
    m = re.sub(r"\s+", " ", m).strip()
    m2 = TAIL.sub("", m).strip()
    return m2 or m


DES = TAX.get("designers", {})


def designer_of(name):
    """Имя дизайнера как на сайте; бюро фабрики («Design center», «R&D Poliform») — без имени."""
    n = re.sub(r"\s+", " ", (name or "").strip())
    n = DES.get("aliases", {}).get(n, n)
    return "" if n in DES.get("in_house", []) else n


def type_name(typ, lang):
    return TAX["types"][typ][lang]


def product_name(model, typ, lang):
    t = type_name(typ, lang)
    if lang == "en":
        return f"{model} {t}"
    return f"{model} {t}" if lang in MODEL_FIRST else f"{t} {model}"


def place_of(it, factory):
    pl = it.get("place") or []
    if "outdoor" in pl and "indoor" not in pl:
        return "outdoor"
    if "outdoor" in pl:
        return "both"
    return "indoor"


def images_of(it, factory, cols):
    """Фото товара: [{src, w, h}] — файлы выгрузки (images/shop/<фабрика>/…). Без чертежей."""
    out = []
    for im in it.get("images") or []:
        if im.get("file") and im.get("width"):
            out.append({"src": im["file"], "w": im["width"], "h": im["height"]})
    if not out and factory == "idl":                      # у IDL фото бывает только у коллекции
        col = cols.get(it["collection"], {})
        code = it.get("mfr_code")
        for im in col.get("images") or []:
            if code in (im.get("products") or []) and im.get("width"):
                out.append({"src": im["file"], "w": im["width"], "h": im["height"]})
    return out


def drawings_of(it):
    out = []
    for d in it.get("drawings") or []:
        if d.get("file") and d.get("width"):
            src = d.get("source") or {}
            out.append({"src": d["file"], "w": d["width"], "h": d["height"],
                        "title": d.get("title") or src.get("version") or src.get("title") or ""})
    dr = (it.get("tech") or {}).get("drawing") if isinstance(it.get("tech"), dict) else None
    if isinstance(dr, dict) and dr.get("file"):
        out.append({"src": dr["file"], "w": dr["width"], "h": dr["height"], "title": ""})
    return out


def variant_words(it, model, typ):
    """Чем изделие отличается от другого с тем же названием и типом: слова адреса у фабрики, которых нет в названии."""
    have = set(slug(model).split("-")) | set(slug(TAX["types"][typ]["en"]).split("-"))
    words = [w for w in re.split(r"[-_]+", (it.get("mfr_key") or "").lower().split("/")[-1])
             if w and w not in have and w not in NOISE and not w.isdigit()]
    return " ".join(dict.fromkeys(words))


def build():
    products, problems = [], []
    for factory, mf in MFR.items():
        path = os.path.join(ROOT, mf["catalog"])
        if not os.path.exists(path):
            continue
        cat = json.load(open(path, encoding="utf-8"))
        cols = cat.get("collections") or {}
        brand = mf["name"]
        bslug = BRAND_SLUG.get(factory) or slug(brand)
        fix = TAX.get("fix_type", {}).get(factory, {})
        texts = jload(os.path.join(HOME, "texts", f"{factory}.json"), {})
        for it in cat["products"]:
            typ = fix.get(it["type"], it["type"])
            if typ not in TAX["types"] or typ not in CAT_OF:
                problems.append(f"{it['sku']}: тип «{typ}» не входит в структуру каталога (taxonomy.json)")
                continue
            col = cols.get(it.get("collection"), {})
            model = it.get("model") or f"{col.get('name', it.get('collection', ''))} {it.get('mfr_code', '')}".strip()
            p = {"sku": it["sku"], "factory": factory, "brand": brand, "brand_slug": bslug,
                 "type": typ, "category": CAT_OF[typ], "department": DEPT_OF[CAT_OF[typ]],
                 "place": place_of(it, factory), "model": clean_model(model, typ),
                 "collection": it.get("collection"), "collection_name": col.get("name") or "",
                 "designer": designer_of(it.get("designer") or col.get("designer")),
                 "year": it.get("year") or "", "new": bool(it.get("new")),
                 "mfr_code": it.get("mfr_code") or "", "mfr_key": it.get("mfr_key") or "",
                 "mfr_url": (it.get("links") or {}).get("page") or col.get("mfr_url") or "",
                 "images": images_of(it, factory, cols), "drawings": drawings_of(it),
                 "text": texts.get(it["sku"]) or {},
                 "_src": it}
            rooms = list(TAX["categories"][p["category"]]["rooms"])
            if p["place"] in ("outdoor", "both") and "outdoor" not in rooms:
                rooms.append("outdoor")
            if p["place"] == "outdoor":
                rooms = [r for r in rooms if r == "outdoor"] or ["outdoor"]
            p["rooms"] = rooms
            products.append(p)
    # повторы: одинаковые название и тип у одной фабрики
    groups = defaultdict(list)
    for p in products:
        groups[(p["factory"], p["model"].lower(), p["type"])].append(p)
    dups = []
    for key, g in groups.items():
        if len(g) < 2:
            continue
        seen = []
        for p in g:
            sig = (tuple(sorted(i["src"].rsplit("/", 1)[-1].lower() for i in p["images"])),
                   (p["_src"].get("text") or {}).get("en", "")[:200])
            twin = next((q for q, s in seen if s == sig or (sig[0] and s[0] == sig[0])), None)
            if twin:
                p["duplicate_of"] = twin["sku"]
                dups.append((p["sku"], twin["sku"]))
            else:
                seen.append((p, sig))
        rest = [p for p in g if not p.get("duplicate_of")]
        if len(rest) < 2:
            continue
        places = {p["place"] for p in rest}
        for p in rest:
            key = (p["mfr_key"] or "").lower()
            v = ""
            if p["factory"] == "baxter" and re.search(r"open-?air", key):
                p["model"] = re.sub(r"\s+Outdoor$", "", p["model"])
                v = "Open Air"
            elif "sectional" in key:
                p["qual"] = "sectional"
            elif "stand-alone" in key:
                v = ""
            elif ("outdoor" in key or (len(places) > 1 and p["place"] == "outdoor")) and "outdoor" not in p["model"].lower():
                v = "Outdoor"
            elif len(places) == 1 or p["place"] != "indoor":
                v = variant_words(p["_src"], p["model"], p["type"]).title()
            p["variant"] = v
    # правки вручную
    for p in products:
        o = OVR.get(p["sku"]) or {}
        if "variant" in o:
            p["variant"] = o["variant"]
            p.pop("variant_unresolved", None)
        if o.get("hide"):
            p["hidden"] = o["hide"]
        if o.get("duplicate_of"):
            p["duplicate_of"] = o["duplicate_of"]
        for k in ("model", "type", "designer", "place", "qual", "name", "collection", "collection_name"):
            if k in o:
                p[k] = o[k]
        if "type" in o:
            p["category"] = CAT_OF[p["type"]]
            p["department"] = DEPT_OF[p["category"]]
            rooms = list(TAX["categories"][p["category"]]["rooms"])
            if p["place"] in ("outdoor", "both") and "outdoor" not in rooms:
                rooms.append("outdoor")
            if p["place"] == "outdoor":
                rooms = [r for r in rooms if r == "outdoor"] or ["outdoor"]
            p["rooms"] = rooms
        if o.get("images_keep"):                        # у фабрики в галерее чужие снимки — оставляем только свои
            p["images"] = [i for i in p["images"] if o["images_keep"].lower() in i["src"].lower()]
        if "versions_keep" in o:                        # у фабрики на странице изделия исполнения всей коллекции
            rx = re.compile(o["versions_keep"])
            p["_src"] = {**p["_src"], "versions": [v for v in p["_src"].get("versions") or []
                                                   if rx.search(v["name"]["en"] if isinstance(v.get("name"), dict) else str(v.get("name")))]}
        if o.get("no_drawings"):                        # чертежи от другого изделия
            p["drawings"] = []
        for d in p["drawings"]:
            d["title"] = rename(d["title"])
        if not p["images"] and not p.get("hidden"):
            p["hidden"] = "нет фото"
    # названия, адреса, имена фото (одно фото у двух товаров фабрики — один файл на сайте, имя по первому товару)
    used, named = defaultdict(set), {}
    users = defaultdict(set)                       # фото → товары, где оно есть (общие снимки коллекции)
    for p in products:
        for im in p["images"]:
            users[im["src"]].add(p["sku"])
    col_n = Counter()
    for p in sorted(products, key=lambda p: p["sku"]):
        full = (p["model"] + (" " + p["variant"] if p.get("variant") else "")).strip()
        p["full_model"] = full
        if isinstance(p.get("name"), dict):
            pass
        elif p.get("qual"):
            p["name"] = {l: QUAL[p["qual"]][l].format(m=full) for l in LANGS}
        else:
            p["name"] = {l: product_name(full, p["type"], l) for l in LANGS}
        fr = FROZEN.get(p["sku"])
        if fr:
            p["path"] = fr["path"]
        else:
            p["path"] = {}
            for l in LANGS:
                base = slug(p["name"][l], 70)
                s, i = base, 2
                while s in used[(l, p["brand_slug"])]:
                    s, i = f"{base}-{i}", i + 1
                p["path"][l] = ("" if l == "en" else f"/{l}") + f"/{p['brand_slug']}/{s}"
        for l in LANGS:
            used[(l, p["brand_slug"])].add(p["path"][l].rsplit("/", 1)[-1])
        stem = f"{p['brand_slug']}-{p['path']['en'].rsplit('/', 1)[-1]}"[:72].rstrip("-")
        for kind, lst, suffix in (("images", p["images"], ""), ("drawings", p["drawings"], "-dimensions")):
            names = (fr or {}).get(kind) or {}
            n = 0
            for im in lst:
                if im["src"] in names:
                    im["name"] = names[im["src"]]
                elif im["src"] in named:
                    im["name"] = named[im["src"]]
                elif kind == "images" and len(users[im["src"]]) > 1:      # общий снимок — имя по коллекции
                    cs = f"{p['brand_slug']}-{slug(p['collection_name'] or p['collection'] or p['model'], 50)}"
                    col_n[cs] += 1
                    im["name"] = f"{cs}-{col_n[cs]:02d}"
                else:
                    n += 1
                    im["name"] = f"{stem}{suffix}-{n:02d}"
                named.setdefault(im["src"], im["name"])
    live = [p for p in products if not p.get("duplicate_of") and not p.get("hidden")]
    same = Counter((p["factory"], p["name"]["en"].lower()) for p in live)
    for p in live:
        if same[(p["factory"], p["name"]["en"].lower())] > 1:
            p["variant_unresolved"] = True
    for p in products:
        p["published"] = p["factory"] in PUBLISH["factories"] and not p.get("hidden") and not p.get("duplicate_of")
    return products, problems, dups


def check(products):
    """Адреса не пересекаются: товары между собой, с категориями, разделами и страницами брендов."""
    errs = []
    taken = {}
    for l in LANGS:
        pre = "" if l == "en" else f"/{l}"
        for d in TAX["departments"]:
            taken[pre + "/" + d["slug"][l]] = f"раздел {d['id']}"
        for c, v in TAX["categories"].items():
            taken.setdefault(pre + "/" + v["slug"][l], f"категория {c}")
        taken[pre + "/" + TAX["outdoor"]["slug"][l]] = "для улицы"
        for b in {p["brand_slug"] for p in products}:
            if pre + "/" + b in taken:
                errs.append(f"адрес бренда {pre}/{b} совпадает с: {taken[pre + '/' + b]}")
            taken[pre + "/" + b] = f"бренд {b}"
    for p in products:
        if p.get("duplicate_of") or p.get("hidden"):
            continue
        for l, u in p["path"].items():
            if u in taken:
                errs.append(f"{p['sku']}: адрес {u} уже занят ({taken[u]})")
            taken[u] = p["sku"]
    names = defaultdict(set)
    for p in products:
        for im in p["images"] + p["drawings"]:
            names[im["name"]].add(im["src"])
    errs += [f"имя фото у разных файлов: {n} ({', '.join(sorted(v))})" for n, v in names.items() if len(v) > 1]
    return errs


def summary(products, problems, dups, errs):
    live = [p for p in products if not p.get("duplicate_of") and not p.get("hidden")]
    hid = Counter(str(p["hidden"]) for p in products if p.get("hidden") and not p.get("duplicate_of"))
    print(f"товаров в каталогах: {len(products)}, на сайт (без повторов и скрытых): {len(live)}, повторов скрыто: "
          f"{sum(1 for p in products if p.get('duplicate_of'))}, не показываем: " + ", ".join(f"{k} — {v}" for k, v in hid.items()))
    by_f = Counter(p["factory"] for p in live)
    print("по фабрикам:", ", ".join(f"{MFR[f]['name']} {n}" for f, n in by_f.most_common()))
    for d in TAX["departments"]:
        cnt = Counter(p["category"] for p in live if p["department"] == d["id"])
        print(f"\n{d['name']['ru']} ({sum(cnt.values())})")
        for c in d["categories"]:
            byf = Counter(p["factory"] for p in live if p["category"] == c)
            print(f"  {TAX['categories'][c]['name']['ru']}: {cnt[c]}  — " + ", ".join(f"{MFR[f]['name']} {n}" for f, n in byf.most_common()))
    out = [p for p in live if p["place"] in ("outdoor", "both")]
    print(f"\nДля улицы: {len(out)}")
    print(f"без фото: {sum(1 for p in live if not p['images'])}, без чертежей: {sum(1 for p in live if not p['drawings'])}, "
          f"с дизайнером: {sum(1 for p in live if p['designer'])}, новинки: {sum(1 for p in live if p['new'])}, "
          f"свой текст: {sum(1 for p in live if p['text'])}")
    unres = [p for p in live if p.get("variant_unresolved")]
    if unres:
        print(f"\nодинаковые названия — уточнить в content/home/overrides.json ({len(unres)}):")
        for p in unres:
            print(f"  {p['sku']} {p['name']['en']}  ← {p['mfr_key']}  {p['mfr_url']}")
    for e in problems + errs:
        print("  ✗", e)


WORDS = {"Ткани": "Fabrics", "Кожа": "Leather"}
FIX_WORDS = re.compile("|".join(WORDS))


def export(products, out_path, only_published):
    only = {f for f in os.environ.get("HOME_FACTORIES", "").split(",") if f}       # просмотр: только эти фабрики
    keep = [p for p in products if not p.get("duplicate_of") and not p.get("hidden") and (p["published"] or not only_published)
            and (not only or p["factory"] in only)]
    slim = []
    for p in keep:
        it = p["_src"]
        q = {k: v for k, v in p.items() if not k.startswith("_") and k not in ("variant_unresolved",)}
        q["facts"] = {k: it[k] for k in ("tech", "versions", "finishes") if it.get(k)}
        if q["facts"].get("finishes"):                 # у Poliform в английских группах отделок бывает «Ткани»
            q["facts"]["finishes"] = {rename(FIX_WORDS.sub(lambda m: WORDS[m.group(0)], k)): v for k, v in q["facts"]["finishes"].items()}
        if q["facts"].get("versions") and RENAME:
            q["facts"]["versions"] = [{**v, "name": {l: rename(n) for l, n in v["name"].items()}} if isinstance(v.get("name"), dict) else v
                                      for v in q["facts"]["versions"]]
        q["source_text"] = it.get("text") or {}
        slim.append(q)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump({"generated": datetime.datetime.now().isoformat(timespec="seconds"), "taxonomy": TAX,
               "brands": {f: {"name": MFR[f]["name"], "slug": BRAND_SLUG.get(f) or slug(MFR[f]["name"]), "country": MFR[f]["country"],
                              "site": MFR[f]["site"], "legal": MFR[f].get("legal", ""), "published": PUBLISH["factories"].get(f), "ru": TAX.get("brands_ru", {}).get(f, "")}
                          for f in {p["factory"] for p in products}},
               "products": slim}, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"→ {os.path.relpath(out_path, ROOT)}: товаров {len(slim)}")


def publish(products, factory):
    if factory not in MFR:
        sys.exit(f"нет фабрики {factory}")
    for p in products:
        if p["factory"] != factory or p.get("duplicate_of") or p.get("hidden"):
            continue
        if p.get("variant_unresolved"):
            sys.exit(f"{p['sku']}: одинаковое название с другим товаром — сначала уточнить в overrides.json")
        FROZEN[p["sku"]] = {"path": p["path"], "images": {i["src"]: i["name"] for i in p["images"]},
                            "drawings": {i["src"]: i["name"] for i in p["drawings"]}}
    PUBLISH["factories"].setdefault(factory, {"since": datetime.date.today().isoformat()})
    os.makedirs(HOME, exist_ok=True)
    json.dump(dict(sorted(FROZEN.items())), open(os.path.join(HOME, "frozen.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    json.dump(PUBLISH, open(os.path.join(HOME, "publish.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{MFR[factory]['name']}: адреса и имена фото закреплены, выложена с {PUBLISH['factories'][factory]['since']}")


if __name__ == "__main__":
    prods, probs, dups = build()
    errs = check(prods)
    if "--publish" in sys.argv:
        publish(prods, sys.argv[sys.argv.index("--publish") + 1])
    elif "--write" in sys.argv:
        export(prods, os.path.join(ROOT, "home/data/catalog.json"), only_published=os.environ.get("HOME_ALL") != "1")
    if "--quiet" not in sys.argv:
        summary(prods, probs, dups, errs)
    sys.exit(1 if probs or errs else 0)
