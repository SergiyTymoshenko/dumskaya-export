# Baxter: товары (EN + RU) из данных страниц (Nuxt) → baxter.json
import re, json
from concurrent.futures import ThreadPoolExecutor
from common import get, sitemap_urls, save
from nuxt import nuxt_data
B = 'https://www.baxter.it'
def big(files):
    for k in ('sb_full_jpg', 'original', 'sb_full_png', 'webImage', 'sb_medium_jpg'):
        if files.get(k, {}).get('url'): return files[k]['url']
def prod(url):
    h = get(url, delay=0.6)
    if not h: return None
    d = (nuxt_data(h) or {}).get('data', {})
    page = next((v for k, v in d.items() if k.startswith('directus-page:')), None)
    item = next((v['list'][0] for v in d.values() if isinstance(v, dict) and isinstance(v.get('list'), list) and v['list'] and isinstance(v['list'][0], dict) and 'modello' in v['list'][0]), None)
    files = next((v for v in d.values() if isinstance(v, dict) and 'bims' in v), {})
    if not page: return None
    st = page['story']; c = st['content']
    return {'url': url, 'story': st, 'content': c, 'item': item, 'has2d3d': bool(files.get('list')), 'hasBim': bool(files.get('bims'))}
def compact(p, ru):
    c, it, st = p['content'], p['item'] or {}, p['story']
    imgs = []
    for key in ('mainImages', 'thumbPLP', 'thumb'):
        for im in c.get(key) or []:
            if not isinstance(im, dict): continue
            u = big(im.get('files') or {})
            if u and u not in imgs: imgs.append(u)
    for pan in c.get('panoramics') or []:
        st_ = pan.get('story') if isinstance(pan, dict) else None
        for im in ((st_ if isinstance(st_, dict) else {}).get('image') or []):
            if not isinstance(im, dict): continue
            u = big(im.get('files') or {})
            if u and u not in imgs: imgs.append(u)
    ts = [im['files']['original']['url'] for im in (c.get('technicalSheetBynder') or []) if (im.get('files') or {}).get('original', {}).get('url')]
    if not ts and (c.get('technicalSheet') or {}).get('filename'): ts = [c['technicalSheet']['filename']]
    vers = []
    ru_v = {v.get('immaginePdf'): v for v in (((ru or {}).get('item') or {}).get('versions') or {}).get('nodes', [])} if ru else {}
    for v in (it.get('versions') or {}).get('nodes', []):
        if v.get('site') is False: continue
        sp = ((v.get('specifications') or {}).get('nodes') or [{}])[0] or {}
        dims = {k: sp[k]['cm'] for k in ('l', 'w', 'h', 'd') if isinstance(sp.get(k), dict) and sp[k].get('cm')}
        mats = sorted({f"{m['material'].get('gmCodiceLingua')}: {m['material'].get('descrBaseLingua')}" for m in (v.get('materialVersions') or {}).get('nodes', []) if m.get('material')})
        rv = ru_v.get(v.get('immaginePdf')) or {}
        vers.append({'code': (v.get('immaginePdf') or '').replace('.pdf', ''), 'name_en': (v.get('descrizioneLingua') or '').strip(), 'name_ru': (rv.get('descrizioneLingua') or '').strip(),
                     'dims_cm': dims, 'materials': mats})
    slug = p['url'].rstrip('/').split('/')[-1]
    return {'url': p['url'], 'slug': slug, 'model': it.get('modello') or c.get('baxterId'), 'title': c.get('title') or st.get('name'),
            'designer': (it.get('designer') or {}).get('description', ''), 'indoor': c.get('isIndoor'), 'outdoor': c.get('isOutdoor') or c.get('isOpenAir'),
            'new': c.get('isNewArrival'), 'category_slug': slug, 'text_en': it.get('didascaliaPoetica') or '', 'text_ru': ((ru or {}).get('item') or {}).get('didascaliaPoetica') or '',
            'url_ru': ru['url'] if ru else '', 'meta': c.get('metadata') or {}, 'images': imgs, 'tech_sheets': ts, 'versions': vers,
            'has_2d3d_login': p['has2d3d'], 'has_bim_login': p['hasBim']}
if __name__ == '__main__':
    urls = sorted({u for u in sitemap_urls(B + '/sitemaps/sitemap-en.xml') if '/en/products/' in u})
    def one(u):
        p = prod(u)
        if not p: return {'url': u, 'error': True}
        ru = None
        tr = next((t['path'] for t in p['story'].get('translated_slugs') or [] if t.get('lang') == 'ru'), None)
        if tr: ru = prod(f'{B}/ru/{tr}')
        try: return compact(p, ru)
        except Exception as e: return {'url': u, 'error': repr(e)}
    with ThreadPoolExecutor(3) as ex: data = list(ex.map(one, urls))
    ok = [x for x in data if not x.get('error')]
    save('baxter.json', ok)
    print(len(urls), 'ok', len(ok), 'err', [x['url'] for x in data if x.get('error')][:10], 'imgs', sum(len(x['images']) for x in ok), 'ts', sum(len(x['tech_sheets']) for x in ok), 'vers', sum(len(x['versions']) for x in ok), 'ru', sum(1 for x in ok if x['text_ru']))
