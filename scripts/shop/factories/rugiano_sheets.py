# Rugiano: техкарты PDF («Scheda Tecnica / Technical Sheet») → content/shop/sources/rugiano/sheets.json
#
#   python3 rugiano_sheets.py <links.json>
#
# links.json — ссылки из раздела «Technical specification» страниц изделий, собранные в браузере после входа
# владельца в Area riservata (26.10.2026): {"/en/products/<place>/<раздел>/<изделие>": [["TECHNICAL SHEET", url], …]}.
# Техкарта у Rugiano лежит на CDN по прямой ссылке. Берём из неё английскую колонку (правая половина страницы):
# описание, материалы, размеры в см по исполнениям, вес. Файлы 2D/3D, галереи и архивы не качаем — только ссылки.
import io, json, os, re, sys
import pdfplumber
from common import get, HERE

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
DST = os.path.join(ROOT, 'content/shop/sources/rugiano')


def https(u):
    from urllib.parse import quote, unquote
    u = 'https:' + u if u.startswith('//') else u
    return quote(unquote(u), safe=':/?=&;,+@~#%')           # «CLUB_comò_…pdf» без кодирования не отдаётся


def right(page):
    """Английская колонка: правая половина страницы."""
    w = page.width
    return page.crop((w * 0.5, 0, w, page.height)).extract_text() or ''


def parse(pdf):
    out = {'pages': len(pdf.pages)}
    p1 = right(pdf.pages[0]).splitlines()
    desc = [l for l in p1 if l.strip() and not re.match(r'(Technical Sheet|Copyright|.*All rights reserved)', l.strip())]
    # первая строка — тип, вторая — модель (иногда тип есть только слева); описание — остальное
    # строки до описания — тип и название (название часто разрезано на две колонки: «Bo|heme»): короткие строки без точки
    while desc and len(desc[0].split()) <= 3 and not desc[0].rstrip().endswith('.'):
        desc = desc[1:]
    out['description_en'] = ' '.join(desc).strip()
    spec = next((pg for pg in pdf.pages if 'Technical Specifications' in (pg.extract_text() or '')), None)
    if spec:
        t = right(spec)
        sec, cur = {}, None
        for l in t.splitlines():
            s = l.strip()
            if not s or s.startswith('Technical Specifications'):
                continue
            if re.fullmatch(r'[A-Z][A-Z ()/&]+', s):            # заголовок раздела: MATERIALS, DIMENSIONS (CM), WEIGHT (KG)
                cur = s
                sec[cur] = []
                continue
            if s.startswith('Rugiano Srl reserves') or s.startswith('Rugiano Srl'):
                cur = None
            if cur:
                sec[cur].append(s)
        # конец абзаца оговорок прилипает к последнему разделу — отрезаем по типичным словам
        for k, v in sec.items():
            sec[k] = [x for x in v if not re.search(r'reserves the right|technical|purposes only|indicative|dealer|without$', x, re.I)
                      or re.match(r'^[A-Z]', x) and ':' in x]
        out['materials'] = [x for x in sec.get('MATERIALS', []) if ':' in x or len(x) > 3]
        dims_key = next((k for k in sec if k.startswith('DIMENSIONS')), None)
        out['dimensions'] = [x for x in sec.get(dims_key, []) if re.search(r'\d', x) and not x.startswith('Dimensions are')]
        out['dimensions_unit'] = 'cm' if dims_key and 'CM' in dims_key else None
        out['notes'] = [x for x in sec.get(dims_key, []) if x.startswith('*')]
        w = next((k for k in sec if k.startswith('WEIGHT')), None)
        out['weight_kg'] = ' '.join(sec.get(w, [])) or None
    return out


def main():
    links = json.load(open(sys.argv[1], encoding='utf-8'))
    site = json.load(open(os.path.join(DST, 'site.json'), encoding='utf-8'))
    by_url = {x['url'].replace('https://www.rugiano.com', ''): x for x in site}
    sheets, miss = {}, []
    for path, ls in links.items():
        if not isinstance(ls, list):
            miss.append((path, 'страница')); continue
        d = {t.upper(): https(u) for t, u in ls}
        key = by_url.get(path, {}).get('key') or path
        rec = {'gated_links': {k: v for k, v in d.items() if k in ('2D FILE', '3D FILE', 'GALLERY', 'DOWNLOAD ALL', 'MEDIA ARCHIVE')}}
        u = d.get('TECHNICAL SHEET')
        if u:
            data = get(u, delay=0.5, binary=True)
            if data:
                try:
                    with pdfplumber.open(io.BytesIO(data)) as pdf:
                        rec.update(parse(pdf))
                    rec['sheet_url'] = u
                    rec['sheet_bytes'] = len(data)
                except Exception as e:  # noqa: BLE001
                    miss.append((path, f'pdf: {e}'))
            else:
                miss.append((path, 'pdf не скачался'))
        else:
            miss.append((path, 'нет техкарты'))
        sheets[key] = rec
    json.dump(sheets, open(os.path.join(DST, 'sheets.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    # техкарты — в список файлов для скачивания на Mac (catalogs/rugiano/), как у других фабрик
    fj = os.path.join(DST, 'files.json')
    fl = json.load(open(fj, encoding='utf-8'))
    for key, v in sheets.items():
        if v.get('sheet_url'):
            name = re.sub(r'[^a-z0-9]+', '-', key.lower()).strip('-')
            fl['files'][v['sheet_url']] = {'file': f'catalogs/rugiano/{name}.pdf', 'pages': v['pages'], 'bytes': v['sheet_bytes']}
    json.dump(fl, open(fj, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    ok = [v for v in sheets.values() if v.get('sheet_url')]
    print(f'изделий {len(sheets)}, техкарт {len(ok)}, с размерами {sum(1 for v in ok if v.get("dimensions"))}, '
          f'с материалами {sum(1 for v in ok if v.get("materials"))}, с весом {sum(1 for v in ok if v.get("weight_kg"))}; '
          f'нет: {miss[:15]}')


if __name__ == '__main__':
    main()
