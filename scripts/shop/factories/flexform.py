# Flexform: товары (EN + RU) из __NEXT_DATA__ → flexform.json
import re, json, html as H
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from common import get, sitemap_urls, save
B = 'https://www.flexform.it'
def page(url):
    h = get(url, delay=0.6)
    if not h: return None, None
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
    if not m: return None, h
    res = json.loads(m.group(1))['props']['pageProps'].get('content', {}).get('resource')
    return res, h
def txt(htmls):
    return '\n'.join(BeautifulSoup(x or '', 'lxml').get_text('\n', strip=True) for x in (htmls or []))
def compact(r, url, ru, ru_url):
    a = r.get('onPageArticle') or {}
    imgs = []
    for im in (a.get('images') or []) + ((a.get('design') or {}).get('stillLifeImages') or []):
        if im.get('url') and im['url'] not in imgs: imgs.append(im['url'])
    docs = ((a.get('technicalSpecifications') or {}).get('documents') or {})
    ds = [d['url'] for d in (docs.get('dataSheet') or []) if d.get('url')]
    f2d = (docs.get('attached2dfile') or {}).get('url')
    ra = (ru or {}).get('onPageArticle') or {}
    t_en = txt((a.get('technicalSpecifications') or {}).get('descriptions'))
    dims = re.findall(r'(?:cm|см)\s*\d+(?:[.,]\d+)?(?:\s*[x×]\s*\d+(?:[.,]\d+)?)*|\d+(?:[.,]\d+)?\s*(?:x|×)\s*\d+(?:[.,]\d+)?(?:\s*(?:x|×)\s*\d+)?\s*cm', t_en)
    return {'url': url, 'url_ru': ru_url, 'id': a.get('id'), 'nid': r.get('drupal_internal__nid'), 'title': r.get('title'), 'model': (a.get('model') or {}).get('name'),
            'year': (a.get('model') or {}).get('year'), 'designers': a.get('designers') or [], 'category': (a.get('category') or {}).get('name') or (r.get('field_type') or {}).get('name'),
            'category_ru': (ra.get('category') or {}).get('name') or '', 'collection': ((r.get('field_type') or {}).get('field_collection') or {}).get('name'),
            'new': r.get('field_new'), 'text_en': txt((a.get('design') or {}).get('descriptions')), 'text_ru': txt((ra.get('design') or {}).get('descriptions')),
            'tech_en': t_en, 'tech_ru': txt((ra.get('technicalSpecifications') or {}).get('descriptions')), 'dims_text': dims[:12],
            'images': imgs, 'datasheets': ds, 'file_2d': f2d,
            'meta': next((m['attributes'].get('content') for m in r.get('metatag') or [] if m.get('attributes', {}).get('name') == 'description'), '')}
if __name__ == '__main__':
    urls = sorted({u for u in sitemap_urls(B + '/sitemap.xml') if '/en/products/' in u and u.count('/') >= 7})
    def one(u):
        r, h = page(u)
        if not r or r.get('type') != 'node--product': return None
        ru_url = None
        m = re.search(r'<link[^>]+hreflang="ru"[^>]+href="([^"]+)"', h) or re.search(r'<link[^>]+href="([^"]+)"[^>]+hreflang="ru"', h)
        if m: ru_url = H.unescape(m.group(1))
        ru = page(ru_url)[0] if ru_url else None
        return compact(r, u, ru, ru_url)
    with ThreadPoolExecutor(3) as ex: data = [x for x in ex.map(one, urls) if x]
    seen, uniq = {}, []
    for p in data:
        k = p['id'] or p['nid']
        if k in seen: seen[k]['also_in'] = seen[k].get('also_in', []) + [p['url']]; continue
        seen[k] = p; uniq.append(p)
    save('flexform.json', uniq)
    print(len(urls), 'pages', len(data), 'unique', len(uniq), 'imgs', sum(len(p['images']) for p in uniq), 'ds', sum(len(p['datasheets']) for p in uniq), 'ru', sum(1 for p in uniq if p['text_ru']))
