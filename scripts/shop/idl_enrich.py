#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Данные фабрики IDL для карточек товаров: фото, тексты коллекций, видео, свет и чертежи из каталогов.

Источники (content/shop/sources/idl/, собраны с сайта и из PDF фабрики):
  site.json            — страницы коллекций на idl1987.it (ru/en/it): описание, отделки, подписи, видео YouTube,
                         фото коллекции (файлы — в папке выгрузки на Mac: images/shop/idl/<коллекция>/…);
  tech.json            — технические страницы каталогов 2024 и Novelties 2025: источник света, мощность, люмены,
                         диммирование, чертёж с размерами (images/shop/idl/tech/<артикул>.png);
  catalog-photos.json  — фото товара со страницы каталога, где подписан только он (images/shop/idl/catalog/…).
Фото и чертежи лежат в ~/Documents/dumskaya-export/images/shop/idl на Mac (как остальные оригиналы фото сайта),
в git — только сведения о них.

Скрипт дописывает эти данные в content/shop/catalog/idl.json (артикулы, типы и порядок товаров не трогает):
   python3 scripts/shop/idl_enrich.py
Тексты фабрики — исходник для наших описаний, на сайт их дословно не ставим."""
import json, os, re
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, 'content/shop/sources/idl')
CAT = os.path.join(ROOT, 'content/shop/catalog/idl.json')
site = json.load(open(os.path.join(SRC, 'site.json')))
tech = json.load(open(os.path.join(SRC, 'tech.json')))
catph = json.load(open(os.path.join(SRC, 'catalog-photos.json')))
cat = json.load(open(CAT))

DIM = {'A': 'DALI', 'B': 'диммируемый (Dimmable)', 'C': 'диммирование 1–10 В', 'D': 'диммирование по запросу'}
cat['dimming_legend'] = DIM

by_col = defaultdict(list)
for p in cat['products']: by_col[p['collection']].append(p['mfr_code'])


def codes_in_name(url, codes):
    """Артикулы фабрики в имени файла фото: «ACROPORA-650_20-light-gold.jpg» → 650/20.
    Если в имени код без окончания DX/SX (бра «левое/правое»), фото подходит обоим вариантам."""
    name = re.sub(r'-\d{3,4}x\d{3,4}(?=\.)', '', url.rsplit('/', 1)[1].lower())
    found = []
    for code in sorted(codes, key=len, reverse=True):
        num, suf = code.lower().split('/', 1)
        pat = re.escape(suf).replace('\\+', '[+_-]?').replace('/', '[-_]')
        if re.search(rf'(?<![0-9]){num}[-_ ]{pat}(?![0-9a-z])', name) and not any(f.lower().startswith(code.lower()) for f in found):
            found.append(code)
    if not found:
        for m in re.finditer(r'(?<![0-9])(\d{3})[-_ ]([0-9]+[a-z]*)(?![0-9a-z])', name):
            fam = [c for c in codes if c.lower().startswith(f'{m.group(1)}/{m.group(2)}') and c.lower()[len(m.group(1)) + 1 + len(m.group(2)):] in ('dx', 'sx')]
            found += [c for c in fam if c not in found]
    return found


def clean_light(t):
    t = re.sub(r'(\s+(•|\d{1,3}))+$', '', t or '').strip()
    return re.sub(r'\s*\d{4}\s*K$', '', t)


LIGHT = re.compile(r'LED|E14|E27|G9|G4|GU10|R7S|STRIP|Strip')


def parse_tech(v):
    """Строки ячейки каталога → свет: «3 x G9», «MAX 33W», «+ 3 LED x 1 W», «369 lumen», «2700 K», «B - C»."""
    out = {}
    lines = [l for l in v.get('lines', [])[1:] if l.strip() not in ('•', '')]
    parts = []
    for l in lines:
        m = re.match(r'(\d+)\s*LED\s*-?\s*MAX\s*([\d,]+)\s*W', l, re.I)   # «6 LED - MAX 2,3W» — 6 светодиодов по 2,3 Вт
        if m:
            parts.append(f'{m.group(1)} x LED {m.group(2)} W'); continue
        if 'lumen' in l.lower() and not re.search(r'LED\s*\d|x\s*LED', l): continue
        if not LIGHT.search(l): continue
        l = re.sub(r'MAX\s*\d+(?:[.,]\d+)?\s*W', '', l, flags=re.I)
        l = re.sub(r'\d[\d.]*\s*lumen.*$', '', l, flags=re.I)
        l = clean_light(re.sub(r'\s+(and|-)$', '', l.strip()).lstrip('+ ').strip())
        if l and l not in parts: parts.append(l)
    light = ' + '.join(parts) or clean_light(v.get('light', ''))
    text = ' '.join(lines)
    mx = None if re.search(r'\d+\s*LED\s*-?\s*MAX', text, re.I) else re.search(r'MAX\s*\d+(?:[.,]\d+)?\s*W', text, re.I)
    if light: out['light'] = light
    if mx: out['max_power'] = re.sub(r'MAX\s*', 'MAX ', mx.group(0).upper())
    lm = re.search(r'(\d[\d.]*)\s*lumen', text, re.I)
    if lm: out['lumen'] = int(lm.group(1).replace('.', ''))
    k = re.search(r'(?<!\d)(2700|2800|3000|3200|4000)\s*K\b', text)
    if k: out['cct'] = int(k.group(1))
    if re.search(r'doppia accensione|double switch', text, re.I): out['double_switch'] = True
    if re.search(r'ricaricabil|rechargeable|micro usb', text, re.I): out['rechargeable'] = True
    dl = v.get('dimming') or next((re.sub(r'[•\s]', '', l) for l in lines if re.fullmatch(r'[A-D](-[A-D])*', re.sub(r'[•\s]', '', l))), '')
    dim = [x for x in re.split(r'\s*-\s*', dl) if x in DIM]
    if dim: out['dimming'] = dim
    if v.get('drawing'): out['drawing'] = v['drawing']
    out['source'] = {'catalog': v['catalog'], 'page': v['page']}
    if v.get('shared'): out['shared_cell'] = v['shared']   # на чертеже общий рисунок с этими артикулами
    return out


# фото коллекций и товаров с сайта фабрики
prod_imgs = defaultdict(list)
for slug, c in site.items():
    col = cat['collections'].get(slug)
    if not col: continue
    gallery = []
    for im in c['images']:
        codes = codes_in_name(im['url'], by_col[slug])
        e = {'file': im['file'], 'width': im['width'], 'height': im['height'], 'bytes': im['bytes'], 'src': im['url']}
        if codes:
            e['products'] = codes
            for code in codes: prod_imgs[code].append({k: e[k] for k in ('file', 'width', 'height', 'bytes')} | {'source': {'site': im['url']}})
        gallery.append(e)
    col['images'] = gallery
    col['videos'] = c['videos']
    t = c['texts']
    col['factory_text'] = {lang: t[lang]['description'] for lang in ('ru', 'en', 'it') if lang in t}
    # отделки как на сайте фабрики (иногда с подписью к фото проекта в конце); finishes.ru — наш сжатый текст
    col['factory_finishes'] = {lang: t[lang]['finishes'] for lang in ('ru', 'en', 'it') if t.get(lang, {}).get('finishes')}

# фото со страниц каталога
cat_imgs = defaultdict(list)
for ph in catph:
    cat_imgs[ph['code']].append({k: ph[k] for k in ('file', 'width', 'height', 'bytes')} | {'source': {'catalog': 'IDL 2024' if ph['catalog'] == '2024' else 'IDL Novelties 2025', 'page': ph['page']}})

# варианты, нарисованные в ячейке другого артикула (в каталоге у них нет своей ячейки)
ALIAS = {'606/10': '605/10', '606/16': '605/16'}
ALIAS_NOTE = {k: f'вариант с одной точкой крепления (single fastening); свет и чертёж — в ячейке {v}' for k, v in ALIAS.items()}
# поправки страниц из первичного указателя (проверено по тексту страниц: на старой странице артикула нет)
PAGE_FIX = {'642/50': {127: 126}, '642/70': {127: 126}, '643/4': {127: 126}, '668/16PF': {82: 83}, '670/16PF': {82: 83},
            '655/1LG': {111: 13}, '448/SPOT': {207: 12}, '468/P': {351: 348}}
stats = defaultdict(int)
for p in cat['products']:
    code = p['mfr_code']
    if code in PAGE_FIX:
        p['catalog_pages'] = sorted({PAGE_FIX[code].get(n, n) for n in p['catalog_pages']})
    imgs = list({i['file']: i for i in prod_imgs.get(code, [])}.values()) + cat_imgs.get(code, [])
    if imgs: p['images'] = imgs; stats['photo'] += 1
    # техданные: Novelties 2025 новее каталога 2024
    v = tech.get(code) or tech.get(ALIAS.get(code, ''))
    if v:
        p['tech'] = parse_tech(v); stats['tech'] += 1
        # артикулы в одной ячейке («509/16A-G glass», ниже «509/16A-M metal» и общий свет) — свет из соседнего
        if 'light' not in p['tech']:
            for o in v.get('shared', []) + [k for k, w in tech.items() if code in w.get('shared', [])]:
                q = parse_tech(tech[o]) if o in tech else {}
                if q.get('light'):
                    p['tech'].update({k: q[k] for k in ('light', 'max_power', 'lumen', 'cct', 'dimming') if k in q}); break
        if code in ALIAS: p['tech']['note'] = ALIAS_NOTE[code]
        if v.get('drawing'): stats['drawing'] += 1
    for k in ('images', 'tech'):
        if k in p and not p[k]: del p[k]

# каталоги: id — как в поле "catalog" товаров; catalog_pages и tech.source.page — номера страниц PDF.
# В Novelties 2025 страница PDF — разворот из двух страниц каталога (стр. PDF 12 = стр. 22–23).
# Копии PDF — в папке выгрузки на Mac (file).
cat['sources'] = [
    {'id': 'IDL 2024', 'title': 'IDL — каталог 2024 (388 стр.)', 'url': 'https://www.idl1987.it/file-download/IDL-luce1987-2024.pdf',
     'file': 'catalogs/idl/IDL-luce1987-2024.pdf', 'index_pages': [12, 13]},
    {'id': 'IDL Novelties 2025', 'title': 'IDL — Novelties 2025 (49 стр. PDF, развороты)', 'url': 'https://www.idl1987.it/wp-content/uploads/2025/04/IDL-2025-novelties-1.pdf',
     'file': 'catalogs/idl/IDL-2025-novelties.pdf', 'spreads': True},
    {'title': 'IDL — коллекции на сайте фабрики (тексты ru/en/it, фото, видео)', 'url': 'https://www.idl1987.it/ru/collezioni/illuminazione/'},
]
cat['status'] = ('черновик: номенклатура и артикулы; с сайта и из каталогов фабрики — фото, видео, тексты коллекций (исходник), '
                 'свет, диммирование и чертежи с размерами. Страниц на сайте пока нет.')
json.dump(cat, open(CAT, 'w'), ensure_ascii=False, indent=1)
n = len(cat['products'])
print(f"товаров {n}: с фото {stats['photo']}, с техданными {stats['tech']}, с чертежом {stats['drawing']}")
nophoto = [p['mfr_code'] for p in cat['products'] if 'images' not in p]
print('без фото:', len(nophoto))
