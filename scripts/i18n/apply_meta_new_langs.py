#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Словацкая и немецкая версии сайта (23.10.2026): адреса, title/description, проекты, магазин, меню.

Вход: файлы адресов и мета-тегов вида {"/русский-адрес": {"path", "title", "description", "project_title", "facts"}}
(по одному на язык; без аргументов — content/i18n/meta-sk.json и meta-de.json). Меняется только язык из переданных файлов.
Скрипт:
  • прописывает адреса SK/DE в alternates русских страниц (у страниц без перевода — убирает);
  • сохраняет title/description в content/i18n/meta-<lang>.json — их берёт assemble.py;
  • дополняет content/projects.json (адреса, названия, «штамп» проекта);
  • создаёт SK/DE-страницы товаров магазина (как английские, с переведёнными мета-тегами) и связывает языковые версии;
  • строит меню SK и DE в content/site.json.
   python3 scripts/i18n/apply_meta_new_langs.py out-sk.json out-de.json
   python3 scripts/i18n/apply_meta_new_langs.py          (после правки meta-*.json)
"""
import glob, json, os, re, sys, copy

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES = os.path.join(ROOT, 'content/pages')
LANGS = ('sk', 'de')
SLUG = re.compile(r'^/(sk|de)(/[a-z0-9-]+)*$')

meta = {}
args = sys.argv[1:] or [os.path.join(ROOT, 'content/i18n', f'meta-{l}.json') for l in LANGS
                         if os.path.exists(os.path.join(ROOT, 'content/i18n', f'meta-{l}.json'))]
for f in args:
    lang = 'sk' if 'sk' in os.path.basename(f) else 'de'
    meta[lang] = json.load(open(f, encoding='utf-8'))

# проверка: адреса уникальные и по правилам, длины мета-тегов
for lang, m in meta.items():
    seen = {}
    for ru, v in m.items():
        assert SLUG.match(v['path']) and v['path'].startswith(f'/{lang}'), (lang, ru, v['path'])
        assert v['path'] not in seen, (lang, v['path'], ru, seen.get(v['path']))
        seen[v['path']] = ru
        assert 0 < len(v['title']) <= 60, (lang, ru, len(v['title']))
        assert 0 < len(v['description']) <= 155, (lang, ru, len(v['description']))
redirects = json.load(open(os.path.join(ROOT, 'content/redirects.json'), encoding='utf-8'))
for lang, m in meta.items():
    for v in m.values():
        assert v['path'] not in redirects, v['path']


def dump(path, data):
    open(path, 'w', encoding='utf-8').write(json.dumps(data, ensure_ascii=False, indent=1))


def files_of(lang):
    out = {}
    for f in glob.glob(os.path.join(PAGES, lang, '**', '*.json'), recursive=True):
        d = json.load(open(f, encoding='utf-8'))
        out[d['path']] = (f, d)
    return out


ru_pages = files_of('ru')
# 1. адреса SK/DE у русских страниц (верхний уровень — для assemble.py)
for path, (f, d) in ru_pages.items():
    if path.startswith('/shop/'):
        continue
    alt = d['alternates']
    for lang in meta:
        if path in meta[lang]:
            alt[lang] = meta[lang][path]['path']
        else:
            alt.pop(lang, None)
    dump(f, d)

# 2. мета-теги для assemble.py (название и «штамп» проекта, если есть, сохраняются — без них projects.json не пересобрать)
KEEP = ('path', 'title', 'description', 'project_title', 'facts')
for lang, m in meta.items():
    out = {ru: {k: v[k] for k in KEEP if k in v} for ru, v in sorted(m.items())}
    dump(os.path.join(ROOT, 'content/i18n', f'meta-{lang}.json'), out)

# 3. проекты
pp = os.path.join(ROOT, 'content/projects.json')
projects = json.load(open(pp, encoding='utf-8'))
for pr in projects:
    for lang in meta:
        v = meta[lang].get(pr['path'])
        if not v:
            pr['alternates'].pop(lang, None); continue
        pr['alternates'][lang] = v['path']
        if v.get('project_title'):
            pr['title'][lang] = v['project_title']
        if v.get('facts'):
            pr.setdefault('facts', {})[lang] = v['facts']
dump(pp, projects)

# 4. магазин: страницы товаров и раздела (вложенные папки shop/ — их assemble.py не собирает)
en_pages = files_of('en')
for path, (f, d) in ru_pages.items():
    if not path.startswith('/shop/'):
        continue
    for lang in LANGS:
        v = meta.get(lang, {}).get(path)
        if v:
            d['alternates'][lang] = v['path']
    alts = d['alternates']
    dump(f, d)
    en = en_pages.get(alts.get('en'))
    for lang in LANGS:
        v = meta.get(lang, {}).get(path)
        if not v or not en:
            continue
        new = copy.deepcopy(en[1])
        new.update(path=v['path'], lang=lang, title=v['title'], description=v['description'], alternates=alts)
        new['h1'] = re.sub(r'\s*\|\s*DUMSKAYA DESIGN\s*$', '', v['title'])
        name = re.sub(r'\s*\((TDD-\d+)\)$', '', new['h1'])
        # текст карточки товара — только название, артикул и описание; английские кнопки и подписи не переносим
        for sec in new['sections']:
            sec['blocks'] = [b for b in sec['blocks'] if b['type'] != 'buttons']
            for b in sec['blocks']:
                if b['type'] == 'heading':
                    b['text'] = new['h1']
                for n, im in enumerate(b.get('images', [])):
                    im['alt'] = name
        new['sections'] = [sec for sec in new['sections'] if sec['blocks']]
        rel = os.path.relpath(en[0], os.path.join(PAGES, 'en'))
        target = os.path.join(PAGES, lang, os.path.dirname(rel), v['path'].rstrip('/').split('/')[-1] + '.json')
        os.makedirs(os.path.dirname(target), exist_ok=True)
        dump(target, new)
    # у украинской и английской версий — те же языковые пары
    for lang in ('ua', 'en'):
        other = files_of(lang).get(alts.get(lang))
        if other:
            other[1]['alternates'] = alts
            dump(other[0], other[1])

# 5. меню SK и DE
site_p = os.path.join(ROOT, 'content/site.json')
raw = open(site_p, encoding='utf-8').read()
site = json.loads(raw)
LABELS = {
    'sk': {
        '/about-studio': 'O štúdiu', '/proekty-interior-design': 'Portfólio', '/kupkuhni-na-zakaz-vienna-bratislava': 'Kuchyne',
        '/shop': 'Obchod', 'Услуги': 'Služby', 'Советы': 'Tipy', 'Где мы работаем': 'Kde pracujeme', 'Цены': 'Ceny',
        '/contact-studio-interior-design-bratislava-vienna': 'Kontakt',
        '/interior-design-apartments-bratislava|Услуги': 'Dizajn obytných interiérov', '/interior-design-office-bratislava-wien': 'Dizajn komerčných interiérov',
        '/kuhni-shkafi-bratislava': 'Nábytok na mieru',
        '/izgotovlenie-mebeli-pod-zakaz-dlya-kommercheskih-obektov-ofis-resepshen-peregovornaya-kabinet-kuhnya-bratislava': 'Nábytok na mieru pre firmy',
        '/architecture-design-bratislava': 'Architektúra a projektovanie', '/3d-vizualizaciya-fasada-zdaniya-cena': '3D vizualizácia fasád',
        '/priemka-kvartiry-ot-zastrojshchika': 'Preberanie bytu', '/stroitelstvo-remont-bratislava': 'Rekonštrukcia na kľúč',
        '/smeta-na-remont-bratislava-vienna': 'Rozpočet rekonštrukcie',
        '/why-you-need-an-interior-designer': 'Prečo potrebujete interiérového dizajnéra',
        '/kak-pravilno-organizovat-udobnuyu-i-funkcionalnuyu-kuhnyu': 'Rozmiestnenie nábytku v kuchyni',
        '/osnovnye-principy-i-pravila-pri-proektirovanie-dizajna-interera-detskoj-komnaty': 'Návrh detskej izby',
        '/kak-pravilno-organizovat-rabochee-mesto-v-spalne': 'Pracovné miesto v spálni',
        '/transformaciya-malenkoj-kvartiry-prakticheskie-sovety-dlya-maksimalnogo-ispolzovaniya-prostranstva': 'Malé byty',
        '/kak-pravilno-organizovat-svoj-sanuzel': 'Usporiadanie kúpeľne', '/kak-pravilno-organizovat-udobnyj-i-funkcionalnyj-balkon': 'Útulný balkón',
        '/interior-design-apartments-bratislava|Где мы работаем': 'Bratislava', '/dizajn-interera-vena': 'Viedeň',
        '/express-interior-design-package-bratislava-vienna': 'Balík Express', '/custom-furniture-bratislava-design-production': 'Balík Nábytok',
        '/basic-interior-design-package-bratislava-vienna': 'Balík Základný', '/premium-interior-design-package-bratislava-vienna': 'Balík Premium',
        '/premium-plus-interior-design-package-bratislava-vienna': 'Balík Premium+',
    },
    'de': {
        '/about-studio': 'Über das Studio', '/proekty-interior-design': 'Portfolio', '/kupkuhni-na-zakaz-vienna-bratislava': 'Küchen',
        '/shop': 'Shop', 'Услуги': 'Leistungen', 'Советы': 'Tipps', 'Где мы работаем': 'Wo wir arbeiten', 'Цены': 'Preise',
        '/contact-studio-interior-design-bratislava-vienna': 'Kontakt',
        '/interior-design-apartments-bratislava|Услуги': 'Innenarchitektur Wohnen', '/interior-design-office-bratislava-wien': 'Innenarchitektur Gewerbe',
        '/kuhni-shkafi-bratislava': 'Möbel nach Maß',
        '/izgotovlenie-mebeli-pod-zakaz-dlya-kommercheskih-obektov-ofis-resepshen-peregovornaya-kabinet-kuhnya-bratislava': 'Möbel nach Maß für Unternehmen',
        '/architecture-design-bratislava': 'Architektur und Planung', '/3d-vizualizaciya-fasada-zdaniya-cena': '3D-Visualisierung von Fassaden',
        '/priemka-kvartiry-ot-zastrojshchika': 'Wohnungsübergabe', '/stroitelstvo-remont-bratislava': 'Sanierung schlüsselfertig',
        '/smeta-na-remont-bratislava-vienna': 'Kostenschätzung',
        '/why-you-need-an-interior-designer': 'Warum ein Innenarchitekt',
        '/kak-pravilno-organizovat-udobnuyu-i-funkcionalnuyu-kuhnyu': 'Möbel in der Küche anordnen',
        '/osnovnye-principy-i-pravila-pri-proektirovanie-dizajna-interera-detskoj-komnaty': 'Kinderzimmer planen',
        '/kak-pravilno-organizovat-rabochee-mesto-v-spalne': 'Arbeitsplatz im Schlafzimmer',
        '/transformaciya-malenkoj-kvartiry-prakticheskie-sovety-dlya-maksimalnogo-ispolzovaniya-prostranstva': 'Kleine Wohnungen',
        '/kak-pravilno-organizovat-svoj-sanuzel': 'Badezimmer einrichten', '/kak-pravilno-organizovat-udobnyj-i-funkcionalnyj-balkon': 'Balkon gestalten',
        '/interior-design-apartments-bratislava|Где мы работаем': 'Bratislava', '/dizajn-interera-vena': 'Wien', '/dizajn-interera-germaniya': 'Deutschland',
        '/express-interior-design-package-bratislava-vienna': 'Paket Express', '/custom-furniture-bratislava-design-production': 'Paket Möbel',
        '/basic-interior-design-package-bratislava-vienna': 'Paket Basis', '/premium-interior-design-package-bratislava-vienna': 'Paket Premium',
        '/premium-plus-interior-design-package-bratislava-vienna': 'Paket Premium+',
    },
}
ORDER_WHERE = {'sk': ['/interior-design-apartments-bratislava', '/dizajn-interera-vena'],
               'de': ['/dizajn-interera-vena', '/interior-design-apartments-bratislava', '/dizajn-interera-germaniya']}
ru_alt = {p: d['alternates'] for p, (f, d) in files_of('ru').items()}
for lang in LANGS:
    if lang not in meta:
        continue
    L = LABELS[lang]; menu = []
    for item in site['menu']['ru']:
        if item.get('children'):
            group = item['label']
            kids = [c for c in item['children'] if c.get('href') and ru_alt.get(c['href'], {}).get(lang)]
            if group == 'Где мы работаем':
                kids = sorted(kids, key=lambda c: ORDER_WHERE[lang].index(c['href']) if c['href'] in ORDER_WHERE[lang] else 99)
            kids = [{'label': L.get(f"{c['href']}|{group}") or L[c['href']], 'href': ru_alt[c['href']][lang]} for c in kids]
            if kids:
                menu.append({'label': L[group], 'children': kids})
        elif item.get('href') and ru_alt.get(item['href'], {}).get(lang):
            menu.append({'label': L[item['href']], 'href': ru_alt[item['href']][lang]})
    site['menu'][lang] = menu
open(site_p, 'w', encoding='utf-8').write(json.dumps(site, ensure_ascii=False, indent=1) + ('\n' if raw.endswith('\n') else ''))
print('готово:', {l: len(m) for l, m in meta.items()})
