#!/usr/bin/env python3
"""Проверка переведённого пакета: python3 scripts/i18n/check_batch.py i18n-work/ua-03.json
Ищет файлы ответа i18n-work/out-ua-03*.json. Печатает ошибки (надо исправить) и замечания (проверить)."""
import json, sys, os, re, glob, collections
src_file = sys.argv[1]
B = json.load(open(src_file, encoding='utf-8'))
lang = B['lang']; nn = f"{B['batch']:02d}"
outs = sorted(glob.glob(os.path.join(os.path.dirname(src_file), f'out-{lang}-{nn}*.json')))
T = {}
for f in outs:
    try:
        T.update(json.load(open(f, encoding='utf-8')))
    except Exception as e:
        print(f'ОШИБКА: {f} — не читается как JSON: {e}'); sys.exit(1)
items = [i for pg in B['pages'] for i in pg['items']]
errors, warns = [], []
ids = {i['id'] for i in items}
for k in T:
    if k not in ids: errors.append(f'{k}: лишний id')
tag = re.compile(r'</?(?:strong|a|em|b|i|br)\b[^>]*>')
href = re.compile(r'href="([^"]*)"')
def nums(s):
    s = re.sub(r'(?<=\d)[\s  ,.](?=\d{3}\b)', '', s)
    return collections.Counter(re.findall(r'\d+', s))
RU_ONLY = re.compile(r'[ыэъё]', re.I); CYR = re.compile(r'[а-яёіїєґ]', re.I); UA = re.compile(r'[іїєґ’]', re.I)
for it in items:
    i, s = it['id'], it['src']; t = T.get(i)
    if not isinstance(t, str) or not t.strip():
        errors.append(f'{i}: нет перевода'); continue
    if sorted(re.sub(r'\s+href="[^"]*"', '', x) for x in tag.findall(s)) != sorted(re.sub(r'\s+href="[^"]*"', '', x) for x in tag.findall(t)):
        errors.append(f'{i}: теги не совпадают\n   src: {tag.findall(s)}\n   tr:  {tag.findall(t)}')
    if sorted(href.findall(s)) != sorted(href.findall(t)):
        errors.append(f'{i}: изменены href {href.findall(s)} → {href.findall(t)}')
    if lang == 'en' and CYR.search(re.sub(r'<[^>]+>', '', t)):
        errors.append(f'{i}: кириллица в английском: {t[:90]}')
    if lang == 'ua' and RU_ONLY.search(t):
        errors.append(f'{i}: русские буквы (ы/э/ъ/ё) в украинском: {t[:90]}')
    if lang == 'ua' and len(s) > 60 and CYR.search(s) and not UA.search(t):
        warns.append(f'{i}: нет ни одной украинской буквы (і/ї/є/ґ/’) — точно украинский? {t[:90]}')
    ns, nt = nums(s), nums(t)
    if ns - nt:
        warns.append(f'{i}: пропали числа {dict(ns - nt)}: {t[:90]}')
    if len(s) > 60 and not 0.55 < len(t) / len(s) < 1.9:
        warns.append(f'{i}: длина {len(t)}/{len(s)} — проверь, не пропущено ли что-то')
    if re.search(r'варшав|warsaw|москв|moscow', t, re.I) and not re.search(r'варшав|москв', s, re.I):
        errors.append(f'{i}: появился город, которого нет в исходнике')
print(f'{src_file}: строк {len(items)}, переведено {sum(1 for i in items if T.get(i["id"]))}, файлов ответа {len(outs)}')
for e in errors: print('ОШИБКА', e)
for w in warns: print('замечание', w)
print('OK' if not errors else f'ошибок: {len(errors)}')
sys.exit(1 if errors else 0)
