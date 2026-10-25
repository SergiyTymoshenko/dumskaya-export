# Размеры фото и текст PDF по фабрике → _work/manifest-<фабрика>.json (дописывает, уже сделанное пропускает).
#   python3 manifest.py <фабрика> [секунд]
import json, os, re, sys, time, warnings
warnings.filterwarnings('ignore')
from PIL import Image
import pymupdf
ROOT = os.environ.get('EXPORT_DIR') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # скрипт лежит в <выгрузка>/_work/
f = sys.argv[1]; end = time.time() + float(sys.argv[2] if len(sys.argv) > 2 else 150)
out = os.path.join(ROOT, '_work', f'manifest-{f}.json')
M = json.load(open(out)) if os.path.exists(out) else {'images': {}, 'pdfs': {}}
def save(): json.dump(M, open(out + '.tmp', 'w'), ensure_ascii=False); os.replace(out + '.tmp', out)
def en_column(d):
    """Minotti: описание в техкарте — четыре колонки (IT, EN, DE, FR); берём английскую (вторую) с первых страниц."""
    res = []
    for i in range(min(d.page_count, 8)):
        pg = d[i]; W, Hh = pg.rect.width, pg.rect.height
        bl = [b for b in pg.get_text('blocks') if b[4].strip() and Hh * 0.09 < b[1] < Hh * 0.95]
        col = lambda b: 0 if b[0] < W * 0.27 else 1 if b[0] < W * 0.5 else 2 if b[0] < W * 0.72 else 3
        t = '\n'.join(b[4].strip() for b in sorted((b for b in bl if col(b) == 1), key=lambda b: (b[1], b[0])))
        t = re.split(r'^[\d\s/.,¼½¾⅛⅜⅝⅞]+$', t, maxsplit=1, flags=re.M)[0].strip()   # дальше — размеры с чертежа
        prose = re.search(r'^[A-Z][^:\n]{2,40}:', t, re.M) or len(re.findall(r'[a-z]{4,}', t)) >= 10
        if len({col(b) for b in bl}) < 4 or not prose:      # страница с чертежами — не текст
            if res: break
            continue
        res.append(t)
    return res
n = 0
for top, kind in ((f'images/shop/{f}', 'images'), (f'catalogs/{f}', 'pdfs')):
    for dp, _, fs in os.walk(os.path.join(ROOT, top)):
        for name in sorted(fs):
            if '.part' in name or name.startswith('.'): continue
            p = os.path.join(dp, name); rel = os.path.relpath(p, ROOT)
            if rel in M[kind]: continue
            if time.time() > end: save(); print('пауза, сделано', len(M['images']), len(M['pdfs'])); sys.exit(0)
            try:
                if kind == 'images' and name.lower().endswith('.svg'):      # чертёж SVG — размеры по viewBox
                    t = open(p, 'rb').read(8192).decode('utf-8', 'ignore')
                    m = re.search(r'viewBox="\s*[-\d.]+[ ,]+[-\d.]+[ ,]+([\d.]+)[ ,]+([\d.]+)', t) or \
                        re.search(r'<svg[^>]*\swidth="([\d.]+)(?:px)?"[^>]*\sheight="([\d.]+)(?:px)?"', t)
                    M[kind][rel] = [round(float(m.group(1))), round(float(m.group(2))), os.path.getsize(p)] if m else {'error': 'svg без размеров'}
                elif kind == 'images':
                    with Image.open(p) as im: M[kind][rel] = [im.width, im.height, os.path.getsize(p)]
                elif name.lower().endswith('.pdf'):
                    d = pymupdf.open(p)
                    M[kind][rel] = {'pages': d.page_count, 'bytes': os.path.getsize(p), 'text': [d[i].get_text()[:6000] for i in range(min(d.page_count, 6))]}
                    if f == 'minotti': M[kind][rel]['text_en'] = en_column(d)
                    d.close()
            except Exception as e:
                M[kind][rel] = {'error': f'{type(e).__name__}: {e}'}
            n += 1
            if n % 300 == 0: save()
save(); print('ГОТОВО', f, 'фото', len(M['images']), 'pdf', len(M['pdfs']))
