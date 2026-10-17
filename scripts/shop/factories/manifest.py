# Размеры фото и текст PDF по фабрике → _work/manifest-<фабрика>.json (дописывает, уже сделанное пропускает).
#   python3 manifest.py <фабрика> [секунд]
import json, os, sys, time, warnings
warnings.filterwarnings('ignore')
from PIL import Image
import pymupdf
ROOT = os.environ.get('EXPORT_DIR') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # скрипт лежит в <выгрузка>/_work/
f = sys.argv[1]; end = time.time() + float(sys.argv[2] if len(sys.argv) > 2 else 150)
out = os.path.join(ROOT, '_work', f'manifest-{f}.json')
M = json.load(open(out)) if os.path.exists(out) else {'images': {}, 'pdfs': {}}
def save(): json.dump(M, open(out + '.tmp', 'w'), ensure_ascii=False); os.replace(out + '.tmp', out)
n = 0
for top, kind in ((f'images/shop/{f}', 'images'), (f'catalogs/{f}', 'pdfs')):
    for dp, _, fs in os.walk(os.path.join(ROOT, top)):
        for name in sorted(fs):
            if '.part' in name or name.startswith('.'): continue
            p = os.path.join(dp, name); rel = os.path.relpath(p, ROOT)
            if rel in M[kind]: continue
            if time.time() > end: save(); print('пауза, сделано', len(M['images']), len(M['pdfs'])); sys.exit(0)
            try:
                if kind == 'images':
                    with Image.open(p) as im: M[kind][rel] = [im.width, im.height, os.path.getsize(p)]
                elif name.lower().endswith('.pdf'):
                    d = pymupdf.open(p)
                    M[kind][rel] = {'pages': d.page_count, 'bytes': os.path.getsize(p), 'text': [d[i].get_text()[:6000] for i in range(min(d.page_count, 6))]}
                    d.close()
            except Exception as e:
                M[kind][rel] = {'error': f'{type(e).__name__}: {e}'}
            n += 1
            if n % 300 == 0: save()
save(); print('ГОТОВО', f, 'фото', len(M['images']), 'pdf', len(M['pdfs']))
