# Фото товаров со страниц каталога, где подписан один артикул: самая большая картинка страницы
import pymupdf, json, os, io, sys
from PIL import Image, ImageCms
H = os.path.expanduser('~')
EXP = f'{H}/mnt/dumskaya-export/images/shop/idl/catalog'; os.makedirs(EXP, exist_ok=True)
cp = json.load(open('catphotos.json'))
res = json.load(open('catphotos-out.json')) if os.path.exists('catphotos-out.json') else {}
part, nparts = int(sys.argv[1]), int(sys.argv[2])
for tag, fn in (('2024', 'IDL-2024.pdf'), ('2025', 'IDL-2025.pdf')):
    doc = pymupdf.open(fn)
    items = sorted(cp[tag].items())
    for k, (code, pages) in enumerate(items):
        if k % nparts != part: continue
        for pg, (xref, w, h), n in pages:
            name = f"{code.replace('/', '_')}-{tag}-p{pg}.jpg"
            if os.path.exists(f'{EXP}/{name}'): continue
            try:
                d = doc.extract_image(xref)
                im = Image.open(io.BytesIO(d['image']))
                if im.mode == 'CMYK':
                    im = im.convert('RGB') if not d.get('cs-name', '').startswith('ICC') else im.convert('RGB')
                if im.mode not in ('RGB', 'L'): im = im.convert('RGB')
                im.thumbnail((2000, 2000), Image.LANCZOS)
                im.save(f'{EXP}/{name}', quality=86, optimize=True, progressive=True)
            except Exception as e:
                print('ERR', code, pg, e, flush=True)
