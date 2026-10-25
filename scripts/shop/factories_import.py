#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Каталоги фабрик (кроме IDL — у неё свой scripts/shop/idl_import.py) из исходников с их сайтов:
content/shop/sources/<фабрика>/{site,files}.json → content/shop/catalog/<фабрика>.json.

   python3 scripts/shop/factories_import.py [фабрика ...]      # без аргументов — все

Товар каталога — страница изделия на сайте фабрики (модель со всеми исполнениями/размерами). У каждого —
наш артикул: DL-<тип><номер> у света, DF-<тип><номер> у мебели (типы и диапазоны номеров по фабрикам — README,
«Артикулы фабрик»). Номера идут по коллекциям (моделям), внутри — по типу. Выданный артикул не меняется:
при повторном запуске товар узнаётся по адресу у фабрики (mfr_key), новым товарам — следующие свободные номера.
Ни фото, ни PDF скрипт не качает — только сводит то, что уже собрано (scripts/shop/factories/README.md)."""
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "content/shop/sources")
OUT = os.path.join(ROOT, "content/shop/catalog")

# тип → (буква артикула, по-русски, по-английски); у света артикул DL-, у мебели DF-
LIGHT = {
    "suspension": ("S", "Подвесной светильник", "suspension lamp"),
    "ceiling": ("C", "Потолочный светильник", "ceiling lamp"),
    "recessed": ("C", "Встраиваемый светильник", "recessed lamp"),
    "track": ("C", "Трековый светильник", "track light"),
    "profile": ("C", "Встраиваемый профиль", "recessed profile"),
    "spot": ("C", "Спот", "spotlight"),
    "wall": ("W", "Бра", "wall lamp"),
    "table_lamp": ("T", "Настольная лампа", "table lamp"),
    "floor": ("F", "Торшер", "floor lamp"),
    "wall_recessed": ("W", "Встраиваемый настенный светильник", "recessed wall light"),
    "inground": ("G", "Встраиваемый в пол светильник", "in-ground light"),
    "bollard": ("G", "Ландшафтный светильник", "bollard light"),
    "pole": ("G", "Светильник для опоры", "pole-top light"),
    "light_part": ("C", "Комплектующие для света", "lighting component"),
}
FURN = {
    "sofa": ("S", "Диван", "sofa"),
    "sofa_bed": ("S", "Диван-кровать", "sofa bed"),
    "armchair": ("A", "Кресло", "armchair"),
    "chaise": ("A", "Кушетка", "chaise longue"),
    "sunbed": ("A", "Шезлонг", "sun lounger"),
    "pouf": ("A", "Пуф", "pouf"),
    "chair": ("C", "Стул", "chair"),
    "stool": ("C", "Табурет", "stool"),
    "bench": ("C", "Скамья", "bench"),
    "table": ("T", "Стол", "table"),
    "desk": ("T", "Письменный стол", "desk"),
    "console": ("T", "Консоль", "console"),
    "coffee_table": ("K", "Журнальный столик", "coffee table"),
    "side_table": ("K", "Приставной столик", "side table"),
    "bedside": ("K", "Прикроватная тумба", "bedside table"),
    "bed": ("B", "Кровать", "bed"),
    "mattress": ("B", "Матрас", "mattress"),
    "headboard": ("B", "Изголовье", "headboard"),
    "storage": ("H", "Система хранения", "storage unit"),
    "bookcase": ("H", "Книжный стеллаж", "bookcase"),
    "sideboard": ("H", "Буфет", "sideboard"),
    "drawers": ("H", "Комод", "chest of drawers"),
    "wardrobe": ("H", "Шкаф", "wardrobe"),
    "boiserie": ("H", "Буазери", "boiserie"),
    "doors": ("H", "Двери", "doors"),
    "bathroom": ("H", "Мебель для ванной", "bathroom furniture"),
    "mirror": ("D", "Зеркало", "mirror"),
    "rug": ("D", "Ковёр", "rug"),
    "screen": ("D", "Ширма", "screen"),
    "cushion": ("D", "Декоративная подушка", "cushion"),
    "throw": ("D", "Плед", "throw"),
    "bedding": ("D", "Постельный текстиль", "bed linen"),
    "vase": ("D", "Ваза", "vase"),
    "tray": ("D", "Поднос", "tray"),
    "candle": ("D", "Подсвечник", "candle holder"),
    "bowl": ("D", "Чаша", "bowl"),
    "basket": ("D", "Корзина", "basket"),
    "clock": ("D", "Часы", "clock"),
    "umbrella": ("D", "Зонт от солнца", "parasol"),
    "valet": ("D", "Вешалка", "valet stand"),
    "trolley": ("K", "Сервировочный столик", "serving trolley"),
    "decor": ("D", "Аксессуар", "accessory"),
    "kitchen": ("E", "Кухня", "kitchen"),
    "kitchen_unit": ("E", "Кухонный модуль", "kitchen unit"),
}
ORDER_L = "SCWTFG"
ORDER_F = "SACTKBHDE"

# слова изделий → тип (по порядку: первое совпадение в коротком тексте — названии, категории, исполнении)
KW = [
    ("sofa_bed", r"sofa[ -]?beds?|divan[oi] lett[oi]"),
    ("suspension", r"suspensions?|pendants?|hanging lamps?|chandeliers?|sospension"),
    ("wall", r"wall (lamps?|lights?)|sconces?|appliques?"),
    ("floor", r"floor lamps?|standing lamps?|piantan"),
    ("table_lamp", r"table lamps?|desk lamps?"),
    ("rug", r"\brugs?\b|carpets?|tappet|\bmats?\b"),
    ("mattress", r"mattress|materass"),
    ("bedding", r"bed runners?|bedspreads?|quilts?|\bsheets?\b|duvets?|pillowcases?|bed linen|set[- ]letto"),
    ("throw", r"\bplaids?\b|\bthrows?\b|blankets?"),
    ("cushion", r"cushions?|pillows?|cuscin"),
    ("umbrella", r"umbrellas?|parasols?|ombrellon"),
    ("valet", r"valet|coat ?stands?|hangers?|appendiabiti"),
    ("trolley", r"trolleys?|serving carts?|carrello"),
    ("vase", r"\bvases?\b|\bvasi?\b"),
    ("tray", r"\btrays?\b|vassoi"),
    ("candle", r"candle|candelabr|candelier"),
    ("bowl", r"\bbowls?\b|centerpieces?|centrepieces?|centrotavola"),
    ("basket", r"baskets?|cestin"),
    ("clock", r"\bclocks?\b|orologi"),
    ("mirror", r"\bmirrors?\b|specchi"),
    ("screen", r"\bscreens?\b|paravent"),
    ("kitchen", r"\bkitchens?\b|cucin"),
    ("wardrobe", r"wardrobes?|walk-in|closets?|armadi"),
    ("bedside", r"bedside|night ?tables?|nightstands?|comodin|\bnotte\b"),
    ("coffee_table", r"coffee tables?|low tables?|tavolin"),
    ("side_table", r"side tables?|small tables?|end tables?"),
    ("console", r"consoles?|consolle"),
    ("desk", r"\bdesks?\b|writing (table|desk)s?|scrittoi|secr[eé]taire|home[- ]office"),
    ("sunbed", r"sunbeds?|sun loungers?|deck chairs?|lettin"),
    ("chaise", r"chaise|dormeuse|daybeds?|day beds?|\bloungers?\b"),
    ("sofa", r"\bsofas?\b|divan|love ?seats?|sectional|\bmodules?\b|settee"),
    ("armchair", r"armchairs?|poltron|berg[eè]re|lounge chairs?|easy chairs?"),
    ("pouf", r"\bpoufs?\b|ottomans?|footstools?"),
    ("stool", r"\bstools?\b|sgabell"),
    ("bench", r"\bbench(es)?\b|panch"),
    ("chair", r"\bchairs?\b|sedi[ae]\b"),
    ("table", r"\btables?\b|tavol[oi]\b"),
    ("headboard", r"headboards?|testat"),
    ("bed", r"\bbeds?\b|lett[oi]\b"),
    ("bookcase", r"bookcases?|bookshel|librer|shelving"),
    ("sideboard", r"sideboards?|credenz|madi[ae]\b|buffet"),
    ("drawers", r"drawer units?|chests? of drawers|cassettier|\bdressers?\b"),
    ("doors", r"\bdoors?\b|\bporte\b"),
    ("boiserie", r"boiserie"),
    ("storage", r"cabinets?|cupboards?|storage|contenitor|wall units?|living systems?|tv units?|single units?|\bshel(f|ves)\b"),
    ("bathroom", r"bathrooms?|\bbagno\b"),
    ("decor", r"objects?|accessor|complement"),
    ("lamp", r"\blamps?\b|lighting|illuminazion|lampad"),
]
KW = [(t, re.compile(p, re.I)) for t, p in KW]


def kw(text):
    for t, p in KW:
        if p.search(text or ""):
            return t
    return None


def majority(names, allowed=None, skip=("decor",)):
    """Тип по исполнениям: самый частый среди найденных (подушки и т. п. не в счёт)."""
    cnt = {}
    for n in names:
        t = kw(re.split(r"[.,;(]", n or "")[0])
        if t and t not in skip and (allowed is None or t in allowed):
            cnt[t] = cnt.get(t, 0) + 1
    return max(cnt, key=lambda t: (cnt[t], -[x for x, _ in KW].index(t))) if cnt else None


def norm(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", norm(s).lower()).strip("-")


def cap(w, short_upper=False):
    if re.search(r"\d", w):                                   # IP44, 7TUBI, '09 — как есть
        return w
    if re.fullmatch(r"[IVX]{2,4}", w.upper()) and w.isupper():   # римские цифры: II, III, IV
        return w
    if short_upper and w.isupper() and len(w) <= 2:            # у Delta Light: M, S, OK, HI — обозначения исполнений
        return w
    if re.fullmatch(r"([A-Za-z]\.){2,}[A-Za-z]?\.?", w):     # сокращения: S.H., A.B.C.
        return w.upper()
    return "-".join(x[:1].upper() + x[1:].lower() if x[:1].isalpha() else x for x in w.split("-"))


def smart_title(s, mixed=False, short_upper=False):
    """КАПС фабрик → «Как в названии»; mixed — в смешанных названиях поправить только слова целиком заглавными."""
    s = re.sub(r"\s+", " ", (s or "").strip())
    if s.isupper() or s.islower():
        return " ".join(cap(w, short_upper) for w in s.split(" "))
    if mixed:
        return " ".join(cap(w, short_upper) if w.isupper() and len(w) > 1 else w for w in s.split(" "))
    return s


LIGHT_SUFFIX = re.compile(r"\s+(PL|PT|AP|SO|TA|PP|FA)$")      # OLEV: plafoniera, piantana, applique, sospensione, tavolo


def model_for_name(model, t=None):
    """Модель для названия: без слов-типа в конце, если они того же вида, что и изделие (Vicino Table → Vicino)."""
    m = (model or "").strip()
    if t in LIGHT:
        m = LIGHT_SUFFIX.sub("", m).strip() or m
    letter = type_info(t)[0] if t else None
    while True:
        w = m.split(" ")
        if len(w) < 2:
            return m
        for n in (2, 1):
            tail = " ".join(w[-n:])
            k = kw(tail) if len(w) > n else None
            if k and re.fullmatch(r"[A-Za-z -]+", tail) and (k == t or (letter and type_info(k)[0] == letter and (k in LIGHT) == (t in LIGHT))):
                m = " ".join(w[:-n])
                break
        else:
            return m


def files_of(f):
    fj = json.load(open(os.path.join(SRC, f, "files.json"), encoding="utf-8"))
    files = {u.replace("|", "%7C"): v for u, v in fj["files"].items()}
    return files, fj["sheets"]


def img(files, url):
    v = files.get((url or "").replace("|", "%7C"))
    if not v or "width" not in v:
        return None
    return {"file": "images/" + v["file"] if not v["file"].startswith("images/") else v["file"],
            "width": v["width"], "height": v["height"], "bytes": v["bytes"], "src": url}


def sheet(files, sheets, url):
    v = files.get((url or "").replace("|", "%7C"))
    if not v or "pages" not in v:
        return None, {}
    return {"file": v["file"], "url": url, "pages": v["pages"], "bytes": v["bytes"]}, sheets.get(v["file"], {})


def drawings_of(info, file):
    return [{"file": d["file"], "width": d["width"], "height": d["height"], "bytes": d["bytes"],
             "source": {"sheet": file, "page": d["page"]}} for d in info.get("drawings") or []]


def strip_names(text, names):
    """Убрать из текста техкарты строки с именем дизайнера / изделия (шапка страницы)."""
    bad = {norm(n).upper() for n in names if n}
    out = [l for l in (text or "").split("\n") if norm(l).strip().upper() not in bad and not any(norm(l).strip().upper() in b for b in bad if len(norm(l).strip()) > 2)]
    return "\n".join(out).strip()


# ---------- фабрики ----------
def olev():
    files, sheets = files_of("olev")
    T = {"suspension": "suspension", "wall": "wall", "floor": "floor", "ceiling": "ceiling", "ceiling_recessed": "recessed",
         "track_48v": "track", "micro_track_48v": "track", "track_230v": "track", "recessed_profile": "profile",
         "table": "table_lamp", "floor_recessed": "inground"}
    out = []
    for p in json.load(open(os.path.join(SRC, "olev/site.json"), encoding="utf-8")):
        types = p.get("types") or []
        t = next((T[x] for x in types if x in T), None) or kw(p["title"]) or kw(p.get("category")) or "suspension"
        if t == "lamp":
            t = "suspension"
        model = smart_title(p["title"])
        sh, drw, tech = [], [], {}
        for d in p.get("datasheets") or []:
            s, info = sheet(files, sheets, d["url"])
            if s:
                sh.append(s)
                drw += drawings_of(info, s["file"])
            for pg in d.get("pages") or []:
                for k_src, k in (("items", "codes"), ("power_w", "power_w"), ("lumen", "lumen"), ("cct", "cct"), ("beam", "beam")):
                    for v in pg.get(k_src) or []:
                        tech.setdefault(k, [])
                        if v not in tech[k]:
                            tech[k].append(v)
                for k in ("supply", "ip", "net_kg"):
                    if pg.get(k) and pg[k] not in tech.setdefault(k, []):
                        tech[k].append(pg[k])
                if pg.get("cri90"):
                    tech["cri"] = ">90"
        text = "\n\n".join((f"{h}\n{x}" if h else x) for h, x in p.get("sections") or [] if x)
        links = {"page": p["url"]}
        for fl in p.get("files") or []:
            k = {"3d": "model_3d", "photometric": "photometric", "assembly": "assembly", "datasheet_us": "datasheet_us"}.get(fl["kind"])
            if k:
                links.setdefault(k, fl["url"])
        codes = [c for c in tech.get("codes") or [] if not re.match(r"^\dA\d|^CN\d", c)]
        out.append({"mfr_key": p["slug"], "model": model, "type": t, "collection": slug(model.split(" ")[0]),
                    "category": p.get("category"), "designer": p.get("designer"), "place": p.get("place") or [],
                    "mfr_code": ", ".join(codes[:6]) + (" …" if len(codes) > 6 else "") if codes else None,
                    "text": {"en": text}, "tech": {k: v for k, v in tech.items() if v and k != "codes"} or None,
                    "versions": [{"code": c} for c in codes],
                    "images": [x for x in (img(files, u) for u in p.get("images") or []) if x],
                    "drawings": drw, "sheets": sh, "links": links})
    return out


def baxter():
    files, sheets = files_of("baxter")
    out = []
    for p in json.load(open(os.path.join(SRC, "baxter/site.json"), encoding="utf-8")):
        cat = p.get("category_slug") or ""
        fam = cat.split("-", 1)[1] if "-" in cat else cat
        names = [v.get("name_en") for v in p.get("versions") or []]
        title_t = kw(p.get("title"))
        if re.search(r"sofas-and-armchairs|divani-e-poltrone", fam):
            found = {majority([n], skip=()) for n in names} - {None}
            t = next((x for x in ("sofa_bed", "sofa", "armchair", "chaise", "sunbed", "pouf", "bench") if x in found), "armchair")
        elif re.search(r"tables|tavoli", fam):
            t = majority(names, {"coffee_table", "side_table", "bedside", "table", "desk", "console"}) or "coffee_table"
        elif re.search(r"chairs|sedie", fam):
            t = majority(names, {"chair", "stool", "bench", "armchair", "sunbed", "chaise"}) or "chair"
        elif re.search(r"beds|letti", fam):
            t = "bed"
        elif re.search(r"lighting|illuminazione", fam):
            t = majority(names, set(LIGHT)) or ("wall" if "wall" in (p.get("title") or "").lower() else "suspension")
        elif re.search(r"carpets|tappeti", fam):
            t = "rug"
        else:                                           # accessories / complementi / прочее
            t = majority(names) or title_t or "decor"
            if t == "lamp":
                t = "suspension"
        model = smart_title(p.get("title") or p.get("model"))
        vers, mats = [], []
        for v in p.get("versions") or []:
            d = {k: float(x) for k, x in (v.get("dims_cm") or {}).items() if x not in (None, "", "0.00")}
            d = {k: (int(x) if x == int(x) else x) for k, x in d.items()}
            vers.append({"code": v.get("code"), "name": {"en": v.get("name_en"), "ru": v.get("name_ru")}, "dims_cm": d or None})
            for m in v.get("materials") or []:
                if m not in mats:
                    mats.append(m)
        sh, drw, tech_en, fin = [], [], "", []
        for u in p.get("tech_sheets") or []:
            s, info = sheet(files, sheets, u)
            if s:
                sh.append(s)
                drw += drawings_of(info, s["file"])
                tech_en = tech_en or info.get("tech_en", "")
                fin += [x for x in info.get("finishes_en") or [] if x not in fin]
        fins = {}
        for m in mats:                                  # «Fabric: Bouclé» → {"Fabric": ["Bouclé"]}
            g, _, n = m.partition(":")
            fins.setdefault(g.strip() if n else "", []).append((n or g).strip())
        if fin:
            fins.setdefault("Finishes", []).extend(x for x in fin if x not in fins.get("Finishes", []))
        links = {"page": p["url"], "page_ru": p.get("url_ru")}
        if p.get("has_2d3d_login"):
            links["files_2d3d"] = p["url"] + "  (2D/3D — после входа на сайте Baxter)"
        if p.get("has_bim_login"):
            links["bim"] = p["url"] + "  (BIM — после входа на сайте Baxter)"
        place = (["indoor"] if p.get("indoor") else []) + (["outdoor"] if p.get("outdoor") else [])
        codes = [v["code"] for v in vers if v.get("code")]
        out.append({"mfr_key": p["slug"], "model": model, "type": t, "collection": slug(p.get("model") or model),
                    "category": fam, "designer": smart_title(p.get("designer")), "place": place, "new": bool(p.get("new")),
                    "mfr_code": ", ".join(codes[:4]) + (" …" if len(codes) > 4 else "") if codes else None,
                    "text": {"en": p.get("text_en"), "ru": p.get("text_ru")}, "tech": {"en": tech_en} if tech_en else None,
                    "finishes": fins or None, "versions": vers,
                    "images": [x for x in (img(files, u) for u in p.get("images") or []) if x],
                    "drawings": drw, "sheets": sh, "links": links})
    return out


def flexform():
    files, sheets = files_of("flexform")
    CAT = {"Armchairs": "armchair", "Coffee and Side tables": "coffee_table", "Stand-alone sofas": "sofa", "Sectional sofas": "sofa",
           "Accessories": "decor", "Dining chairs/Chairs": "chair", "Tables": "table", "Beds/Bed accessories": "bed",
           "Ottomans": "pouf", "Chaise longue/Dormeuse": "chaise", "Bookshelves/Cabinets": "storage", "Daybeds": "chaise",
           "Stools": "stool", "Sofa beds": "sofa_bed"}
    FAMILY = {"coffee_table": {"coffee_table", "side_table", "bedside"}, "bed": {"bed", "bedside", "headboard", "bench"},
              "storage": {"bookcase", "storage", "sideboard", "drawers", "wardrobe"}, "decor": None}
    out = []
    for p in json.load(open(os.path.join(SRC, "flexform/site.json"), encoding="utf-8")):
        parts = p["url"].rstrip("/").split("/")
        key = f"{parts[-1]}-{parts[-2]}" + ("-outdoor" if "/outdoor/" in p["url"] and "outdoor" not in parts[-1] + parts[-2] else "")
        sh, drw, codes = [], [], []
        for u in p.get("datasheets") or []:
            s, info = sheet(files, sheets, u)
            if s:
                sh.append(s)
                drw += drawings_of(info, s["file"])
                codes += info.get("codes") or []
        t = CAT.get(p.get("category"), "decor")
        if t == "decor":
            t = kw(p.get("title")) or t
        if t in FAMILY:                                 # уточнить по названиям исполнений из техкарты
            t = majority([c["name_en"] for c in codes], FAMILY[t]) or t
            if t == "lamp":
                t = "suspension"
        model = smart_title(p.get("title") or p.get("model"))
        links = {"page": p["url"], "page_ru": p.get("url_ru")}
        if p.get("file_2d"):
            links["files_2d"] = p["file_2d"]
        out.append({"mfr_key": key, "model": model, "type": t, "collection": slug(p.get("model") or model),
                    "category": p.get("category"), "category_ru": p.get("category_ru"),
                    "designer": ", ".join(p.get("designers") or []) or None, "year": p.get("year"),
                    "place": ["outdoor"] if p.get("collection") == "Outdoor" else ["indoor"], "new": bool(p.get("new")),
                    "mfr_code": ", ".join(c["code"] for c in codes[:4]) + (" …" if len(codes) > 4 else "") if codes else None,
                    "text": {"en": p.get("text_en"), "ru": p.get("text_ru")},
                    "tech": {"en": p.get("tech_en"), "ru": p.get("tech_ru")} if p.get("tech_en") or p.get("tech_ru") else None,
                    "versions": [{"code": c["code"], "name": {"en": c["name_en"]}} for c in codes],
                    "images": [x for x in (img(files, u) for u in p.get("images") or []) if x],
                    "drawings": drw, "sheets": sh, "links": links})
    return out


def molteni():
    files, sheets = files_of("molteni")
    CAT = {"Armchairs": "armchair", "Coffee tables": "coffee_table", "Sofas": "sofa", "Rugs": "rug", "Chairs and Stools": "chair",
           "Tables and Desks": "table", "Beds and Benches": "bed", "Kitchens": "kitchen", "Single Units": "storage",
           "Wardrobes and Walk-in closets": "wardrobe", "Accessories": "decor", "Objects": "decor", "Drawer Units": "drawers",
           "Living System and Bookshelves": "storage", "Columns": "kitchen", "Wall Units and Systems": "storage",
           "BATHROOM ACCESSORIES": "decor", "Stools": "stool", "Armchairs and Sofas": "armchair", "Tables": "table",
           "Boiserie and Doors": "boiserie", "Special Bases": "kitchen", "BATHROOMS": "bathroom", "Sunbeds": "sunbed",
           "Bookshelves": "bookcase", "Systems": "storage", "Bed Accessories": "decor", "Tables, Desks and Chairs": "table",
           "Benches": "bench", "Consoles": "console", "Doors": "doors"}
    out = []
    for p in json.load(open(os.path.join(SRC, "molteni/site.json"), encoding="utf-8")):
        col = p.get("collection")
        t = kw(p.get("kind_hint")) or kw(p.get("title"))
        if col == "Kitchen" and t not in ("table", "chair", "stool", "bench"):
            t = "kitchen" if p.get("category") == "Kitchens" else "kitchen_unit"
        elif col == "BATHROOMS" and t is None:
            t = "bathroom"
        t = t or CAT.get(p.get("category"), "decor")
        if t == "lamp":
            t = "suspension"
        model = smart_title(p.get("title"))
        sh, drw, tech, fin = [], [], "", []
        for u in p.get("datasheets") or []:
            s, info = sheet(files, sheets, u)
            if s:
                sh.append(s)
                drw += drawings_of(info, s["file"])
                tech = tech or info.get("tech_en", "")
                fin = fin or info.get("finishes_en") or []
        tech = strip_names(tech, (p.get("designers") or []) + [p.get("title")])
        place = ["outdoor"] if col == "Outdoor" or re.search(r"outdoor", p.get("kind_hint") or "", re.I) else ["indoor"]
        out.append({"mfr_key": p["slug"], "model": model, "type": t, "collection": slug(p.get("title")),
                    "category": p.get("category"), "line": col, "designer": ", ".join(p.get("designers") or []) or None,
                    "place": place, "mfr_code": None, "text": {"en": p.get("text_en")},
                    "tech": {"en": tech} if tech else None, "finishes": {"": fin} if fin else None, "versions": [],
                    "images": [x for x in (img(files, u) for u in p.get("images") or []) if x],
                    "drawings": drw, "sheets": sh, "links": {"page": p["url"]}})
    return out


def maxalto():
    files, sheets = files_of("maxalto")
    SUF = {"poltrone": "armchair", "divani": "sofa", "tavolini": "coffee_table", "letti": "bed", "contenitori": "storage",
           "sedie": "chair", "tavoli": "table", "pouf": "pouf", "scrittoi": "desk", "panche": "bench", "consoles": "console",
           "testate": "headboard", "specchi": "mirror", "lampade": "floor", "librerie": "bookcase", "notte": "bedside",
           "paraventi": "screen"}
    out = []
    for p in json.load(open(os.path.join(SRC, "maxalto/site.json"), encoding="utf-8")):
        words = p["slug"].replace("en-", "", 1).split("-")
        t = next((SUF[w] for w in reversed(words) if w in SUF), None) or kw(" ".join(words)) or kw(p.get("category")) or "decor"
        if t == "lamp":
            t = "floor"
        model = smart_title(p.get("title"))
        s, info = sheet(files, sheets, p.get("product_pdf"))
        links = {"page": p["url"]}
        if p.get("dimensions_page"):
            links["files_2d3d"] = p["dimensions_page"] + "  (чертежи в форматах CAD — после входа на сайте Maxalto)"
        out.append({"mfr_key": p["slug"], "model": model, "type": t, "collection": slug(p.get("title")),
                    "category": p.get("category"), "designer": p.get("designer"), "year": p.get("year"), "place": ["indoor"],
                    "mfr_code": None, "text": {"en": p.get("text_en")},
                    "tech": {"en": info.get("tech_en")} if info.get("tech_en") else None, "versions": [],
                    "images": [x for x in (img(files, u) for u in p.get("images") or []) if x],
                    "drawings": drawings_of(info, s["file"]) if s else [], "sheets": [s] if s else [], "links": links})
    return out


def delta():
    """Delta Light: товар — подсемейство (страница с таблицей исполнений: цвет, свет, мощность, размеры)."""
    files, _ = files_of("delta")
    MEDIA = "https://deltalight.com/media/cache/resolve/"
    out = []
    for p in json.load(open(os.path.join(SRC, "delta/site.json"), encoding="utf-8")):
        f = p.get("facets") or {}
        fix, ins = f.get("Fixation"), f.get("Installation")
        props0 = {k: v for x in p.get("variants") or [] for k, v in x.get("props", {}).items()}
        if fix in ("Mains voltage track", "Low voltage systems") or (ins or "").endswith("track mounted"):
            t = "track"
        elif fix == "Pole" or ins == "Pole top":
            t = "pole"
        elif fix == "Table top":
            t = "table_lamp"
        elif fix == "All":
            t = "light_part"
        elif ins == "Suspended":
            t = "suspension"
        elif fix == "Wall":
            t = "wall_recessed" if ins in ("Recessed", "Semi-recessed") else "wall"
        elif fix == "Floor":
            t = "inground" if ins in ("Recessed", "Semi-recessed") else "bollard" if "Height bollard" in props0 or f.get("Location") == "Outdoor" else "floor"
        elif ins in ("Recessed", "Semi-recessed"):
            t = "recessed"
        elif "Height bollard" in props0:
            t = "bollard"
        else:
            t = "ceiling"
        model = smart_title(p.get("subfamily"), mixed=True, short_upper=True)
        cols = p.get("colours") or {}
        allp = [{k: x for k, x in (v.get("props") or {}).items() if k != "Certificates"} for v in p.get("variants") or []]
        keys = {k for pr in allp for k in pr}
        same = {k for k in keys if len({pr.get(k) for pr in allp}) == 1}
        vers, tech = [], {}
        for v, pr in zip(p.get("variants") or [], allp):
            vers.append({"code": v.get("sku"), "colour": cols.get(v.get("colour"), v.get("colour")) if isinstance(cols, dict) else v.get("colour"),
                         "props": {k: x for k, x in pr.items() if k not in same}})
            for k in ("Luminaire power", "Luminaire lm", "CCT", "CRI", "Beam angle", "IP", "Dimming type", "Voltage", "Length",
                      "Cutout size", "Min. recessed depth", "Height", "Width", "Diameter", "Height bollard"):
                if pr.get(k) and pr[k] not in tech.setdefault(k, []):
                    tech[k].append(pr[k])
        common = {k: v for k, v in (p.get("common") or {}).items() if v}
        if allp:
            common.update({k: allp[0][k] for k in sorted(same) if allp[0].get(k)})
        bases = list(dict.fromkeys(v.get("base") for v in p.get("variants") or [] if v.get("base")))
        imgs = [x for x in (img(files, MEDIA + "website_image_w_1600/" + s["resource"]) for s in (p.get("shots") or [])[:1]) if x]
        drw = []
        if p.get("drawing"):
            d = img(files, MEDIA + "website_image_w_640/" + p["drawing"])
            if d:
                drw.append({k: d[k] for k in ("file", "width", "height", "bytes")} | {"source": {"site": d["src"]}})
        place = [x.lower() for x in [f.get("Location")] if x]
        out.append({"mfr_key": p["url"].split("/products/", 1)[-1], "model": model, "type": t,
                    "collection": slug(p.get("family") or model), "category": " / ".join(x for x in (fix, ins) if x) or None,
                    "place": place, "mfr_code": ", ".join(bases[:4]) + (" …" if len(bases) > 4 else "") if bases else None,
                    "text": {"en": p.get("family_desc")} if p.get("family_desc") else None,
                    "tech": {"common": common, **{k: v for k, v in tech.items() if v and k not in same}} or None,
                    "finishes": {"": list(cols.values())} if isinstance(cols, dict) and cols else None,
                    "versions": vers, "images": imgs, "drawings": drw, "sheets": [],
                    "links": {"page": p["url"], "family": p["url"].rsplit("/", 1)[0]}})
    return out


def cm_dims(name):
    """Размеры из названия исполнения Minotti: «Bed 192x246xh102 cm», «CM 98X98 H116», «Sofa 214 cm»,
    «coffee table d100 h40,5», «Ø 150». Ширина × глубина (× высота) → l, w (h); диаметр → d."""
    s = (name or "").lower().replace(",", ".")
    n = r"(\d+(?:\.\d+)?)"
    num = lambda x: int(float(x)) if float(x) == int(float(x)) else float(x)
    out = {}
    m = re.search(n + r"\s*x\s*" + n + r"(?:\s*x\s*h?\s*" + n + r")?", s)
    if m:
        out["l"], out["w"] = num(m.group(1)), num(m.group(2))
        if m.group(3):
            out["h"] = num(m.group(3))
    m = re.search(r"[ø∅]\s*" + n + r"|(?<![a-z])d\s?" + n + r"\b", s)
    if m and "l" not in out:
        out["d"] = num(m.group(1) or m.group(2))
    m = re.search(r"(?<![a-z])h\s?" + n, s)
    if m and "h" not in out:
        out["h"] = num(m.group(1))
    if not out:
        m = re.search(r"\bcm\s*" + n + r"|" + n + r"\s*cm\b", s)
        if m:
            out["l"] = num(m.group(1) or m.group(2))
    return out or None


def minotti():
    """Minotti: товар — страница изделия; исполнения — элементы из «Technical Features» (у каждого свой чертёж
    с размерами в см и дюймах, он и идёт в чертежи), текст техкарты — английская колонка её описания."""
    from urllib.parse import unquote
    files, sheets = files_of("minotti")
    # раздел списка на сайте Minotti → тип; внутри раздела уточняем по названию изделия и его исполнений
    HEAD = {"sofas": "sofa", "armchairs": "armchair", "chaise-longue and daybed": "chaise", "coffee tables": "coffee_table",
            "little armchairs and stools": "chair", "accessories": "decor", "rugs": "rug", "bookcases – sideboards": "storage",
            "tables and writing desks": "table", "tables": "table", "console tables": "console", "beds": "bed",
            "night storage units": "bedside", "bedwear": "bedding", "sunloungers": "sunbed"}
    FAMILY = {"sofa": {"sofa", "sofa_bed"}, "coffee_table": {"coffee_table", "side_table"}, "chair": {"chair", "stool", "bench"},
              "storage": {"bookcase", "sideboard", "storage", "drawers"}, "table": {"table", "desk"},
              "bedside": {"bedside", "drawers"}, "bedding": {"bedding", "throw", "cushion"}, "bed": {"bed", "headboard"},
              "chaise": {"chaise", "sunbed"}, "decor": None}
    Q = r"[\"“”]"
    out = []
    for p in json.load(open(os.path.join(SRC, "minotti/site.json"), encoding="utf-8")):
        vers, drw = [], []
        for v in p.get("versions") or []:
            nm = v.get("name_en") or ""
            if not nm and v.get("drawing"):                       # подписи нет — из имени файла чертежа
                f = unquote(v["drawing"].rsplit("/", 1)[-1].rsplit(".", 1)[0])
                nm = re.sub(r"\s+", " ", re.sub(r"[_-]+", " ", re.sub(r"^\d+_n_", "", f))).strip().capitalize()
            vers.append({"name": {"en": nm}, "dims_cm": cm_dims(nm)})
            d = img(files, v.get("drawing"))
            if d:
                drw.append({k: d[k] for k in ("file", "width", "height", "bytes")} | {"source": {"site": d["src"], "version": nm}})
        heads = p.get("list_heads") or []
        t = next((HEAD[h.lower()] for h in heads if h.lower() in HEAD), None) or "decor"
        title_t = kw(re.sub(Q, " ", p.get("title") or ""))
        fam = FAMILY.get(t, set())
        if t in FAMILY:
            t = (title_t if title_t and (fam is None or title_t in fam) else None) or majority([x["name"]["en"] for x in vers], fam) or t
        if t == "lamp":
            t = "floor" if re.search(r"floor|terra", p.get("title") or "", re.I) else "table_lamp"
        # «Saki "Table"», «Fynn "Stool"» — слово-тип в кавычках: без кавычек, чтобы в названии не было «Стол Saki "Table"»
        model = re.sub(Q + r"([^\"“”]+)" + Q, lambda m: m.group(1) if kw(m.group(1)) and kw(m.group(1)) != "lamp" else m.group(0),
                       smart_title(p.get("title")))
        base = re.sub(r"\s+", " ", re.sub(Q + r"[^\"“”]*" + Q + r"|\boutdoor\b", " ", model, flags=re.I)).strip() or model
        sh, tech = [], ""
        for u in p.get("tech_sheets") or []:
            s, info = sheet(files, sheets, u)
            if s:
                sh.append(s)
                tech = tech or info.get("tech_en", "")
        links = {"page": p["url"]}
        if p.get("has_2d3d_login"):
            links["files_2d3d"] = p["url"] + "  (2D/3D — после входа на сайте Minotti)"
        if p.get("arrangements"):
            links["arrangements"] = p["url"] + f"  (схемы композиций PDF на странице изделия: {len(p['arrangements'])})"
        out.append({"mfr_key": p["slug"], "model": model, "type": t, "collection": slug(model_for_name(base, t)),
                    "category": (heads or [p.get("category")])[0], "designer": ", ".join(p.get("designers") or []) or None,
                    "place": p.get("place") or ["indoor"], "new": bool(p.get("new")), "mfr_code": None,
                    "text": {"en": p.get("text_en")}, "tech": {"en": tech} if tech else None,
                    "versions": [{k: v for k, v in x.items() if v} for x in vers],
                    "images": [x for x in (img(files, u) for u in p.get("images") or []) if x],
                    "drawings": drw, "sheets": sh, "links": links})
    return out


FACT = {
    "olev": {"fn": olev, "kind": "light", "range": (3000, 3399), "name": "OLEV", "site": "https://www.olevlight.com/en/"},
    "delta": {"fn": delta, "kind": "light", "range": (3400, 4699), "name": "Delta Light", "site": "https://deltalight.com/en"},
    "baxter": {"fn": baxter, "kind": "furn", "range": (5000, 5599), "name": "Baxter", "site": "https://www.baxter.it/en/products"},
    "flexform": {"fn": flexform, "kind": "furn", "range": (5600, 6199), "name": "Flexform", "site": "https://www.flexform.it/en/products"},
    "molteni": {"fn": molteni, "kind": "furn", "range": (6200, 6799), "name": "Molteni&C", "site": "https://www.molteni.it/en/eu"},
    "maxalto": {"fn": maxalto, "kind": "furn", "range": (6800, 7099), "name": "Maxalto", "site": "https://www.maxalto.com/en"},
    "minotti": {"fn": minotti, "kind": "furn", "range": (7100, 7899), "name": "Minotti", "site": "https://www.minotti.com/en"},
}


def type_info(t):
    return LIGHT.get(t) or FURN.get(t) or ("D", "Изделие", "item")


def assign_skus(products, old, lo, hi):
    keep = {p["mfr_key"]: p["sku"] for p in old}
    used = {int(re.search(r"(\d+)$", s).group(1)) for s in keep.values()}
    def order(p):
        letter = type_info(p["type"])[0]
        seq = ORDER_L if p["type"] in LIGHT else ORDER_F
        return (p["collection"], seq.index(letter) if letter in seq else 99, p["type"], p["model"].lower(), p["mfr_key"])
    nxt = lo
    for p in sorted(products, key=order):
        if p["mfr_key"] in keep:
            p["sku"] = keep[p["mfr_key"]]
            continue
        while nxt in used:
            nxt += 1
        if nxt > hi:
            sys.exit(f"не хватило номеров {lo}–{hi}")
        used.add(nxt)
        p["sku"] = ("DL-" if p["type"] in LIGHT else "DF-") + type_info(p["type"])[0] + str(nxt)


def build(f):
    cfg = FACT[f]
    items = cfg["fn"]()
    dst = os.path.join(OUT, f"{f}.json")
    old = json.load(open(dst, encoding="utf-8"))["products"] if os.path.exists(dst) else []
    lo, hi = cfg["range"]
    assign_skus(items, old, lo, hi)
    for p in items:
        letter, ru, en = type_info(p["type"])
        base = model_for_name(p["model"], p["type"])
        if kw(base) == p["type"] and re.fullmatch(r"[A-Za-z -]+", base):   # модель и есть тип («Blankets») — с фабрикой
            p["name"] = {"ru": f"{ru} {cfg['name']}", "en": f"{cfg['name']} {base.lower()}"}
        else:
            p["name"] = {"ru": f"{ru} {base}", "en": f"{base} {en}"}
    items.sort(key=lambda p: int(re.search(r"(\d+)$", p["sku"]).group(1)))
    cols = {}
    for p in items:
        c = cols.setdefault(p["collection"], {"name": model_for_name(p["model"], p["type"]), "designer": p.get("designer"), "products": 0, "skus": []})
        c["products"] += 1
        c["skus"].append(p["sku"])
    for c in cols.values():
        n = sorted(int(re.search(r"(\d+)$", s).group(1)) for s in c.pop("skus"))
        c["sku_block"] = f"{n[0]}–{n[-1]}" if n[0] != n[-1] else str(n[0])
    ordered = []
    for p in items:                                     # поля в одном порядке, пустые — не пишем
        q = {"sku": p["sku"]}
        for k in ("name", "model", "type", "collection", "category", "category_ru", "line", "designer", "year", "place", "new",
                  "mfr_key", "mfr_code", "text", "tech", "finishes", "versions", "images", "drawings", "sheets", "links"):
            v = p.get(k)
            if isinstance(v, dict):
                v = {kk: vv for kk, vv in v.items() if vv not in (None, "", [], {})}
            if v not in (None, "", [], {}, False):
                q[k] = v
        ordered.append(q)
    cat = {"manufacturer": f,
           "sources": [{"id": f"{cfg['name']} — сайт", "title": f"{cfg['name']} — страницы изделий на сайте фабрики (тексты, фото, техкарты PDF)",
                        "url": cfg["site"]}],
           "status": "черновик: изделия с сайта фабрики — тексты, фото, чертежи с размерами из техкарт, ссылки на техкарты и файлы 2D/3D. "
                     "Страниц на сайте пока нет.",
           "sku_range": f"{'DL' if cfg['kind'] == 'light' else 'DF'}-…{lo}–{hi}",
           "collections": dict(sorted(cols.items(), key=lambda kv: kv[1]["sku_block"])),
           "products": ordered}
    json.dump(cat, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    by = {}
    for p in ordered:
        by[p["sku"].split("-")[1][0]] = by.get(p["sku"].split("-")[1][0], 0) + 1
    print(f"{f}: товаров {len(ordered)}, коллекций {len(cols)}, по типам {dict(sorted(by.items()))}, "
          f"без фото {sum(1 for p in ordered if not p.get('images'))}, без чертежа {sum(1 for p in ordered if not p.get('drawings'))}, "
          f"без техкарты {sum(1 for p in ordered if not p.get('sheets'))}")


if __name__ == "__main__":
    which = sys.argv[1:] or [f for f, c in FACT.items() if c["fn"] and os.path.exists(os.path.join(SRC, f, "site.json"))]
    for f in which:
        build(f)
