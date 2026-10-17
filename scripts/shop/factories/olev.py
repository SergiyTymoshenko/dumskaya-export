# OLEV: страницы товаров (EN) → olev.json
import re, sys
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from common import get, sitemap_urls, save
STOP = re.compile(r'in the projects|^designer$|related products|request information|where to buy', re.I)
def parse(url, html):
    d = BeautifulSoup(html, 'lxml')
    slug = url.rstrip('/').split('/')[-1]
    title = (d.find('h1').get_text(strip=True) if d.find('h1') else '')
    see = next((a for a in d.find_all('a') if re.match(r'See all:', a.get_text(strip=True), re.I)), None)
    designer = next((a.get_text(strip=True) for a in d.select('a[href*="/designers/"]') if a.get_text(strip=True) and 'designer' not in a.get_text(strip=True).lower()), '')
    root = d.select_one('.detail-prodotti-container') or d.body
    # файлы
    files = []
    for a in root.select('.download-group a[href]'):
        h = a['href']
        kind = ('datasheet_us' if '/UL|' in h else 'datasheet') if 'datris/datasheet' in h else '3d' if re.search(r'\.(3ds|rfa|dwg|skp|obj|step|stp|max|fbx)$', h, re.I) else 'photometric' if re.search(r'photometric|\.ies|\.ldt', h, re.I) else 'assembly' if re.search(r'assembly|instruction', h, re.I) else 'other'
        if not any(f['url'] == h for f in files): files.append({'kind': kind, 'url': h})
    if sum(f['kind'] == 'assembly' for f in files) > 12: files = [f for f in files if f['kind'] != 'assembly']
    # картинки товара: обложка + картинки с именем товара в файле
    key = slug.replace('-', '').lower()[:6]
    imgs = []
    og = d.find('meta', property='og:image')
    if og and og.get('content'): imgs.append(og['content'])
    for im in root.find_all('img'):
        for s in [im.get('data-src'), im.get('src'), ((im.get('data-srcset') or im.get('srcset') or '').split(',')[-1].strip().split(' ')[0])]:
            if not s or 'uploads' not in s: continue
            fn = s.split('/')[-1].lower().replace('-', '').replace('_', '').replace(' ', '')
            if key in fn: imgs.append(re.sub(r'-\d{2,4}x\d{2,4}(?=\.\w+$)', '', s))
    seen, uniq = set(), []
    for s in imgs:
        k = re.sub(r'-(scaled|\d+)(?=\.\w+$)', '', s)
        if k not in seen: seen.add(k); uniq.append(s)
    # текст
    for x in root.select('form,script,style,noscript,.download-group'): x.decompose()
    secs, cur, taken = [], None, []
    for n in root.find_all(['h1', 'h2', 'h3', 'p', 'li', 'div']):
        if n.name == 'div' and not ('x-text' in (n.get('class') or []) and 'x-text-headline' not in (n.get('class') or [])): continue
        if any(n in t.descendants for t in taken): continue
        if n.name in ('h1', 'h2', 'h3'):
            t = n.get_text(' ', strip=True)
            if STOP.search(t): break
            if n.name == 'h2' and t.lower() != title.lower(): cur = [t, []]; secs.append(cur)
            continue
        t = re.sub(r'\s+', ' ', n.get_text(' ', strip=True)); taken.append(n)
        if len(t) > 3 and not re.match(r'(where to buy|request info|download)', t, re.I):
            if cur is None: cur = ['', []]; secs.append(cur)
            if t not in cur[1]: cur[1].append(t)
    meta = d.find('meta', attrs={'name': 'description'})
    types = sorted({f['url'].split('/')[-1].split('|')[1].lower() for f in files if f['kind'] == 'datasheet' and f['url'].count('|') >= 2})
    places = sorted({f['url'].split('/')[-1].split('|')[0].lower() for f in files if f['kind'] == 'datasheet' and '|' in f['url']})
    return {'url': url, 'slug': slug, 'title': title, 'category': see['href'].rstrip('/').split('/')[-1] if see else '', 'types': types, 'place': places,
            'designer': designer, 'meta': meta['content'] if meta else '', 'sections': [[a, ' '.join(b)] for a, b in secs if b],
            'images': uniq, 'files': files}
if __name__ == '__main__':
    urls = sorted({u for u in sitemap_urls('https://www.olevlight.com/prodotti-sitemap.xml') if re.search(r'/en/products/[^/]+/?$', u)})
    def one(u):
        h = get(u, delay=0.7)
        return parse(u, h) if h else {'url': u, 'error': True}
    with ThreadPoolExecutor(3) as ex: data = list(ex.map(one, urls))
    data = [p for p in data if not p.get('error') and p['slug'] != 'timeline']
    save('olev.json', data)
    print(len(urls), 'ok', len(data), 'imgs', sum(len(p['images']) for p in data), 'ds', sum(1 for p in data for f in p['files'] if f['kind'] == 'datasheet'))
