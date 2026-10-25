# MisuraEmme: товары (EN) → misuraemme.json
# Список — карта сайта /en/products/<изделие> (разделы-списки отбрасываются: у изделия есть «Type / …»).
# Со страницы: название, дизайнер, тип, текст и техническое описание, отделки с кодами, размеры (чертежи
# «Dimensions» — у каждого подпись и PNG), фото (папка изделия, 1920 px). Фото высокого разрешения и 2D/3D
# (PDF, DWG, 3DS) у MisuraEmme — после входа: не качаем, записываем, что есть, чтобы дизайнер знал, где взять.
import re, json
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, unquote, urljoin
from bs4 import BeautifulSoup
from common import get, save, sitemap_urls
BASE = 'https://www.misuraemme.it'
def txt(el): return re.sub(r'\s+', ' ', el.get_text(' ')).replace('\xa0', ' ').strip() if el else ''
def enc(u): return quote(unquote(urljoin(BASE, u)), safe=':/?=&;,+@~#%') if u else u
def full(u):
    """Миниатюра → оригинал: /files/.thumbs/…/450x/x.png → /files/…/x.png."""
    return enc(re.sub(r'/(?:\d+x\d*[a-z]?|x\d+)/', '/', u.replace('/files/.thumbs/', '/files/')))
def head_box(d):
    h2 = next((x for x in d.find_all('h2') if 'col-sm-8' in ' '.join(x.parent.get('class') or [])), None)
    return h2.parent if h2 else None, h2
def finishes(d):
    """{«Top Finishings / Marbles / Matt Veneers»: ["SD Saint Denis", …]} — разделы, группы, подгруппы по порядку."""
    out = {}
    for h in d.find_all('h3'):
        if 'fxFadeIn' not in ' '.join(h.parent.get('class') or []) or 'finish' not in txt(h).lower(): continue
        sec = h.find_parent('section')
        if not sec: continue
        grp = sub = ''
        for el in sec.find_all(['h3', 'h4', 'p']):
            cls = ' '.join(el.parent.get('class') or []) + ' ' + ' '.join(el.get('class') or [])
            if el.name == 'h3' and 'prodottoFinitureTitle' in cls: grp, sub = txt(el), ''
            elif el.name == 'h4' and 'finitureArticolo__title' in cls: sub = txt(el)
            elif el.name == 'p' and el.find_parent(class_='swiper-slide'):
                key = ' / '.join(x for x in (txt(h), grp, sub) if x)
                v = txt(el)
                if v and v not in out.setdefault(key, []): out[key].append(v)
    return out
def one(url):
    h = get(url, delay=1.0)
    if not h: return {'url': url, 'error': 'fetch'}
    d = BeautifulSoup(h, 'lxml')
    box, h2 = head_box(d)
    kind = next((txt(x) for x in (box.find_all('h4') if box else []) if txt(x).startswith('Type')), '')
    if not box or not kind: return {'url': url, 'error': 'not product'}
    title = txt(h2)
    designer = next((txt(x) for x in box.find_all('h4') if not txt(x).startswith('Type') and txt(x) != title), '')
    intro = []
    for el in box.find_all(['p', 'h5', 'h6']):
        if el.find_parent('section'): continue
        t = txt(el)
        if t and t not in intro: intro.append(t)
    tech_h = next((x for x in d.find_all('h4') if txt(x).startswith('Technical')), None)
    tech = '\n\n'.join(txt(p) for p in tech_h.parent.find_all('p')) if tech_h else ''
    dims = []
    cont = d.find(id='product2dContainer')
    for b in (cont.select('.product2d__boxImg') if cont else []):
        im = b.find('img', src=True)
        if im: dims.append({'title': txt(b.select_one('.product2d__title')) or im.get('alt', ''), 'drawing': full(im['src'])})
    # фото: оригиналы 1920 px из папки этого изделия (на странице бывают и соседние изделия)
    cand = [m for m in re.findall(r'/files/\.thumbs/prodotti/[^"\' )]+?/1920x/[^"\' )]+\.(?:jpe?g|png|webp)', h)]
    folder = lambda u: '/'.join(u.split('/')[3:6])           # prodotti/<раздел>/<изделие>
    top = max(set(map(folder, cand)), key=lambda f: sum(folder(u) == f for u in cand)) if cand else ''
    photos = list(dict.fromkeys(enc(u) for u in cand if folder(u) == top))
    restricted = [txt(li) for li in d.select('.productDownload li.openLogin')]
    open_dl = [{'title': txt(a), 'url': enc(a['href'])} for a in d.select('.productDownload li a[href]')]
    return {'url': url, 'slug': url.rstrip('/').rsplit('/', 1)[-1], 'title': title.rstrip("'").strip(), 'designer': designer,
            'type': kind.split('/', 1)[-1].strip(), 'text_en': '\n\n'.join(intro), 'tech_en': tech, 'finishes': finishes(d),
            'dimensions': dims, 'images': photos, 'downloads_open': open_dl, 'downloads_login': restricted}
if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        urls = [f'{BASE}/en/products/{s}' for s in sys.argv[1:]]
    else:
        urls = sorted({u for u in sitemap_urls(BASE + '/sitemap.xml') if re.match(r'^https://www\.misuraemme\.it/en/products/[^/]+$', u)})
    print('адресов', len(urls), flush=True)
    with ThreadPoolExecutor(2) as ex: data = list(ex.map(one, urls))
    ok = [x for x in data if not x.get('error')]
    save('misuraemme.json' if len(sys.argv) < 2 else 'misuraemme-test.json', ok)
    print(len(urls), 'ok', len(ok), 'пропущено', [(x['url'].rsplit('/', 1)[-1], x['error']) for x in data if x.get('error')][:40],
          'фото', sum(len(x['images']) for x in ok), 'без фото', sum(1 for x in ok if not x['images']),
          'чертежей', sum(len(x['dimensions']) for x in ok), 'без чертежей', sum(1 for x in ok if not x['dimensions']),
          'с отделками', sum(1 for x in ok if x['finishes']), 'без текста', sum(1 for x in ok if not x['text_en']),
          'закрыто после входа', sum(1 for x in ok if x['downloads_login']))
