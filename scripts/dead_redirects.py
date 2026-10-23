#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Редиректы для старых адресов, которые были в Google, но на Weblium уже отдают 404.

  python3 scripts/dead_redirects.py "<папка выгрузки>/https___dumskaya-design/Страницы.csv"

Для каждого мёртвого адреса ищет ближайшую живую страницу:
  • кухни K-NN → карточка той же кухни, иначе каталог кухонь;
  • польская версия /pl-pl/… → английская страница (польского больше нет);
  • остальное — по совпадению слов в адресе с адресами живых страниц того же языка,
    плюс ручные правила ниже. Если ничего похожего — главная этого языка.
Результат дописывается в content/redirects.json и печатается для проверки.
"""
import csv
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = os.path.join(ROOT, "content")
HOST = "https://dumskaya-design.com"

# слово в старом адресе → русский адрес страницы-назначения (язык подставится сам)
KEYWORDS = [
    (r"kontakt|contact", "/contact-studio-interior-design-bratislava-vienna"),
    (r"smet|koshtorys|kosztorys|estimate", "/smeta-na-remont-bratislava-vienna"),
    (r"stroitel|remont|budivn|budowl|renovation|construction|prais|ceny-na-uslugi-bud", "/stroitelstvo-remont-bratislava"),
    (r"priemk|pryimann|odbior|handover", "/priemka-kvartiry-ot-zastrojshchika"),
    (r"price|cena-uslug|tsina|pricing", "/price-interior-design-bratislava-wien-praha"),
    (r"serial-kuhni|serijnuyu|typovu|standard-models|kuchnie-na-wymiar|kitchen", "/kupkuhni-na-zakaz-vienna-bratislava"),
    (r"kuhni-shkafi|mebl|furniture|meble|autorskich", "/kuhni-shkafi-bratislava"),
    (r"komercyjn|komertsiin|commercial|biur|office|restoran|sklep|butik|salon|sauna", "/interior-design-office-bratislava-wien"),
    (r"arhitek|architect|arkhitekt", "/architecture-design-bratislava"),
    (r"3d|wizualizacja|vizualiz", "/3d-vizualizaciya-fasada-zdaniya-cena"),
    (r"zrealizowane|realizovani|portfolio|projekty", "/proekty-interior-design"),
    (r"pochemu|why|dlaczego|chomu", "/why-you-need-an-interior-designer"),
    (r"bedroom|sypialn|spaln", "/kak-pravilno-organizovat-rabochee-mesto-v-spalne"),
    (r"lazienk|sanuzel|vann", "/kak-pravilno-organizovat-svoj-sanuzel"),
    (r"balkon", "/kak-pravilno-organizovat-udobnyj-i-funkcionalnyj-balkon"),
    (r"dzieci|detsk|dytiach", "/osnovnye-principy-i-pravila-pri-proektirovanie-dizajna-interera-detskoj-komnaty"),
    (r"maleg|malenk|malohab|small-apartment", "/transformaciya-malenkoj-kvartiry-prakticheskie-sovety-dlya-maksimalnogo-ispolzovaniya-prostranstva"),
    (r"mieszkal|zhytlov|residential|apartmens-warsaw", "/interior-design-apartmens-bratislava"),
]

# точные ручные соответствия (старый адрес → русский адрес назначения или полный адрес)
MANUAL = {
    "/pl-pl": "/en",
    "/pl-pl/jak-prawidlowo-zorganizowac-wygodna-i-funkcjonalna-kuchnie-warsaw-poland": "/kak-pravilno-organizovat-udobnuyu-i-funkcionalnuyu-kuhnyu",
    "/interior-design-private-house-217m": "/dizainer-interierov-kiev",
    "/en/luxury-interior-design-private-house-217sqm": "/dizainer-interierov-kiev",
    "/pl-pl/projekt-wnetrza-domu-217m": "/dizainer-interierov-kiev",
    "/pl-pl/interior-design-private-house-217m": "/dizainer-interierov-kiev",
    "/ua/dyzain-proekt-interieru-pryvatnoho-budynku-217-m-varshava-polshcha": "/dizainer-interierov-kiev",
    "/interior-design-private-house-179m": "/interior-design-villa-179m-madrid-spain",
    "/en/luxury-interior-private-house-179sqm": "/interior-design-villa-179m-madrid-spain",
    "/pl-pl/interior-design-private-house-179m": "/interior-design-villa-179m-madrid-spain",
    "/pl-pl/projekt-wnetrza-domu-warszawa-179m": "/interior-design-villa-179m-madrid-spain",
    "/ua/dyzain-proekt-interieru-pryvatnoho-budynku-179-m-varshava-polshcha": "/interior-design-villa-179m-madrid-spain",
    "/pl-pl/luxury-interior-madrid-villa-179m2": "/interior-design-villa-179m-madrid-spain",
    "/interior-design-apartment-warsaw-158m": "/interior-design-apartment-bratislava-158m",
    "/pl-pl/interior-design-apartment-warsaw-158m": "/interior-design-apartment-bratislava-158m",
    "/en/luxury-158sqm-duplex-apartment-interior-design-warsaw": "/interior-design-apartment-bratislava-158m",
    "/ua/dyzain-interieru-apartamentiv-z-terasoiu-u-varshavi-polshcha-158-m2": "/interior-design-apartment-bratislava-158m",
    "/apartment-interior-design-warsaw-58m": "/apartment-interior-design-bratislava-58m",
    "/pl-pl/apartment-interior-design-warsaw-58m": "/apartment-interior-design-bratislava-58m",
    "/en/58sqm-luxury-apartment-interior-design-warsaw": "/apartment-interior-design-bratislava-58m",
    "/ua/dyzain-proekt-interieru-kvartyry-58-m2-varshava-polshcha": "/apartment-interior-design-bratislava-58m",
    "/pl-pl/apartmens-vienna-luxury-interior-design-58m": "/apartments-vienna-luxury-interior-design-58m",
    "/pl-pl/projektant-wnetrza-apartamentu-wieden-austria": "/apartments-wien-luxury-interior-design-115m",
    "/pl-pl/apartmens-wien-luxury-interior-design-115m": "/apartments-wien-luxury-interior-design-115m",
    "/en/luxury-54sqm-apartment-interior-design-warsaw": "/apartment-interior-design-54m",
    "/ua/dyzain-proekt-ynterera-kvartyrы-54-m2-varshava-polsha": "/apartment-interior-design-54m",
    "/en/51sqm-luxury-apartment-interior-design-warsaw": "/apartment-interior-design-51m",
    "/ua/dyzain-proekt-interieru-kvartyry-51-m2-varshava-polshcha": "/apartment-interior-design-51m",
    "/apartment-luxury-interior-design-kharkiv-108m": "/interior-design-private-house-kharkiv-212m",
    "/apartment-luxury-interior-design-kharkiv-107m": "/interior-design-private-house-kharkiv-212m",
    "/pl-pl/apartment-luxury-interior-design-kharkiv-108m": "/interior-design-private-house-kharkiv-212m",
    "/pl-pl/apartment-luxury-interior-design-kharkiv-107m": "/interior-design-private-house-kharkiv-212m",
    "/en/apartment-luxury-interior-design-107m": "/apartment-luxury-interior-design-madrid-spain-107m",
    "/ua/dyzain-proekt-interieru-apartamentiv-107-m2-varshava": "/apartment-luxury-interior-design-madrid-spain-107m",
    "/ua/dyzain-proekt-interieru-apartamentiv-108-m2-varshava": "/luxury-interior-design-barcelona-spain-108m",
    "/en/luxury-108sqm-apartment-interior-design": "/luxury-interior-design-barcelona-spain-108m",
    "/pl-pl/luxury-interior-projekt-wnetrza-barcelona-hiszpania-108m2": "/luxury-interior-design-barcelona-spain-108m",
    "/pl-pl/luksusowy-projekt-wnetrza-madryt-hiszpania-107m2": "/apartment-luxury-interior-design-madrid-spain-107m",
    "/pl-pl/luxury-interior-design-madryt-hiszpania-107m": "/apartment-luxury-interior-design-madrid-spain-107m",
    "/dom-jednorodzinny-interior-design-warsaw-85m": "/interior-design-apartments-bratislava",
    "/pl-pl/dom-jednorodzinny-interior-design-warsaw-85m": "/interior-design-apartments-bratislava",
    "/en/85sqm-semi-detached-house-design-marki-warsaw": "/interior-design-apartments-bratislava",
    "/ua/dyzain-proekt-interieru-budynok-blyzniuk-marky-varshava-polshcha": "/interior-design-apartments-bratislava",
    "/photo-studio-interior-design-warsaw-130m": "/photo-studio-interior-design-custom-furniture-130m2-bratislava",
    "/pl-pl/photo-studio-interior-design-warsaw-130m": "/photo-studio-interior-design-custom-furniture-130m2-bratislava",
    "/pl-pl/projekt-wnetrza-biura-warszawa-500m": "/office-interior-design-500m",
    "/pl-pl/office-interior-design-warsaw-500m": "/office-interior-design-500m",
    "/pl-pl/projektowanie-wnetrz-biurowych-warszawa": "/office-interior-design-500m",
    "/pl-pl/projekt-wnetrza-biura-poznan-53m": "/office-interior-design-53m",
    "/pl-pl/office-interior-design-53м": "/office-interior-design-53m",
    "/office-interior-design-53м": "/office-interior-design-53m",
    "/pl-pl/office-interior-design-140m": "/office-interior-design-140m",
    "/ua/dyzain-interieru-ofisu-140-m-vyhotovlennia-mebliv-na-zamovlennia-vid-dumskaya-design-varshava": "/office-interior-design-140m",
    "/pl-pl/projekt-wnetrza-biura-warszawa-7m": "/boss-office-interior-design",
    "/pl-pl/boss-office-interior-design-warsaw": "/boss-office-interior-design",
    "/pl-pl/projekt-wnetrza-salonu-pieknosci-warszawa": "/beauty-salon-interior-design-63m",
    "/pl-pl/beauty-salon-interior-design-warsaw-63m": "/beauty-salon-interior-design-63m",
    "/pl-pl/luxury-interior-cosmetology-salon-warsaw": "/interior-design-cosmetology-salon",
    "/pl-pl/projekt-wnetrza-sauny-lazni-warszawa": "/dizayn-kommercheskogo-interyera-sauna-banya",
    "/pl-pl/projekt-wnetrza-sklepu": "/shop-show-room-interior-design-50m",
    "/pl-pl/shop-show-room-interior-design-warsaw-50m": "/shop-show-room-interior-design-50m",
    "/pl-pl/projekt-wnetrza-butiku-warszawa": "/clothing-boutique-interior-design-kyiv-140",
    "/pl-pl/clothing-boutique-interior-design-kyiv-140": "/clothing-boutique-interior-design-kyiv-140",
    "/ua/butik-zhinochoho-odyahu-kyyiv-vid-dumskaya-design-varshava": "/clothing-boutique-interior-design-kyiv-140",
    "/interior-design-restoran-warsaw": "/interior-design-office-bratislava-wien",
    "/pl-pl/projekt-wnetrza-mieszkania-studio-projektowe-warszawa-80m": "/studio-interior-design-disain-proekt-kvartira-kiev-80m",
    "/pl-pl/studio-interior-design-bratislava-eurovea-56m": "/studio-interior-design-bratislava-eurovea-56m",
    "/pl-pl/apartment-interior-design-bratislava-52m": "/apartment-interior-design-bratislava-52m",
    "/pl-pl/projekt-wnetrza-domu-burgas-bulgaria": "/dumskaya-interior-design-villa-220m",
    "/ua/dyzain-proekt-interieru-pryvatnoho-budynku-220-m-varshava-polshcha": "/dumskaya-interior-design-villa-220m",
    "/pl-pl/projekt-wnetrza-mieszkania-warna-bulgaria": "/interior-design-furniture-60m",
    "/pl-pl/projekt-wnetrza-domu-jednorodzinnego-berlin": "/interior-design-private-house-215m",
    "/pl-pl/interior-design-private-house-215m": "/interior-design-private-house-215m",
    "/pl-pl/projekt-wnetrza-domu-160m": "/villa-interior-design-160m",
    "/pl-pl/projekt-wnetrza-domu-230m": "/dumskaya-interior-design-villa-230m",
    "/pl-pl/dumskaya-interior-design-villa-230m": "/dumskaya-interior-design-villa-230m",
    "/ua/dyzain-proekt-interieru-pryvatnoho-budynku-230-m-varshava-polshcha": "/dumskaya-interior-design-villa-230m",
    "/pl-pl/projektant-wnetrza-mieszkania-londyn": "/interior-design-furniture-classic-120m-london",
    "/pl-pl/interior-design-furniture-classic-120m": "/interior-design-furniture-classic-120m-london",
    "/pl-pl/interior-design-apartment-luxury-kyiv-119m": "/interior-design-apartment-luxury-kyiv-119m",
    "/ua/dyzain-interieru-apartamentiv-z-terasoiu-u-kyievi-119-m2-varshava": "/interior-design-apartment-luxury-kyiv-119m",
    "/ua/realizatsiia-dyzain-proektu-interieru-pid-kliuch-kharkiv-60-m-vid-dumskaya-design-varshava-polsha": "/interior-design-furniture-65m",
    "/ua/arkhitekturne-rishennia-altanka-z-perholoiu-vid-dumskaya-design-varshava-polsha": "/architecture-gazebo-pergola",
    "/ua/arkhitekturne-rishennia-fasadu-barbershopu-kyiv-vid-dumskaya-design-varshava": "/architecture-facade-barbershop-kyiv",
    "/ua/arkhitekturni-rishennia-dlia-fasadu-pryvatnoho-budynku-vid-dumskaya-design-varshava-polsha": "/architecture-private-house",
    "/ua/eskiznyy-proekt-iz-3d-vizualizatsiyeyu-varshava-polshcha": "/3d-architecture-bratislava",
    "/3d-vizualizaciya-fasada-varshava": "/3d-vizualizaciya-fasada-bratislava",
    "/pl-pl/wizualizacja-3d-elewacji-warszawa": "/3d-vizualizaciya-fasada-bratislava",
    "/pl-pl/wizualizacja-3d-elewacji-budynku": "/3d-vizualizaciya-fasada-zdaniya-cena",
    "/pl-pl/3d-architecture-warsaw": "/3d-architecture-bratislava",
    "/3d-architecture-warsaw": "/3d-architecture-bratislava",
    "/apartment-furniture-interior-design-warsaw-43m-2": "/apartment-interior-design-warsaw-43m2",
    "/pl-pl/apartment-furniture-interior-design-warsaw-43m-2": "/apartment-interior-design-warsaw-43m2",
    "/pl-pl/apartment-interior-design-warsaw-43m": "/apartment-interior-design-warsaw-43m",
    "/pl-pl/furniture-interior-design-43m": "/furniture-interior-design-43m",
    "/ua/dyzain-proekt-interieru-apartamentiv-108-m2": "/luxury-interior-design-barcelona-spain-108m",
    "/en/interior-design-apartmens-warsaw": "/interior-design-apartments-bratislava",
    "/ua/dyzain-interieriv-komertsiinykh-prymishchen-warsawa": "/interior-design-office-bratislava-wien",
    "/izgotovlenie-mebeli-pod-zakaz-dlya-kommercheskih-obektov-ofis-resepshen-peregovornaya-kabinet-kuhnya": "/izgotovlenie-mebeli-pod-zakaz-dlya-kommercheskih-obektov-ofis-resepshen-peregovornaya-kabinet-kuhnya-bratislava",
    "/pl-pl/produkcja-mebli-na-wymiar-do-obiektow-komercyjnych-recepcja-sala-konferencyjna-kuchnia-biuro": "/izgotovlenie-mebeli-pod-zakaz-dlya-kommercheskih-obektov-ofis-resepshen-peregovornaya-kabinet-kuhnya-bratislava",
    "/pl-pl/furniture-private-house-design": "/furniture-private-house-design",
    "/pl-pl/architecture-private-house": "/architecture-private-house",
    "/pl-pl/architecture-gazebo-pergola": "/architecture-gazebo-pergola",
    "/pl-pl/architecture-villa-spain-marbella": "/architecture-villa-spain-marbella",
    "/pl-pl/architecture-facade-barbershop-kyiv": "/architecture-facade-barbershop-kyiv",
    "/pl-pl/arhitekrura-proektirovanie-warsaw": "/architecture-design-bratislava",
    "/pl-pl/interior-design-apartment-ukraine-47m": "/interior-design-apartment-ukraine-47m",
    "/pl-pl/interior-design-private-house-kharkiv-212m": "/interior-design-private-house-kharkiv-212m",
    "/pl-pl/interior-design-furniture-65m": "/interior-design-furniture-65m",
    "/pl-pl/interior-design-furniture-60m": "/interior-design-furniture-60m",
    "/pl-pl/apartmens-dubai-luxury-interior-design-160": "/apartments-dubai-luxury-interior-design-160m",
    "/pl-pl/apartmens-los-angeles-interior-design-140": "/apartments-los-angeles-interior-design-140m",
    "/pl-pl/apartmens-praha-luxury-interior-design-90m": "/apartments-praha-luxury-interior-design-90m",
    "/pl-pl/apartmens-ny-luxury-interior-design-57m": "/apartments-new-york-luxury-interior-design-57m",
    "/pl-pl/apartment-interior-design-krakow-63m": "/apartment-interior-design-krakow-63m",
    "/pl-pl/apartment-interior-design-krakow-64m": "/apartment-interior-design-krakow-64m",
    "/pl-pl/apartment-interior-design-warsaw-60m": "/apartment-interior-design-60m",
    "/pl-pl/apartment-interior-design-warsaw-54m": "/apartment-interior-design-54m",
    "/pl-pl/apartment-interior-design-warsaw-52m": "/apartment-interior-design-52m",
    "/pl-pl/apartment-interior-design-warsaw-51m": "/apartment-interior-design-51m",
    "/pl-pl/apartment-interior-design-warsaw-48m": "/apartment-interior-design-48m",
    "/pl-pl/apartment-furniture-interior-design-warsaw-45m": "/apartment-furniture-interior-design-45m",
    "/pl-pl/transformacja-malego-mieszkania-praktyczne-porady-dotyczace-maksymalnego-wykorzystania-przestrzeni-warsaw-poland": "/transformaciya-malenkoj-kvartiry-prakticheskie-sovety-dlya-maksimalnogo-ispolzovaniya-prostranstva",
}


def lang_of(path):
    first = path.strip("/").split("/", 1)[0]
    return {"ua": "ua", "en": "en", "pl-pl": "en"}.get(first, "ru")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    pages = {}
    for f in glob.glob(os.path.join(C, "pages", "**", "*.json"), recursive=True):
        p = json.load(open(f, encoding="utf-8"))
        pages[p["path"]] = p
    red_path = os.path.join(C, "redirects.json")
    red = json.load(open(red_path, encoding="utf-8"))

    def in_lang(ru_or_any, lang):
        """Адрес страницы на нужном языке (через языковые пары)."""
        target = red.get(ru_or_any, ru_or_any)
        p = pages.get(target)
        if not p:
            return None
        return p["alternates"].get(lang) or p["alternates"].get("ru") or target

    home = {"ru": "/", "ua": "/ua", "en": "/en"}
    kitchens = {l: in_lang("/kupkuhni-na-zakaz-vienna-bratislava", l) for l in home}
    kitchen_cards = {}
    for p in pages.values():
        if p["type"] == "kitchen":
            m = re.search(r"k-?(\d{2})", p["alternates"].get("ru", ""))
            if m:
                kitchen_cards[m.group(1)] = p["alternates"]

    old = []
    with open(sys.argv[1], encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            u = r["Популярные страницы"].split("#")[0].split("?")[0]
            u = u.replace(HOST, "") or "/"
            if len(u) > 1:
                u = u.rstrip("/")
            clicks = int(str(r["Kлики"]).replace("\xa0", "").replace(" ", "") or 0)
            old.append((u, clicks))
    added, report = 0, []
    for u, clicks in old:
        if u in pages or u in red:
            continue
        lang = lang_of(u)
        target, how = None, ""
        if u in MANUAL:
            target, how = in_lang(MANUAL[u], lang) or MANUAL[u], "вручную"
        if not target:
            m = re.search(r"(?:^|[/-])k-?(\d{2})(?:-|$)", u) or re.search(r"kitchen-(\d{2})$", u) or re.search(r"kitchen-k(\d{2})", u)
            if m and ("kuh" in u or "kitchen" in u or "kuch" in u):
                alts = kitchen_cards.get(m.group(1))
                target = (alts or {}).get(lang) or kitchens[lang]
                how = "кухня K-" + m.group(1) if alts else "каталог кухонь"
        if not target:
            for rx, dest in KEYWORDS:
                if re.search(rx, u, re.I):
                    target, how = in_lang(dest, lang), "по слову"
                    break
        if not target:
            target, how = home[lang], "на главную"
        red[u] = target
        added += 1
        report.append((clicks, u, target, how))
    # без цепочек: каждый редирект сразу ведёт на живую страницу
    for k, v in list(red.items()):
        seen = set()
        while v in red and v not in seen:
            seen.add(v)
            v = red[v]
        red[k] = v
    bad = {k: v for k, v in red.items() if v not in pages}
    if bad:
        sys.exit(f"Редиректы ведут на несуществующие страницы: {bad}")
    json.dump(dict(sorted(red.items())), open(red_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for c, u, t, h in sorted(report, reverse=True):
        print(f"{c:>6}  {u}\n        → {t}   [{h}]")
    print(f"\nдобавлено редиректов: {added}, всего: {len(red)}")


if __name__ == "__main__":
    main()
