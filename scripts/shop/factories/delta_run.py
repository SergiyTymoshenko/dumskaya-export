# Delta Light целиком в одном процессе (общая пауза 20 с между любыми запросами к deltalight.com):
# 1) страницы подсемейств → delta.json (из кеша — мгновенно, новые — по одной в 20 с);
# 2) по одному фото изделия и чертёж (SVG) на подсемейство → delta_files/<путь в выгрузке> + dl-delta.tsv.
# Повторный запуск продолжает с того же места.
import json, os, re, sys, time
from common import get, save
import delta
D = 20
BASE = 'https://deltalight.com/media/cache/resolve/'
def slug(s): return re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')
time.sleep(D)   # пауза и после прошлого запуска
U = delta.urls(); print('подсемейств', len(U), flush=True)
out = []
for i, u in enumerate(U):
    h = get(u, delay=D)
    try: out.append(delta.parse(u, h) if h else {'url': u, 'error': 'fetch'})
    except Exception as e: out.append({'url': u, 'error': f'parse {type(e).__name__}: {e}'})
    if i % 25 == 0: save('delta.json', out); print('стр', i, flush=True)
save('delta.json', out)
ok = [x for x in out if not x.get('error')]
print('страницы готовы:', len(ok), 'ошибок', len(out) - len(ok), flush=True)
rows, seen = [], set()
for x in ok:
    fam, sub = slug(x.get('family')), slug(x.get('subfamily')) or x['url'].rsplit('/', 1)[-1]
    for kind, res, flt in ([('shot', x['shots'][0]['resource'], 'website_image_w_1600')] if x.get('shots') else []) + \
                          ([('drawing', x['drawing'], 'website_image_w_640')] if x.get('drawing') else []):
        if res in seen: continue
        seen.add(res)
        rows.append((f"images/shop/delta/{fam}/{sub}/{res.rsplit('/', 1)[-1]}", BASE + flt + '/' + res))
open('dl-delta.tsv', 'w').write(''.join(f'{d}\t{u}\n' for d, u in rows))
print('файлов к скачиванию', len(rows), flush=True)
done = 0
for d, u in rows:
    p = os.path.join('delta_files', d)
    if os.path.exists(p) and os.path.getsize(p) > 0: done += 1; continue
    b = get(u, delay=D, cache=False, binary=True)
    if b:
        os.makedirs(os.path.dirname(p), exist_ok=True); open(p, 'wb').write(b); done += 1
    else:
        print('НЕТ', u, flush=True)
    if done % 25 == 0: print('файлы', done, 'из', len(rows), flush=True)
print('ГОТОВО файлов', done, 'из', len(rows), flush=True)
