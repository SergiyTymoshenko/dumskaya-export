#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Строка «Работы» в карточке проекта (content/projects.json) и мета-описания страниц проектов —
по тому, что действительно сделано на объекте (по тексту страницы), а не одной фразой для всех.
   python3 scripts/project_facts.py"""
import json, glob, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = {
    'D':   ('Дизайн-проект', 'Дизайн-проєкт', 'Interior design'),
    'Dx':  ('Дизайн-проект (пакет «Экспресс»)', 'Дизайн-проєкт (пакет «Експрес»)', 'Interior design (“Express” package)'),
    'Df':  ('Дизайн-проект (пакет «Мебель»)', 'Дизайн-проєкт (пакет «Меблі»)', 'Interior design (“Furniture” package)'),
    'Db':  ('Дизайн-проект (пакет «Базовый»)', 'Дизайн-проєкт (пакет «Базовий»)', 'Interior design (“Basic” package)'),
    'V':   ('3D-визуализация', '3D-візуалізація', '3D visualization'),
    'T':   ('техническая документация', 'технічна документація', 'technical drawings'),
    'E':   ('проект электрики', 'проєкт електрики', 'electrical design'),
    'F':   ('мебель на заказ', 'меблі на замовлення', 'custom furniture'),
    'Fd':  ('проект мебели', 'проєкт меблів', 'furniture design'),
    'R':   ('ремонт под ключ', 'ремонт під ключ', 'turnkey renovation'),
    'Dec': ('декорирование', 'декорування', 'styling'),
    'A':   ('авторское сопровождение', 'авторський супровід', 'design supervision'),
}
WORKS = {
    '/design-interior-studio-bratislava-metropolis-sk-75m': 'Df V F',
    '/studio-interior-design-disain-proekt-kvartira-kiev-80m': 'D V T F',
    '/studio-interior-design-bratislava-eurovea-56m': 'Df V F',
    '/interior-design-apartment-bratislava-158m': 'D T F R',
    '/interior-design-private-house-bratislava-120m2': 'Dx E',
    '/apartments-vienna-luxury-interior-design-58m': 'D T F R',
    '/interior-design-private-house-dunajska-streda-140m': 'D',
    '/interior-design-private-house-kharkiv-212m': 'D V T F R',
    '/apartment-interior-design-warsaw-43m2': 'Db V',
    '/apartment-interior-design-krakow-63m': 'D V T F R Dec',
    '/apartment-interior-design-60m': 'D V',
    '/apartment-interior-design-54m': 'D V T F R Dec',
    '/apartment-furniture-interior-design-45m': 'D',
    '/apartment-interior-design-48m': 'D F R Dec',
    '/apartment-interior-design-bratislava-58m': 'D V T F R Dec',
    '/apartment-interior-design-52m': 'D V T F R Dec',
    '/apartment-interior-design-warsaw-43m': 'D T F R Dec',
    '/apartment-interior-design-bratislava-52m': 'D V T F R',
    '/apartments-dubai-luxury-interior-design-160m': 'D V F R',
    '/apartments-los-angeles-interior-design-140m': 'D V T Fd',
    '/apartments-praha-luxury-interior-design-90m': 'D V T F R',
    '/apartments-new-york-luxury-interior-design-57m': 'D V T F R',
    '/apartment-interior-design-krakow-64m': 'D V T',
    '/dizainer-interierov-kiev': 'D V T F R',
    '/villa-interior-design-160m': 'D V T F R',
    '/interior-design-private-house-215m': 'D V T F R',
    '/interior-design-apartment-luxury-kyiv-119m': 'D',
    '/interior-design-furniture-classic-120m-london': 'D V T F R',
    '/apartment-luxury-interior-design-madrid-spain-107m': 'D V T F R',
    '/luxury-interior-design-barcelona-spain-108m': 'D V T F R',
    '/apartment-interior-design-51m': 'D V T F R Dec',
    '/apartments-wien-luxury-interior-design-115m': 'D V T F R',
    '/interior-design-furniture-60m': 'D V T F R',
    '/interior-design-apartment-ukraine-47m': 'D',
    '/interior-design-villa-179m-madrid-spain': 'D V T F R',
    '/dumskaya-interior-design-villa-220m': 'D V T F R',
    '/dumskaya-interior-design-villa-230m': 'D V T F R',
    '/furniture-interior-design-43m': 'D V T F R',
    '/interior-design-cosmetology-salon': 'Dx V T',
    '/beauty-salon-interior-design-63m': 'D T',
    '/office-interior-design-500m': 'D V F',
    '/photo-studio-interior-design-custom-furniture-130m2-bratislava': 'D F R A',
    '/clothing-boutique-interior-design-kyiv-140': 'D V Fd R',
    '/dizayn-kommercheskogo-interyera-sauna-banya': 'D Fd',
    '/office-interior-design-140m': 'D V F R',
    '/office-interior-design-53m': 'D V F R',
    '/boss-office-interior-design': 'D V F',
    '/shop-show-room-interior-design-50m': 'D V F',
}
AND = {'ru': ' и ', 'ua': ' та ', 'en': ' and '}
TAIL = {'ru': 'Студия DUMSKAYA DESIGN в Братиславе и Вене.', 'ua': 'Студія DUMSKAYA DESIGN у Братиславі та Відні.', 'en': 'DUMSKAYA DESIGN, Bratislava and Vienna.'}
LI = {'ru': 0, 'ua': 1, 'en': 2}

def works(codes, lang):
    xs = [T[c][LI[lang]] for c in codes.split()]
    return xs[0] if len(xs) == 1 else ', '.join(xs[:-1]) + AND[lang] + xs[-1]

def main():
    pj = os.path.join(ROOT, 'content/projects.json')
    raw = open(pj, encoding='utf-8').read()
    P = json.loads(raw)
    files = {}
    for f in glob.glob(os.path.join(ROOT, 'content/pages/*/*.json')):
        files[json.load(open(f, encoding='utf-8'))['path']] = f
    changed = 0
    for pr in P:
        codes = WORKS.get(pr['path'])
        if not codes: continue
        for lang in ('ru', 'ua', 'en'):
            w = works(codes, lang)
            pr.setdefault('facts', {}).setdefault(lang, {})['works'] = w
            f = files.get(pr['alternates'].get(lang))
            if not f: continue
            page = json.load(open(f, encoding='utf-8'))
            d = page['description']
            if ':' not in d: continue
            lead = d.split(':')[0]
            low = w[0].lower() + w[1:] if not w.startswith('3D') else w
            new = f'{lead}: {low}. {TAIL[lang]}'
            if len(new) > 155: new = f'{lead}: {low}.'
            if new != d:
                page['description'] = new
                json.dump(page, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
                changed += 1
    indent = 1 if raw.startswith('[\n {') else 0
    json.dump(P, open(pj, 'w', encoding='utf-8'), ensure_ascii=False, indent=indent)
    print('описаний обновлено:', changed)

if __name__ == '__main__':
    main()
