# Rugiano: товары (EN) → rugiano.json, размеры фото → rugiano-sizes.json, исходники → content/shop/sources/rugiano/
#
#   python3 rugiano.py crawl     — страницы изделий из карты сайта (/en/products/<indoor|outdoor>/<раздел>/<изделие>), 1 запрос в секунду
#   python3 rugiano.py sizes     — размеры фото и схем (читается только начало файла), 4 потока
#   python3 rugiano.py sources   — content/shop/sources/rugiano/site.json и files.json (адрес → файл в выгрузке, размеры)
#
# Со страницы (открыто без входа): тип изделия (подпись над названием), название, тексты блоков описания, фото изделия
# (кроме мобильных копий и общих картинок внизу страницы), схемы «Measures» с размерами (PNG, имя файла — модель
# и размер). Раздел «Technical specification» (материалы, отделки, техкарты) у Rugiano — только после входа
# в Area riservata: не качаем, отмечаем ссылкой на страницу изделия. Дизайнеров фабрика на сайте не указывает.
import io, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from urllib.parse import quote, unquote
from common import get, save, HERE
import requests
from common import UA

BASE = 'https://www.rugiano.com'
FOOTER = {'professional.jpg', 'experience.jpg', 'service.jpg'}


def txt(el):
    return re.sub(r'\s+', ' ', el.get_text(' ')).replace('\xa0', ' ').strip() if el else ''


def absu(u):
    if not u:
        return u
    u = 'https:' + u if u.startswith('//') else (BASE + u if u.startswith('/') else u)
    return quote(unquote(u), safe=':/?=&;,+@~#%')          # «COMO'-BOHEME.png» без кодирования сервер не отдаёт


def media_key(u):
    """Одно и то же фото бывает на CDN и на сайте и с разными папками-uuid: ключ — имя файла."""
    return u.rsplit('/', 1)[-1].lower()


def one(path):
    url = BASE + path
    h = get(url, delay=1.0)
    if not h:
        return {'url': url, 'error': 'fetch'}
    d = BeautifulSoup(h, 'lxml')
    pc = d.select_one('.product-content')
    if not pc or not pc.select_one('h1'):
        return {'url': url, 'error': 'not product'}
    parts = path.strip('/').split('/')                  # en/products/<place>/<раздел>/<изделие>
    place, section, slug = parts[2], parts[3].lower(), parts[4]
    crumbs = [txt(x) for x in d.select('#breadcrumbs a, #breadcrumbs span:not(.slash)')]
    label = txt(pc.select_one('p.label'))
    title = txt(pc.select_one('h1'))
    blocks = []                                         # [(заголовок, текст)] блоков описания
    for b in pc.select('.block-product-description, .block-one-image-left-five-texts, .block-one-image-left-one-title, .plugin-section-two'):
        heads = [txt(x) for x in b.find_all(['h1', 'h2', 'h3']) if txt(x) and txt(x) != title]
        paras = [txt(p) for p in b.find_all('p') if txt(p) and 'label' not in (p.get('class') or [])]
        if paras or heads:
            blocks.append({'heads': heads, 'paras': paras})
    # схемы с размерами
    meas, seen = [], set()
    for im in d.select('.plugin-modules-combinations img'):
        u = absu(im.get('data-src') or im.get('src'))
        if u and 'base64' not in u and media_key(u) not in seen:
            seen.add(media_key(u))
            name = os.path.splitext(u.rsplit('/', 1)[-1])[0]
            meas.append({'title': name.replace('_', ' ').replace('-', ' ').strip(), 'drawing': u})
    # фото изделия: картинка вверху и блоки страницы (без мобильных копий <source>, схем, общих картинок внизу)
    photos = []
    for im in d.find_all('img'):
        if im.find_parent(class_='plugin-modules-combinations') or im.find_parent(class_='block-product-footer'):
            continue
        u = absu(im.get('data-src') or im.get('src'))
        if not u or 'base64' in u or '/backoffice/media/' not in u:
            continue
        k = media_key(u)
        if k in FOOTER or k in seen:
            continue
        seen.add(k)
        photos.append(u)
    gated = bool(d.select_one('#technical-specification a[href*="login"]'))
    it = next((a['href'] for a in d.select('.language-container a[href]') if '/it/' in a['href']), None)
    full = crumbs[-1] if crumbs and crumbs[-1].lower().startswith(title.lower()) else title   # «Rafael Componibile»
    return {'url': url, 'url_it': it, 'key': f'{place}/{section}/{slug}', 'slug': slug, 'place': place, 'section': section,
            'crumbs': crumbs, 'name_full': full,
            'label': label, 'title': title, 'blocks': blocks, 'measures': meas, 'images': photos, 'spec_after_login': gated}


def crawl(only=None):
    sm = get(BASE + '/sitemap.xml', cache=False) or ''
    locs = re.findall(r'<loc>\s*([^<\s]+)', sm)
    paths = sorted({l for l in locs if re.match(r'^/en/products/(indoor|outdoor)/[^/]+/[^/]+$', l)})
    if only:
        paths = [p for p in paths if p.rsplit('/', 1)[-1] in only]
    print('страниц изделий', len(paths), flush=True)
    with ThreadPoolExecutor(2) as ex:
        data = list(ex.map(one, paths))
    ok = [x for x in data if not x.get('error')]
    save('rugiano.json' if not only else 'rugiano-test.json', ok)
    print('ok', len(ok), 'пропущено', [(x['url'].rsplit('/', 1)[-1], x['error']) for x in data if x.get('error')][:30],
          'фото', sum(len(x['images']) for x in ok), 'без фото', sum(1 for x in ok if not x['images']),
          'схем', sum(len(x['measures']) for x in ok), 'без схем', sum(1 for x in ok if not x['measures']),
          'характеристики после входа', sum(1 for x in ok if x['spec_after_login']))


def probe(u):
    """Размеры картинки по началу файла (без скачивания целиком)."""
    from PIL import ImageFile
    try:
        with requests.get(u, headers={'User-Agent': UA}, stream=True, timeout=40) as r:
            if r.status_code != 200:
                return u, {'error': r.status_code}
            total = int(r.headers.get('Content-Length') or 0)
            p = ImageFile.Parser()
            got = 0
            for chunk in r.iter_content(16384):
                got += len(chunk)
                p.feed(chunk)
                if p.image:
                    return u, {'width': p.image.size[0], 'height': p.image.size[1], 'format': p.image.format, 'bytes': total}
                if got > 4_000_000:
                    break
    except Exception as e:  # noqa: BLE001
        return u, {'error': str(e)[:80]}
    return u, {'error': 'size'}


def sizes():
    items = json.load(open(os.path.join(HERE, 'rugiano.json'), encoding='utf-8'))
    fn = os.path.join(HERE, 'rugiano-sizes.json')
    have = json.load(open(fn, encoding='utf-8')) if os.path.exists(fn) else {}
    urls = list(dict.fromkeys(u for x in items for u in x['images'][:12] + [m['drawing'] for m in x['measures']]))
    todo = [u for u in urls if u not in have or 'error' in have[u]]
    print('картинок', len(urls), 'узнать размер', len(todo), flush=True)
    with ThreadPoolExecutor(4) as ex:
        for i, (u, v) in enumerate(ex.map(probe, todo), 1):
            have[u] = v
            if i % 200 == 0:
                json.dump(have, open(fn, 'w'), ensure_ascii=False)
                print(' ', i, flush=True)
    json.dump(have, open(fn, 'w'), ensure_ascii=False)
    print('размеры:', sum(1 for u in urls if 'width' in have.get(u, {})), 'из', len(urls),
          'ошибки', [(u.rsplit('/', 1)[-1], have[u]['error']) for u in urls if 'error' in have.get(u, {})][:10])


def fslug(s):
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')


def sources():
    root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    items = json.load(open(os.path.join(HERE, 'rugiano.json'), encoding='utf-8'))
    sz = json.load(open(os.path.join(HERE, 'rugiano-sizes.json'), encoding='utf-8'))
    files, taken = {}, set()

    def add(u, folder, sub=''):
        info = sz.get(u) or {}
        if u in files or not info.get('width'):
            return u if u in files else None
        name = fslug(os.path.splitext(u.rsplit('/', 1)[-1])[0])[:80] or 'foto'
        ext = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp', 'MPO': 'jpg'}.get(info.get('format'), 'jpg')
        n, k = f'{name}.{ext}', 1
        while (folder, sub, n) in taken:
            k += 1
            n = f'{name}-{k}.{ext}'
        taken.add((folder, sub, n))
        files[u] = {'file': f"images/shop/rugiano/{folder}/{sub + '/' if sub else ''}{n}", 'width': info['width'],
                    'height': info['height'], 'bytes': info.get('bytes') or 0}
        return u

    site = []
    for x in items:
        folder = fslug(f"{x['section']}-{x['slug']}") if x['place'] == 'indoor' else fslug(f"outdoor-{x['section']}-{x['slug']}")
        imgs = [u for u in (add(u, folder) for u in x['images'][:12]) if u]
        meas = [{**m, 'drawing': add(m['drawing'], folder, 'measures')} for m in x['measures']]
        site.append({**{k: v for k, v in x.items() if k not in ('images', 'measures')}, 'images': imgs,
                     'measures': [m for m in meas if m['drawing']]})
    dst = os.path.join(root, 'content/shop/sources/rugiano')
    os.makedirs(dst, exist_ok=True)
    json.dump(site, open(os.path.join(dst, 'site.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump({'files': files, 'sheets': {}}, open(os.path.join(dst, 'files.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'страниц изделий {len(site)}, файлов {len(files)} → content/shop/sources/rugiano/')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'crawl'
    {'crawl': lambda: crawl(sys.argv[2:] or None), 'sizes': sizes, 'sources': sources}[cmd]()
