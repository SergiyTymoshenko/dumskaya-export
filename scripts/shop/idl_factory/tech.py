# Чертежи и техданные с технических страниц каталога IDL (PyMuPDF).
# Слова берутся с флагом TEXT_CLIP: на многих страницах лист со всеми ячейками вложен несколько раз и обрезан
# «окнами», без учёта обрезки в слое текста оказываются чужие подписи. Ячейка товара — от его подписи-артикула
# до соседних подписей справа и снизу; техданные — строки текста под подписью.
# python3 tech9.py <pdf> <tag> <codes.json {code: page}> <K> <N> → ~/work/idl/tech-<tag>/part-K.json
import re, json, sys, os
from collections import defaultdict
import pymupdf
from PIL import Image, ImageOps
src, tag, codesf, K, N = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
codes = json.load(open(codesf))
out = os.path.expanduser(f'~/work/idl/tech-{tag}'); os.makedirs(out, exist_ok=True)
part = os.path.join(out, f'part-{K}.json')
res = json.load(open(part)) if os.path.exists(part) else {}
CODE = re.compile(r'^\d{3}[A-Z]?/[A-Za-z0-9+\-/x]+$')
SPEC = re.compile(r'LED|E14|E27|G9|G4|GU10|R7S|Strip|STRIP|lumen', re.I)
DPI = 220; s = DPI / 72
doc = pymupdf.open(src)
by_page = defaultdict(list)
for c, pg in codes.items(): by_page[pg].append(c)
def trim(im, pad=20):
    bb = ImageOps.invert(im).point(lambda v: 255 if v > 40 else 0).getbbox()
    return im.crop((max(bb[0] - pad, 0), max(bb[1] - pad, 0), min(bb[2] + pad, im.width), min(bb[3] + pad, im.height))) if bb else im
for i, (pg, want) in enumerate(sorted(by_page.items())):
    if i % N != K or all(c in res for c in want): continue
    p = doc[pg - 1]; pw, ph = p.rect.width, p.rect.height
    ws = [dict(x0=w[0], top=w[1], x1=w[2], bottom=w[3], text=w[4]) for w in p.get_text('words', flags=pymupdf.TEXTFLAGS_WORDS | pymupdf.TEXT_CLIP)]
    pix = p.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY, alpha=False)
    A = Image.frombytes('L', (pix.width, pix.height), pix.samples)
    labs = [w for w in ws if CODE.match(w['text']) and any(w['x0'] - 4 < v['x0'] < w['x0'] + 60 and 3 < v['top'] - w['top'] < 48 and SPEC.search(v['text']) for v in ws)]
    # горизонтальные линейки над ячейками (длиннее 100 pt)
    rules = []
    for d in p.get_drawings():
        for it in d['items']:
            if it[0] == 'l' and abs(it[1].y - it[2].y) < 0.8 and abs(it[2].x - it[1].x) > 100:
                rules.append((min(it[1].x, it[2].x), it[1].y, max(it[1].x, it[2].x)))
            elif it[0] == 're' and it[1].height < 1.2 and it[1].width > 100:
                rules.append((it[1].x0, it[1].y0, it[1].x1))
    for c in want:
        cand = [w for w in labs if w['text'] == c]
        if not cand:
            res[c] = {'page': pg, 'err': 'no label'}; continue
        L = cand[0]
        others = [o for o in labs if not (abs(o['x0'] - L['x0']) < 5 and abs(o['top'] - L['top']) < 5)]
        # верх стопки артикулов с общим чертежом (подписи друг под другом ближе 70 pt)
        Hd = L
        while True:
            up = [o for o in labs if abs(o['x0'] - Hd['x0']) < 12 and 5 < Hd['top'] - o['top'] < 70]
            if not up: break
            Hd = max(up, key=lambda o: o['top'])
        x0, top = max(L['x0'] - 4, 0), max(Hd['top'] - 6, 0)
        nxt_own = [o['top'] for o in labs if abs(o['x0'] - L['x0']) < 12 and 5 < o['top'] - L['top'] < 70]
        right = [o['x0'] for o in others if abs(o['top'] - L['top']) < 30 and o['x0'] > L['x0'] + 40]
        x1 = min(min(right) - 6 if right else pw - 8, L['x0'] + 176, pw - 8)
        below = [o['top'] for o in others if o['top'] > L['top'] + 20 and o['x0'] < x1 - 10 and o['x1'] > x0 + 10]
        def cell_bottom(M, x1):
            below = [o for o in labs if o['top'] > M['top'] + 20 and o['x0'] < x1 - 10 and o['x1'] > M['x0'] - 4 + 10]
            b = (min(o['top'] for o in below) - 12) if below else ph - 40
            rb = [y for a, y, b_ in rules if y > M['top'] + 60 and abs(a - M['x0']) < 12]
            if rb: b = min(b, min(rb) - 4)
            return b, below
        bottom, below = cell_bottom(L, x1)
        # несколько артикулов друг под другом в одной ячейке (общий чертёж) — ячейка до конца последнего
        M = L; shared = [Hd['text']] if Hd is not L else []
        while bottom - top < 60 and below:
            nxt = min(below, key=lambda o: o['top'])
            if abs(nxt['x0'] - L['x0']) > 12 or nxt['top'] - M['top'] > 70: break
            shared.append(nxt['text']); M = nxt
            bottom, below = cell_bottom(M, x1)
        tb = (min(nxt_own) - 2) if nxt_own else bottom
        cw = [w for w in ws if L['x0'] - 2 <= w['x0'] < min(L['x0'] + 95, x1) and L['top'] - 2 < w['top'] < tb]
        lines = defaultdict(dict)
        for w in cw: lines[round(w['top'] / 2)].setdefault(round(w['x0']), w)
        tl = [' '.join(q['text'] for q in sorted(v.values(), key=lambda w: w['x0'])) for k, v in sorted(lines.items())]
        tl = [t.strip() for t in tl if t.strip()]
        r = {'page': pg, 'dup': len(cand), 'shared': shared,
             'light': next((t for t in tl if re.search(r'LED|E14|E27|G9|G4|GU10|R7S|STRIP|Strip', t) and t != c), ''),
             'max': next((t for t in tl if t.upper().startswith('MAX')), ''),
             'lumen': next((t for t in tl if 'lumen' in t.lower()), ''),
             'dimming': next((t for t in tl if re.fullmatch(r'[A-D](\s*-\s*[A-D])*', t)), ''),
             'lines': tl[:10]}
        if x1 - x0 >= 90 and bottom - top >= 60:
            f = c.replace('/', '_') + '.png'
            im = A.crop((int(x0 * s), int(top * s), int(x1 * s), int(bottom * s)))
            bb = ImageOps.invert(im).point(lambda v: 255 if v > 40 else 0).getbbox()
            txr = max([w['x1'] for w in cw if not re.fullmatch(r'[\d.,/Øx•·\-–max ]*', w['text'])] + [L['x1']]) - x0
            if bb and bb[2] > (txr + 10) * s:
                trim(im).save(os.path.join(out, f), optimize=True)
                r['drawing'] = f
            else:
                r['note'] = 'no drawing in cell'
        else:
            r['note'] = f'small cell {x0:.0f},{top:.0f},{x1:.0f},{bottom:.0f}'
        res[c] = r
    json.dump(res, open(part, 'w'), ensure_ascii=False, indent=1)
    print('page', pg, len(want), sum(1 for c in want if 'err' not in res[c]), sum(1 for c in want if res[c].get('drawing')), flush=True)
