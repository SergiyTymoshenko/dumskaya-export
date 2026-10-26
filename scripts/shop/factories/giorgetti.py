# Giorgetti: данные из браузера → content/shop/sources/giorgetti/{site,files}.json
#
#   python3 giorgetti.py <dump.json>
#
# Сайт giorgettimeda.com закрыт проверкой от роботов, поэтому 26.10.2026 страницы прочитаны во встроенном браузере
# владельца (по его просьбе, без входа: всё ниже открыто посетителям): карта сайта /ww/en/sitemap.xml → 340 страниц
# изделий /ww/en/products/<раздел>/<изделие>; со страницы — название, подзаголовок, дизайнер и год (разметка Product),
# «Details», фото галереи (/media/immagini/<n>_z_…), техкарта «Technical data sheet» (/downloads/…pdf); исполнения —
# /api/products/versions?productId= (код, описание, размеры в см), отделки — /api/materials/product?productId=
# (группы и число отделок). Размеры фото — по началу файла. Технические чертежи у фабрики — после входа (Login): ссылка.
# Формат dump.json: {"fields": [...], "M": {коллекция отделок: [примеры]}, "P": [[u, pid, h1, hero, det, designer, year,
# covers, imgs[[file, w, h, bytes]], pdfs, insights, finishes, versions[[code, family, title, abstract, cm, pdf]], materials]]}
import json, os, re, sys
from common import HERE

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
DST = os.path.join(ROOT, 'content/shop/sources/giorgetti')
BASE = 'https://www.giorgettimeda.com'


def fslug(s):
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')


def main():
    d = json.load(open(sys.argv[1], encoding='utf-8'))
    M = d['M']
    files, site, taken = {}, [], set()
    for u, pid, h1, hero, det, des, yr, cov, imgs, pdfs, ins, fin, vers, mats in d['P']:
        parts = u.split('/')
        section, slug = '/'.join(parts[:-1]), parts[-1]
        folder = fslug(f"{parts[-2]}-{slug}")
        images = []
        for f, w, h, b in imgs:
            if not w or f.lower().endswith('.gif'):
                continue
            url = f'{BASE}/media/immagini/{f}'
            stem = re.sub(r'^\d+_z_', '', os.path.splitext(f)[0])
            ext = os.path.splitext(f)[1].lower().lstrip('.') or 'jpg'
            name, k = fslug(stem)[:80] or 'foto', 1
            n = f'{name}.{ext}'
            while (folder, n) in taken:
                k += 1
                n = f'{name}-{k}.{ext}'
            taken.add((folder, n))
            files[url] = {'file': f'images/shop/giorgetti/{folder}/{n}', 'width': w, 'height': h, 'bytes': b or 0}
            images.append(url)
        sheets = []
        for p in pdfs:
            url = f'{BASE}/downloads/{p}'
            files[url] = {'file': f'catalogs/giorgetti/{fslug(slug)}-{fslug(os.path.splitext(p.rsplit("/", 1)[-1])[0])}.pdf',
                          'pages': None, 'bytes': 0}
            sheets.append(url)
        # подзаголовок: «Aura Aura is … Designer Umberto Asnago 2014.2015» → только фраза
        sub = hero[len(h1):].strip() if hero.lower().startswith(h1.lower()) else hero
        sub = re.sub(r'\s*Designer\s.*$', '', sub).strip()
        site.append({'url': f'{BASE}/ww/en/products/{u}', 'key': u, 'pid': pid, 'section': section, 'slug': slug,
                     'title': h1, 'subtitle': sub, 'details': det, 'designer': des or None,
                     'year': (yr or '').replace('.', '–') or None, 'covers': cov or None, 'images': images, 'sheets': sheets,
                     'drawings_after_login': 'Technical drawings:Login' in (ins or ''), 'finishes_photo': fin,
                     'versions': [{'code': c, 'family': fam, 'title': t, 'abstract': a, 'cm': cm} for c, fam, t, a, cm, _ in vers],
                     'materials': {c: {col: {'count': n, 'examples': M.get(col, [])[:6]} for col, n in cols.items()}
                                   for c, cols in (mats or {}).items()}})
    os.makedirs(DST, exist_ok=True)
    json.dump(site, open(os.path.join(DST, 'site.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump({'files': files, 'sheets': {}}, open(os.path.join(DST, 'files.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'изделий {len(site)}, фото {sum(len(x["images"]) for x in site)}, техкарт {sum(len(x["sheets"]) for x in site)}, '
          f'исполнений {sum(len(x["versions"]) for x in site)}, без фото {sum(1 for x in site if not x["images"])}')


if __name__ == '__main__':
    main()
