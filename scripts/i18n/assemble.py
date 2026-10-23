#!/usr/bin/env python3
"""Шаг 3 перевода: 1) добавляет готовые пакеты i18n-work/out-*.json в память переводов
content/i18n/tm-{ua,en}.json; 2) собирает украинские и английские страницы из русских:
та же структура, фото и блоки, тексты — из памяти переводов, ссылки — на страницы того же языка.
Адрес, title, description и картинка для соцсетей у страниц UA/EN остаются прежними.
Словацкие и немецкие страницы (NEW_LANGS): title и description — из content/i18n/meta-<lang>.json (ключ — русский адрес);
ссылки на страницы, которых на этом языке нет, убираются (текст остаётся, кнопка или карточка — нет);
телефоны — только номер своего языка (sk — словацкий, de — австрийский).
   python3 scripts/i18n/assemble.py            (ошибка, если какой-то строки нет в памяти)"""
import json, os, re, sys, glob, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

# 1. память переводов (пакеты добавляются только с флагом --import)
for lang in (LANGS if '--import' in sys.argv else ()):
    tm = load_tm(lang); added = 0
    for bf in sorted(glob.glob(os.path.join(WORK, f'{lang}-[0-9][0-9].json'))):
        B = json.load(open(bf, encoding='utf-8')); nn = f"{B['batch']:02d}"
        T = {}
        for of in sorted(glob.glob(os.path.join(WORK, f'out-{lang}-{nn}*.json'))):
            T.update(json.load(open(of, encoding='utf-8')))
        for pg in B['pages']:
            for it in pg['items']:
                if it['id'] in T and it['src'] not in tm:   # уже отредактированные строки не перезаписываем
                    tm[it['src']] = T[it['id']]; added += 1
    save_tm(lang, tm)
    print(f'память {lang}: {len(tm)} строк (из пакетов {added})')

# 2. сборка страниц
P = load_pages()
RU = {p['path']: p for (l, _), p in P.items() if l == 'ru'}
redirects = {r['from'] if isinstance(r, dict) else r[0]: r['to'] if isinstance(r, dict) else r[1]
             for r in (lambda d: d if isinstance(d, list) else [{'from': k, 'to': v} for k, v in d.items()])(
                 json.load(open(os.path.join(ROOT, 'content/redirects.json'), encoding='utf-8')))}

def localize(href, lang):
    if not href or not href.startswith('/') or href.startswith('//'):
        return href
    path, sep, frag = href.partition('#')
    seen = 0
    while path not in RU and path in redirects and seen < 5:
        path = redirects[path]; seen += 1
    if path in RU and RU[path]['alternates'].get(lang):
        return RU[path]['alternates'][lang] + (sep + frag if sep else '')
    return href

missing = {l: set() for l in LANGS}
def tr(lang, s, tm):
    if not isinstance(s, str) or not s.strip(): return s
    if s in tm: return tm[s]
    missing[lang].add(s); return s

def localize_html(html, lang):
    html = re.sub(r'href="([^"]*)"', lambda m: f'href="{localize(m.group(1), lang)}"', html)
    if lang in NEW_LANGS:
        # ссылка на страницу, которой нет на этом языке, — обычный текст
        html = re.sub(r'<a href="(/[^"]*)">(.*?)</a>', lambda m: m.group(0) if untranslated(m.group(1), lang) is False else m.group(2), html)
        html = swap_phones(html, lang)
    return html

def untranslated(href, lang):
    """True — внутренняя ссылка ведёт на страницу не своего языка (перевода нет)."""
    if not href or not href.startswith('/') or href.startswith('//'):
        return False
    path = href.split('#')[0].split('?')[0]
    return not (path == f'/{lang}' or path.startswith(f'/{lang}/'))

# номера студии: на SK — только словацкий, на DE — только австрийский
SITE = json.load(open(os.path.join(ROOT, 'content/site.json'), encoding='utf-8'))
PHONES = {p['key']: p for p in SITE['contacts']['phones']}
OWN_PHONE = {'sk': 'sk', 'de': 'at'}
def swap_phones(text, lang):
    own = PHONES.get(OWN_PHONE.get(lang))
    if not own:
        return text
    for p in PHONES.values():
        if p is own: continue
        text = text.replace(f'tel:{p["tel"]}', f'tel:{own["tel"]}').replace(p['text'], own['text'])
    return text

META = {l: json.load(open(os.path.join(ROOT, f'content/i18n/meta-{l}.json'), encoding='utf-8'))
        if os.path.exists(os.path.join(ROOT, f'content/i18n/meta-{l}.json')) else {} for l in NEW_LANGS}

written = 0
for lang in LANGS:
    tm = load_tm(lang)
    # описания фото на языке: со старой страницы, затем с любой страницы этого языка
    global_alt = {}
    for (l, _), p in P.items():
        if l == lang:
            for im in images(p):
                if alt_ok(lang, im.get('alt')): global_alt.setdefault(im['id'], im['alt'])
    for path, ru in RU.items():
        tpath = ru['alternates'].get(lang)
        if not tpath: continue
        old = P.get((lang, tpath))
        old_alt = {im['id']: im['alt'] for im in images(old) if alt_ok(lang, im.get('alt'))} if old else {}
        new = copy.deepcopy(ru)
        new['lang'] = lang; new['path'] = tpath
        if old:
            for k in ('title', 'description', 'og_image', 'alternates'):
                if k in old: new[k] = old[k]
        new['alternates'] = ru['alternates']
        new['h1'] = tr(lang, ru['h1'], tm)
        for s in new['sections']:
            for b in s['blocks']:
                t = b['type']
                if t == 'heading':
                    b['text'] = tr(lang, b['text'], tm)
                elif t == 'text':
                    for part in b['parts']:
                        if part['t'] == 'p':
                            part['html'] = localize_html(tr(lang, part['html'], tm), lang)
                        else:
                            part['items'] = [localize_html(tr(lang, x, tm), lang) for x in part['items']]
                elif t == 'buttons':
                    for it in b['items']:
                        it['text'] = tr(lang, it['text'], tm); it['href'] = localize(it.get('href'), lang)
                    if lang in NEW_LANGS:
                        b['items'] = [it for it in b['items'] if not untranslated(it.get('href'), lang)]
                elif t == 'cards':
                    for it in b['items']:
                        it['title'] = tr(lang, it['title'], tm); it['href'] = localize(it.get('href'), lang)
                    if lang in NEW_LANGS:
                        b['items'] = [it for it in b['items'] if not untranslated(it.get('href'), lang)]
                elif t == 'faq':
                    for it in b['items']:
                        it['q'] = tr(lang, it['q'], tm); it['a'] = localize_html(tr(lang, it['a'], tm), lang)
                elif t == 'form':
                    if b.get('title'): b['title'] = tr(lang, b['title'], tm)
                    if b.get('text'): b['text'] = tr(lang, b['text'], tm)
                elif t == 'figure':
                    if b.get('caption'): b['caption'] = tr(lang, b['caption'], tm)
                elif t == 'facts':
                    if b.get('title'): b['title'] = tr(lang, b['title'], tm)
                    b['rows'] = [[tr(lang, kk, tm), localize_html(tr(lang, vv, tm), lang)] for kk, vv in b['rows']]
        GEO = re.compile(r'варшав|warsaw|москв|moscow', re.I)
        for im in images(new):
            ru_alt = im.get('alt', '')
            cands = [old_alt.get(im['id']), global_alt.get(im['id'])]
            # чужое описание с Варшавой/Москвой не берём, если в русском описании этого фото их нет
            cands = [a for a in cands if a and (not GEO.search(a) or GEO.search(ru_alt))]
            a = cands[0] if cands else (tr(lang, ru_alt, tm) if ru_alt else '')
            if lang == 'ua' and a:
                a = re.sub(r"(?<=[А-Яа-яІіЇїЄєҐґ])'(?=[А-Яа-яІіЇїЄєҐґ])", '’', a)
                a = re.sub(r'(?<![А-Яа-яІіЇїЄєҐґ])([Пп])роект', r'\1роєкт', a)
            im['alt'] = a
        if lang in NEW_LANGS and path in META[lang]:
            new['title'] = META[lang][path]['title']; new['description'] = META[lang][path]['description']
        elif not old:
            new['title'] = new['description'] = None   # заполняются отдельно (новая страница)
        f = page_file(lang, tpath)
        if old:   # файл старой страницы
            for cand in glob.glob(os.path.join(PAGES, lang, '*.json')):
                if json.load(open(cand, encoding='utf-8'))['path'] == tpath: f = cand; break
        json.dump(new, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        written += 1
for lang in LANGS:
    if missing[lang]:
        print(f'НЕТ ПЕРЕВОДА ({lang}): {len(missing[lang])}'); [print('  ', s[:100]) for s in list(missing[lang])[:10]]
        os.makedirs(WORK, exist_ok=True)
        json.dump(sorted(missing[lang]), open(os.path.join(WORK, f'missing-{lang}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('страниц записано:', written)
sys.exit(1 if any(missing.values()) else 0)
