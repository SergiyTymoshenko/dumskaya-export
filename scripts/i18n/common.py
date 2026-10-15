# Общие функции перевода: строки страницы, ссылки на другие языки, память переводов.
import json, glob, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES = os.path.join(ROOT, 'content/pages')
TM_DIR = os.path.join(ROOT, 'content/i18n')
WORK = os.path.join(ROOT, 'i18n-work')          # временные пакеты для перевода (в .gitignore)
LANGS = ('ua', 'en')

def load_pages():
    P = {}
    for f in sorted(glob.glob(os.path.join(PAGES, '*/*.json'))):
        p = json.load(open(f, encoding='utf-8'))
        P[(p['lang'], p['path'])] = p
    return P

def page_file(lang, path):
    slug = path.strip('/').split('/')[-1] if path.strip('/') not in ('', 'ua', 'en') else 'index'
    return os.path.join(PAGES, lang, slug + '.json')

def strings(p):
    """Все переводимые строки страницы: (ключ, текст)."""
    out = [('h1', p['h1'])]
    for si, s in enumerate(p['sections']):
        for bi, b in enumerate(s['blocks']):
            t = b['type']; k = f's{si}.b{bi}'
            if t == 'heading':
                out.append((k, b['text']))
            elif t == 'text':
                for pi, part in enumerate(b['parts']):
                    if part['t'] == 'p':
                        out.append((f'{k}.p{pi}', part['html']))
                    else:
                        for ii, it in enumerate(part['items']):
                            out.append((f'{k}.p{pi}.i{ii}', it))
            elif t == 'buttons':
                for ii, it in enumerate(b['items']):
                    out.append((f'{k}.i{ii}', it['text']))
            elif t == 'cards':
                for ii, it in enumerate(b['items']):
                    out.append((f'{k}.i{ii}', it['title']))
    return [(k, v) for k, v in out if isinstance(v, str) and v.strip()]

def images(p):
    for s in p['sections']:
        for b in s['blocks']:
            if b['type'] == 'gallery':
                for im in b['images']:
                    yield im
            elif b['type'] == 'cards':
                for it in b['items']:
                    if it.get('image'):
                        yield it['image']

def load_tm(lang):
    f = os.path.join(TM_DIR, f'tm-{lang}.json')
    return json.load(open(f, encoding='utf-8')) if os.path.exists(f) else {}

def save_tm(lang, tm):
    os.makedirs(TM_DIR, exist_ok=True)
    with open(os.path.join(TM_DIR, f'tm-{lang}.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(sorted(tm.items())), f, ensure_ascii=False, indent=0)

RU_ONLY = re.compile(r'[ыэъё]', re.I)
CYR = re.compile(r'[а-яёіїєґ]', re.I)

def alt_ok(lang, a):
    if not a or not a.strip():
        return False
    return not CYR.search(a) if lang == 'en' else not RU_ONLY.search(a)
