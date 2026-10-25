# Minotti: товары (EN) → minotti.json
# Список — сервис их же страницы списка (/WS/wsMinottiProducts.asmx/GetList): Indoor, Outdoor и «2026 Collection».
# Со страницы изделия: название, дизайнер, тип, текст, фото, исполнения (элементы) с чертежами размеров,
# техкарта PDF, схемы композиций PDF. Файлы 2D/3D у Minotti только после входа — их не трогаем, в каталоге ссылка.
import re, json, html as H
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from common import get, save, _s, _lock, _last
import time
BASE = 'https://www.minotti.com'
TAGS = {'10038': 'indoor', '10039': 'outdoor', '26397': 'new'}
def listing(tag):
    """Все изделия раздела: [(адрес, заголовок раздела списка)]."""
    body = {'f': {'idDT': '10', 'idCA': '13151', 'idCO': '0', 'idTag': tag, 'idDesigner': '0', 'idCertificazione': '0',
                  'pageSize': '2000', 'pageIndex': '1', 'preview': False}, 'isReload': 0}
    with _lock:
        w = _last.get('www.minotti.com', 0) + 1.0 - time.time()
        if w > 0: time.sleep(w)
        _last['www.minotti.com'] = time.time()
    r = _s.post(BASE + '/WS/wsMinottiProducts.asmx/GetList', json=body, timeout=60)
    h = r.json()['d']['HTML']
    out, head = [], ''
    for m in re.finditer(r'<h4>(.*?)</h4>|<a href="(/en/[^"?#]+)" title="([^"]*)"', h, re.S):
        if m.group(1) is not None: head = H.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()
        else: out.append((BASE + m.group(2), head))
    return out
def txt(el): return re.sub(r'\s+', ' ', el.get_text(' ')).strip() if el else ''
def abs_(u):
    """Полный адрес; пробелы и прочее в именах файлов Minotti («AERON MOD A.jpg») — закодировать, иначе не скачать."""
    if not u: return u
    u = (BASE + u) if u.startswith('/') else u
    return quote(u, safe=":/%?=&;,+@~#")
def paras(div):
    ps = [re.sub(r'\s+', ' ', p.get_text(' ')).replace('\xa0', ' ').strip() for p in div.find_all('p')] if div else []
    ps = [p for p in ps if p]
    if not ps and div: ps = [txt(div)]
    out = []
    for p in ps:                                   # у Minotti абзац иногда разрезан посреди слова («sche» / «mes»)
        if out and re.search(r'[a-z]$', out[-1]) and re.match(r'[a-z]', p): out[-1] += p
        else: out.append(p)
    return '\n\n'.join(out)
def one(url):
    h = get(url, delay=1.0)
    if not h: return {'url': url, 'error': 'fetch'}
    d = BeautifulSoup(h, 'lxml')
    if not d.select_one('.prod-sheet'): return {'url': url, 'error': 'not product'}
    h1 = d.select_one('.prod-sheet h1') or d.select_one('section.introduzione h2')
    title = txt(h1)
    t = txt(d.find('title'))
    cat = t.split('|', 1)[1].rsplit(' - ', 1)[0].strip() if '|' in t else ''
    intro = d.select_one('section.introduzione:not(.hide)') or d.select_one('section.introduzione')
    designers = list(dict.fromkeys(txt(a) for a in (intro.select('.text-by a') if intro else []) if txt(a)))
    text = paras(intro.select_one('.descrizione .text') if intro else None)
    tag = txt(d.select_one('.versioni h4'))
    imgs = []
    def add(u):
        u = abs_(H.unescape(u or '').split('?')[0])
        if u and '/media/immagini/' in u and re.search(r'/\d+_z_', u) and u not in imgs: imgs.append(u)
    hero = d.select_one('.prod-sheet .slide div[style]')
    if hero:
        m = re.search(r"url\(['\"]?([^'\")]+)", H.unescape(hero['style'])); add(m and m.group(1))
    for a in d.select('#prod-gallery a.wrap-archive[href]'): add(a['href'])
    for a in d.select('.single-slider-prod a[href]'): add(a['href'])
    sheets = []
    for li in d.select('.cta.dropdown .contenuto li'):
        a = li.select_one('a.azioni[href*="/downloads/"]')
        if a and a['href'].lower().endswith('.pdf'):
            lab = txt(li.select_one('.link')) or txt(li)
            u = abs_(a['href'])
            if u not in [s['url'] for s in sheets]: sheets.append({'label': lab, 'url': u})
    has_2d3d = bool(d.select_one('.cta.dropdown a.modelli'))
    versions = []
    tech = d.select_one('section.technical')
    for it in (tech.select('.item') if tech else []):
        im = it.select_one('img[src*="/media/immagini/"]'); nm = txt(it.select_one('span.small'))
        if nm or im: versions.append({'name_en': nm, 'drawing': abs_(im['src']) if im else None})
    arr = []
    for a in d.select('a[data-download-composition][href]'):
        box = a.find_parent(class_='item') or a.find_parent('section')
        lines = [txt(li) for li in (box.select('ul li:not(.tit)') if box else [])]
        u = abs_(a['href'])
        if u not in [x['url'] for x in arr]: arr.append({'url': u, 'items': lines})
    return {'url': url, 'slug': url.rstrip('/').rsplit('/', 1)[-1], 'title': title, 'category': cat, 'designers': designers,
            'tagline': tag, 'text_en': text, 'images': imgs, 'tech_sheets': sheets, 'has_2d3d_login': has_2d3d,
            'versions': versions, 'arrangements': arr}
if __name__ == '__main__':
    import sys
    meta = {}
    for tag, what in TAGS.items():
        for u, head in listing(tag):
            m = meta.setdefault(u, {'place': [], 'new': False, 'list_heads': []})
            if what == 'new': m['new'] = True
            elif what not in m['place']: m['place'].append(what)
            if head and head not in m['list_heads']: m['list_heads'].append(head)
    urls = sorted(meta) if len(sys.argv) < 2 else [BASE + '/en/' + s for s in sys.argv[1:]]
    print('в списках:', len(meta), 'indoor', sum('indoor' in m['place'] for m in meta.values()),
          'outdoor', sum('outdoor' in m['place'] for m in meta.values()), 'new', sum(m['new'] for m in meta.values()), flush=True)
    with ThreadPoolExecutor(2) as ex: data = list(ex.map(one, urls))
    for x in data: x.update(meta.get(x['url'], {}))
    ok = [x for x in data if not x.get('error')]
    save('minotti.json' if len(sys.argv) < 2 else 'minotti-test.json', ok)
    print(len(urls), 'ok', len(ok), 'err', [(x['url'], x['error']) for x in data if x.get('error')][:10],
          'фото', sum(len(x['images']) for x in ok), 'техкарт', sum(len(x['tech_sheets']) for x in ok),
          'без техкарты', sum(1 for x in ok if not x['tech_sheets']), 'исполнений', sum(len(x['versions']) for x in ok),
          'схем', sum(len(x['arrangements']) for x in ok), 'без текста', sum(1 for x in ok if not x['text_en']))
