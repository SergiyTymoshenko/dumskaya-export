# Molteni&C: чистка molteni.json → molteni2.json. В данных страницы — фото и техкарты и других изделий
# (вся библиотека документов), поэтому оставляем только те, в имени которых есть название изделия.
import json, re, unicodedata
def norm(s): return unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
def key(s): return re.sub(r'[^a-z0-9]', '', norm(s))
def has(k, name):
    """Название изделия — целыми словами имени файла (Green-Point → greenpoint, но «out» не совпадает с «outdoor»)."""
    t = [x for x in re.split(r'[^a-z0-9]+', norm(name)) if x]
    return bool(k) and any(''.join(t[i:j]) == k for i in range(len(t)) for j in range(i + 1, min(len(t), i + 6) + 1))
out = []
for p in json.load(open('molteni.json')):
    m = re.match(r'^(.*?)\s*\((.*)\)\s*$', p['title'] or '')
    title, hint = (m.group(1), m.group(2)) if m else (p['title'], None)
    # варианты названия: полное без «by»; до «by»; без слов-типа в конце (wall unit, column, table, system)
    t = norm(title)
    ks = [key(re.sub(r'\bby\b', ' ', t)), key(re.split(r'\bby\b', t)[0]),
          key(re.sub(r'\b(wall units?|columns?|tables?|systems?|sofas?|armchairs?)\s*$', '', re.split(r'\bby\b', t)[0]))]
    def pick(items, name):
        for k in dict.fromkeys(ks):
            hit = [x for x in items if has(k, name(x))]
            if hit: return hit
        return []
    imgs = (pick(p['images'], lambda x: x['id']) or p['images'][:2])[:10]
    ds = pick(p['datasheets'], lambda u: u.rsplit('/', 1)[-1])
    en = [u for u in ds if re.search(r'_EN\.pdf$', u)]
    q = {kk: v for kk, v in p.items() if kk != 'docs_other'}
    q.update(title=title, images=imgs, datasheets=en or ds, kind_hint=hint)
    out.append(q)
json.dump(out, open('molteni2.json', 'w'), ensure_ascii=False, indent=1)
print(len(out), 'фото', sum(len(x['images']) for x in out), 'техкарт', sum(len(x['datasheets']) for x in out))
