# Molteni&C: товары (EN) из данных страниц (Next.js RSC) → molteni.json
import re, json
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from common import get, sitemap_urls, save
from rsc import rsc_text, json_at
def walk(o, fn):
    if isinstance(o, dict):
        fn(o)
        for v in o.values(): walk(v, fn)
    elif isinstance(o, list):
        for v in o: walk(v, fn)
def cl(u, w=2000):
    return re.sub(r'/image/upload/', f'/image/upload/c_limit,w_{w},q_auto:good,f_jpg/', u.replace('http://', 'https://'), count=1)
def one(url):
    h = get(url, delay=0.8)
    if not h: return {'url': url, 'error': 'fetch'}
    s = rsc_text(h); i = s.find('{"pageData":')
    if i < 0: return {'url': url, 'error': 'nodata'}
    pd = json_at(s, i)['pageData']; p = pd.get('product_details') or {}
    imgs = []
    def addimg(o):
        if o.get('resource_type') == 'image' and o.get('format') in ('jpg', 'jpeg', 'png', 'webp', 'tif', 'tiff') and o.get('secure_url'):
            u = o['secure_url']
            if u not in [x['src'] for x in imgs]: imgs.append({'src': u, 'w': o.get('width'), 'h': o.get('height'), 'id': o.get('public_id')})
    walk({k: v for k, v in pd.items() if k != 'document_section'}, addimg)
    docs = []
    def adddoc(o):
        if isinstance(o.get('pdf'), list) and o.get('document_permission') == 'Public':
            for f in o['pdf']:
                u = f.get('secure_url') or f.get('url')
                if u and u not in [d['url'] for d in docs]:
                    docs.append({'url': u.replace('http://', 'https://'), 'id': f.get('public_id'), 'lang': o.get('language'), 'type': o.get('document_type'), 'tags': f.get('tags')})
    walk(pd.get('document_section'), adddoc)
    desc = ''
    for b in pd.get('content_blocks') or []:
        if isinstance(b, dict) and b.get('anchor_id') == 'desc' and b.get('body'): desc = BeautifulSoup(b['body'], 'lxml').get_text(' ', strip=True)
    if not desc and p.get('abstract'): desc = BeautifulSoup(p['abstract'], 'lxml').get_text(' ', strip=True)
    designers = [d.get('title') for d in p.get('designers') or [] if isinstance(d, dict) and d.get('title')]
    ds = [d for d in docs if '_DS_' in (d['id'] or '') and (d['lang'] or '').lower().startswith('english')] or [d for d in docs if '_DS_' in (d['id'] or '')]
    return {'url': url, 'slug': url.rstrip('/').split('/')[-1], 'title': p.get('title'), 'category': p.get('category_title'), 'collection': p.get('collection_title'),
            'designers': designers, 'text_en': desc, 'images': [dict(x, dl=cl(x['src'])) for x in imgs if not re.search(r'logo|icon|signature', x['id'] or '', re.I)][:40],
            'datasheets': [d['url'] for d in ds], 'docs_other': [d for d in docs if d not in ds][:10]}
if __name__ == '__main__':
    idx = get('https://www.molteni.it/sitemap.xml', cache=False)
    en = next(u for u in re.findall(r'<loc>\s*([^<\s]+)', idx) if 'en-eu' in u)
    sub = re.findall(r'<loc>\s*([^<\s]+)', get(en, cache=False))
    urls = re.findall(r'<loc>\s*([^<\s]+)', get(next(u for u in sub if 'products.xml' in u), cache=False))
    with ThreadPoolExecutor(2) as ex: data = list(ex.map(one, urls))
    ok = [x for x in data if not x.get('error')]
    save('molteni.json', ok)
    print(len(urls), 'ok', len(ok), 'err', [(x['url'], x['error']) for x in data if x.get('error')][:8], 'imgs', sum(len(x['images']) for x in ok), 'ds', sum(len(x['datasheets']) for x in ok), 'nods', sum(1 for x in ok if not x['datasheets']))
