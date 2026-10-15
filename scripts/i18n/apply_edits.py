#!/usr/bin/env python3
"""Применяет редакторские правки к русским страницам:
   python3 scripts/i18n/apply_edits.py i18n-work/review/edits-*.json
Формат правки: {"page": "/path", "key": "s1.b2.p3", "old": "точная текущая строка", "new": "новая строка"}
  key: h1 | title | description | s<i>.b<j> (заголовок) | s<i>.b<j>.p<k> (абзац) | s<i>.b<j>.p<k>.i<n> (пункт списка)
       | s<i>.b<j>.i<n> (кнопка/карточка) | s<i>.b<j>.q<n> / a<n> (вопрос/ответ)
  new = "" — удалить абзац/пункт. Если old не совпадает с текущим текстом, правка пропускается.
Переводы для изменённых строк потом делаются заново (extract → перевод → assemble --import)."""
import json, os, sys, re, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

files = {}
for f in glob.glob(os.path.join(PAGES, 'ru/*.json')):
    files[json.load(open(f, encoding='utf-8'))['path']] = f
applied, skipped, removed = 0, [], 0
TAGS = re.compile(r'</?(?!strong\b|a\b|em\b)[a-z]+[^>]*>', re.I)

KEY = re.compile(r's(\d+)\.b(\d+)(?:\.(p|i|q|a)(\d+))?(?:\.i(\d+))?$')

def find(page, key):
    """возвращает (контейнер, индекс/ключ, родитель для удаления: (список, индекс) или None)"""
    if key in ('h1', 'title', 'description'): return page, key, None
    m = KEY.match(key)
    if not m: return None
    si, bi, kind, n, ii = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4), m.group(5)
    try:
        b = page['sections'][si]['blocks'][bi]
        if kind is None:
            if b['type'] == 'heading': return b, 'text', None
            return (b, 'title', None) if b['type'] in ('facts', 'form') else None
        n = int(n)
        if kind == 'p':
            part = b['parts'][n]
            if ii is not None: return part['items'], int(ii), (part['items'], int(ii))
            return part, 'html', (b['parts'], n)
        if kind == 'i':
            it = b['items'][n]; return it, ('text' if 'text' in it else 'title'), None
        if kind in ('q', 'a'): return b['items'][n], kind, None
    except (IndexError, KeyError):
        return None

def order(e):
    """сначала замены (индексы ещё не сдвинуты), потом удаления — от больших индексов к меньшим"""
    m = KEY.match(e['key'])
    nums = tuple(int(x) for x in m.groups() if x and x.isdigit()) if m else ()
    return (e['new'].strip() == '', tuple(-x for x in nums))

for ef in sys.argv[1:]:
    edits = json.load(open(ef, encoding='utf-8'))
    by_page = {}
    for e in edits: by_page.setdefault(e['page'], []).append(e)
    for path, es in by_page.items():
        if path not in files: skipped += [(path, e['key'], 'нет страницы') for e in es]; continue
        page = json.load(open(files[path], encoding='utf-8'))
        for e in sorted(es, key=order):
            loc = find(page, e['key'])
            if not loc: skipped.append((path, e['key'], 'нет ключа')); continue
            cont, k, parent = loc
            cur = cont[k]
            if cur.strip() != e['old'].strip():
                skipped.append((path, e['key'], f'старый текст не совпал: {cur[:60]!r}')); continue
            new = e['new'].strip()
            if TAGS.search(new): skipped.append((path, e['key'], 'недопустимые теги')); continue
            if k in ('title', 'description') and cont is page and len(new) > (60 if k == 'title' else 155):
                skipped.append((path, e['key'], 'слишком длинно')); continue
            if new == '':
                if not parent: skipped.append((path, e['key'], 'нельзя удалить')); continue
                lst, idx = parent
                del lst[idx]; removed += 1
            else:
                cont[k] = new
            applied += 1
        # пустые текстовые блоки и списки — убрать
        for s in page['sections']:
            for b in s['blocks']:
                if b['type'] == 'text': b['parts'] = [p for p in b['parts'] if p['t'] == 'p' or p['items']]
            s['blocks'] = [b for b in s['blocks'] if b['type'] != 'text' or b['parts']]
        if page['sections'] and page['sections'][0]['blocks'] and page['sections'][0]['blocks'][0]['type'] == 'heading' and page['sections'][0]['blocks'][0]['level'] == 1:
            page['h1'] = page['sections'][0]['blocks'][0]['text']
        json.dump(page, open(files[path], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'применено {applied} (удалено {removed}), пропущено {len(skipped)}')
for s in skipped[:30]: print('  пропуск:', s)
