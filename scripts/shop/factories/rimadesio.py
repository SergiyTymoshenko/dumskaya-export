# Rimadesio: товары (EN + RU) → rimadesio.json
# Список — карта сайта product-sitemap.xml (/en/product/<изделие>/). Со страницы: название, тип (выделен в списке
# изделий коллекции под заголовком), раздел (хлебные крошки), текст и дизайнер («Design …»), технические детали,
# фото галереи, техническая документация PDF коллекции (открыта: «Catalogues» / «Download»).
# Файлы 2D/3D — только в Reserved Area после входа: не качаем, записываем, где взять.
import re, json
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, unquote
from bs4 import BeautifulSoup
from common import get, save, sitemap_urls
def txt(el): return re.sub(r'\s+', ' ', el.get_text(' ')).replace('\xa0', ' ').strip() if el else ''
def enc(u): return quote(unquote(u), safe=':/?=&;,+@~#%') if u else u
def describe(d):
    """Текст и дизайнер: блок section[data-dynamic-content], в конце — «Design Giuseppe Bavuso.»"""
    s = d.select_one('section[data-dynamic-content]')
    t = txt(s)
    if not t:                                          # другая вёрстка: длинные абзацы после заголовка, до меню
        h1, parts = d.find('h1'), []
        for el in (h1.find_all_next(['p', 'div']) if h1 else []):
            if el.find(['p', 'div']) or el.find_parent(['nav', 'footer', 'figure', 'figcaption']): continue
            if 'w-lg-14' in ' '.join(el.get('class') or []): break
            v = txt(el)
            if 120 < len(v) < 2000 and v not in parts: parts.append(v)
            if len(parts) >= 4: break
        t = '\n\n'.join(parts)
    m = re.search(r'\bDesign(?:ed by)?\s+([A-Z][^.]{2,60})\.?\s*$', t)
    return t, (m.group(1).strip() if m else '')
def one(url):
    h = get(url, delay=1.0)
    if not h: return {'url': url, 'error': 'fetch'}
    d = BeautifulSoup(h, 'lxml')
    h1 = d.find('h1')
    if not h1: return {'url': url, 'error': 'not product'}
    title = txt(h1)
    if re.search(r'/(interior-[a-z]+(?:-\d+)?|night(?:-\d)?|living-\d|dining|walk-in-closet)/?$', url):
        return {'url': url, 'error': 'интерьер, не изделие'}             # готовые интерьеры («New interiors»)
    hg = h1.find_parent('hgroup')
    kind = txt(hg.select_one('ul b')) if hg else ''
    family = [{'type': txt(a), 'url': a['href']} for a in (hg.select('ul a[href]') if hg else [])]
    home = next((a for a in d.find_all('a', href=True) if txt(a) == 'Homepage'), None)
    crumbs = [x for x in (txt(home.parent.parent).split(' / ') if home else []) if x and x not in ('Homepage', 'Products', title)]
    text, designer = describe(d)
    det = next((x for x in d.find_all(string=re.compile(r'^\s*TECHNICAL DETAILS\s*$'))), None)
    details = []
    if det:
        sec = det.find_parent('section') or det.parent.parent
        details = [txt(p) for p in sec.find_all(['p', 'li']) if re.match(r'^\d+\.', txt(p))]
    photos = []
    for im in d.select('.carousel__gallery img[src]'):
        if im.find_parent(class_=re.compile('related')): continue
        s = enc(re.sub(r'-\d+x\d+(\.\w+)$', r'\1', im['src']))
        if re.search(r'\.(jpe?g|png|webp)$', s, re.I) and s not in photos: photos.append(s)
    pdfs = []
    for a in d.find_all('a', href=True):
        if a['href'].lower().endswith('.pdf') and 'static.rimadesio.it' in a['href'] and enc(a['href']) not in [x['url'] for x in pdfs]:
            pdfs.append({'title': txt(a), 'url': enc(a['href'])})
    gated = next((a['href'] for a in d.find_all('a', href=True) if txt(a) == '2D/3D'), '')
    ru = next((l['href'] for l in d.find_all('link', hreflang='ru') if l.get('href')), '')
    text_ru = title_ru = ''
    if ru:
        hr = get(ru, delay=1.0)
        if hr:
            r = BeautifulSoup(hr, 'lxml'); title_ru = txt(r.find('h1')); text_ru = describe(r)[0]
    return {'url': url, 'url_ru': ru, 'slug': url.rstrip('/').rsplit('/', 1)[-1], 'title': title, 'title_ru': title_ru,
            'type': kind, 'family': family, 'crumbs': crumbs, 'designer': designer, 'text_en': text, 'text_ru': text_ru,
            'details': details, 'images': photos, 'pdfs': pdfs, 'files_2d3d_login': gated}
if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        urls = [f'https://www.rimadesio.it/en/product/{s}/' for s in sys.argv[1:]]
    else:
        urls = sorted({u for u in sitemap_urls('https://www.rimadesio.it/product-sitemap.xml') if '/en/product/' in u})
    print('адресов', len(urls), flush=True)
    with ThreadPoolExecutor(2) as ex: data = list(ex.map(one, urls))
    ok = [x for x in data if not x.get('error')]
    save('rimadesio.json' if len(sys.argv) < 2 else 'rimadesio-test.json', ok)
    print(len(urls), 'ok', len(ok), 'пропущено', [(x['url'].rstrip('/').rsplit('/', 1)[-1], x['error']) for x in data if x.get('error')][:30],
          'фото', sum(len(x['images']) for x in ok), 'без фото', sum(1 for x in ok if not x['images']),
          'с PDF', sum(1 for x in ok if x['pdfs']), 'разных PDF', len({p['url'] for x in ok for p in x['pdfs']}),
          'с RU', sum(1 for x in ok if x['text_ru']), 'без типа', sum(1 for x in ok if not x['type']),
          'с дизайнером', sum(1 for x in ok if x['designer']))
