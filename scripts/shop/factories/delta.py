# Delta Light: подсемейства (EN) с исполнениями, характеристиками, фото и чертежами → delta.json
# robots.txt: для ClaudeBot Crawl-delay 20 (для остальных 10) — берём 20 с между запросами; /asset/file/* не трогаем.
import re, json, html, gzip, io
from common import get, save
SM = 'https://deltalight.com/sitemap/4f9a860e-0f15-11ed-a945-00505693b57f/sitemap.categories.xml.gz'
def urls():
    b = get(SM, binary=True, cache=False, delay=20)
    t = gzip.decompress(b).decode()
    return sorted({u for u in re.findall(r'<loc>\s*([^<\s]+)', t) if re.match(r'https://deltalight\.com/en/products/[^/]+/[^/]+$', u)})
def parse(url, h):
    props = []
    for v in re.findall(r'data-props="([^"]+)"', h):
        try: props.append(json.loads(html.unescape(v)))
        except Exception: pass
    sf = None; assets = []
    def walk(o):
        nonlocal sf
        if isinstance(o, dict):
            if 'subFamily' in o and isinstance(o['subFamily'], dict) and 'products' in o['subFamily'] and sf is None: sf = o['subFamily']
            if 'subType' in o and 'resource' in o: assets.append({'type': o['subType'], 'resource': o['resource'], 'title': o.get('title'), 'w': (o.get('dimensions') or {}).get('width'), 'h': (o.get('dimensions') or {}).get('height')})
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(props)
    if not sf: return {'url': url, 'error': 'no subfamily'}
    variants = []; fam = {}; sub = {}
    for sku_base, colours in (sf.get('products') or {}).items():
        for col, p in (colours.items() if isinstance(colours, dict) else ((None, x) for x in (colours or []))):
            if not isinstance(p, dict): continue
            fam = p.get('family') or fam; sub = p.get('subFamily') or sub
            pr = {}
            for k, v in (p.get('properties') or {}).items():
                if isinstance(v, dict) and v.get('value') not in (None, [], ['-']) and all(isinstance(x, (str, int, float)) for x in (v['value'] if isinstance(v['value'], list) else [v['value']])):
                    pr[v.get('name') or k] = (', '.join(map(str, v['value'])) if isinstance(v['value'], list) else str(v['value'])) + ((' ' + v['unit']) if v.get('unit') else '')
            variants.append({'sku': p.get('sku'), 'base': p.get('productSku'), 'colour': col or (p.get('sku') or '').replace(p.get('productSku') or '', '').strip(), 'title': p.get('title'), 'url': p.get('url'), 'props': pr})
    seen = set(); A = []
    for a in assets:
        if a['resource'] in seen: continue
        seen.add(a['resource']); A.append(a)
    drw = (sf.get('technicalDrawing') or {}).get('assetView', {}).get('resource')
    # фильтры над списком: где (Indoor/Outdoor), крепление (Wall/Ceiling/…), монтаж (Surface mounted/Recessed/…), форма
    facets = {}
    for k, v in re.findall(r'<label class="dropdown-label"><span>([^<]+)</span></label><div class="dropdown-selection"><span>([^<]+)</span>', h):
        facets.setdefault(html.unescape(k).strip(), html.unescape(v).strip())
    return {'url': url, 'family': fam.get('title'), 'family_desc': fam.get('shortDescription'), 'subfamily': sub.get('title') or url.split('/')[-1].upper(),
            'columns': [c.get('title') for c in sf.get('columns') or []], 'common': {v.get('name'): ', '.join(map(str, v.get('value') or [])) + ((' ' + v['unit']) if v.get('unit') else '') for v in (sf.get('equivalentProperties') or {}).values() if isinstance(v, dict)},
            'colours': {k: (v.get('value') if isinstance(v, dict) else v) for k, v in (sf.get('availableColours') or {}).items()} if isinstance(sf.get('availableColours'), dict) else sf.get('availableColours'),
            'facets': facets, 'variants': variants, 'drawing': drw, 'shots': [a for a in A if a['type'] == 'product_shot'], 'projects': [a for a in A if a['type'] == 'project_picture'][:4]}
if __name__ == '__main__':
    U = urls(); print('subfamilies', len(U), flush=True)
    out = []
    for i, u in enumerate(U):
        h = get(u, delay=20)
        try: out.append(parse(u, h) if h else {'url': u, 'error': 'fetch'})
        except Exception as e: out.append({'url': u, 'error': f'parse {type(e).__name__}: {e}'}); print('ERR', u, e, flush=True)
        if i % 25 == 0:
            save('delta.json', out); print(i, flush=True)
    save('delta.json', out)
    ok = [x for x in out if not x.get('error')]
    print('ok', len(ok), 'err', len(out) - len(ok), 'variants', sum(len(x['variants']) for x in ok), 'shots', sum(len(x['shots']) for x in ok), 'drawings', sum(1 for x in ok if x['drawing']))
