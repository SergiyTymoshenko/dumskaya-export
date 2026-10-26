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
    "partition": ("H", "Перегородка", "partition system"),
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


def poliform():
    """Poliform: товар — страница изделия (EN + RU). Исполнения — подписи чертежей из вкладки DIMENSIONS (у Poliform
    размеры нарисованы на чертежах SVG, числами в тексте их нет); материалы — пары «Structure: …»; отделки с кодами.
    Файлы 2D/3D у Poliform — после формы подписки: не скачаны, их список (формат, размер, адрес) — в files_after_login."""
    files, _ = files_of("poliform")
    out = []
    for p in json.load(open(os.path.join(SRC, "poliform/site.json"), encoding="utf-8")):
        props = p.get("props") or {}
        kind = props.get("Type") or props.get("Typology") or ""
        CAT = {"day systems": "storage", "night systems": "wardrobe"}
        t = kw(kind)
        if t in (None, "decor", "lamp"):
            t = (CAT.get((p.get("category") or "").lower()) or kw(p.get("category")) or kw(p["slug"].replace("-", " "))
                 or kw(p.get("title")) or kw(p.get("collection_line")) or t or "decor")
        if t == "lamp":                                   # какой именно светильник — по типу, названию и тексту
            about = " ".join(x for x in (kind, p.get("title"), (p.get("text_en") or "")[:400]) if x)
            t = next((x for x, _ in KW if x in LIGHT and kw(about) == x), None) or \
                ("floor" if re.search(r"floor|standing", about, re.I) else "table_lamp")
        model = smart_title(p.get("title"), mixed=True)
        vers, drw = [], []
        for v in p.get("dimensions") or []:
            nm = " — ".join(x for x in (v.get("section"), v.get("group"), v.get("title")) if x)
            if nm and nm not in [x["name"]["en"] for x in vers]:
                vers.append({"name": {"en": nm}})
            d = img(files, v.get("drawing"))
            if d:
                drw.append({k: d[k] for k in ("file", "width", "height", "bytes")} | {"source": {"site": d["src"], "version": nm or None}})
        tech = "\n".join(f"{k}: {v}" for k, v in props.items())
        gated = [{"title": f.get("title"), "size": f.get("size"), "url": f.get("url")} for f in p.get("files_2d3d_form") or []]
        links = {"page": p["url"], "page_ru": p.get("url_ru") or None}
        if gated:
            links["files_2d3d"] = p["url"] + "  (2D/3D — после формы подписки на сайте Poliform; список файлов — files_after_login)"
        place = ["outdoor"] if re.search(r"outdoor", " ".join(x for x in (p.get("slug"), p.get("category"), kind,
                                                                         (p.get("text_en") or "")[:200]) if x), re.I) else ["indoor"]
        out.append({"mfr_key": p["slug"], "model": model, "type": t,
                    "collection": slug(model_for_name(re.sub(r"\boutdoor\b", "", model, flags=re.I).strip() or model, t)),
                    "category": p.get("category"), "line": p.get("collection_line"), "designer": p.get("designer") or None,
                    "year": p.get("year") or None, "place": place, "new": bool(p.get("new")), "mfr_code": None,
                    "text": {"en": p.get("text_en"), "ru": p.get("text_ru")}, "tech": {"en": tech} if tech else None,
                    "finishes": p.get("finishes") or None, "versions": vers,
                    "images": [x for x in (img(files, u) for u in p.get("images") or []) if x],
                    "drawings": drw, "sheets": [], "links": {k: v for k, v in links.items() if v},
                    "files_after_login": gated})
    return out


def mm_dims(name):
    """Размеры MisuraEmme (в мм) → см: «W. 824 x D. 816 mm», «W.2300 mm», «mattress size 1600 x 2000 mm», «H.740»."""
    s = (name or "").replace(",", ".")                 # у MisuraEmme размеры всегда в мм, даже без «mm»
    n = r"(\d+(?:\.\d+)?)"
    cm = lambda x: (lambda v: int(v) if v == int(v) else round(v, 1))(float(x) / 10)
    out = {}
    for lab, key in (("W|L", "l"), ("D|P", "w"), ("H", "h")):
        m = re.search(r"\b(?:" + lab + r")\.?\s*" + n, s)
        if m:
            out[key] = cm(m.group(1))
    if not out:
        m = re.search(n + r"\s*x\s*" + n + r"(?:\s*x\s*" + n + r")?", s)
        if m:
            out = {"l": cm(m.group(1)), "w": cm(m.group(2))} | ({"h": cm(m.group(3))} if m.group(3) else {})
    m = re.search(r"[øØ∅]\s*" + n, s)
    if m and "l" not in out:
        out["d"] = cm(m.group(1))
    return out or None


def misuraemme():
    """MisuraEmme: товар — страница изделия (EN). Исполнения — подписи чертежей «Dimensions» (размеры там в мм, у нас — см);
    отделки с кодами; текст и техническое описание. Фото высокого разрешения и 2D/3D (PDF, DWG, 3DS) — после входа:
    не скачаны, в files_after_login — что есть (адрес — страница изделия, где после входа их скачать)."""
    files, _ = files_of("misuraemme")
    T = {"systems": "storage", "day systems": "storage", "night systems": "wardrobe", "small tables": "coffee_table",
         "doors": "doors", "night complements": "bedside", "complements": "decor"}
    out = []
    for p in json.load(open(os.path.join(SRC, "misuraemme/site.json"), encoding="utf-8")):
        kind = p.get("type") or ""
        t = T.get(kind.lower()) or kw(kind) or kw(p["slug"].replace("-", " ")) or kw(p.get("title")) or "decor"
        if t == "decor":                                  # «Accessories»: что именно — по чертежам и первой фразе текста
            first = re.split(r"(?<=[.!?])\s", p.get("text_en") or "", maxsplit=1)[0]
            t = majority([v.get("title") for v in p.get("dimensions") or []]) or kw(first) or t
        if t == "lamp":
            t = "floor" if re.search(r"floor", (p.get("title") or "") + " " + (p.get("text_en") or "")[:300], re.I) else "table_lamp"
        model = smart_title(p.get("title"), mixed=True)
        vers, drw = [], []
        for v in p.get("dimensions") or []:
            nm = v.get("title") or ""
            if nm and nm not in [x["name"]["en"] for x in vers]:
                vers.append({k: x for k, x in {"name": {"en": nm}, "dims_cm": mm_dims(nm)}.items() if x})
            d = img(files, v.get("drawing"))
            if d:
                drw.append({k: d[k] for k in ("file", "width", "height", "bytes")} | {"source": {"site": d["src"], "version": nm or None}})
        login = p.get("downloads_login") or []
        models = [x for x in login if re.search(r"2D|3D", x, re.I)]
        links = {"page": p["url"]}
        sheet_page = next((x["url"] for x in p.get("downloads_open") or [] if "data sheet" in (x.get("title") or "").lower()), None)
        if sheet_page:
            links["datasheet_page"] = sheet_page
        if models:
            links["files_2d3d"] = p["url"] + "  (2D/3D — после входа на сайте MisuraEmme)"
        if any(re.search(r"\bHR\b", x) for x in login):
            links["photos_hr"] = p["url"] + "  (фото высокого разрешения — после входа на сайте MisuraEmme)"
        out.append({"mfr_key": p["slug"], "model": model, "type": t, "collection": slug(model_for_name(model, t)),
                    "category": kind or None, "designer": p.get("designer") or None, "place": ["indoor"], "mfr_code": None,
                    "text": {"en": p.get("text_en")}, "tech": {"en": p.get("tech_en")} if p.get("tech_en") else None,
                    "finishes": p.get("finishes") or None, "versions": vers,
                    "images": [x for x in (img(files, u) for u in p.get("images") or []) if x],
                    "drawings": drw, "sheets": [], "links": links,
                    "files_after_login": [{"title": x, "url": p["url"]} for x in models]})
    return out


def rimadesio():
    """Rimadesio: товар — страница изделия (EN + RU): двери, перегородки, системы хранения, гардеробные, мебель.
    Техническая документация — PDF коллекции (открыта; одна на несколько изделий, размеры — в ней). 2D/3D — в Reserved
    Area после входа: не скачаны, подсказка дизайнеру — ссылка на Reserved Area."""
    files, sheets = files_of("rimadesio")
    out = []
    for p in json.load(open(os.path.join(SRC, "rimadesio/site.json"), encoding="utf-8")):
        crumbs = p.get("crumbs") or []
        kind = p.get("type") or ""
        # разделы сайта Rimadesio → тип (слова «Day», «Night», «Office» под заголовком — это линейка, не тип)
        SECT = {"modular furniture": "storage", "day systems": "storage", "closets": "wardrobe", "walk-in closets": "wardrobe",
                "beauty corner": "storage", "wall partition systems": "partition", "partition system": "partition",
                "modulor wall paneling system": "boiserie", "mobili tv": "storage", "comodini": "bedside", "scrittoi": "desk",
                "bar cabinet": "storage", "bar cabinets": "storage", "glass cabinets": "storage",
                "glass cabinets and display cases": "storage", "shelves": "storage", "bookshelves": "bookcase",
                "sliding doors": "doors", "syncro": "doors", "office": "desk"}
        t = kw(kind) if kind.lower() not in SECT else SECT[kind.lower()]
        if not t or t in ("decor", "lamp"):
            t = next((SECT[c.lower()] for c in reversed(crumbs) if c.lower() in SECT), None)
        for src in ((crumbs[-1] if crumbs else ""), " ".join(crumbs), p.get("title"), p["slug"].replace("-", " ")):
            if t and t not in ("decor", "lamp"):
                break
            t = kw(src)
        if not t or t in ("decor", "lamp"):
            first = re.split(r"(?<=[.!?])\s", p.get("text_en") or "", maxsplit=1)[0]
            t = kw(first) or ("boiserie" if re.search(r"panel+ing|boiserie", " ".join(crumbs) + " " + first, re.I) else "storage")
        model = smart_title(p.get("title"), mixed=True)
        sh = [s for s in (sheet(files, sheets, d["url"])[0] for d in p.get("pdfs") or []) if s]
        links = {"page": p["url"], "page_ru": p.get("url_ru") or None}
        gate = p.get("files_2d3d_login")
        if gate:
            links["files_2d3d"] = gate + "  (2D/3D — после входа в Reserved Area на сайте Rimadesio)"
        out.append({"mfr_key": p["slug"], "model": model, "type": t, "collection": slug(model_for_name(model, t)),
                    "category": " / ".join(crumbs) or None, "line": kind or None, "designer": p.get("designer") or None,
                    "place": ["indoor"], "mfr_code": None,
                    "text": {"en": p.get("text_en"), "ru": p.get("text_ru")},
                    "tech": {"en": "\n".join(p.get("details") or [])} if p.get("details") else None,
                    "versions": [], "images": [x for x in (img(files, u) for u in p.get("images") or []) if x],
                    "drawings": [], "sheets": sh, "links": {k: v for k, v in links.items() if v},
                    "files_after_login": [{"title": "2D/3D (Reserved Area)", "url": gate}] if gate else []})
    return out


def calligaris():
    """Calligaris: у фабрики страница — одно исполнение (код CS5156-C); наш товар — модель одного вида (семейство + тип:
    «Twins coffee table» с исполнениями CS5156-A, -B, -C). Исполнения — коды с размерами (см), «MTO» — под заказ.
    Розничная цена в евро с сайта фабрики — подсказка студии (retail), на сайт не идёт. Файлы OBJ / DWG / SKP —
    прямые ссылки у фабрики (downloads), в базу не качаем. Фото: на белом фоне (по исполнениям) и интерьерные."""
    files, _ = files_of("calligaris")
    LEAF = {"chairs without arms": "chair", "chairs with arms": "chair", "stacking chairs": "chair", "home office chairs": "chair",
            "folding chairs": "chair", "benches": "bench", "fix tables": "table", "extendable tables": "table", "desks": "desk",
            "coffee tables": "coffee_table", "mirrors": "mirror", "fixed consoles": "console",
            "fixed stools": "stool", "adjustable stools": "stool", "armchairs": "armchair", "ottomans": "pouf", "sofa": "sofa",
            "beds": "bed", "nightstands": "bedside", "drawer dressers": "drawers", "drawer chests": "drawers",
            "sideboards buffets": "sideboard", "bookcases": "bookcase", "tv stands": "storage", "rugs": "rug"}
    TOPT = {"chairs": "chair", "armchairs": "armchair", "sofas": "sofa", "tables": "table", "stools": "stool", "beds": "bed",
            "rugs": "rug", "cabinets, sideboards, wall uni": "storage", "bedroom furniture": "drawers", "occasional furniture": "decor",
            "objects": "decor"}

    def type_of(p):
        cat = [c.strip().replace("\xa0", " ").strip() for c in (p.get("category") or "").split(";;")]
        short = p.get("short") or ""
        t = LEAF.get(cat[-1].lower()) if cat else None
        if cat and cat[0].lower() == "chairs":           # «стулья с подлокотниками» Calligaris зовёт armchair — у нас это стул
            k = kw(short)
            return k if k in ("bench", "stool", "pouf") else "chair"
        if t in (None, "armchair", "sofa", "bed") or len(cat) < 2:
            k = kw(short)                                # «Sofa bed …», «Armchair …», «Bench …» — по описанию точнее
            if k and k not in ("lamp", "decor") and (t is None or k in ("sofa_bed", "bench", "pouf", "armchair", "chaise", "headboard")):
                t = k
        return t or TOPT.get((cat[0] if cat else "").lower()) or kw(short) or "decor"

    def num(v):
        m = re.search(r"(\d+(?:[.,]\d+)?)", str(v or ""))
        return (lambda f: int(f) if f == int(f) else round(f, 1))(float(m.group(1).replace(",", "."))) if m else None

    groups = {}
    for p in json.load(open(os.path.join(SRC, "calligaris/site.json"), encoding="utf-8")):
        t = type_of(p)
        fam = smart_title(p.get("family") or p["code"])
        groups.setdefault((slug(fam), t), {"fam": fam, "t": t, "pages": []})["pages"].append(p)
    out = []
    for (fs, t), g in groups.items():
        pages = sorted(g["pages"], key=lambda p: ("MTO" in p["code"], p["code"]))
        main = pages[0]
        vers, imgs, seen, dls, prices = [], [], set(), [], []
        for p in pages:
            m = p.get("measures") or {}
            dims = {k: v for k, v in {"l": num(m.get("larghezza_singola")), "w": num(m.get("profondita_singola")),
                                      "h": num(m.get("altezza_totale")), "d": num(m.get("diametro"))}.items() if v}
            v = {"name": {"en": p["code"]}, "code": p["code"]}    # код у всех языков один (MTO в коде — исполнение под заказ)
            if dims:
                v["dims_cm"] = dims
            extra = {k: num(x) for k, x in m.items() if k not in ("larghezza_singola", "profondita_singola", "altezza_totale", "diametro")}
            if extra:
                v["dims_extra_cm"] = {k: x for k, x in extra.items() if x}
            if p.get("short"):
                v["note"] = {"en": p["short"]}
            vers.append(v)
            for u in p.get("images") or []:
                if u not in seen:
                    seen.add(u)
                    x = img(files, u)
                    if x:
                        imgs.append(x)
            for d in p.get("downloads") or []:
                if d.get("type") in ("dwg", "obj", "skp") and d.get("url"):
                    dls.append({"format": d["type"].upper(), "url": d["url"], "version": p["code"]})
            if str(p.get("price_eur") or "").replace(".", "").isdigit():
                prices.append(float(p["price_eur"]))
        text = max((p.get("text") or "" for p in pages), key=len) or None
        cat = [c.strip().replace("\xa0", " ").strip() for c in (main.get("category") or "").split(";;") if c.strip()]
        item = {"mfr_key": f"{fs}--{t}", "model": g["fam"], "type": t, "collection": fs,
                "category": " / ".join(cat) or None, "designer": next((p["designer"] for p in pages if p.get("designer")), None),
                "place": ["indoor"], "new": any(p.get("new") for p in pages),
                "mfr_code": ", ".join(p["code"] for p in pages[:6]) + (" …" if len(pages) > 6 else ""),
                "text": {"en": text}, "versions": vers, "images": imgs[:12], "drawings": [], "sheets": [],
                "links": {"page": main["url"]}, "downloads": dls}
        if prices:
            item["retail"] = {"from": min(prices), "to": max(prices), "currency": "EUR", "source": "calligaris.com (en-RW)"}
        out.append(item)
    return out


IT_WORDS = [(r"\bCOMPOSIZIONE\b", "composition"), (r"\bCON\b", "with"), (r"\bTAVOLINO\b", "side table"), (r"\bTAVOLO\b", "table"),
            (r"\bANGOLO\b", "corner"), (r"\bPANCA\b", "bench"), (r"\bLETTO\b", "bed"), (r"\bCOMODINO\b", "bedside table"),
            (r"\bSPECCHIO\b", "mirror"), (r"\bTONDO\b", "round"), (r"\bRETTANGOLARE\b", "rectangular"), (r"\bOVALE\b", "oval"),
            (r"\bDIVANO\b", "sofa"), (r"\bPOLTRONA\b", "armchair"), (r"\bSEDIA\b", "chair"), (r"\bSGABELLO\b", "stool"),
            (r"\bBRACCIOLI\b", "armrests"), (r"\bSENZA\b", "without"), (r"\bDX\b", "right"), (r"\bSX\b", "left")]


def rugiano_version(title):
    """Подпись схемы «Measures» (имя файла: «BOHEME CON POUF», «RAFAEL 175») → по-английски, с заглавной."""
    t = title
    for a, b in IT_WORDS:
        t = re.sub(a, b, t, flags=re.I)
    return smart_title(t, mixed=False)


def rugiano():
    """Rugiano: товар — страница изделия (EN) в разделе indoor или outdoor; одна модель бывает в нескольких разделах
    (Boheme — кровать, скамья, зеркало, тумба, диван), поэтому ключ — раздел + изделие. Исполнения — схемы «Measures»
    (картинки с размерами; подпись — имя файла). Дизайнер на сайте не указан. Технические характеристики (материалы,
    отделки) — после входа в Area riservata: не скачаны, в files_after_login — ссылка на страницу изделия."""
    files, sheet_info = files_of("rugiano")
    sf = os.path.join(SRC, "rugiano/sheets.json")
    SHEETS = json.load(open(sf, encoding="utf-8")) if os.path.exists(sf) else {}

    def cm_line(s):
        """«L 215 x D 217 x H 32/165 - Slat 160» → {l: 215, w: 217, h: 165} (см; у «32/165» — большее)."""
        out = {}
        for lab, key in (("L|W", "l"), ("D|P", "w"), ("H|A", "h")):
            m = re.search(r"\b(?:" + lab + r")\s*(\d+(?:[.,]\d+)?(?:\s*/\s*\d+(?:[.,]\d+)?)*)", s)
            if m:
                out[key] = max(float(x.replace(",", ".")) for x in re.split(r"\s*/\s*", m.group(1)))
                out[key] = int(out[key]) if out[key] == int(out[key]) else out[key]
        m = re.search(r"(?:Ø|ø|diam\.?)\s*(\d+)", s, re.I)
        if m and "l" not in out:
            out["d"] = int(m.group(1))
        return out or None
    SEC = {"beds": "bed", "vanity-tables": "console", "sofas": "sofa", "night-storage-units": None, "living-storage-units": None,
           "armchairs": "armchair", "chaise-longues": "chaise", "coffee-tables": None, "tables": "table", "chairs": "chair",
           "barstools": "stool", "bookcases": "bookcase", "desks": "desk", "consoles": "console", "benches": "bench",
           "poufs": "pouf", "mirrors": "mirror", "home-accessories": None, "carpets": "rug", "lighting": None,
           "office": None, "fireplaces": "decor", "sunbeds": "sunbed", "metal-curtains": "screen", "bar-cabinets": "sideboard"}
    out = []
    for p in json.load(open(os.path.join(SRC, "rugiano/site.json"), encoding="utf-8")):
        label, sec = p.get("label") or "", p["section"]
        first = " ".join((b.get("paras") or [""])[0] for b in (p.get("blocks") or [])[:1])
        t = SEC.get(sec) or kw(label) or kw(p.get("title")) or kw(first) or "decor"
        if sec == "coffee-tables":
            t = "side_table" if re.search(r"side", label + " " + p["title"], re.I) else "coffee_table"
        LABEL = {"library": "bookcase", "tv cabinet": "storage", "bar cabinets": "sideboard", "painting": "decor",
                 "office chair": "chair", "chests of drawers": "drawers", "vanity table": "console", "fireplace": "decor",
                 "home accessory": "decor", "tray": "tray", "wardrobe": "wardrobe", "bedside table": "bedside"}
        if sec in ("night-storage-units", "living-storage-units", "office", "home-accessories"):
            t = LABEL.get(label.lower()) or kw(label) or kw(p["title"]) or ("storage" if "storage" in sec else "decor")
            if sec == "night-storage-units" and t == "side_table":      # «Side Table» в ночных — тумба у кровати
                t = "bedside"
            if sec == "home-accessories" and t == "decor":            # аксессуар: что именно — по названию и первой фразе
                t = kw(p["title"]) or kw(first) or "decor"
                if t in ("table", "chair", "sofa", "bed", "lamp"):
                    t = "decor"
        if t == "lamp" or sec == "lighting":
            s = f"{p['title']} {label} {first}"
            t = ("ceiling" if re.search(r"\bceiling\b", p["title"], re.I)
                 else "suspension" if re.search(r"suspension|pendant|chandelier|ceiling", s, re.I) and not re.search(r"\bfloor\b", p["title"], re.I)
                 else "wall" if re.search(r"\bwall\b|sconce|appliqu", s, re.I)
                 else "floor" if re.search(r"\bfloor\b", s, re.I)
                 else "table_lamp" if re.search(r"\btable\b|desk", s, re.I) else "suspension")
        model = smart_title(p.get("name_full") or p.get("title"), mixed=True)
        text = "\n\n".join(x for b in p.get("blocks") or [] for x in (b.get("heads") or []) + (b.get("paras") or []) if x)
        vers, drw = [], []
        for m in p.get("measures") or []:
            nm = rugiano_version(m.get("title") or "")
            if nm and nm not in [x["name"]["en"] for x in vers]:
                vers.append({"name": {"en": nm}})
            d = img(files, m.get("drawing"))
            if d:
                drw.append({k: d[k] for k in ("file", "width", "height", "bytes")} | {"source": {"site": d["src"], "version": nm or None}})
        links = {"page": p["url"]}
        gated = []
        sh = SHEETS.get(p["key"]) or {}
        sheets = []
        tech = None
        if sh.get("sheet_url"):                           # техкарта из Area riservata (вход владельца, 26.10.2026)
            links["datasheet"] = sh["sheet_url"]
            shp, _ = sheet(files, sheet_info, sh["sheet_url"])
            sheets = [shp] if shp else []
            rows = [f"Materials: {'; '.join(sh.get('materials') or [])}"] if sh.get("materials") else []
            if sh.get("weight_kg"):
                rows.append(f"Weight (kg): {sh['weight_kg']}")
            rows += sh.get("notes") or []
            tech = {"en": "\n".join(rows)} if rows else None
            dv = [{"name": {"en": x}, "dims_cm": cm_line(x)} for x in sh.get("dimensions") or []]
            if dv:
                vers = [{k: v for k, v in x.items() if v} for x in dv]
        for k, title in (("2D FILE", "2D (DWG)"), ("3D FILE", "3D"), ("GALLERY", "Photo gallery (ZIP)")):
            if k in (sh.get("gated_links") or {}):
                gated.append({"title": title, "url": p["url"]})
        if gated:
            links["files_2d3d"] = p["url"] + "  (2D/3D и галерея — после входа на сайте Rugiano, Area riservata)"
        elif p.get("spec_after_login") and not sh.get("sheet_url"):
            links["spec_after_login"] = p["url"] + "  (технические характеристики — после входа на сайте Rugiano, Area riservata)"
            gated = [{"title": "Technical specification", "url": p["url"]}]
        out.append({"mfr_key": p["key"], "model": model, "type": t, "collection": slug(model_for_name(smart_title(p.get("title"), mixed=True), t)),
                    "category": " / ".join(c for c in (p.get("crumbs") or [])[1:-1]) or None, "designer": None,
                    "place": [p["place"]], "mfr_code": None, "text": {"en": text}, "tech": tech,
                    "versions": vers, "images": [x for x in (img(files, u) for u in p.get("images") or []) if x],
                    "drawings": drw, "sheets": sheets, "links": links, "files_after_login": gated})
    return out


def giorgetti():
    """Giorgetti: товар — страница изделия (EN) в разделе сайта (данные прочитаны в браузере 26.10.2026,
    scripts/shop/factories/giorgetti.py). Исполнения — коды фабрики с описанием и размерами в см (Ш × Г × В или Ø × В),
    отделки — группы и число вариантов, техкарта PDF — открыта; технические чертежи — после входа на сайте (ссылка)."""
    files, _ = files_of("giorgetti")
    SEC = {"armchairs": "armchair", "office-armchairs": "chair", "sofas": "sofa", "tables": "table", "writing-desk": "desk",
           "beds": "bed", "wardrobes-and-cabins": "wardrobe", "giorgetti-atmosphere/Rugs": "rug",
           "kitchens-and-accessories": "kitchen"}
    ALLOW = {"chairs-and-stools": ("chair", "stool", "bench"), "poufs-and-benches": ("pouf", "bench", "stool"),
             "tables-and-trolleys": ("coffee_table", "side_table", "trolley", "console", "table", "desk"),
             "containers-and-bookcases": ("bookcase", "sideboard", "storage", "drawers", "bedside", "console"),
             "chests-of-drawers-night-tables-and-vanity": ("drawers", "bedside", "console", "desk", "storage", "mirror"),
             }

    def dims(cm):
        """«58 x 60 x h 84» → {l, w, h}; «Ø cm 30 x h 100 ÷ 325» → {d, h} (см; у диапазона — большее)."""
        s = cm.replace(",", ".")
        num = r"(\d+(?:\.\d+)?)"
        out = {}
        m = re.search(r"Ø\s*(?:cm\s*)?" + num, s)
        if m:
            out["d"] = float(m.group(1))
        else:
            m = re.match(r"\s*" + num + r"\s*x\s*" + num, s)
            if m:
                out["l"], out["w"] = float(m.group(1)), float(m.group(2))
        m = re.search(r"\bh\s*" + num + r"(?:\s*÷\s*" + num + r")?", s)
        if m:
            out["h"] = max(float(x) for x in m.groups() if x)
        return {k: int(v) if v == int(v) else v for k, v in out.items()} or None

    def lamp(text):
        return ("suspension" if re.search(r"suspen|pendant|chandelier", text, re.I)
                else "ceiling" if re.search(r"ceiling", text, re.I)
                else "wall" if re.search(r"\bwall\b|applique", text, re.I)
                else "floor" if re.search(r"\bfloor\b", text, re.I)
                else "table_lamp")
    out = []
    for p in json.load(open(os.path.join(SRC, "giorgetti/site.json"), encoding="utf-8")):
        sec = p["section"]
        abstracts = [v.get("abstract") or "" for v in p.get("versions") or []]
        first = (p.get("details") or "").split(".")[0]
        t = SEC.get(sec)
        if not t:
            allowed = ALLOW.get(sec)
            t = majority(abstracts, allowed) or (kw(first) if not allowed or kw(first) in allowed else None) \
                or majority(abstracts) or kw(first) or kw(p.get("subtitle")) or (allowed[0] if allowed else None)
        if sec == "giorgetti-atmosphere/Lighting" or t == "lamp":
            t = lamp(" ".join(abstracts[:3]) + " " + first)
        if sec == "chairs-and-stools" and t == "armchair":       # «Small armchair» у стульев — стул с подлокотниками
            t = "chair"
        if sec == "tables-and-trolleys" and t == "table":
            t = "coffee_table" if re.search(r"low|coffee|occasional|side", " ".join(abstracts) + first, re.I) else "table"
        t = t or "decor"
        place = ["outdoor"] if sec == "open-air" or re.search(r"open air|outdoor", p["slug"] + " " + p["title"], re.I) else ["indoor"]
        model = smart_title(p["title"], mixed=True)
        vers = []
        for v in p.get("versions") or []:
            name = " — ".join(x for x in (v["code"], v.get("abstract")) if x)
            if v.get("cm"):
                name += f" ({v['cm'].replace('Ø cm', 'Ø').rstrip(' Ø')} cm)"
            vers.append({k: x for k, x in {"name": {"en": name}, "code": v["code"], "dims_cm": dims(v.get("cm") or "")}.items() if x})
        fin = {}
        for cat, cols in (p.get("materials") or {}).items():
            for col, info in cols.items():
                fin[cat if col == cat else f"{cat} / {col}"] = {"count": info["count"], "examples": info["examples"]}
        text = "\n\n".join(x for x in (p.get("subtitle"), p.get("details")) if x)
        sheets = []
        for u in p.get("sheets") or []:
            v = files.get(u)
            if v:
                sheets.append({"file": v["file"], "url": u, "pages": v.get("pages"), "bytes": v.get("bytes")})
        links = {"page": p["url"]}
        if sheets:
            links["datasheet"] = sheets[0]["url"]
        gated = []
        if p.get("drawings_after_login"):
            links["files_2d3d"] = p["url"] + "  (технические чертежи — после входа на сайте Giorgetti)"
            gated = [{"title": "Technical drawings", "url": p["url"]}]
        out.append({"mfr_key": p["key"], "model": model, "type": t,
                    "collection": slug(model_for_name(model, t)), "category": sec.replace("giorgetti-atmosphere/", "Atmosphere / ").replace("-", " ").title(),
                    "designer": p.get("designer"), "year": p.get("year"), "place": place, "mfr_code": None,
                    "text": {"en": text}, "tech": {"en": f"Covers: {p['covers']}"} if p.get("covers") else None,
                    "finishes": fin or None, "versions": vers,
                    "images": [x for x in (img(files, u) for u in p.get("images") or []) if x],
                    "drawings": [], "sheets": sheets, "links": links, "files_after_login": gated})
    return out


def lago():
    """Lago: товар — страница изделия lagodesign.com/en/design/<изделие>/ (scripts/shop/factories/lago.py). Название
    у фабрики — «модель + тип» («Air Sofa», «36e8 Glass Sideboard», иногда «Coffee Table Layers»): тип — по названию,
    модель — название без слов типа. Размеров и исполнений на сайте нет (конфигуратор, каталог фабрики), отделки — списком."""
    files, _ = files_of("lago")
    TYPEWORDS = r"\b(sofa bed|sofa|armchair|chaise longue|pouf|chair|stool|bench|coffee table|side table|table|desk|console|" \
                r"bedside tables?|bed|single bed|bookshelf|bookcase|wall unit|tv unit|sideboard|dresser|storage furniture|" \
                r"walk-in closet|wardrobe|pantry|kitchen|basin|mirror|lamp|centerpiece|rug|cabinet)\b"
    out = []
    for p in json.load(open(os.path.join(SRC, "lago/site.json"), encoding="utf-8")):
        title = p.get("title") or p["slug"]
        cat = " ".join(p.get("category") or [])
        t = kw(title) or kw(cat) or "decor"
        if t == "lamp":
            t = "suspension" if re.search(r"suspen|pendant", title + " " + (p.get("description") or ""), re.I) else \
                "floor" if re.search(r"floor", title + " " + (p.get("description") or ""), re.I) else "table_lamp"
        if re.search(r"basin", title, re.I):
            t = "bathroom"
        if re.search(r"pantry", title, re.I):
            t = "kitchen_unit" if "kitchen_unit" in FURN else "kitchen"
        kids = re.search(r"child|kids", title, re.I)
        m = re.sub(r"\bfor (the )?children['’]?s ?rooms?\b|\bchildren['’]?s ?room\b|\bchildren['’]?s\b|\bchildrenroom\b", " ", title, flags=re.I)
        m = re.sub(r"\btv[ -]unit\b", "TV", m, flags=re.I)                   # ТВ-тумба и стенка одной серии — разные названия
        m = re.sub(TYPEWORDS + r"|\b(shelf|shelving|storage|walk-in-closet|lavabo|sedia|letto)\b", " ", m, flags=re.I)
        m = re.sub(r"\bTv\b", "TV", re.sub(r"N\.O\.W\.\s+Now\b", "N.O.W.", m))
        model = re.sub(r"\s+", " ", m).strip(" -") or title
        if kids:
            model += " Kids"
        model = re.sub(r"\bTv\b", "TV", smart_title(model, mixed=True))
        fins = {}
        for f in p.get("finishings") or []:
            g = (f.get("what") or "Finishes").strip()
            fins.setdefault(g, []).append(f.get("title"))
        text = "\n\n".join(x for x in [p.get("subtitle"), p.get("description")] + [
            ((b.get("title") + ". ") if b.get("title") else "") + (b.get("text") or "") for b in p.get("blocks") or []] if x)
        links = {"page": p["url"]}
        if p.get("configurator"):
            links["configurator"] = p["configurator"]
        if p.get("catalog"):
            links["catalog"] = p["catalog"]
        tl = p.get("tech_links") or {}
        if tl.get("link_models"):
            links["files_2d3d"] = tl["link_models"] + "  (модели 2D/3D — Dropbox фабрики)"
        if tl.get("link_technical_sheet"):
            links["datasheet"] = tl["link_technical_sheet"]
        place = ["outdoor"] if re.search(r"outdoor", cat + " " + " ".join(p.get("rooms") or []) + " " + title, re.I) else ["indoor"]
        out.append({"mfr_key": p["slug"], "model": model, "type": t, "collection": slug(model),
                    "category": cat or None, "designer": p.get("designer"), "year": p.get("year"), "place": place,
                    "mfr_code": None, "text": {"en": text},
                    "finishes": {g: {"count": len(v), "examples": v[:8]} for g, v in fins.items()} or None, "versions": [],
                    "images": [x for x in (img(files, u) for u in p.get("images") or []) if x],
                    "drawings": [], "sheets": [], "links": links})
    return out


FACT = {
    "olev": {"fn": olev, "kind": "light", "range": (3000, 3399), "name": "OLEV", "site": "https://www.olevlight.com/en/"},
    "delta": {"fn": delta, "kind": "light", "range": (3400, 4699), "name": "Delta Light", "site": "https://deltalight.com/en"},
    "baxter": {"fn": baxter, "kind": "furn", "range": (5000, 5599), "name": "Baxter", "site": "https://www.baxter.it/en/products"},
    "flexform": {"fn": flexform, "kind": "furn", "range": (5600, 6199), "name": "Flexform", "site": "https://www.flexform.it/en/products"},
    "molteni": {"fn": molteni, "kind": "furn", "range": (6200, 6799), "name": "Molteni&C", "site": "https://www.molteni.it/en/eu"},
    "maxalto": {"fn": maxalto, "kind": "furn", "range": (6800, 7099), "name": "Maxalto", "site": "https://www.maxalto.com/en"},
    "minotti": {"fn": minotti, "kind": "furn", "range": (7100, 7899), "name": "Minotti", "site": "https://www.minotti.com/en"},
    "poliform": {"fn": poliform, "kind": "furn", "range": (7900, 8399), "name": "Poliform", "site": "https://www.poliform.it/en/"},
    "misuraemme": {"fn": misuraemme, "kind": "furn", "range": (8400, 8699), "name": "MisuraEmme", "site": "https://www.misuraemme.it/en/"},
    "rimadesio": {"fn": rimadesio, "kind": "furn", "range": (8700, 8999), "name": "Rimadesio", "site": "https://www.rimadesio.it/en/"},
    "calligaris": {"fn": calligaris, "kind": "furn", "range": (9000, 9499), "name": "Calligaris", "site": "https://www.calligaris.com/en-RW"},
    "rugiano": {"fn": rugiano, "kind": "furn", "range": (9500, 9999), "name": "Rugiano", "site": "https://www.rugiano.com/en/products"},
    "lago": {"fn": lago, "kind": "furn", "range": (10000, 10299), "name": "Lago", "site": "https://www.lagodesign.com/en/design/"},
    "giorgetti": {"fn": giorgetti, "kind": "furn", "range": (10300, 10799), "name": "Giorgetti", "site": "https://www.giorgettimeda.com/ww/en/products"},
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
                  "mfr_key", "mfr_code", "text", "tech", "finishes", "versions", "images", "drawings", "sheets", "links",
                  "files_after_login", "downloads", "retail"):
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
