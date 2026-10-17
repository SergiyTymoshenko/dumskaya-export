# Списки на скачивание (dest \t url) + карта url → локальный путь, для baxter / molteni / flexform / delta
import json, re, sys, collections
from urllib.parse import unquote, urlparse
def safe(n): return re.sub(r'[^\w.\-]+', '_', unquote(n)).strip('_')
def build(f, items):
    """Один файл на адрес; уже скачанным (есть в прошлом dl-<f>.tsv) путь не меняется."""
    import os
    prev = {}
    if os.path.exists(f'dl-{f}.tsv'):
        for l in open(f'dl-{f}.tsv'):
            if '\t' in l:
                d, u = l.rstrip('\n').split('\t'); prev.setdefault(u, d)
    rows, mp, used = [], {}, collections.defaultdict(set)
    keep = {u for _, u in items if u in prev}
    used[f] |= {prev[u] for u in keep}
    for dest, url in items:
        if url in mp: continue
        if url in keep:
            mp[url] = prev[url]; rows.append((prev[url], url)); continue
        d = dest; base, dot, ext = d.rpartition('.')
        i = 2
        while d in used[f]: d = f'{base}_{i}.{ext}'; i += 1
        used[f].add(d); mp[url] = d; rows.append((d, url))
    open(f'dl-{f}.tsv', 'w').write(''.join(f'{d}\t{u}\n' for d, u in rows))
    json.dump(mp, open(f'map-{f}.json', 'w'), ensure_ascii=False, indent=0)
    print(f, len(rows))
def olev():
    """OLEV: фото — в папку каждого изделия (одно фото может лежать в двух папках), техлисты (без версий UL)."""
    rows = {}
    for p in json.load(open('olev.json')):
        for u in (p.get('images') or [])[:8]:
            rows.setdefault(f"images/shop/olev/{p['slug']}/{safe(u.rsplit('/', 1)[-1])}", u)
        for f in p.get('files') or []:
            if f['kind'] == 'datasheet':
                u = f['url'].replace('|', '%7C')
                rows.setdefault(f"catalogs/olev/datasheets/{safe(u.rsplit('/', 1)[-1]).replace('%7C', '_')}", u)
    open('dl-olev.tsv', 'w').write(''.join(f'{d}\t{u}\n' for d, u in rows.items()))
    print('olev', len(rows))
def maxalto():
    out = []
    for p in json.load(open('maxalto.json')):
        s = p['slug'].replace('en-', '', 1)
        for u in (p.get('images') or [])[:8]:
            out.append((f"images/shop/maxalto/{s}/{safe(u.split('?')[0].rsplit('/', 1)[-1])}", u))
        if p.get('product_pdf'):
            out.append((f"catalogs/maxalto/sheets/{s}.pdf", p['product_pdf']))
    build('maxalto', out)
def baxter():
    out = []
    for p in json.load(open('baxter.json')):
        for u in (p.get('images') or [])[:8]:
            n = safe(u.rsplit('/', 1)[-1]).replace('sb_full_jpg-', '')
            out.append((f"images/shop/baxter/{p['slug']}/{n}", u))
        for u in p.get('tech_sheets') or []:
            out.append((f"catalogs/baxter/sheets/{safe(u.rsplit('/', 1)[-1])}", u))
    build('baxter', out)
def molteni():
    out = []
    for p in json.load(open('molteni2.json')):
        for im in (p.get('images') or [])[:8]:
            out.append((f"images/shop/molteni/{p['slug']}/{safe(im['id'])}.jpg", im['dl']))
        for d in p.get('datasheets') or []:
            u = d if isinstance(d, str) else d.get('url')
            n = safe(urlparse(u).path.rsplit('/', 1)[-1])
            if not n.lower().endswith('.pdf'): n += '.pdf'
            out.append((f"catalogs/molteni/datasheets/{n}", u))
    build('molteni', out)
def fx_key(p):
    parts = p['url'].rstrip('/').split('/')
    k = f"{parts[-1]}-{parts[-2]}"
    if '/outdoor/' in p['url'] and 'outdoor' not in k: k += '-outdoor'
    return k
def flexform():
    out = []
    for p in json.load(open('flexform.json')):
        slug = fx_key(p)
        for u in (p.get('images') or [])[:8]:
            out.append((f"images/shop/flexform/{slug}/{safe(u.rsplit('/', 1)[-1])}", u))
        for u in p.get('datasheets') or []:
            out.append((f"catalogs/flexform/datasheets/{slug}_{safe(u.rsplit('/', 1)[-1])}", u))
    build('flexform', out)
if __name__ == '__main__':
    for f in sys.argv[1:]: globals()[f]()
