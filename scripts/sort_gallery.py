#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Порядок фото в жилых проектах: гостиная-кухня → хозяйская спальня → хозяйский санузел → кабинет →
детская → гостевая → гардеробная → постирочная → прихожая → терраса → прочее → чертежи.
Помещение каждого фото — в content/image-rooms.json (id фото → код). Титульное фото проекта
(первое в первой галерее — обложка со старого сайта) остаётся первым. Внутри одного помещения порядок
прежний; галереи на странице (например, визуализации и фото готового объекта) сортируются каждая отдельно,
а галереи-документы (страницы дизайн-проекта, где много чертежей — код D) остаются как есть.
UA/EN-страницы повторяют порядок после  python3 scripts/i18n/assemble.py
   python3 scripts/sort_gallery.py"""
import json, glob, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDER = ['L', 'MB', 'MBA', 'ST', 'KID', 'G', 'W', 'LA', 'H', 'T', 'X', 'D']
rooms = json.load(open(os.path.join(ROOT, 'content/image-rooms.json'), encoding='utf-8'))
projects = json.load(open(os.path.join(ROOT, 'content/projects.json'), encoding='utf-8'))
residential = {p['path'] for p in projects if p['group'] == 'residential'}
changed = 0
for f in sorted(glob.glob(os.path.join(ROOT, 'content/pages/ru/*.json'))):
    page = json.load(open(f, encoding='utf-8'))
    if page['path'] not in residential: continue
    first = True; touched = False
    for s in page['sections']:
        for b in s['blocks']:
            if b['type'] != 'gallery' or not b['images']: continue
            ims = b['images']
            head, rest = (ims[:1], ims[1:]) if first else ([], ims)
            first = False
            # галерея-документ (страницы дизайн-проекта: обложка, обмеры, чертежи, визуализации) — порядок не трогаем
            if sum(1 for im in ims if rooms.get(im['id']) == 'D') >= 0.25 * len(ims): continue
            rank = lambda im: ORDER.index(rooms.get(im['id'], 'X')) if rooms.get(im['id'], 'X') in ORDER else len(ORDER)
            new = head + sorted(rest, key=rank)   # sorted() устойчивая — внутри помещения порядок прежний
            if [i['id'] for i in new] != [i['id'] for i in ims]:
                b['images'] = new; touched = True
    if touched:
        json.dump(page, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=1); changed += 1
print('страниц с новым порядком фото:', changed)
