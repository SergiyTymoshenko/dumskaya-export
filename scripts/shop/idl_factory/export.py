# Фото и тексты с сайта IDL + чертежи из каталогов → папка выгрузки на Mac и сводный JSON
import json, os, shutil, glob, re
from PIL import Image
H = os.path.expanduser('~')
site = json.load(open(f'{H}/work/idl/site/img/site.json'))
EXP = f'{H}/mnt/dumskaya-export/images/shop/idl'
os.makedirs(EXP, exist_ok=True)
PRE = 'https://www.idl1987.it/wp-content/uploads/'
out = {'collections': {}, 'tech': {}}
seen = {}
for slug, langs in site.items():
    c = {'texts': {}, 'videos': [], 'images': []}
    for lang, d in langs.items():
        ps = [x for t, x in d['blocks'] if t == 'P']
        mk = next((i for i, x in enumerate(ps) if x.strip().lower() in ('доступные отделки', 'available finishes', 'finiture disponibili')), None)
        h2 = next((x for t, x in d['blocks'] if t == 'H2'), '')
        caps = [x for t, x in d['blocks'] if t == 'FIGCAPTION']
        c['texts'][lang] = {'designer_line': h2, 'description': ps[:mk] if mk is not None else ps,
                            'finishes': ' '.join(ps[mk + 1:]) if mk is not None else '', 'captions': caps}
        for y in d.get('yt', []):
            if y not in c['videos']: c['videos'].append(y)
    for url, alt in langs['ru']['figs']:
        rel = url.replace(PRE, '')
        src = f'{H}/work/idl/site/img/{rel}'
        if not os.path.exists(src): continue
        name = os.path.basename(rel)
        if url in seen:
            c['images'].append(seen[url]); continue
        dst_rel = f'{slug}/{name}'
        if os.path.exists(f'{EXP}/{dst_rel}') and os.path.getsize(f'{EXP}/{dst_rel}') != os.path.getsize(src):
            dst_rel = f"{slug}/{rel.replace('/', '-')}"
        os.makedirs(f'{EXP}/{slug}', exist_ok=True)
        if not os.path.exists(f'{EXP}/{dst_rel}'): shutil.copyfile(src, f'{EXP}/{dst_rel}')
        im = Image.open(src)
        e = {'file': f'images/shop/idl/{dst_rel}', 'url': url, 'width': im.width, 'height': im.height, 'bytes': os.path.getsize(src)}
        seen[url] = e; c['images'].append(e)
    out['collections'][slug] = c
# чертежи: сначала 2024, затем 2025 (новее — поверх)
os.makedirs(f'{EXP}/tech', exist_ok=True)
for tag, cat in (('2024', 'IDL 2024'), ('2025', 'IDL Novelties 2025')):
    d = {}
    for f in sorted(glob.glob(f'{H}/work/idl/tech-{tag}/part-*.json')) + sorted(glob.glob(f'{H}/work/idl/tech-{tag}fix/part-*.json')): d.update(json.load(open(f)))
    for code, v in d.items():
        if 'err' in v: continue
        v = dict(v, catalog=cat)
        if v.get('drawing'):
            src = f'{H}/work/idl/tech-{tag}/{v["drawing"]}'
            if not os.path.exists(src): src = f'{H}/work/idl/tech-{tag}fix/{v["drawing"]}'
            shutil.copyfile(src, f'{EXP}/tech/{v["drawing"]}')
            im = Image.open(src)
            v['drawing'] = {'file': f'images/shop/idl/tech/{v["drawing"]}', 'width': im.width, 'height': im.height, 'bytes': os.path.getsize(src)}
        out['tech'][code] = v
json.dump(out, open(f'{H}/mnt/dumskaya-export/_work/idl-site.json', 'w'), ensure_ascii=False, indent=1)
print(len(out['collections']), sum(len(c['images']) for c in out['collections'].values()), len(out['tech']), sum(1 for v in out['tech'].values() if v.get('drawing')))
