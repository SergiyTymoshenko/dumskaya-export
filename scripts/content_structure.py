#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Структура текста на русских страницах (переводы в памяти переносятся автоматически):
  1) «заголовок» длиннее 140 знаков — это абзац, оформленный на старом сайте как заголовок → обычный абзац;
  2) короткий абзац целиком жирным («<strong>1. Обмерный план</strong>»), за которым идёт текст, — это
     подзаголовок → настоящий подзаголовок (H3; если до него на странице нет H2, он выводится как H2);
     такая же строка, за которой сразу идут подзаголовки («<strong>Что входит в пакет</strong>»), — заголовок раздела (H2).
Не трогаются: строки с ценой (€, zł), строки на «:» (подводка к списку, заголовок таблицы характеристик кухни),
законченные фразы на «.»/«!», страницы главной, кухонь и обзора цен (у них свои шаблоны разбора).
   python3 scripts/content_structure.py"""
import json, glob, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'i18n'))
from common import *

STRONG = re.compile(r'^\s*<strong>\s*([^<]{3,90}?)\s*</strong>\s*$')
SKIP_TYPES = {'home', 'kitchen', 'contact', 'shop'}
SKIP_PATHS = {'/price-interior-design-bratislava-wien-praha'}

def as_heading(html):
    m = STRONG.match(html)
    if not m: return None
    t = m.group(1).strip()
    if t.endswith(('.', '!', ':', ';', ',')) or re.search(r'€|zł|\bEUR\b', t): return None
    return t

def main():
    tms = {l: load_tm(l) for l in LANGS}
    log = {'длинных заголовков → абзац': 0, 'жирных абзацев → подзаголовок': 0, 'переводов перенесено': 0}
    for f in sorted(glob.glob(os.path.join(PAGES, 'ru/*.json'))):
        p = json.load(open(f, encoding='utf-8'))
        if p['type'] in SKIP_TYPES or p['path'] in SKIP_PATHS: continue
        changed = False
        for s in p['sections']:
            out = []
            for b in s['blocks']:
                # 1) длинный «заголовок» → абзац
                if b['type'] == 'heading' and b['level'] > 1 and len(re.sub('<[^>]+>', '', b['text'])) > 140:
                    out.append({'type': 'text', 'parts': [{'t': 'p', 'html': b['text']}]})
                    log['длинных заголовков → абзац'] += 1; changed = True; continue
                if b['type'] != 'text':
                    out.append(b); continue
                # 2) жирный короткий абзац, за которым есть текст → подзаголовок
                parts, cur = b['parts'], []
                for i, part in enumerate(parts):
                    h = as_heading(part['html']) if part['t'] == 'p' else None
                    if h and i + 1 < len(parts) and not (parts[i + 1]['t'] == 'p' and as_heading(parts[i + 1]['html'])):
                        if cur: out.append({'type': 'text', 'parts': cur}); cur = []
                        out.append({'type': 'heading', 'level': 3, 'text': h})
                        for l in LANGS:
                            v = tms[l].get(part['html'])
                            if v is not None:
                                m = STRONG.match(v)
                                if m: tms[l][h] = m.group(1).strip(); log['переводов перенесено'] += 1
                        log['жирных абзацев → подзаголовок'] += 1; changed = True
                    else:
                        cur.append(part)
                if cur: out.append({'type': 'text', 'parts': cur})
            # жирная строка в конце абзацев, за которой сразу идут подзаголовки, — заголовок раздела (H2):
            # «Что входит в пакет» → «1. Обмерный план», «2. План расстановки мебели»…
            for k in range(len(out) - 1, -1, -1):
                bk = out[k]
                if bk['type'] != 'text' or k + 1 >= len(out): continue
                nx = out[k + 1]
                last = bk['parts'][-1]
                h = as_heading(last['html']) if last['t'] == 'p' else None
                if h and nx['type'] == 'heading' and nx['level'] >= 3:
                    for l in LANGS:
                        v = tms[l].get(last['html'])
                        m = STRONG.match(v) if v else None
                        if m: tms[l][h] = m.group(1).strip(); log['переводов перенесено'] += 1
                    bk['parts'].pop()
                    out.insert(k + 1, {'type': 'heading', 'level': 2, 'text': h})
                    if not bk['parts']: out.pop(k)
                    log['жирных абзацев → подзаголовок'] += 1; changed = True
            # соседние текстовые блоки (после превращения заголовка в абзац) — склеить
            merged = []
            for b in out:
                if b['type'] == 'text' and merged and merged[-1]['type'] == 'text':
                    merged[-1]['parts'].extend(b['parts'])
                else:
                    merged.append(b)
            s['blocks'] = merged
        if changed:
            json.dump(p, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for l in LANGS: save_tm(l, tms[l])
    print(log)

if __name__ == '__main__':
    main()
