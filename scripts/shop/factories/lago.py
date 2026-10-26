# Lago: изделия с lagodesign.com (EN) → content/shop/sources/lago/{site,files}.json
#
#   python3 lago.py crawl     — список изделий со страницы /en/design/ и данные каждого (Nuxt payload.js), 1 запрос в секунду
#   python3 lago.py sources   — site.json и files.json (фото Thron → файл в выгрузке)
#   python3 lago.py sizes     — настоящие размеры фото (у Thron обрезка в данных страницы не совпадает с файлом), 4 потока
#
# Карта сайта lago.it (sitemap_it.xml) с октября 2026 пустая, поэтому список — ссылки /en/design/<изделие>/ со страницы
# всех изделий английского сайта lagodesign.com (там же разделы и подборки: их отличает payload — не «LayoutProduct»).
# Данные страницы — /_nuxt/static/1/en/design/<изделие>/payload.js (JSONP: выполняем в node, scripts/shop/factories/nuxt.cjs):
# название, подзаголовок, описание и блоки с текстом, дизайнер, год, категория и комнаты, отделки (finishings),
# фото (Thron, id + имя), ссылки: конфигуратор, каталог (lago-share.thron.com), модели 2D/3D (Dropbox, если есть).
# Размеров на сайте нет — они в конфигураторе и каталоге фабрики. robots.txt разрешает обход.
import json, os, re, subprocess, sys
from common import get, save, HERE

BASE = 'https://www.lagodesign.com'
NUXT = os.path.join(HERE, 'nuxt.cjs')
CDN = 'https://lago-cdn.thron.com/delivery/public/image/lago/{id}/sqVrcnw/std/{w}x0/{name}.jpg'


def payload(slug):
    js = get(f'{BASE}/_nuxt/static/1/en/design/{slug}/payload.js', delay=1.0)
    if not js:
        return None
    r = subprocess.run(['node', NUXT], input=js, capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout else None


def strip(h):
    t = re.sub(r'<br\s*/?>|</p>', '\n', h or '')
    t = re.sub(r'<[^>]+>', '', t).replace('&nbsp;', ' ').replace('&amp;', '&')
    return re.sub(r'[ \t]+', ' ', re.sub(r'\n\s*\n+', '\n\n', t)).strip()


def pics(x, out):
    """Все фото Thron в блоке: {thronId, locales, width, height}."""
    if isinstance(x, dict):
        if x.get('thronId') and x.get('width'):
            loc = (x.get('locales') or {}).get('en') or (x.get('locales') or {}).get('it') or {}
            out.append({'id': x['thronId'], 'w': x['width'], 'h': x['height'], 'name': loc.get('name') or '',
                        'alt': loc.get('description') or ''})
        for v in x.values():
            pics(v, out)
    elif isinstance(x, list):
        for v in x:
            pics(v, out)


def one(slug):
    d = payload(slug)
    if not d:
        return {'slug': slug, 'error': 'fetch'}
    top = (d.get('data') or [{}])[0]
    if top.get('component') != 'LayoutProduct':
        return {'slug': slug, 'error': 'not product', 'component': top.get('component')}
    p = top['options']['product']
    a = p.get('acf') or {}
    tax = p.get('taxonomies') or {}
    blocks, fins, tech, imgs = [], [], {}, []
    for k in ('header', 'card', 'thumbnail'):
        pics(a.get(k), imgs)
    for b in a.get('cms_layout') or []:
        f, kind = b.get('fields') or {}, b.get('acf_fc_layout')
        if kind in ('img_text_module', 'text_module', 'img_or_video_with_text_module') and (f.get('title') or f.get('text')):
            cta = (f.get('cta') or {}).get('url', '') if isinstance(f.get('cta'), dict) else ''
            if 'configurator' not in cta:                 # блок «Настройте в конфигураторе» — не про изделие
                blocks.append({'title': strip(f.get('title')), 'text': strip(f.get('text'))})
        if kind == 'finishings':
            fins += [{'title': (x.get('finishing') or {}).get('title'), 'slug': (x.get('finishing') or {}).get('slug'),
                      'what': x.get('description')} for x in f.get('finishings') or []]
        if kind == 'technical_materials':
            tech = {k: v for k, v in f.items() if k.startswith('link_') and v}
        if kind in ('gallery', 'img_text_module'):
            pics(f, imgs)
    seen, photos = set(), []
    for i in imgs:
        if i['id'] not in seen:
            seen.add(i['id'])
            photos.append(i)
    return {'slug': slug, 'url': f'{BASE}/en/design/{slug}/', 'id': p.get('id'), 'title': p.get('title'),
            'subtitle': a.get('subtitle'), 'subtitle_card': a.get('subtitle_card'), 'description': strip(a.get('description')),
            'blocks': blocks, 'designer': a.get('designer'), 'year': a.get('anno'),
            'category': [v.get('name') for v in (tax.get('product-category') or {}).values()],
            'category_slug': list((tax.get('product-category') or {}).keys()),
            'rooms': [v.get('name') for v in (tax.get('rooms') or {}).values()],
            'slugs': {k: v.get('slug') for k, v in (tax.get('post_translations') or {}).items()},
            'seo_title': (p.get('seo') or {}).get('_yoast_wpseo_title'), 'finishings': fins, 'tech_links': tech,
            'configurator': (a.get('configurator_link') or {}).get('url'), 'catalog': (a.get('catalog_link') or {}).get('url'),
            'images': photos}


def crawl():
    h = get(f'{BASE}/en/design/', cache=False) or ''
    slugs = sorted(set(re.findall(r'href="/en/design/([^"/#?]+)/"', h)))
    print('ссылок', len(slugs), flush=True)
    data = [one(s) for s in slugs]
    ok = [x for x in data if not x.get('error')]
    save('lago.json', ok)
    print('изделий', len(ok), 'не изделия', [x['slug'] for x in data if x.get('error') == 'not product'][:60],
          'ошибки', [x['slug'] for x in data if x.get('error') == 'fetch'],
          'фото', sum(len(x['images']) for x in ok), 'без фото', sum(1 for x in ok if not x['images']))


def fslug(s):
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')


def sources():
    root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    items = json.load(open(os.path.join(HERE, 'lago.json'), encoding='utf-8'))
    files, site = {}, []
    for x in items:
        folder = fslug(x['slug'])
        imgs, taken = [], set()
        for i in x['images'][:12]:
            w = min(int(i['w']), 1920)
            h = round(int(i['h']) * w / int(i['w']))
            name = fslug(re.sub(r'\|.*$', '', i['name']) or i['alt'] or x['slug'])[:70] or 'foto'
            n, k = name, 1
            while n in taken:
                k += 1
                n = f'{name}-{k}'
            taken.add(n)
            u = CDN.format(id=i['id'], w=w, name=n)
            files[u] = {'file': f'images/shop/lago/{folder}/{n}.jpg', 'width': w, 'height': h, 'bytes': 0}
            imgs.append(u)
        site.append({**{k: v for k, v in x.items() if k != 'images'}, 'images': imgs})
    dst = os.path.join(root, 'content/shop/sources/lago')
    os.makedirs(dst, exist_ok=True)
    json.dump(site, open(os.path.join(dst, 'site.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump({'files': files, 'sheets': {}}, open(os.path.join(dst, 'files.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'изделий {len(site)}, фото {len(files)} → content/shop/sources/lago/')


def sizes():
    from concurrent.futures import ThreadPoolExecutor
    from rugiano import probe
    root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    fj = os.path.join(root, 'content/shop/sources/lago/files.json')
    fl = json.load(open(fj, encoding='utf-8'))
    todo = [u for u, v in fl['files'].items() if not v.get('probed')]
    with ThreadPoolExecutor(4) as ex:
        for u, v in ex.map(probe, todo):
            if 'width' in v:
                fl['files'][u].update(width=v['width'], height=v['height'], bytes=v.get('bytes') or 0, probed=True)
            else:
                fl['files'][u]['error'] = v.get('error')
    json.dump(fl, open(fj, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    bad = [u for u, v in fl['files'].items() if v.get('error')]
    print('фото', len(fl['files']), 'размеры', sum(1 for v in fl['files'].values() if v.get('probed')), 'ошибки', len(bad), bad[:5])


if __name__ == '__main__':
    {'crawl': crawl, 'sources': sources, 'sizes': sizes}[sys.argv[1] if len(sys.argv) > 1 else 'crawl']()
