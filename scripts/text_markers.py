#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Поиск шаблонных оборотов («нейромаркеров») и невидимых символов в текстах сайта.
Правила — content/TEXT_STYLE.md. Проверяет страницы на трёх языках (видимый текст, title, description).
   python3 scripts/text_markers.py            — отчёт по всем страницам
   python3 scripts/text_markers.py /адрес …   — только эти страницы (русский адрес — со всеми переводами)
Код выхода 1, если что-то найдено."""
import glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INVISIBLE = re.compile('[​‌‍⁠﻿­]')
RU = [
    r'не просто\b[^.]{0,60}?,\s*а\b', r'\bэто не (про|о)\b', r'больше,? чем\b[^.]{0,30}—',
    r'важно (отметить|подчеркнуть|понимать)', r'стоит (отметить|подчеркнуть)', r'следует (отметить|подчеркнуть)',
    r'нельзя не', r'как известно', r'в современном мире', r'в наше время', r'сегодня как никогда',
    r'^\s*(итак|таким образом|в итоге|в заключение|подводя итог)\b', r'\b(результат|итог)\s*—',
    r'\bидеальн', r'\bуникальн', r'\bбезупречн', r'\bгармони(чн|я|ей|ю)', r'органично', r'\bизысканн', r'\bутончённ|\bутонченн',
    r'атмосфер\w* уюта', r'уютн\w* и функциональн', r'стильн\w* и практичн', r'\bроскошн',
    r'воплоти\w* (вашу |в жизнь )?мечт', r'(интерьер|дом|квартир\w*) (вашей )?мечты', r'вдохновля', r'хочется возвращаться',
    r'погрузит', r'окунут', r'откройте для себя', r'становятся реальностью', r'кажд\w+ детал\w+ продуман',
    r'внимани\w+ к детал', r'до мелочей', r'с любовью', r'мы гордимся',
    r'\bявляется\b', r'\bявляются\b', r'представляет собой', r'играет (ключевую|важную) роль', r'позволяет обеспечить',
    r'\bданн(ый|ая|ое|ого|ой|ом)\b',
]
EN = [
    r'\bnot (just|only) [^.]{0,40}?,? but\b', r'\bseamless', r'\belevat(e|es|ed|ing)\b', r'\bcurated\b', r'\bnestled\b', r'\bboasts?\b',
    r'testament to', r'\btapestry', r'\bdelve', r"\bwhether you(?:'|’)re\b", r"in today(?:'|’)s world", r'\bsanctuary',
    r'\beffortless', r'\bmeticulous', r'\bharmonious', r'timeless elegance', r'transform your', r'dream home',
    r'\bunique\b', r'\bperfect(ly)?\b', r'\bflawless', r'\bexquisite', r'\bluxurious\b',
]
UA = [
    r'не просто\b[^.]{0,60}?,\s*а\b', r'варто (зазначити|відзначити)', r'слід (зазначити|підкреслити)',
    r'\bгармоні(йн|я)', r'\bідеальн', r'\bунікальн', r'\bбездоганн', r'затишок і функціональн', r'втіли\w* мрі',
    r'являє собою', r'\bвишукан', r'органічно',
]
TAG = re.compile(r'<[^>]+>')


def scan(text, patterns):
    t = TAG.sub('', text)
    hits = []
    if INVISIBLE.search(text):
        hits.append('невидимый символ')
    for p in patterns:
        m = re.search(p, t, re.I | re.M)
        if m:
            hits.append(m.group(0))
    return hits


def strings(page):
    for s in page['sections']:
        for b in s['blocks']:
            if b['type'] == 'heading':
                yield b['text']
            elif b['type'] == 'text':
                for part in b['parts']:
                    if part['t'] == 'p':
                        yield part['html']
                    else:
                        yield from part['items']
            elif b['type'] == 'faq':
                for it in b['items']:
                    yield it['q']
                    yield it['a']
    for k in ('title', 'description', 'h1'):
        if page.get(k):
            yield page[k]


def main():
    only = set(sys.argv[1:])
    found = 0
    pats = {'ru': RU, 'ua': UA, 'en': EN}
    for lang in ('ru', 'ua', 'en'):
        for f in sorted(glob.glob(os.path.join(ROOT, f'content/pages/{lang}/*.json'))):
            page = json.load(open(f, encoding='utf-8'))
            if only and page['path'] not in only and page.get('alternates', {}).get('ru') not in only:
                continue
            for s in strings(page):
                hits = scan(s, pats[lang])
                if hits:
                    found += 1
                    print(f"{page['path']}: {', '.join(hits)} | {TAG.sub('', s)[:140]}")
    print('найдено:', found)
    sys.exit(1 if found else 0)


if __name__ == '__main__':
    main()
