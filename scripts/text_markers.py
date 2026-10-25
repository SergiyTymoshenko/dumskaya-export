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
SK = [
    r'\bnielen\b[^.]{0,60}?,\s*ale (aj|tiež)\b', r'\bjedinečn', r'\bdokonal', r'\bideáln', r'\bbezchybn', r'\bharmonick',
    r'\bluxusn', r'\bsofistikovan', r'\bexkluzívn', r'vysníva', r'\bsnov\b', r'v dnešnej dobe', r'je dôležité poznamenať',
    r'stojí za zmienku', r'neoddeliteľn', r'kľúčovú úlohu', r'zohráva (dôležitú|kľúčovú) úlohu', r'\bponor(iť|te) sa', r'\bobjavte\b',
    r'\bpremeňte\b', r'útuln\w* a funkčn', r'štýlov\w* a praktick', r's láskou', r'sme hrdí',
    r'\bprémiov', r'\belitn', r'\bštýlov\w*\b', r'\bluxus',
]
DE = [
    r'\bnicht nur\b[^.]{0,60}?,?\s*sondern auch\b', r'\beinzigartig', r'\bperfekt', r'\bmakellos', r'\bharmonisch', r'\bnahtlos',
    r'\bluxuriös', r'\bexklusiv', r'zeitlose Eleganz', r'\bTraum(wohnung|haus|küche|zuhause)', r'Wohlfühloase', r'in der heutigen Zeit',
    r'es ist wichtig zu beachten', r'(entscheidende|wichtige) Rolle', r'\beintauchen', r'\bentdecken Sie\b', r'\bverwandeln Sie\b',
    r'gemütlich und funktional', r'stilvoll und praktisch', r'mit Liebe zum Detail', r'rundum sorglos', r'höchste Qualität',
    r'maßgeschneiderte Lösung', r'wir sind stolz',
    r'\bPremium-?(segment|qualität|klasse)', r'\bstilvoll', r'\belitär', r'\bLuxus',
]
# французский и испанский — для каталога DUMSKAYA HOME (dumskaya-home.com), проверяет scripts/check_home.py
FR = [
    r'\bnon seulement\b[^.]{0,60}?\bmais (aussi|également)\b', r'\bunique\b', r'\bparfait', r'\bidéal', r'\bharmoni',
    r'\bsublim', r'\braffiné', r'élégance intemporelle', r'\bluxueu', r'\bhaut de gamme\b', r'\bun véritable\b', r'\bune véritable\b',
    r'\bécrin\b', r'havre de paix', r'\bcocon\b', r'\bdécouvrez\b', r'laissez-vous', r'\bplongez\b', r'sans compromis',
    r'\bincontournable', r"savoir-faire d['’]exception", r'art de vivre', r"dans le monde d['’]aujourd['’]hui", r'il est important de noter',
    r'(joue|jouent) un rôle (clé|essentiel|crucial)', r'\btransformez\b', r'intérieur de rêve', r'allie à la perfection',
]
ES = [
    r'\bno solo\b[^.]{0,60}?\bsino (también|que)\b', r'\búnic[oa]s?\b', r'\bperfect', r'\bideal(es)?\b', r'\barmon(ía|ios)',
    r'\bexquisit', r'\blujos', r'elegancia atemporal', r'\bsin igual\b', r'\binigualable', r'\bdescubr(a|e)\b', r'déjese', r'\bsumérj',
    r'\bun auténtico\b', r'\buna auténtica\b', r'(hogar|casa) de (sus|tus) sueños', r'en el mundo actual', r'es importante (destacar|señalar)',
    r'(juega|desempeña) un papel (clave|fundamental|crucial)', r'\btransforme\b', r'a la perfección', r'\boasis\b', r'\brefugio\b',
]
TAG = re.compile(r'<[^>]+>')
ALTS = False


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
            elif ALTS and b['type'] in ('gallery', 'figure', 'cards'):
                for im in b.get('images', []) + ([b['image']] if b.get('image') else []) + [c.get('image') or {} for c in b.get('items', [])]:
                    if im.get('alt'):
                        yield im['alt']
    for k in ('title', 'description', 'h1'):
        if page.get(k):
            yield page[k]


def main():
    only = set(sys.argv[1:])
    found = 0
    pats = {'ru': RU, 'ua': UA, 'en': EN, 'sk': SK, 'de': DE}
    for lang in ('ru', 'ua', 'en', 'sk', 'de'):
        for f in sorted(glob.glob(os.path.join(ROOT, f'content/pages/{lang}/*.json'))):
            page = json.load(open(f, encoding='utf-8'))
            global ALTS
            ALTS = lang in ('sk', 'de')   # подписи фото SK/DE переведены заново — проверяем и их
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
