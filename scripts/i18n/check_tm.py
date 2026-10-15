#!/usr/bin/env python3
"""Проверка всей памяти переводов: python3 scripts/i18n/check_tm.py ua|en
Для каждой пары «русский → перевод»: теги и ссылки те же, числа на месте, нет чужих букв."""
import json, re, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
lang = sys.argv[1]; tm = load_tm(lang)
tag = re.compile(r'</?(?:strong|a|em|b|i|br)\b[^>]*>'); href = re.compile(r'href="([^"]*)"')
strip = lambda xs: sorted(re.sub(r'\s+href="[^"]*"', '', x) for x in xs)
def nums(s):
    s = re.sub(r'(?<=\d)[\s  ,.](?=\d{3}\b)', '', s); return collections.Counter(re.findall(r'\d+', s))
E, W = [], []
for s, t in tm.items():
    if not isinstance(t, str) or not t.strip(): E.append(f'пусто: {s[:60]}'); continue
    if strip(tag.findall(s)) != strip(tag.findall(t)): E.append(f'теги: {t[:90]}')
    if sorted(href.findall(s)) != sorted(href.findall(t)): E.append(f'href: {t[:90]}')
    if lang == 'en' and CYR.search(re.sub(r'<[^>]+>', '', t)): E.append(f'кириллица: {t[:90]}')
    if lang == 'ua' and RU_ONLY.search(t): E.append(f'ы/э/ъ/ё: {t[:90]}')
    if nums(s) - nums(t): W.append(f'числа {dict(nums(s) - nums(t))}: {t[:90]}')
for e in E: print('ОШИБКА', e)
for w in W: print('замечание', w)
print(f'{lang}: строк {len(tm)}, ошибок {len(E)}, замечаний {len(W)}')
sys.exit(1 if E else 0)
