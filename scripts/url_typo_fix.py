#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Разовая правка 23.10.2026: опечатка «apartmens» в адресах страниц → «apartments».

Старые адреса остаются переадресациями 301 на новые (content/redirects.json), прежние переадресации,
которые вели на старые адреса, сразу ведут на новые — без цепочек. Имена файлов фото не меняются
(content/image-names.json и поле file в images.json не трогаем).
   python3 scripts/url_typo_fix.py
"""
import glob, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOVES = {
    '/interior-design-apartmens-bratislava': '/interior-design-apartments-bratislava',
    '/interior-design-apartmens-warsaw': '/interior-design-apartments-warsaw',
    '/en/interior-design-apartmens-warsaw': '/en/interior-design-apartments-warsaw',
    '/apartmens-vienna-luxury-interior-design-58m': '/apartments-vienna-luxury-interior-design-58m',
    '/en/apartmens-vienna-luxury-interior-design-58m': '/en/apartment-interior-design-vienna-austria-58sqm',
    '/apartmens-wien-luxury-interior-design-115m': '/apartments-wien-luxury-interior-design-115m',
    '/apartmens-ny-luxury-interior-design-57m': '/apartments-new-york-luxury-interior-design-57m',
    '/apartmens-dubai-luxury-interior-design-160': '/apartments-dubai-luxury-interior-design-160m',
    '/apartmens-praha-luxury-interior-design-90m': '/apartments-praha-luxury-interior-design-90m',
    '/apartmens-los-angeles-interior-design-140': '/apartments-los-angeles-interior-design-140m',
}
# адрес целиком: слева кавычка/скобка/«=», справа кавычка, якорь, параметры или конец ссылки
RX = re.compile(r'(?<=[\'"(=])(' + '|'.join(re.escape(k) for k in sorted(MOVES, key=len, reverse=True)) + r')(?=[\'"#?)\s<\\]|$)')


def fix_text(s):
    return RX.sub(lambda m: MOVES[m.group(1)], s)


def rewrite(path, fn=fix_text):
    old = open(path, encoding='utf-8').read()
    new = fn(old)
    if new != old:
        open(path, 'w', encoding='utf-8').write(new)
        return True
    return False


changed = []
# страницы: содержимое, затем имя файла по новому адресу
for f in glob.glob(os.path.join(ROOT, 'content/pages/*/*.json')):
    if rewrite(f):
        changed.append(f)
    d = json.load(open(f, encoding='utf-8'))
    want = d['path'].strip('/').split('/')[-1] + '.json'
    if os.path.basename(f) != want and d['path'] in MOVES.values():
        os.rename(f, os.path.join(os.path.dirname(f), want))
for name in ['projects.json', 'projects-order.json', 'projects-overrides.json', 'site.json', 'home.json',
             'i18n/tm-ua.json', 'i18n/tm-en.json']:
    if rewrite(os.path.join(ROOT, 'content', name)):
        changed.append(name)
for name in ['city_pages.py', 'seo_meta.py', 'project_facts.py']:
    if rewrite(os.path.join(ROOT, 'scripts', name)):
        changed.append(name)

# dead_redirects.py: старые адреса там — источники переадресаций, меняем только цели (после двоеточия)
def fix_targets(s):
    return re.sub(r'(:\s*["\'])([^"\']+)(["\'])', lambda m: m.group(1) + MOVES.get(m.group(2), m.group(2)) + m.group(3), s)
if rewrite(os.path.join(ROOT, 'scripts', 'dead_redirects.py'), fix_targets):
    changed.append('dead_redirects.py')

# переадресации: цели — на новые адреса, старые адреса — на новые
red_path = os.path.join(ROOT, 'content', 'redirects.json')
red = json.load(open(red_path, encoding='utf-8'))
red = {k: MOVES.get(v, v) for k, v in red.items()}
for old, new in MOVES.items():
    red[old] = new
open(red_path, 'w', encoding='utf-8').write(json.dumps(dict(sorted(red.items())), ensure_ascii=False, indent=1) + '\n')

# подпись фото с опечаткой (alt, не имя файла)
rewrite(os.path.join(ROOT, 'content', 'images.json'),
        lambda s: s.replace('"apartmens dumskaya interior design bratislava"', '"apartment interior design bratislava"'))
print('изменено файлов:', len(changed))
