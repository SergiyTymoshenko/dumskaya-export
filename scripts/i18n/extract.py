#!/usr/bin/env python3
"""Шаг 1 перевода: собирает из русских страниц строки, которых ещё нет в памяти переводов
(content/i18n/tm-{ua,en}.json), и раскладывает их по пакетам i18n-work/<lang>-NN.json.
   python3 scripts/i18n/extract.py [--batch-chars 30000] [--langs sk,de]
Для SK и DE берутся только страницы, у которых в русской странице есть адрес на этом языке (alternates)."""
import json, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

ORDER = ['kitchen', 'project', 'article', 'price', 'service', 'generic', 'portfolio', 'contact', 'shop', 'home']
size = int(sys.argv[sys.argv.index('--batch-chars') + 1]) if '--batch-chars' in sys.argv else 30000
P = load_pages()
ru = sorted((p for (l, _), p in P.items() if l == 'ru'),
            key=lambda p: (ORDER.index(p['type']) if p['type'] in ORDER else 99, p['path']))
os.makedirs(WORK, exist_ok=True)
import shutil; shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'GUIDE.md'), os.path.join(WORK, 'GUIDE.md'))
langs = sys.argv[sys.argv.index('--langs') + 1].split(',') if '--langs' in sys.argv else LANGS
for lang in langs:
    tm = load_tm(lang)
    # описания фото, которых нет на языке
    have = {}
    for (l, _), p in P.items():
        if l == lang:
            for im in images(p):
                if alt_ok(lang, im.get('alt')):
                    have.setdefault(im['id'], im['alt'])
    seen = set(tm); pages = []
    for p in ru:
        if lang in NEW_LANGS and not p['alternates'].get(lang):
            continue
        items = []
        for k, s in strings(p):
            if s in seen: continue
            seen.add(s); items.append({'src': s})
        for im in images(p):
            a = im.get('alt') or ''
            if im['id'] not in have and a and a not in seen:
                seen.add(a); items.append({'src': a, 'kind': 'alt'})
        if items:
            pages.append({'page': p['path'], 'type': p['type'], 'title_ru': p['h1'], 'items': items})
    # пакеты примерно по size символов, страница целиком в одном пакете
    batches, cur, n = [], [], 0
    for pg in pages:
        c = sum(len(i['src']) for i in pg['items'])
        if cur and n + c > size:
            batches.append(cur); cur, n = [], 0
        cur.append(pg); n += c
    if cur: batches.append(cur)
    idn = 0
    for bi, b in enumerate(batches, 1):
        for pg in b:
            for it in pg['items']:
                idn += 1; it['id'] = f't{idn:05d}'
        f = os.path.join(WORK, f'{lang}-{bi:02d}.json')
        json.dump({'lang': lang, 'batch': bi, 'pages': b}, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    tot = sum(len(i['src']) for b in batches for pg in b for i in pg['items'])
    print(f'{lang}: пакетов {len(batches)}, строк {idn}, символов {tot}')
