# Delta Light: размеры скачанных фото и чертежей (SVG — по viewBox) → manifest-delta.json для make_sources.py
#   python3 delta_manifest.py            (в этой папке, после delta_run.py; файлы — в delta_files/)
import json, os, re
from PIL import Image
M = {'images': {}, 'pdfs': {}}
for l in open('dl-delta.tsv', encoding='utf-8'):
    if '\t' not in l: continue
    d = l.split('\t')[0]; p = os.path.join('delta_files', d)
    if not os.path.exists(p) or not os.path.getsize(p): continue
    b = os.path.getsize(p)
    head = open(p, 'rb').read(4096)
    if b'<svg' in head or d.lower().endswith('.svg'):
        t = head.decode('utf-8', 'ignore')
        vb = re.search(r'viewBox="\s*[-\d.]+[ ,]+[-\d.]+[ ,]+([\d.]+)[ ,]+([\d.]+)', t)
        wh = re.search(r'<svg[^>]*\swidth="([\d.]+)(?:px)?"[^>]*\sheight="([\d.]+)(?:px)?"', t)
        m = vb or wh
        if m: M['images'][d] = [round(float(m.group(1))), round(float(m.group(2))), b]
    else:
        try:
            with Image.open(p) as im: M['images'][d] = [im.width, im.height, b]
        except Exception as e:
            print('не открылось', d, e)
json.dump(M, open('manifest-delta.json', 'w'), ensure_ascii=False)
print('файлов', len(M['images']))
