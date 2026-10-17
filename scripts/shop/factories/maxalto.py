# Maxalto (B&B Italia): товары (EN) → maxalto.json
import re
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from common import get, sitemap_urls, save
def one(url):
    h = get(url, delay=0.8)
    if not h: return {'url': url, 'error': 'fetch'}
    d = BeautifulSoup(h, 'lxml')
    h1 = d.find('h1'); title = h1.get_text(strip=True) if h1 else ''
    bc = [b.get_text(strip=True) for b in d.select('.breadcrumbs li')]
    if len(bc) < 3 or bc[1] != 'Products': return {'url': url, 'error': 'not product', 'bc': bc}
    desc = d.select_one('div.description')
    txt = ''
    if desc:
        for x in desc.select('h2,h3'): x.decompose()
        parts = [re.sub(r'\s+', ' ', t).strip() for t in desc.get_text('\n').split('Read more')]
        txt = re.sub(r'\s*Read less\s*$', '', max(parts, key=len)) if parts else ''
    main = re.sub(r'\s+', ' ', (d.select_one('div.column.main') or d).get_text(' '))
    year = re.search(r'Share\s+\S+(?:\s+\S+)*?\s+(19\d\d|20\d\d)\s', main)
    imgs = []
    for m in re.finditer(r'https?:[\\/]+www\.maxalto\.com[\\/]+media[\\/]+catalog[\\/]+product[\\/]+[^"\'\s)?]+\.(?:jpe?g|png|webp)', h):
        u = m.group(0).replace('\\/', '/')
        if 'placeholder' in u or '/cache/' in u or u in imgs: continue
        imgs.append(u)
    pdf = next((a['href'] for a in d.find_all('a', href=True) if '/productpdf/download/' in a['href']), '')
    dimurl = next((a['href'] for a in d.find_all('a', href=True) if 'content.maxalto.com' in a['href'] and 'type=dimension' in a['href']), '')
    designer = ''
    if dimurl:
        dh = get(dimurl, delay=0.8) or ''
        t = re.sub(r'\s+', ' ', BeautifulSoup(dh, 'lxml').get_text(' '))
        m = re.search(re.escape('| ' + title) + r'\s+' + re.escape(title) + r'\s+(.+?)\s+[A-Z][A-Z &]{3,}\s+Dimensions', t)
        if m: designer = m.group(1).strip()
    return {'url': url, 'slug': url.rstrip('/').split('/')[-1].replace('.html', ''), 'title': title, 'category': bc[2] if len(bc) > 3 else '', 'year': year.group(1) if year else '',
            'designer': designer, 'text_en': txt, 'images': [u + '?width=2000' for u in imgs], 'product_pdf': pdf, 'dimensions_page': dimurl}
if __name__ == '__main__':
    urls = [u for u in sitemap_urls('https://www.maxalto.com/media/sitemap/sitemapmaxaltoen.xml') if '/modern-furniture/' in u and u.count('/') == 5]
    with ThreadPoolExecutor(2) as ex: data = list(ex.map(one, urls))
    ok = [x for x in data if not x.get('error')]
    save('maxalto.json', ok)
    print(len(urls), 'ok', len(ok), 'skipped', len(data) - len(ok), 'imgs', sum(len(x['images']) for x in ok), 'pdf', sum(1 for x in ok if x['product_pdf']), 'designer', sum(1 for x in ok if x['designer']))
