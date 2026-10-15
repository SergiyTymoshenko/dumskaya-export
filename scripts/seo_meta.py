#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Title и description для всех страниц на трёх языках + факты проектов.

  python3 scripts/seo_meta.py

• Проекты: из таблицы PROJECTS (тип объекта, площадь, город, особенность).
  Город указывается только там, где он назван явно; Варшава — только у двух
  явно варшавских проектов. Те же данные идут в «штамп» на странице проекта
  (content/projects-overrides.json) и в подписи карточек (content/projects.json).
• Кухни: номер модели + цвет/стиль/форма из английского адреса.
• Остальные страницы: тексты в MANUAL.
Лимиты: title ≤ 60, description ≤ 155 символов; скрипт остановится, если что-то длиннее
или повторяется.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = os.path.join(ROOT, "content")
LANGS = ("ru", "ua", "en")
BRAND = "DUMSKAYA DESIGN"
T_MAX, D_MAX = 60, 155

# ─── объекты ──────────────────────────────────────────────────────────────
KINDS = {  # именительный, родительный (для «Дизайн ...»)
    "apt": {"ru": ("Квартира", "квартиры"), "ua": ("Квартира", "квартири"), "en": ("Apartment", "apartment")},
    "apt2": {"ru": ("Двухуровневая квартира", "двухуровневой квартиры"), "ua": ("Дворівнева квартира", "дворівневої квартири"), "en": ("Duplex apartment", "duplex apartment")},
    "apt3": {"ru": ("Трёхкомнатная квартира", "трёхкомнатной квартиры"), "ua": ("Трикімнатна квартира", "трикімнатної квартири"), "en": ("Three-room apartment", "three-room apartment")},
    "aparts": {"ru": ("Апартаменты", "апартаментов"), "ua": ("Апартаменти", "апартаментів"), "en": ("Apartment", "apartment")},
    "house": {"ru": ("Частный дом", "частного дома"), "ua": ("Приватний будинок", "приватного будинку"), "en": ("Private house", "private house")},
    "villa": {"ru": ("Вилла", "виллы"), "ua": ("Вілла", "вілли"), "en": ("Villa", "villa")},
    "office": {"ru": ("Офис", "офиса"), "ua": ("Офіс", "офісу"), "en": ("Office", "office")},
    "beauty": {"ru": ("Салон красоты", "салона красоты"), "ua": ("Салон краси", "салону краси"), "en": ("Beauty salon", "beauty salon")},
    "cosmo": {"ru": ("Косметологический салон", "косметологического салона"), "ua": ("Косметологічний салон", "косметологічного салону"), "en": ("Cosmetology salon", "cosmetology salon")},
    "photo": {"ru": ("Фотостудия", "фотостудии"), "ua": ("Фотостудія", "фотостудії"), "en": ("Photo studio", "photo studio")},
    "boutique": {"ru": ("Бутик одежды", "бутика одежды"), "ua": ("Бутик одягу", "бутика одягу"), "en": ("Clothing boutique", "clothing boutique")},
    "sauna": {"ru": ("Баня и сауна", "бани и сауны"), "ua": ("Лазня і сауна", "лазні та сауни"), "en": ("Sauna and bathhouse", "sauna and bathhouse")},
    "shop": {"ru": ("Магазин", "магазина"), "ua": ("Магазин", "магазину"), "en": ("Retail store", "retail store")},
    "cabinet": {"ru": ("Кабинет руководителя", "кабинета руководителя"), "ua": ("Кабінет керівника", "кабінету керівника"), "en": ("Executive office", "executive office")},
}
CITIES = {  # ru: имен., «в ...»; ua; en
    "bratislava": ("Братислава", "в Братиславе", "Братислава", "у Братиславі", "Bratislava", "in Bratislava"),
    "vienna": ("Вена", "в Вене", "Відень", "у Відні", "Vienna", "in Vienna"),
    "kyiv": ("Киев", "в Киеве", "Київ", "у Києві", "Kyiv", "in Kyiv"),
    "kharkiv": ("Харьков", "в Харькове", "Харків", "у Харкові", "Kharkiv", "in Kharkiv"),
    "dunajska": ("Дунайска-Стреда", "в Дунайска-Стреде", "Дунайська-Стреда", "у Дунайській-Стреді", "Dunajská Streda", "in Dunajská Streda"),
    "krakow": ("Краков", "в Кракове", "Краків", "у Кракові", "Kraków", "in Kraków"),
    "warsaw": ("Варшава", "в Варшаве", "Варшава", "у Варшаві", "Warsaw", "in Warsaw"),
    "dubai": ("Дубай", "в Дубае", "Дубай", "у Дубаї", "Dubai", "in Dubai"),
    "la": ("Лос-Анджелес", "в Лос-Анджелесе", "Лос-Анджелес", "у Лос-Анджелесі", "Los Angeles", "in Los Angeles"),
    "prague": ("Прага", "в Праге", "Прага", "у Празі", "Prague", "in Prague"),
    "ny": ("Нью-Йорк", "в Нью-Йорке", "Нью-Йорк", "у Нью-Йорку", "New York", "in New York"),
    "munich": ("Мюнхен", "в Мюнхене", "Мюнхен", "у Мюнхені", "Munich", "in Munich"),
    "berlin": ("Берлин", "в Берлине", "Берлін", "у Берліні", "Berlin", "in Berlin"),
    "london": ("Лондон", "в Лондоне", "Лондон", "у Лондоні", "London", "in London"),
    "madrid": ("Мадрид", "в Мадриде", "Мадрид", "у Мадриді", "Madrid", "in Madrid"),
    "barcelona": ("Барселона", "в Барселоне", "Барселона", "у Барселоні", "Barcelona", "in Barcelona"),
    "varna": ("Варна", "в Варне", "Варна", "у Варні", "Varna", "in Varna"),
    "burgas": ("Бургас", "в Бургасе", "Бургас", "у Бургасі", "Burgas", "in Burgas"),
    "poznan": ("Познань", "в Познани", "Познань", "у Познані", "Poznań", "in Poznań"),
}
EXTRAS = {
    "metropolis": {"ru": "Metropolis", "ua": "Metropolis", "en": "Metropolis"},
    "eurovea": {"ru": "Eurovea City", "ua": "Eurovea City", "en": "Eurovea City"},
    "terrace18": {"ru": "с террасой 18 м²", "ua": "з терасою 18 м²", "en": "with 18 m² terrace"},
    "terrace20": {"ru": "с террасой 20 м²", "ua": "з терасою 20 м²", "en": "with 20 m² terrace"},
    "terrace30": {"ru": "с террасой 30 м²", "ua": "з терасою 30 м²", "en": "with 30 m² terrace"},
    "minimal": {"ru": "минимализм", "ua": "мінімалізм", "en": "minimalist"},
    "classic": {"ru": "современная классика", "ua": "сучасна класика", "en": "modern classic"},
}

# путь (ru) → (тип, площадь, город, особенность)
PROJECTS = {
    "/design-interior-studio-bratislava-metropolis-sk-75m": ("apt", 75, "bratislava", "metropolis"),
    "/studio-interior-design-disain-proekt-kvartira-kiev-80m": ("apt", 80, "kyiv", None),
    "/studio-interior-design-bratislava-eurovea-56m": ("apt", 56, "bratislava", "eurovea"),
    "/interior-design-apartment-bratislava-158m": ("apt2", 158, "bratislava", "terrace20"),
    "/interior-design-private-house-bratislava-120m2": ("house", 120, "bratislava", None),
    "/apartmens-vienna-luxury-interior-design-58m": ("apt", 58, "vienna", None),
    "/interior-design-private-house-dunajska-streda-140m": ("house", 140, "dunajska", None),
    "/interior-design-private-house-kharkiv-212m": ("house", 212, "kharkiv", None),
    "/apartment-interior-design-warsaw-43m2": ("apt", 43, "warsaw", "minimal"),
    "/apartment-interior-design-krakow-63m": ("apt", 63, "krakow", None),
    "/apartment-interior-design-60m": ("apt", 60, None, "terrace18"),
    "/apartment-interior-design-54m": ("apt", 54, None, None),
    "/apartment-furniture-interior-design-45m": ("apt", 45, None, None),
    "/apartment-interior-design-48m": ("apt", 48, None, None),
    "/apartment-interior-design-bratislava-58m": ("apt", 58, "bratislava", None),
    "/apartment-interior-design-52m": ("apt", 52, None, None),
    "/apartment-interior-design-warsaw-43m": ("apt", 43, "warsaw", None),
    "/apartment-interior-design-bratislava-52m": ("apt", 52, "bratislava", None),
    "/apartmens-dubai-luxury-interior-design-160": ("aparts", 160, "dubai", None),
    "/apartmens-los-angeles-interior-design-140": ("aparts", 140, "la", None),
    "/apartmens-praha-luxury-interior-design-90m": ("aparts", 90, "prague", None),
    "/apartmens-ny-luxury-interior-design-57m": ("aparts", 57, "ny", None),
    "/apartment-interior-design-krakow-64m": ("apt", 64, "krakow", "minimal"),
    "/dizainer-interierov-kiev": ("house", 217, "kyiv", None),
    "/villa-interior-design-160m": ("house", 160, "munich", None),
    "/interior-design-private-house-215m": ("house", 215, "berlin", None),
    "/interior-design-apartment-luxury-kyiv-119m": ("apt", 119, "kyiv", "terrace30"),
    "/interior-design-furniture-classic-120m-london": ("apt", 120, "london", "classic"),
    "/apartment-luxury-interior-design-madrid-spain-107m": ("aparts", 107, "madrid", None),
    "/luxury-interior-design-barcelona-spain-108m": ("aparts", 108, "barcelona", None),
    "/apartment-interior-design-51m": ("apt", 51, None, None),
    "/apartmens-wien-luxury-interior-design-115m": ("apt", 115, "vienna", None),
    "/interior-design-furniture-60m": ("apt", 60, "varna", None),
    "/interior-design-apartment-ukraine-47m": ("apt3", 47, None, None),
    "/interior-design-villa-179m-madrid-spain": ("villa", 179, "madrid", None),
    "/dumskaya-interior-design-villa-220m": ("villa", 220, "burgas", None),
    "/dumskaya-interior-design-villa-230m": ("house", 230, None, None),
    "/furniture-interior-design-43m": ("apt2", 43, None, None),
    "/interior-design-cosmetology-salon": ("cosmo", 54, None, None),
    "/beauty-salon-interior-design-63m": ("beauty", 63, None, None),
    "/office-interior-design-500m": ("office", 500, None, None),
    "/photo-studio-interior-design-custom-furniture-130m2-bratislava": ("photo", 130, None, None),
    "/clothing-boutique-interior-design-kyiv-140": ("boutique", 140, "kyiv", None),
    "/dizayn-kommercheskogo-interyera-sauna-banya": ("sauna", 120, None, None),
    "/office-interior-design-140m": ("office", 140, None, None),
    "/office-interior-design-53m": ("office", 53, "poznan", None),
    "/boss-office-interior-design": ("cabinet", 7, None, None),
    "/shop-show-room-interior-design-50m": ("shop", 50, None, None),
    "/interior-design-furniture-65m": ("apt", 65, "kharkiv", None),
}

WORKS = {
    "design": {"ru": "дизайн-проект", "ua": "дизайн-проєкт", "en": "design project"},
    "viz": {"ru": "3D-визуализация", "ua": "3D-візуалізація", "en": "3D visualization"},
    "furn": {"ru": "мебель на заказ", "ua": "меблі на замовлення", "en": "custom furniture"},
    "reno": {"ru": "ремонт под ключ", "ua": "ремонт під ключ", "en": "turnkey renovation"},
}
JOIN = {"ru": " и ", "ua": " та ", "en": " and "}
STUDIO = {
    "ru": f"Студия {BRAND} в Братиславе и Вене",
    "ua": f"Студія {BRAND} у Братиславі та Відні",
    "en": f"{BRAND}, Bratislava and Vienna",
}
FREE = {"ru": "бесплатная консультация", "ua": "безкоштовна консультація", "en": "free consultation"}


def city(c, lang, form):
    if not c:
        return ""
    t = CITIES[c]
    i = {"ru": 0, "ua": 2, "en": 4}[lang] + (1 if form == "in" else 0)
    return t[i]


def m2(lang):
    return "m²" if lang == "en" else "м²"


def listing(items, lang):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + JOIN[lang] + items[-1]


def project_meta(path, lang, works):
    kind, area, c, extra = PROJECTS[path]
    nom, gen = KINDS[kind][lang]
    ex = EXTRAS[extra][lang] if extra else ""
    cin, cnom = city(c, lang, "in"), city(c, lang, "nom")
    a = f"{area} {m2(lang)}"
    if lang == "en":
        nom_t = " ".join(w if w in ("and", "with", "of") else w[:1].upper() + w[1:] for w in nom.split())
        nom, nom_s = nom_t, nom
        titles = [
            f"{nom} Interior Design {a}{' ' + cin if cin else ''} | {BRAND}",
            f"{nom} Design {a}{', ' + cnom if cnom else ''} | {BRAND}",
            f"{nom} Interior Design {a}{' ' + cin if cin else ''}",
        ]
        if ex:
            titles.insert(0, f"{nom} Interior Design {a}, {ex} | {BRAND}" if not cin else f"{nom} Design {a} {cin}, {ex}")
    else:
        word = "Дизайн" if lang == "ru" else "Дизайн"
        titles = [
            f"{word} {gen} {a}{' ' + cin if cin else ''} | {BRAND}",
            f"{word} {gen} {a}{', ' + cnom if cnom else ''} | {BRAND}",
            f"{word} {gen} {a}{' ' + cin if cin else ''}",
        ]
        if ex:
            titles.insert(0, f"{word} {gen} {a}{' ' + cin if cin else ''}, {ex} | {BRAND}")
            titles.insert(1, f"{word} {gen} {a}{' ' + cin if cin else ''}, {ex}")
    title = next(t for t in titles if len(t) <= T_MAX)
    w = [WORKS[k][lang] for k in works]
    if lang == "en":
        nom = nom_s
        adj = f"{ex} " if extra in ("minimal", "classic") else ""
        after = f" {ex}" if extra and extra.startswith("terrace") else ""
        named = f" ({ex})" if extra in ("metropolis", "eurovea") else ""
        head = f"{a} {adj}{gen}{named}{after}{' ' + cin if cin else ''}"
    else:
        head = f"{nom} {a}{' ' + cin if cin else ''}{', ' + ex if ex and extra not in ('metropolis', 'eurovea') else ''}"
        if extra in ("metropolis", "eurovea"):
            head = f"{nom} {a} ({ex}){' ' + cin if cin else ''}"
    variants = [
        f"{head}: {listing(w, lang)}. {STUDIO[lang]} — {FREE[lang]}.",
        f"{head}: {listing(w, lang)}. {STUDIO[lang]}.",
        f"{head}: {listing(w[:3], lang)}. {STUDIO[lang]}.",
        f"{head}: {listing(w[:2], lang)}. {STUDIO[lang]}.",
        f"{head}: {listing(w, lang)}. {BRAND}.",
    ]
    desc = next(d for d in variants if len(d) <= D_MAX)
    desc = desc[0].upper() + desc[1:]
    caption = f"{nom}{' ' + ex if extra in ('metropolis', 'eurovea') else ''}{' ' + cin if cin else ''}, {a}"
    facts = {"object": nom, "area": a}
    if cnom:
        facts["city"] = cnom
    if ex and extra not in ("metropolis", "eurovea"):
        facts["object"] = f"{nom}, {ex}" if extra in ("minimal", "classic") else f"{nom} {ex}"
    elif ex:
        facts["object"] = f"{nom} {ex}"
    facts["works"] = listing(w, lang)
    facts["works"] = facts["works"][0].upper() + facts["works"][1:]
    return title, desc, caption, facts


# ─── кухни ────────────────────────────────────────────────────────────────
KITCHEN_WORDS = {
    "green": ("зелёная", "зелена", "green"), "beige": ("бежевая", "бежева", "beige"),
    "grey": ("серая", "сіра", "grey"), "gray": ("серая", "сіра", "grey"),
    "white": ("белая", "біла", "white"), "brown": ("коричневая", "коричнева", "brown"),
    "black": ("чёрная", "чорна", "black"), "red": ("красная", "червона", "red"),
    "blue": ("синяя", "синя", "blue"),
    "classic": ("классическая", "класична", "classic"), "minimalist": ("минималистичная", "мінімалістична", "minimalist"),
    "modern": ("современная", "сучасна", "modern"), "loft": ("в стиле лофт", "у стилі лофт", "loft-style"),
    "neoclassical": ("неоклассическая", "неокласична", "neoclassical"),
    "corner": ("угловая", "кутова", "corner"), "straight": ("прямая", "пряма", "straight"),
    "u-shaped": ("П-образная", "П-подібна", "U-shaped"), "l-shaped": ("Г-образная", "Г-подібна", "L-shaped"),
}


def kitchen_meta(en_path, ru_path, lang):
    num = re.search(r"k-?(\d{2})", ru_path).group(1)
    slug = en_path.rsplit("/", 1)[-1]
    tokens = []
    for t in re.findall(r"u-shaped|l-shaped|[a-z]+", slug):
        if t in KITCHEN_WORDS and t not in tokens:
            tokens.append(t)
    i = LANGS.index(lang)
    order = sorted(tokens, key=lambda t: 0 if t in ("modern", "classic", "minimalist", "neoclassical", "loft") else 1 if t in ("green", "beige", "grey", "gray", "white", "brown", "black", "red", "blue") else 2)
    words = [KITCHEN_WORDS[t][i] for t in order]
    style = " ".join(words)
    if lang == "ru":
        title = f"Кухня на заказ K-{num}: {style} | {BRAND}"
        desc = f"Кухня K-{num} — {style}. Проект по вашим размерам, изготовление и монтаж в Братиславе и Вене. Расчёт цены и {FREE[lang]}."
    elif lang == "ua":
        title = f"Кухня на замовлення K-{num}: {style} | {BRAND}"
        desc = f"Кухня K-{num} — {style}. Проєкт за вашими розмірами, виготовлення та монтаж у Братиславі й Відні. Розрахунок ціни та {FREE[lang]}."
    else:
        style_t = " ".join(w[:1].upper() + w[1:] for w in words)
        title = f"Custom Kitchen K-{num}: {style_t} | {BRAND}"
        desc = f"Kitchen K-{num}, {style}. Made to your measurements, manufactured and installed in Bratislava and Vienna. Get a price quote and a {FREE[lang]}."
    for cut in (f" | {BRAND}",):
        if len(title) > T_MAX:
            title = title.replace(cut, "")
    if len(desc) > D_MAX:
        desc = desc.replace(f" Расчёт цены и {FREE['ru']}.", f" Расчёт цены бесплатно.").replace(
            f" Розрахунок ціни та {FREE['ua']}.", " Розрахунок ціни безкоштовно.").replace(
            f" Get a price quote and a {FREE['en']}.", " Free price quote.")
    return title, desc


# ─── остальные страницы ───────────────────────────────────────────────────
M = {}


def add(ru_path, ru, ua, en):
    M[ru_path] = {"ru": ru, "ua": ua, "en": en}


add("/",
    ("Дизайн интерьера в Братиславе и Вене | DUMSKAYA DESIGN",
     "Студия DUMSKAYA DESIGN: дизайн интерьера квартир, домов и офисов, мебель на заказ и ремонт под ключ в Братиславе и Вене. Бесплатная консультация."),
    ("Дизайн інтер’єру у Братиславі та Відні | DUMSKAYA DESIGN",
     "Студія DUMSKAYA DESIGN: дизайн інтер’єру квартир, будинків і офісів, меблі на замовлення та ремонт під ключ у Братиславі й Відні. Консультація безкоштовно."),
    ("Interior Design in Bratislava & Vienna | DUMSKAYA DESIGN",
     "DUMSKAYA DESIGN: interior design for apartments, houses and offices, custom furniture and turnkey renovation in Bratislava and Vienna. Free consultation."))
add("/proekty-interior-design",
    ("Портфолио: проекты дизайна интерьера | DUMSKAYA DESIGN",
     "Проекты студии DUMSKAYA DESIGN: квартиры, частные дома, виллы, офисы и салоны. Фото и 3D-визуализации интерьеров. Студия в Братиславе и Вене."),
    ("Портфоліо: проєкти дизайну інтер’єру | DUMSKAYA DESIGN",
     "Проєкти студії DUMSKAYA DESIGN: квартири, приватні будинки, вілли, офіси та салони. Фото й 3D-візуалізації інтер’єрів. Студія у Братиславі та Відні."),
    ("Interior Design Portfolio | DUMSKAYA DESIGN",
     "Projects by DUMSKAYA DESIGN: apartments, private houses, villas, offices and salons. Photos and 3D visualizations. Studio in Bratislava and Vienna."))
add("/contact-studio-interior-design-bratislava-vienna",
    ("Контакты DUMSKAYA DESIGN — Братислава и Вена",
     "Телефоны в Братиславе и Вене, e-mail и форма заявки. Бесплатная консультация по дизайну интерьера, мебели на заказ и ремонту под ключ."),
    ("Контакти DUMSKAYA DESIGN — Братислава і Відень",
     "Телефони у Братиславі та Відні, e-mail і форма заявки. Безкоштовна консультація з дизайну інтер’єру, меблів на замовлення та ремонту під ключ."),
    ("Contact DUMSKAYA DESIGN — Bratislava & Vienna",
     "Phone numbers in Bratislava and Vienna, e-mail and enquiry form. Free consultation on interior design, custom furniture and turnkey renovation."))
add("/price-interior-design-bratislava-wien-praha",
    ("Цены на дизайн интерьера: пакеты от 20 €/м² | DUMSKAYA",
     "Пакеты дизайна интерьера: Экспресс 20 €/м², Базовый и Мебель 35–45 €/м², Премиум 50 €/м², Премиум+ 70 €/м². Братислава и Вена, консультация бесплатно."),
    ("Ціни на дизайн інтер’єру: пакети від 20 €/м² | DUMSKAYA",
     "Пакети дизайну інтер’єру: Експрес 20 €/м², Базовий і Меблі 35–45 €/м², Преміум 50 €/м², Преміум+ 70 €/м². Братислава й Відень, консультація безкоштовно."),
    ("Interior Design Prices: Packages from €20/m² | DUMSKAYA",
     "Interior design packages: Express €20/m², Basic and Furniture €35–45/m², Premium €50/m², Premium+ €70/m². Bratislava and Vienna, free consultation."))
add("/express-interior-design-package-bratislava-vienna",
    ("Дизайн-пакет «Экспресс» — 20 €/м² | DUMSKAYA DESIGN",
     "Быстрый дизайн интерьера от 14 дней: планировка, расстановка мебели и подбор материалов. 20 €/м², от 1 500 €. Братислава и Вена."),
    ("Дизайн-пакет «Експрес» — 20 €/м² | DUMSKAYA DESIGN",
     "Швидкий дизайн інтер’єру від 14 днів: планування, розстановка меблів і підбір матеріалів. 20 €/м², від 1 500 €. Братислава та Відень."),
    ("Express Interior Design Package — €20/m² | DUMSKAYA DESIGN",
     "Fast interior design from 14 days: layout, furniture plan and choice of materials. €20/m², from €1,500. Bratislava and Vienna."))
add("/custom-furniture-bratislava-design-production",
    ("Дизайн-пакет «Мебель» — 35–45 €/м² | DUMSKAYA DESIGN",
     "Проект и изготовление мебели на заказ: кухни, шкафы, гардеробные, мебель для офиса. 35–45 €/м², от 2 000 €. Братислава и Вена."),
    ("Дизайн-пакет «Меблі» — 35–45 €/м² | DUMSKAYA DESIGN",
     "Проєкт і виготовлення меблів на замовлення: кухні, шафи, гардеробні, меблі для офісу. 35–45 €/м², від 2 000 €. Братислава та Відень."),
    ("Furniture Design Package — €35–45/m² | DUMSKAYA DESIGN",
     "Design and production of custom furniture: kitchens, wardrobes, walk-in closets, office furniture. €35–45/m², from €2,000. Bratislava and Vienna."))
add("/basic-interior-design-package-bratislava-vienna",
    ("Дизайн-пакет «Базовый» — 35–45 €/м² | DUMSKAYA DESIGN",
     "Полный дизайн-проект интерьера: планировка, 3D-визуализация, рабочие чертежи и спецификации. 35–45 €/м², от 2 000 €. Братислава и Вена."),
    ("Дизайн-пакет «Базовий» — 35–45 €/м² | DUMSKAYA DESIGN",
     "Повний дизайн-проєкт інтер’єру: планування, 3D-візуалізація, робочі креслення та специфікації. 35–45 €/м², від 2 000 €. Братислава та Відень."),
    ("Basic Interior Design Package — €35–45/m² | DUMSKAYA DESIGN",
     "Complete interior design project: layout, 3D visualization, working drawings and specifications. €35–45/m², from €2,000. Bratislava and Vienna."))
add("/premium-interior-design-package-bratislava-vienna",
    ("Дизайн-пакет «Премиум» — 50 €/м² | DUMSKAYA DESIGN",
     "Расширенный дизайн-проект интерьера с детальной проработкой мебели, освещения и материалов. 50 €/м², от 2 500 €. Братислава и Вена."),
    ("Дизайн-пакет «Преміум» — 50 €/м² | DUMSKAYA DESIGN",
     "Розширений дизайн-проєкт інтер’єру з детальним опрацюванням меблів, освітлення та матеріалів. 50 €/м², від 2 500 €. Братислава та Відень."),
    ("Premium Interior Design Package — €50/m² | DUMSKAYA DESIGN",
     "Extended interior design project with detailed furniture, lighting and materials. €50/m², from €2,500. Bratislava and Vienna."))
add("/premium-plus-interior-design-package-bratislava-vienna",
    ("Дизайн-пакет «Премиум+» — 70 €/м² | DUMSKAYA DESIGN",
     "Дизайн-проект с авторским надзором и сопровождением ремонта до сдачи объекта. 70 €/м², от 3 500 €. Братислава и Вена."),
    ("Дизайн-пакет «Преміум+» — 70 €/м² | DUMSKAYA DESIGN",
     "Дизайн-проєкт з авторським наглядом і супроводом ремонту до здачі об’єкта. 70 €/м², від 3 500 €. Братислава та Відень."),
    ("Premium+ Interior Design Package — €70/m² | DUMSKAYA DESIGN",
     "Design project with designer supervision and renovation management until handover. €70/m², from €3,500. Bratislava and Vienna."))
add("/interior-design-apartmens-bratislava",
    ("Дизайн интерьера квартир и домов в Братиславе | DUMSKAYA",
     "Дизайн жилых интерьеров: квартиры, частные дома и виллы. Планировка, 3D-визуализация, мебель на заказ и ремонт под ключ в Братиславе и Вене."),
    ("Дизайн інтер’єру квартир і будинків у Братиславі | DUMSKAYA",
     "Дизайн житлових інтер’єрів: квартири, приватні будинки та вілли. Планування, 3D-візуалізація, меблі на замовлення та ремонт під ключ у Братиславі й Відні."),
    ("Residential Interior Design in Bratislava | DUMSKAYA DESIGN",
     "Interior design for apartments, private houses and villas: layout, 3D visualization, custom furniture and turnkey renovation in Bratislava and Vienna."))
add("/interior-design-office-bratislava-wien",
    ("Дизайн коммерческих интерьеров в Братиславе | DUMSKAYA",
     "Дизайн офисов, салонов, магазинов и бутиков: проект, 3D-визуализация и мебель для бизнеса на заказ. Братислава и Вена, бесплатная консультация."),
    ("Дизайн комерційних інтер’єрів у Братиславі | DUMSKAYA",
     "Дизайн офісів, салонів, магазинів і бутиків: проєкт, 3D-візуалізація та меблі для бізнесу на замовлення. Братислава й Відень, консультація безкоштовно."),
    ("Commercial Interior Design in Bratislava | DUMSKAYA DESIGN",
     "Design of offices, salons, shops and boutiques: project, 3D visualization and custom business furniture. Bratislava and Vienna, free consultation."))
add("/kuhni-shkafi-bratislava",
    ("Мебель на заказ в Братиславе и Вене | DUMSKAYA DESIGN",
     "Проектирование и изготовление мебели на заказ: кухни, шкафы, гардеробные, прихожие и кабинеты. Замер, производство и монтаж в Братиславе и Вене."),
    ("Меблі на замовлення у Братиславі та Відні | DUMSKAYA DESIGN",
     "Проєктування й виготовлення меблів на замовлення: кухні, шафи, гардеробні, передпокої та кабінети. Замір, виробництво й монтаж у Братиславі та Відні."),
    ("Custom Furniture in Bratislava & Vienna | DUMSKAYA DESIGN",
     "Design and production of custom furniture: kitchens, wardrobes, walk-in closets, hallways and studies. Measuring, manufacturing and installation."))
add("/izgotovlenie-mebeli-pod-zakaz-dlya-kommercheskih-obektov-ofis-resepshen-peregovornaya-kabinet-kuhnya-bratislava",
    ("Мебель для офиса и бизнеса на заказ | DUMSKAYA DESIGN",
     "Мебель на заказ для офисов, ресепшн, переговорных, кабинетов и кухонь персонала. Проект, производство и монтаж в Братиславе и Вене."),
    ("Меблі для офісу та бізнесу на замовлення | DUMSKAYA DESIGN",
     "Меблі на замовлення для офісів, рецепцій, переговорних, кабінетів і кухонь персоналу. Проєкт, виробництво та монтаж у Братиславі й Відні."),
    ("Custom Office & Business Furniture | DUMSKAYA DESIGN",
     "Custom furniture for offices, receptions, meeting rooms and executive offices. Design, production and installation in Bratislava and Vienna."))
add("/kupkuhni-na-zakaz-vienna-bratislava",
    ("Кухни на заказ в Братиславе и Вене — каталог | DUMSKAYA",
     "Каталог кухонь на заказ: современные, классические и минималистичные модели. Проект по вашим размерам, изготовление и монтаж в Братиславе и Вене."),
    ("Кухні на замовлення у Братиславі та Відні — каталог | DUMSKAYA",
     "Каталог кухонь на замовлення: сучасні, класичні та мінімалістичні моделі. Проєкт за вашими розмірами, виготовлення та монтаж у Братиславі й Відні."),
    ("Custom Kitchens in Bratislava & Vienna — Catalog | DUMSKAYA",
     "Catalog of custom kitchens: modern, classic and minimalist models. Designed to your measurements, made and installed in Bratislava and Vienna."))
add("/kuhni-na-zakaz-bratislava",
    ("Кухни на заказ в Братиславе | DUMSKAYA DESIGN",
     "Дизайн, проектирование и изготовление кухонь на заказ в Братиславе: планировка, 3D-визуализация, производство и монтаж. Бесплатная консультация."),
    ("Кухні на замовлення у Братиславі | DUMSKAYA DESIGN",
     "Дизайн, проєктування та виготовлення кухонь на замовлення у Братиславі: планування, 3D-візуалізація, виробництво й монтаж. Консультація безкоштовно."),
    ("Custom Kitchens in Bratislava | DUMSKAYA DESIGN",
     "Design and manufacture of custom kitchens in Bratislava: layout, 3D visualization, production and installation. Free consultation."))
add("/stroitelstvo-remont-bratislava",
    ("Ремонт квартир и домов под ключ в Братиславе | DUMSKAYA",
     "Ремонт под ключ в Братиславе и Вене: квартиры, дома и коммерческие помещения. Дизайн-проект, смета, отделка, мебель и сдача объекта — одна команда."),
    ("Ремонт квартир і будинків під ключ у Братиславі | DUMSKAYA",
     "Ремонт під ключ у Братиславі та Відні: квартири, будинки й комерційні приміщення. Дизайн-проєкт, кошторис, оздоблення, меблі та здача об’єкта."),
    ("Turnkey Renovation in Bratislava & Vienna | DUMSKAYA DESIGN",
     "Turnkey renovation of apartments, houses and commercial spaces in Bratislava and Vienna: design, cost estimate, finishing, furniture and handover."))
add("/smeta-na-remont-bratislava-vienna",
    ("Смета на ремонт в Братиславе и Вене — 5 €/м² | DUMSKAYA",
     "Подробная смета на ремонт квартиры или дома: работы, материалы, мебель и техника. 5 €/м² площади объекта. Братислава и Вена."),
    ("Кошторис на ремонт у Братиславі та Відні — 5 €/м² | DUMSKAYA",
     "Детальний кошторис ремонту квартири чи будинку: роботи, матеріали, меблі та техніка. 5 €/м² площі об’єкта. Братислава та Відень."),
    ("Renovation Cost Estimate — €5/m² | DUMSKAYA DESIGN",
     "Detailed renovation cost estimate for an apartment or house: works, materials, furniture and appliances. €5/m² of floor area. Bratislava and Vienna."))
add("/priemka-kvartiry-ot-zastrojshchika",
    ("Приемка квартиры от застройщика в Братиславе — от 250 €",
     "Проверка новой квартиры перед подписанием акта: дефекты, геометрия, инженерия, акт замечаний. До 50 м² — 250 €, больше — 400 €. Братислава."),
    ("Приймання квартири від забудовника у Братиславі — від 250 €",
     "Перевірка нової квартири перед підписанням акта: дефекти, геометрія, інженерія, акт зауважень. До 50 м² — 250 €, більше — 400 €. Братислава."),
    ("New Apartment Handover Inspection in Bratislava — from €250",
     "Inspection of a new apartment before signing the handover: defects, geometry, utilities and a defect report. Up to 50 m² — €250, larger — €400."))
add("/architecture-design-bratislava",
    ("Архитектура и проектирование в Братиславе | DUMSKAYA",
     "Архитектурные проекты частных домов, фасадов и малых форм: эскиз, 3D-визуализация, рабочая документация. Братислава и Вена."),
    ("Архітектура та проєктування у Братиславі | DUMSKAYA DESIGN",
     "Архітектурні проєкти приватних будинків, фасадів і малих форм: ескіз, 3D-візуалізація, робоча документація. Братислава та Відень."),
    ("Architecture & Design in Bratislava | DUMSKAYA DESIGN",
     "Architectural design of private houses, facades and garden structures: concept, 3D visualization and working drawings. Bratislava and Vienna."))
add("/3d-vizualizaciya-fasada-zdaniya-cena",
    ("3D-визуализация фасада: цены от 75 € | DUMSKAYA DESIGN",
     "Фотореалистичная 3D-визуализация фасада здания и экстерьера: от 75 до 375 € в зависимости от сложности. Сроки и правки — на странице."),
    ("3D-візуалізація фасаду: ціни від 75 € | DUMSKAYA DESIGN",
     "Фотореалістична 3D-візуалізація фасаду будівлі та екстер’єру: від 75 до 375 € залежно від складності. Терміни та правки — на сторінці."),
    ("3D Facade Visualization: Prices from €75 | DUMSKAYA DESIGN",
     "Photorealistic 3D visualization of building facades and exteriors: €75–375 depending on complexity. Timing and revisions explained."))
add("/3d-architecture-bratislava",
    ("Эскизный проект с 3D-визуализацией фасадов | DUMSKAYA",
     "Эскизный архитектурный проект здания с 3D-визуализацией фасадов и окружения: объём, материалы, озеленение. Студия в Братиславе и Вене."),
    ("Ескізний проєкт з 3D-візуалізацією фасадів | DUMSKAYA",
     "Ескізний архітектурний проєкт будівлі з 3D-візуалізацією фасадів і оточення: об’єм, матеріали, озеленення. Студія у Братиславі та Відні."),
    ("Concept Design with 3D Facade Visualization | DUMSKAYA",
     "Architectural concept design with 3D visualization of facades and surroundings: massing, materials and landscaping. Studio in Bratislava and Vienna."))
add("/furniture-private-house-design",
    ("Мебель на заказ и ремонт частного дома | DUMSKAYA DESIGN",
     "Проект студии DUMSKAYA DESIGN: дизайн и производство мебели на заказ и ремонт частного дома под ключ. Фото реализованного объекта."),
    ("Меблі на замовлення та ремонт приватного будинку | DUMSKAYA",
     "Проєкт студії DUMSKAYA DESIGN: дизайн і виробництво меблів на замовлення та ремонт приватного будинку під ключ. Фото реалізованого об’єкта."),
    ("Custom Furniture & Private House Renovation | DUMSKAYA",
     "A DUMSKAYA DESIGN project: design and production of custom furniture and turnkey renovation of a private house. Photos of the completed project."))
add("/interior-custom-furniture-project-usa",
    ("Мебель и меблировка под ключ для клиентов в США | DUMSKAYA",
     "Меблирование жилых и коммерческих объектов в США: проект, производство мебели в Европе, доставка и монтаж. Нью-Йорк, Лос-Анджелес, Майами."),
    ("Меблювання під ключ для клієнтів у США | DUMSKAYA DESIGN",
     "Меблювання житлових і комерційних об’єктів у США: проєкт, виробництво меблів у Європі, доставка та монтаж. Нью-Йорк, Лос-Анджелес, Маямі."),
    ("Turnkey Custom Furniture for US Clients | DUMSKAYA DESIGN",
     "Furnishing homes and commercial spaces in the USA: design, furniture made in Europe, delivery and installation. New York, Los Angeles, Miami."))
add("/why-you-need-an-interior-designer",
    ("Зачем нужен дизайнер интерьера — DUMSKAYA DESIGN",
     "Как дизайнер интерьера экономит бюджет и время, помогает избежать ошибок ремонта и создать функциональное пространство. Советы студии DUMSKAYA DESIGN."),
    ("Навіщо потрібен дизайнер інтер’єру — DUMSKAYA DESIGN",
     "Як дизайнер інтер’єру заощаджує бюджет і час, допомагає уникнути помилок ремонту та створити функціональний простір. Поради студії DUMSKAYA DESIGN."),
    ("Why Hire an Interior Designer — DUMSKAYA DESIGN",
     "How an interior designer saves budget and time, prevents renovation mistakes and creates a functional space. Advice from DUMSKAYA DESIGN."))
add("/kak-pravilno-organizovat-rabochee-mesto-v-spalne",
    ("Рабочее место в спальне: как организовать | DUMSKAYA",
     "Как разместить рабочее место в спальне: зонирование, освещение, мебель на заказ и хранение. Практические советы дизайнера интерьера."),
    ("Робоче місце у спальні: як організувати | DUMSKAYA DESIGN",
     "Як облаштувати робоче місце у спальні: зонування, освітлення, меблі на замовлення та зберігання. Практичні поради дизайнера інтер’єру."),
    ("Home Office in the Bedroom: How to Plan It | DUMSKAYA",
     "How to fit a workspace into a bedroom: zoning, lighting, custom furniture and storage. Practical advice from an interior designer."))
add("/kak-pravilno-organizovat-svoj-sanuzel",
    ("Как организовать санузел: советы дизайнера | DUMSKAYA",
     "Планировка санузла и ванной: размещение сантехники, хранение, освещение и материалы. Практические советы дизайнера интерьера DUMSKAYA DESIGN."),
    ("Як організувати санвузол: поради дизайнера | DUMSKAYA",
     "Планування санвузла й ванної: розміщення сантехніки, зберігання, освітлення та матеріали. Практичні поради дизайнера інтер’єру DUMSKAYA DESIGN."),
    ("Small Bathroom Layout: Designer Tips | DUMSKAYA DESIGN",
     "Planning a bathroom: placement of fixtures, storage, lighting and materials. Practical advice from interior designer DUMSKAYA DESIGN."))
add("/kak-pravilno-organizovat-udobnuyu-i-funkcionalnuyu-kuhnyu",
    ("Как спланировать удобную кухню: правила | DUMSKAYA",
     "Рабочий треугольник, зоны хранения, расстояния и освещение: как спланировать удобную и функциональную кухню. Советы дизайнера интерьера."),
    ("Як спланувати зручну кухню: правила | DUMSKAYA DESIGN",
     "Робочий трикутник, зони зберігання, відстані та освітлення: як спланувати зручну й функціональну кухню. Поради дизайнера інтер’єру."),
    ("Kitchen Layout Rules: Plan a Functional Kitchen | DUMSKAYA",
     "Work triangle, storage zones, clearances and lighting: how to plan a comfortable, functional kitchen. Advice from an interior designer."))
add("/kak-pravilno-organizovat-udobnyj-i-funkcionalnyj-balkon",
    ("Как обустроить балкон: идеи и советы | DUMSKAYA DESIGN",
     "Как сделать балкон удобным и функциональным: зона отдыха, кабинет или хранение. Мебель, освещение и материалы — советы дизайнера интерьера."),
    ("Як облаштувати балкон: ідеї та поради | DUMSKAYA DESIGN",
     "Як зробити балкон зручним і функціональним: зона відпочинку, кабінет чи зберігання. Меблі, освітлення й матеріали — поради дизайнера інтер’єру."),
    ("Balcony Design: Ideas and Tips | DUMSKAYA DESIGN",
     "How to make a balcony comfortable and functional: a lounge, a study or storage. Furniture, lighting and materials — advice from an interior designer."))
add("/osnovnye-principy-i-pravila-pri-proektirovanie-dizajna-interera-detskoj-komnaty",
    ("Дизайн детской комнаты: принципы и правила | DUMSKAYA",
     "Как спроектировать детскую: безопасность, зонирование, мебель на вырост, свет и цвет. Основные правила от дизайнера интерьера DUMSKAYA DESIGN."),
    ("Дизайн дитячої кімнати: принципи та правила | DUMSKAYA",
     "Як спроєктувати дитячу: безпека, зонування, меблі на виріст, світло й колір. Основні правила від дизайнера інтер’єру DUMSKAYA DESIGN."),
    ("Children's Room Design: Key Principles | DUMSKAYA DESIGN",
     "How to design a child's room: safety, zoning, furniture that grows with the child, light and colour. Key rules from DUMSKAYA DESIGN."))
add("/transformaciya-malenkoj-kvartiry-prakticheskie-sovety-dlya-maksimalnogo-ispolzovaniya-prostranstva",
    ("Дизайн маленькой квартиры: практические советы | DUMSKAYA",
     "Как использовать каждый метр маленькой квартиры: планировка, встроенная мебель, хранение, свет и цвет. Практические советы дизайнера интерьера."),
    ("Дизайн малогабаритної квартири: практичні поради | DUMSKAYA",
     "Як використати кожен метр маленької квартири: планування, вбудовані меблі, зберігання, світло й колір. Практичні поради дизайнера інтер’єру."),
    ("Small Apartment Design: Practical Tips | DUMSKAYA DESIGN",
     "How to use every square metre of a small apartment: layout, built-in furniture, storage, light and colour. Practical advice from an interior designer."))
add("/architecture-villa-spain-marbella",
    ("Архитектурное решение фасада виллы, Марбелья | DUMSKAYA",
     "Проект реконструкции фасада виллы в Марбелье, Испания: архитектурное решение и 3D-визуализация. Студия DUMSKAYA DESIGN в Братиславе и Вене."),
    ("Архітектурне рішення фасаду вілли, Марбелья | DUMSKAYA",
     "Проєкт реконструкції фасаду вілли в Марбельї, Іспанія: архітектурне рішення та 3D-візуалізація. Студія DUMSKAYA DESIGN у Братиславі та Відні."),
    ("Villa Facade Redesign, Marbella | DUMSKAYA DESIGN",
     "Facade reconstruction project for a villa in Marbella, Spain: architectural solution and 3D visualization. DUMSKAYA DESIGN, Bratislava and Vienna."))
add("/3d-vizualizaciya-fasada-bratislava",
    ("3D-визуализация фасада частного дома | DUMSKAYA DESIGN",
     "Эскизный проект фасада частного дома и озеленения участка с фотореалистичной 3D-визуализацией. Студия DUMSKAYA DESIGN в Братиславе и Вене."),
    ("3D-візуалізація фасаду приватного будинку | DUMSKAYA",
     "Ескізний проєкт фасаду приватного будинку та озеленення ділянки з фотореалістичною 3D-візуалізацією. Студія DUMSKAYA DESIGN у Братиславі та Відні."),
    ("3D Visualization of a Private House Facade | DUMSKAYA",
     "Concept design of a private house facade and landscaping with photorealistic 3D visualization. DUMSKAYA DESIGN, Bratislava and Vienna."))
add("/architecture-private-house",
    ("Архитектурный проект фасадов частного дома | DUMSKAYA",
     "Архитектурный проект фасадов частного дома: решение фасадов, материалы и 3D-визуализация. Студия DUMSKAYA DESIGN в Братиславе и Вене."),
    ("Архітектурний проєкт фасадів приватного будинку | DUMSKAYA",
     "Архітектурний проєкт фасадів приватного будинку: рішення фасадів, матеріали та 3D-візуалізація. Студія DUMSKAYA DESIGN у Братиславі та Відні."),
    ("Private House Facade Design | DUMSKAYA DESIGN",
     "Architectural facade design for a private house: facade solution, materials and 3D visualization. DUMSKAYA DESIGN, Bratislava and Vienna."))
add("/architecture-facade-barbershop-kyiv",
    ("Фасад барбершопа в Киеве — архитектурное решение | DUMSKAYA",
     "Архитектурное решение фасада барбершопа в Киеве: концепция, материалы, вывеска и 3D-визуализация. Студия DUMSKAYA DESIGN."),
    ("Фасад барбершопу в Києві — архітектурне рішення | DUMSKAYA",
     "Архітектурне рішення фасаду барбершопу в Києві: концепція, матеріали, вивіска та 3D-візуалізація. Студія DUMSKAYA DESIGN."),
    ("Barbershop Facade Design in Kyiv | DUMSKAYA DESIGN",
     "Architectural facade design for a barbershop in Kyiv: concept, materials, signage and 3D visualization. DUMSKAYA DESIGN."))
add("/architecture-gazebo-pergola",
    ("Беседка с перголой: проект и реализация | DUMSKAYA",
     "Проект эксклюзивной беседки с перголой — от 3D-визуализации до реализации на участке. Архитектура малых форм от студии DUMSKAYA DESIGN."),
    ("Альтанка з перголою: проєкт і реалізація | DUMSKAYA DESIGN",
     "Проєкт ексклюзивної альтанки з перголою — від 3D-візуалізації до реалізації на ділянці. Архітектура малих форм від студії DUMSKAYA DESIGN."),
    ("Gazebo with Pergola: Design and Build | DUMSKAYA DESIGN",
     "An exclusive gazebo with a pergola — from 3D visualization to construction on site. Garden architecture by DUMSKAYA DESIGN."))
add("/shop",
    ("Магазин мебели DUMSKAYA DESIGN — офисная мебель",
     "Мебель для кабинета руководителя из коллекции Executive Desk: столы, шкафы и стол для переговоров. Производство в Европе, доставка по Словакии и Австрии."),
    ("Магазин меблів DUMSKAYA DESIGN — офісні меблі",
     "Меблі для кабінету керівника з колекції Executive Desk: столи, шафи та стіл для переговорів. Виробництво в Європі, доставка Словаччиною та Австрією."),
    ("DUMSKAYA DESIGN Furniture Shop — Office Furniture",
     "Executive office furniture from the Executive Desk collection: desks, cabinets and a conference table. Made in Europe, delivery in Slovakia and Austria."))
add("/shop/cat/ofisnaya-mebel",
    ("Офисная мебель Executive Desk 2025 | DUMSKAYA DESIGN",
     "Коллекция Executive Desk 2025: столы руководителя трёх размеров, шкафы и стол для переговоров. Мебель для кабинета от DUMSKAYA DESIGN."),
    ("Офісні меблі Executive Desk 2025 | DUMSKAYA DESIGN",
     "Колекція Executive Desk 2025: столи керівника трьох розмірів, шафи та стіл для переговорів. Меблі для кабінету від DUMSKAYA DESIGN."),
    ("Executive Desk 2025 Office Furniture | DUMSKAYA DESIGN",
     "The Executive Desk 2025 collection: executive desks in three sizes, cabinets and a conference table. Office furniture by DUMSKAYA DESIGN."))
SHOP = {
    "/shop/executive-desk-boss-s": ("Стол руководителя Boss, размер S", "Стіл керівника Boss, розмір S", "Executive Desk Boss, Size S", "TDD-003"),
    "/shop/executive-desk-boss-m": ("Стол руководителя Boss, размер M", "Стіл керівника Boss, розмір M", "Executive Desk Boss, Size M", "TDD-002"),
    "/shop/executive-desk-boss-l": ("Стол руководителя Boss, размер L", "Стіл керівника Boss, розмір L", "Executive Desk Boss, Size L", "TDD-001"),
    "/shop/executive-conference-table": ("Стол для переговоров Executive", "Стіл для переговорів Executive", "Executive Conference Table", "TDD-004"),
    "/shop/exclusive-executive-office-cabinet": ("Шкаф руководителя Exclusive, XXL", "Шафа керівника Exclusive, XXL", "Exclusive Executive Cabinet, XXL", "TDD-005"),
    "/shop/exclusive-executive-office-cabinet-1": ("Шкаф руководителя Exclusive, S", "Шафа керівника Exclusive, S", "Exclusive Executive Cabinet, Size S", "TDD-006"),
}
for path, (ru, ua, en, code) in SHOP.items():
    add(path,
        (f"{ru} ({code}) | DUMSKAYA DESIGN",
         f"{ru}, артикул {code}, из коллекции Executive Desk 2025 от DUMSKAYA DESIGN. Цена и доставка — по запросу."),
        (f"{ua} ({code}) | DUMSKAYA DESIGN",
         f"{ua}, артикул {code}, з колекції Executive Desk 2025 від DUMSKAYA DESIGN. Ціна та доставка — за запитом."),
        (f"{en} ({code}) | DUMSKAYA DESIGN",
         f"{en}, item {code}, from the Executive Desk 2025 collection by DUMSKAYA DESIGN. Price and delivery on request."))


def fit(t, limit):
    if len(t) <= limit:
        return t
    for cut in (" | DUMSKAYA DESIGN", " | DUMSKAYA", " — DUMSKAYA DESIGN"):
        if t.endswith(cut) and len(t) - len(cut) <= limit:
            return t[: -len(cut)]
    return t


def detect_works(page):
    text = json.dumps(page["sections"], ensure_ascii=False).lower() + " " + page["h1"].lower()
    w = ["design"]
    if "визуализ" in text or "3d" in text:
        w.append("viz")
    if "мебел" in text:
        w.append("furn")
    if "ремонт" in text:
        w.append("reno")
    return w


def main():
    files = glob.glob(os.path.join(C, "pages", "**", "*.json"), recursive=True)
    pages = {}
    for f in files:
        p = json.load(open(f, encoding="utf-8"))
        pages[p["path"]] = (f, p)
    projects = json.load(open(os.path.join(C, "projects.json"), encoding="utf-8"))
    overrides_path = os.path.join(C, "projects-overrides.json")
    overrides = json.load(open(overrides_path, encoding="utf-8")) if os.path.exists(overrides_path) else {}
    missing, done = [], 0
    for path, (f, p) in pages.items():
        lang = p["lang"]
        ru_path = p["alternates"].get("ru") or path
        title = desc = None
        if ru_path in PROJECTS and ru_path in pages:
            works = detect_works(pages[ru_path][1])
            title, desc, caption, facts = project_meta(ru_path, lang, works)
            ov = overrides.setdefault(ru_path, {})
            ov.setdefault("facts", {})[lang] = facts
            ov.setdefault("title", {})[lang] = caption
        elif p["type"] == "kitchen":
            en = p["alternates"].get("en", "")
            title, desc = kitchen_meta(en, ru_path, lang)
        elif ru_path in M:
            title, desc = M[ru_path][lang]
        if title is None:
            if p["type"] != "privacy":
                missing.append(path)
            continue
        p["title"], p["description"] = fit(title, T_MAX), desc
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(p, fh, ensure_ascii=False, indent=1)
        done += 1
    json.dump(overrides, open(overrides_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # проверки
    errs = []
    seen = {}
    for path, (f, _) in pages.items():
        p = json.load(open(f, encoding="utf-8"))
        if len(p["title"]) > T_MAX:
            errs.append(f"title {len(p['title'])}: {path} — {p['title']}")
        if len(p["description"]) > D_MAX:
            errs.append(f"description {len(p['description'])}: {path} — {p['description']}")
        for k in ("title", "description"):
            key = (p["lang"], k, p[k])
            if key in seen:
                errs.append(f"дубль {k}: {path} и {seen[key]}")
            seen[key] = path
    print(f"обновлено страниц: {done}; без мета: {missing}")
    if errs:
        print("\n".join(errs))
        sys.exit(1)


if __name__ == "__main__":
    main()
