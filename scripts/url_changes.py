#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Новые адреса страниц без Варшавы/Польши/Москвы + перенос всех ссылок на них.

  python3 scripts/url_changes.py          — показать план (ничего не меняет)
  python3 scripts/url_changes.py --apply  — переименовать страницы, обновить ссылки,
                                            дописать старые адреса в content/redirects.json

Не трогает: явно варшавские проекты (в H1 написано «Варшава») и Краков.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = os.path.join(ROOT, "content")

# Ручные адреса там, где простое вырезание города даёт плохой результат
MANUAL = {
    # украинские статьи: были длинные спам-хвосты, делаем короткие и понятные
    "/ua/dyzain-proekt-interieru-orhanizatsiia-robochoho-mistsia-u-spalni-varshava-polsha-vyhotovlennia-mebliv-na-zamovlennia": "/ua/orhanizatsiia-robochoho-mistsia-u-spalni",
    "/ua/dyzain-proekt-interieru-orhanizatsiia-vannoi-kimnaty-varshava-polshcha-vyhotovlennia-mebliv-na-zamovlennia": "/ua/orhanizatsiia-vannoi-kimnaty",
    "/ua/dyzain-proekt-interieru-pryntsypy-rozmishchennia-mebliv-na-kukhni-varshavi-polshcha-vyhotovlennia-mebliv-na-zamovlennia": "/ua/pryntsypy-rozmishchennia-mebliv-na-kukhni",
    "/ua/dyzain-proekt-interieru-orhanizatsiia-balkona-varshava-polshcha-vyhotovlennia-mebliv-na-zamovlennia": "/ua/orhanizatsiia-balkona",
    "/ua/dyzain-proekt-interieru-proektuvannia-dytiachoi-kimnaty-varshava-polshcha-vyhotovlennia-mebliv-na-zamovlennia": "/ua/proektuvannia-dytiachoi-kimnaty",
    "/ua/malohabarytni-kvartyry-dyzainer-interieru-dumskaya-design-varshava-polshcha-vyhotovlennia-mebliv-na-zamovlennia": "/ua/dyzain-malohabarytnoi-kvartyry-porady",
    "/ua/chomu-vam-potribnyi-dyzainer-interieru-dumskaya-design-varshava-polshcha-vyhotovlennia-mebliv-na-zamovlennia": "/ua/chomu-vam-potribnyi-dyzainer-interieru",
    # украинские проекты с «хвостами»
    "/ua/dyzain-proekt-interieru-fotostudii-u-varshavi-polsha-vyhotovlennia-mebliv-na-zamovlennia": "/ua/dyzain-interieru-fotostudii-130-m2",
    "/ua/dizayn-proekt-interyeru-lazni-sauny-kyiv-varshava": "/ua/dyzain-interieru-lazni-sauny-120-m2",
    "/ua/dyzain-interieru-salonu-krasy-63-m2-varshava-polsha-vyhotovlennia-mebliv-na-zamovlennia": "/ua/dyzain-interieru-salonu-krasy-63-m2",
    "/ua/kabinet-kerivnyka-vyhotovlennia-mebliv-na-zamovlennia-varshava-polshcha": "/ua/kabinet-kerivnyka-mebli-na-zamovlennia",
    "/ua/dyzain-proekt-interieru-mahazynu-50-m2-varshava-vyhotovlennia-mebliv-na-zamovlennia": "/ua/dyzain-interieru-mahazynu-50-m2",
    "/ua/dyzain-interieru-ofisu-53-m-vyhotovlennia-mebliv-na-zamovlennia-vid-dumskaya-design-varshava": "/ua/dyzain-interieru-ofisu-53-m2",
    "/ua/dyzain-interieru-ofisu-500-m-vyhotovlennia-mebliv-na-zamovlennia-vid-dumskaya-design-varshava": "/ua/dyzain-interieru-ofisu-500-m2",
    "/ua/luxury-interior-cosmetology-salon-warsaw": "/ua/dyzain-interieru-kosmetolohichnoho-salonu-54-m2",
    "/en/warsaw-modern-apartment-45sqm": "/en/modern-apartment-design-45sqm",
    "/en/52sqm-apartment-design-warsaw": "/en/modern-apartment-design-52sqm",
    "/boss-office-interior-design-warsaw": "/boss-office-interior-design",
}

GEO = [
    r"-u-varshavi-polsha", r"-u-varshavi", r"-varshavi-polshcha", r"-varshava-polshcha", r"-varshava-polsha",
    r"-warsaw-poland", r"-kyiv-varshava", r"-varshava", r"-warsaw", r"-moscow", r"-poland",
]
GEO_RE = re.compile(r"(?:%s)(?=-|$)" % "|".join(GEO))
TOUCH = re.compile(r"warsaw|varshav|polsh|poland|moscow", re.I)
KEEP_CITY = re.compile(r"krakiv|krakow", re.I)


def load_pages():
    out = {}
    for f in glob.glob(os.path.join(C, "pages", "**", "*.json"), recursive=True):
        p = json.load(open(f, encoding="utf-8"))
        out[p["path"]] = (f, p)
    return out


def plan(pages, projects):
    explicit = {p["path"] for p in projects if p.get("explicit_warsaw")}
    changes = {}
    for path, (_, p) in pages.items():
        if not TOUCH.search(path):
            continue
        ru = p["alternates"].get("ru")
        if ru in explicit:
            continue
        if KEEP_CITY.search(path) and not re.search(r"warsaw|varshav|moscow", path):
            continue
        if path in MANUAL:
            new = MANUAL[path]
        elif p["type"] == "kitchen" and p["lang"] == "ua":
            new = re.sub(r"-cena-poland-germany-austria-spain$", "-cena-bratislava-slovakia", path)
        else:
            new = GEO_RE.sub("", path)
        if new != path:
            changes[path] = new
    # проверки: новых адресов нет среди существующих, нет повторов
    taken = set(pages) - set(changes)
    dup = [n for n in changes.values() if n in taken or list(changes.values()).count(n) > 1]
    if dup:
        sys.exit(f"Конфликт адресов: {sorted(set(dup))}")
    left = [p for p in changes.values() if TOUCH.search(p)]
    if left:
        sys.exit(f"В новых адресах осталась Варшава: {left}")
    return changes


def rewrite(obj, changes):
    """Меняет старые адреса во всех строках структуры (ссылки, языковые пары, href в тексте)."""
    if isinstance(obj, dict):
        return {k: rewrite(v, changes) for k, v in obj.items()}
    if isinstance(obj, list):
        return [rewrite(v, changes) for v in obj]
    if isinstance(obj, str):
        if obj in changes:
            return changes[obj]
        if 'href="' in obj:
            return re.sub(r'href="([^"]+)"', lambda m: f'href="{changes.get(m.group(1), m.group(1))}"', obj)
    return obj


def slug_file(path, lang):
    parts = [x for x in path.strip("/").split("/") if x]
    if lang != "ru":
        parts = parts[1:]
    return os.path.join(C, "pages", lang, *(parts or ["_home"])) + ".json"


def main():
    pages = load_pages()
    projects = json.load(open(os.path.join(C, "projects.json"), encoding="utf-8"))
    changes = plan(pages, projects)
    for old, new in sorted(changes.items()):
        print(f"{old}\n   → {new}")
    print(f"\nвсего: {len(changes)}")
    if "--apply" not in sys.argv:
        return
    for path, (f, p) in pages.items():
        p2 = rewrite(p, changes)
        target = slug_file(p2["path"], p2["lang"])
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(p2, fh, ensure_ascii=False, indent=1)
        if os.path.abspath(target) != os.path.abspath(f):
            os.remove(f)
    for name in ("projects.json", "projects-order.json", "home.json", "site.json", "projects-overrides.json"):
        fp = os.path.join(C, name)
        if os.path.exists(fp):
            data = json.load(open(fp, encoding="utf-8"))
            if name == "projects-overrides.json":
                data = {changes.get(k, k): v for k, v in data.items()}
            data = rewrite(data, changes)
            json.dump(data, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rp = os.path.join(C, "redirects.json")
    red = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {}
    red.update(changes)
    # цепочки: если старый редирект вёл на адрес, который теперь переименован
    red = {k: changes.get(v, v) for k, v in red.items()}
    json.dump(dict(sorted(red.items())), open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("применено")


if __name__ == "__main__":
    main()
