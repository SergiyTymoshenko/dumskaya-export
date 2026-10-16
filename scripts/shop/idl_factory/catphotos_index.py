# Страницы каталога с фото, где подписан один артикул → catphotos.json {каталог: {артикул: [(стр, (xref, w, h), картинок)]}}
import pymupdf, re, json, os
from collections import defaultdict
CODE = re.compile(r'^\d{3}[A-Z]?/[A-Za-z0-9+\-/x]+$')
H = os.path.expanduser('~')
c24 = json.load(open(f'{H}/mnt/dumskaya-export/_work/codes2024.json')); c25 = json.load(open(f'{H}/mnt/dumskaya-export/_work/codes2025.json'))
out = {}
for tag, fn, codes in (('2024', 'IDL-2024.pdf', c24), ('2025', 'IDL-2025.pdf', c25)):
    doc = pymupdf.open(fn); tech = set(codes.values()) | {12, 13}
    single = defaultdict(list)
    for i in range(len(doc)):
        if i + 1 in tech: continue
        p = doc[i]
        cs = []
        for w in p.get_text('words', flags=pymupdf.TEXTFLAGS_WORDS | pymupdf.TEXT_CLIP):
            t = w[4].split('|')[0]
            if CODE.match(t) and t not in cs: cs.append(t)
        if len(cs) != 1: continue
        area = p.rect.width * p.rect.height
        imgs = [((pymupdf.Rect(x['bbox']) & p.rect).get_area(), x['xref'], x['width'], x['height']) for x in p.get_image_info(xrefs=True)]
        imgs = [x for x in imgs if x[0] > 0.25 * area]
        if imgs: single[cs[0]].append((i + 1, max(imgs)[1:], len(imgs)))
    out[tag] = single
json.dump(out, open('catphotos.json', 'w'))
