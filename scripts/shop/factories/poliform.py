# Poliform: товары (EN + RU) → poliform.json
# Список — карта сайта (EN) /en/products/<изделие>/. Со страницы изделия: название, дизайнер и год, тип, материалы,
# текст (EN и RU — по ссылке hreflang), фото, размеры (чертежи SVG во вкладке DIMENSIONS — у каждого свой),
# отделки с кодами (вкладка FINISHES). Файлы 2D/3D у Poliform отдают только после формы подписки — их не качаем,
# но записываем список (формат, размер, адрес), чтобы после регистрации докачать.
import re, json
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, unquote
from bs4 import BeautifulSoup
from common import get, save, sitemap_urls
def txt(el): return re.sub(r'\s+', ' ', el.get_text(' ')).replace('\xa0', ' ').strip() if el else ''
def enc(u):
    """Адрес файла как есть, но с пробелами и прочим в имени — закодированным."""
    return quote(unquote(u), safe=':/?=&;,+@~#%') if u else u
DESIGNED = re.compile(r'^Designed by ([^.;]{2,60}?)(?:[,\s]+((?:19|20)\d\d(?:\s*[–-]\s*(?:19|20)\d\d)?))?\s*\.?$')
def description(d):
    """Вкладка DESCRIPTION: первый слайд — название, текст, «Designed by …, 2024»; остальные — пары
    «Type — Table», «Structure — …»."""
    pane = d.find(id='tech-1')
    if not pane: return '', '', '', {}
    text, designer, year, props = [], '', '', {}
    slides = pane.select('.swiper-slide')
    first = next((sl for sl in slides if sl.find('h3')), None)
    if first:
        head = txt(first.find('h3'))
        for line in first.stripped_strings:
            line = re.sub(r'\s+', ' ', line).strip()
            m = DESIGNED.match(line)
            if m: designer, year = m.group(1).strip(' ,'), re.sub(r'\s+', ' ', m.group(2) or '')
            elif line != head and len(line) > 2: text.append(line)
    for sl in slides:
        if sl is first: continue
        parts = [x.strip() for x in sl.stripped_strings]
        for i in range(0, len(parts) - 1, 2):
            if len(parts[i + 1]) < 300 and parts[i] not in props:
                props[parts[i]] = parts[i + 1]
    if not text:                                      # бывает без заголовка в слайде — тогда абзацы вкладки
        for p in pane.find_all('p'):
            line = txt(p)
            m = DESIGNED.match(line)
            if m:
                designer, year = designer or m.group(1).strip(' ,'), year or re.sub(r'\s+', ' ', m.group(2) or '')
            elif len(line) > 2:
                text.append(line)
    if not text:                                      # ни слайда, ни абзацев — весь текст вкладки
        t = txt(pane)
        if len(t) > 80: text.append(t)
    return '\n\n'.join(dict.fromkeys(text)), designer, year, props
def short_description(d):
    """Страница новинки без вкладок: текст — первый длинный абзац после заголовка."""
    h1 = d.find('h1')
    for p in (h1.find_all_next('p') if h1 else []):
        t = txt(p)
        if len(t) > 80: return t, '', '', {}
    return '', '', '', {}
def dimensions(d):
    """Вкладка DIMENSIONS: разделы (h2) → группы (display-4) → карточки: чертёж SVG + подпись (если есть)."""
    pane = d.find(id='tech-2')
    out, sec = [], ''
    if not pane: return out
    for el in pane.find_all(attrs={'data-id': True}):
        if el['data-id'].startswith('stech'):
            sec = txt(el.find(['h2', 'h3'])) or txt(el)
            continue
        grp = txt(el.select_one('.display-4'))
        for card in el.select('.technical-card'):
            im = card.select_one('img[src]')
            if not im: continue
            out.append({'section': sec, 'group': grp, 'title': txt(card.select_one('.technical-card__title')), 'drawing': enc(im['src'])})
    return out
def finishes(d):
    """Вкладка FINISHES: {«Structure finishes / Lacquer / Glossy lacquers»: ["64 Arena", …]}."""
    pane = d.find(id='tech-3')
    out, sec = {}, ''
    if not pane: return out
    for el in pane.find_all(attrs={'data-id': True}):
        if el['data-id'].startswith('stech'):
            sec = txt(el).capitalize()
            continue
        for blk in el.select('.finishes_block') or [el]:
            grp = txt(blk.select_one('.display-4'))
            contents = blk.select('.js-finishes-content')
            if contents:
                for c in contents:
                    sub = txt(c.select_one('button'))
                    names = [txt(a.select_one('.display-6')) for a in c.select('a.finishes')]
                    names = [n for n in names if len(n) <= 70]                    # длинные — пояснения, не отделки
                    if names: out[' / '.join(x for x in (sec, grp, sub) if x)] = list(dict.fromkeys(n for n in names if n))
            else:
                names = [n for n in (txt(x) for x in blk.select('.display-6')) if len(n) <= 70]
                if names: out[' / '.join(x for x in (sec, grp) if x)] = list(dict.fromkeys(n for n in names if n))
    return out
def photos(d, title, slug):
    """Фото изделия: галерея между заголовком и техническими вкладками; из них — те, где в имени файла есть
    название модели (в галерее бывают и соседние изделия), а если таких нет — все."""
    words = [w for w in re.findall(r'[a-z0-9]+', (title + ' ' + slug.split('-')[0]).lower()) if len(w) > 2][:2]
    seq = []
    h1 = d.find('h1')
    for im in (h1.find_all_next(['img', 'source']) if h1 else []):
        if im.find_parent(id=re.compile(r'^tech-')): break
        for s in [im.get('src'), im.get('data-src')] + [x.strip().split(' ')[0] for x in (im.get('srcset') or '').split(',')]:
            if not s or 's3.poliform.it' not in s or not re.search(r'\.(jpe?g|png|webp)$', s, re.I): continue
            s = enc(re.sub(r'-\d+x\d+(\.\w+)$', r'\1', s))           # без уменьшенных копий WordPress
            if s not in seq: seq.append(s)
    own = [s for s in seq if any(w in s.rsplit('/', 1)[-1].lower() for w in words)]
    return own or seq
def one(url):
    h = get(url, delay=1.0)
    if not h: return {'url': url, 'error': 'fetch'}
    d = BeautifulSoup(h, 'lxml')
    if not d.find('h1'): return {'url': url, 'error': 'not product'}
    slug = url.rstrip('/').rsplit('/', 1)[-1]
    title = txt(d.find('h1'))
    short = not d.find(id='tech-1')       # новинки 2026: страница без технических вкладок — только текст и фото
    text, designer, year, props = short_description(d) if short else description(d)
    dl = []
    for a in d.select('a.tecnical-download[data-file-url]'):
        size = txt(a).replace(a.get('data-file-title', ''), '').strip()
        dl.append({'title': a.get('data-file-title'), 'size': size, 'url': enc(a['data-file-url'])})
    first = d.select_one('[data-category]') or d.select_one('a.tecnical-download') or {}
    head = txt(d.find('title'))                       # «Poliform Auguste chair | 2026 Collection»
    m = re.match(r'Poliform\s+(.*?)\s*\|\s*(.+)$', head)
    kind_title = re.sub(re.escape(title), '', m.group(1), flags=re.I).strip() if m else ''
    ru = next((l['href'] for l in d.find_all('link', hreflang='ru') if l.get('href')), '')
    text_ru, title_ru = '', ''
    if ru:
        hr = get(ru, delay=1.0)
        if hr:
            r = BeautifulSoup(hr, 'lxml'); title_ru = txt(r.find('h1'))
            text_ru = (short_description(r) if short or not r.find(id='tech-1') else description(r))[0]
    return {'url': url, 'url_ru': ru, 'slug': slug, 'title': title, 'title_ru': title_ru, 'designer': designer, 'year': year,
            'props': props, 'collection_line': (d.select_one('[data-collezione]') or {}).get('data-collezione'),
            'category': (first.get('data-category') or first.get('data-tipologia') if first else None) or kind_title or None,
            'new': bool(m and '2026' in m.group(2)), 'short_page': short, 'text_en': text, 'text_ru': text_ru,
            'images': photos(d, title, slug), 'dimensions': dimensions(d), 'finishes': finishes(d),
            'files_2d3d_form': dl}
if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        urls = [f'https://www.poliform.it/en/products/{s}/' for s in sys.argv[1:]]
    else:
        urls = sorted({u for u in sitemap_urls('https://www.poliform.it/sitemap-pages-en-1.xml')
                       if re.match(r'^https://www\.poliform\.it/en/products/[^/]+/$', u)})
    print('адресов', len(urls), flush=True)
    with ThreadPoolExecutor(2) as ex: data = list(ex.map(one, urls))
    ok = [x for x in data if not x.get('error')]
    save('poliform.json' if len(sys.argv) < 2 else 'poliform-test.json', ok)
    print(len(urls), 'ok', len(ok), 'не изделие/ошибка', [(x['url'].split('/')[-2], x['error']) for x in data if x.get('error')][:20],
          'фото', sum(len(x['images']) for x in ok), 'без фото', sum(1 for x in ok if not x['images']),
          'чертежей', sum(len(x['dimensions']) for x in ok), 'без чертежей', sum(1 for x in ok if not x['dimensions']),
          'с RU', sum(1 for x in ok if x['text_ru']), 'с отделками', sum(1 for x in ok if x['finishes']),
          'файлов 2D/3D (после формы)', sum(len(x['files_2d3d_form']) for x in ok))
