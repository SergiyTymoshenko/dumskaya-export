# Чертежи с размерами из техкарт фабрики → PNG, обрезанные по рисунку (images/shop/<фабрика>/drawings/)
# + _work/drawings-<фабрика>.json.   python3 drawings.py <фабрика> [секунд]
import io, json, os, re, sys, time, warnings
warnings.filterwarnings('ignore')
import pymupdf
from PIL import Image, ImageChops
ROOT = os.environ.get('EXPORT_DIR') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # скрипт лежит в <выгрузка>/_work/
f = sys.argv[1]; end = time.time() + float(sys.argv[2] if len(sys.argv) > 2 else 150)
out = os.path.join(ROOT, '_work', f'drawings-{f}.json')
D = json.load(open(out)) if os.path.exists(out) else {}
RULE = {
    'olev': lambda t: 'Nominal lumen' in t or 'Item' in t and 'Power' in t,
    'baxter': lambda t: len(re.findall(r'\b\d+(?:[.,]\d+)? ?cm\b', t)) >= 3,
    'molteni': lambda t: re.search(r'^\s*DIMENSIONS\s*$', t, re.M),
    'maxalto': lambda t: 'Technical drawings' in t,
    'flexform': lambda t: 'TECHNICAL DRAWINGS' in t,
}[f]
DIMS = re.compile(r'\d+(?:[.,]\d+)? ?x ?\d+(?:[.,]\d+)?.*?h ?\d+(?:[.,]\d+)? ?cm')
LABEL = re.compile(r'^\s*\d+(?:[.,]\d+)?\s?cm\s*$', re.M)
INCH = re.compile(r'^\s*[\d¼½¾⅛⅜⅝⅞\s/.,]+\s?["”″\'’]{1,2}\s*$')
def lines(pg):
    out = []
    for b in pg.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            t = ''.join(s['text'] for s in l['spans']).strip()
            if t: out.append((*l['bbox'], t))
    return out
KEEP = re.compile(r'COD\.|\d+(?:[.,]\d+)?\s?cm\b')
def clip_for(pg):
    W, H = pg.rect.width, pg.rect.height
    x0, y0, x1, y1 = 0, 0, W, H
    blocks = [b for b in pg.get_text('blocks') if b[4].strip()]
    top = [b for b in blocks if b[3] < H * 0.11 and not KEEP.search(b[4])]   # шапка (без подписей чертежа)
    bot = [b for b in blocks if b[1] > H * 0.90 and not KEEP.search(b[4])]   # подвал
    if top: y0 = max(b[3] for b in top) + 2
    if bot: y1 = min(b[1] for b in bot) - 2
    if f == 'molteni':                                     # левая колонка с логотипом; сверху — от «DIMENSIONS»
        x0 = W * 0.22
        ys = [b[1] for b in blocks if re.match(r'\s*DIMENSIONS\s*$', b[4])]
        if ys: y0 = max(y0, min(ys) - 4)
    if f == 'baxter':                                      # полосы с чертежами: по подписям «82 cm» и строкам «280 x 110 h82 cm»
        L = lines(pg)
        ys = [(b[1], b[3]) for b in L if LABEL.search(b[4]) or DIMS.search(b[4])]
        if ys: y0, y1 = max(y0, min(a for a, _ in ys) - 30), min(y1, max(b for _, b in ys) + 30)
        lb = [b for b in L if LABEL.search(b[4])]          # только рисунки, без текста слева (размеры есть в данных)
        if lb: x0, x1 = max(0, min(b[0] for b in lb) - 50), min(W, max(b[2] for b in lb) + 50)
    return pymupdf.Rect(x0, y0, x1, y1)
def ink_crop(im):
    g = im.convert('L')
    bg = max(g.getcolors(1 << 16) or [(0, 255)])[1]
    diff = ImageChops.difference(g, Image.new('L', g.size, bg)).point(lambda v: 255 if v > 40 else 0)
    bb = diff.getbbox()
    if not bb or (bb[2] - bb[0]) < 60 or (bb[3] - bb[1]) < 40: return None
    p = 16
    return im.crop((max(0, bb[0] - p), max(0, bb[1] - p), min(im.width, bb[2] + p), min(im.height, bb[3] + p)))
def save(): json.dump(D, open(out + '.tmp', 'w'), ensure_ascii=False); os.replace(out + '.tmp', out)
odir = os.path.join(ROOT, 'images/shop', f, 'drawings'); os.makedirs(odir, exist_ok=True)
n = 0
for dp, _, fs in os.walk(os.path.join(ROOT, 'catalogs', f)):
    for name in sorted(fs):
        if not name.lower().endswith('.pdf') or '.part' in name: continue
        p = os.path.join(dp, name); rel = os.path.relpath(p, ROOT)
        if rel in D: continue
        if time.time() > end: save(); print('пауза', len(D)); sys.exit(0)
        res = []
        try:
            d = pymupdf.open(p)
            cont = False
            for i in range(d.page_count):
                if len(res) >= 6: break
                pg = d[i]; t = pg.get_text()
                hit = RULE(t)
                if f == 'molteni' and not hit and cont and not re.search(r'^\s*(FINISHES|TECHNICAL INFORMATION)\s*$', t, re.M) and re.search(r'\d', t):
                    hit = True
                if not hit: continue
                cont = True
                dpi = 400 if f == 'baxter' else 200
                cl = clip_for(pg)
                im = Image.open(io.BytesIO(pg.get_pixmap(dpi=dpi, clip=cl, alpha=False).tobytes('png'))).convert('RGB')
                if f == 'baxter':                                  # убрать текст (кроме подписей «82 cm») и линии-разделители
                    from PIL import ImageDraw
                    dr = ImageDraw.Draw(im); k = dpi / 72
                    for b in lines(pg):
                        if not LABEL.search(b[4]) and not INCH.search(b[4]):
                            dr.rectangle([(b[0] - cl.x0) * k - 4, (b[1] - cl.y0) * k - 4, (b[2] - cl.x0) * k + 4, (b[3] - cl.y0) * k + 4], fill='white')
                    g = im.convert('L').point(lambda v: 255 if v < 200 else 0)
                    for y in range(g.height):
                        row = g.crop((0, y, g.width, y + 1))
                        if sum(row.histogram()[255:]) > g.width * 0.6: dr.line([(0, y), (im.width, y)], fill='white')
                c = ink_crop(im)
                if f == 'molteni' and c is not None and c.width * c.height < 40000: c = None   # обрезка не удалась — вся страница
                c = c or ink_crop(Image.open(io.BytesIO(pg.get_pixmap(dpi=200, alpha=False).tobytes('png'))).convert('RGB'))
                if c is None: continue
                if c.width > 2000: c = c.resize((2000, round(c.height * 2000 / c.width)), Image.LANCZOS)
                fn = re.sub(r'[^\w.\-]+', '_', os.path.splitext(name)[0]) + f'-p{i + 1}.png'
                c.save(os.path.join(odir, fn), optimize=True)
                res.append({'page': i + 1, 'file': f'images/shop/{f}/drawings/{fn}', 'width': c.width, 'height': c.height,
                            'bytes': os.path.getsize(os.path.join(odir, fn))})
            d.close()
        except Exception as e:
            res = {'error': f'{type(e).__name__}: {e}'}
        D[rel] = res; n += 1
        if n % 40 == 0: save()
save(); print('ГОТОВО', f, len(D), 'страниц', sum(len(v) for v in D.values() if isinstance(v, list)))
