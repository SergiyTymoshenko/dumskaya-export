#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Чистка текстов, унаследованных со старого сайта (русские страницы + память переводов):
  1) абзацы, начинающиеся с «— », «- », «• », «✅ » → настоящие списки;
  2) «<strong>Заголовок </strong>Текст…» в одном абзаце → подзаголовок (h3) + абзац;
  3) прямые кавычки "…" → «…»;
  4) «DUMSKAYA DESIGN (Братислава, Словакия)» — остаётся только в первом абзаце страницы.
Те же преобразования применяются к украинским и английским переводам в памяти,
поэтому заново переводить ничего не нужно.
   python3 scripts/text_cleanup.py"""
import json, re, os, sys, glob, copy
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'i18n'))
from common import *

BULLET = re.compile(r'^(?:<strong>)?\s*(?:—|-|•|✅|—|–)\s+')
GEO = {'ru': ' (Братислава, Словакия)', 'ua': ' (Братислава, Словаччина)', 'en': ' (Bratislava, Slovakia)'}
GLUED = re.compile(r'^<strong>([^<]{8,80}?)\s*</strong>\s*(?=[А-ЯЁA-ZІЇЄҐ])')

def strip_bullet(h):
    t = BULLET.sub('', h)
    if h.startswith('<strong>') and not t.startswith('<strong>'):
        t = '<strong>' + t
    return t.strip()

def quotes(h):
    # "слово" → «слово» (только парные кавычки вне атрибутов тегов)
    def fix(seg):
        return re.sub(r'"([^"<>]+)"', lambda m: '«' + m.group(1).strip() + '»', seg)
    return ''.join(fix(x) if not x.startswith('<') else x for x in re.split(r'(<[^>]+>)', h))

def split_glued(h):
    m = GLUED.match(h)
    if not m: return None
    head = m.group(1).strip()
    if head.endswith(('.', ':', '!', '?', ';')) or len(h) - m.end() < 40: return None
    return head, h[m.end():].strip()

def clean_parts(parts, first_p_geo_keep, lang, log):
    """parts → список (kind, payload): ('p', html) | ('ul', [items]) | ('h3', text)"""
    out = []
    for part in parts:
        if part['t'] != 'p':
            out.append((part['t'], [quotes(i) for i in part['items']])); continue
        h = quotes(part['html'])
        if BULLET.match(re.sub(r'^<strong>', '', h)) or BULLET.match(h):
            item = strip_bullet(h)
            if out and out[-1][0] == 'ul': out[-1][1].append(item)
            else: out.append(('ul', [item]))
            log['списки'] += 1; continue
        g = split_glued(h)
        if g:
            out.append(('h3', g[0])); out.append(('p', g[1])); log['подзаголовки'] += 1; continue
        out.append(('p', h))
    return out

def main():
    P = load_pages()
    tms = {l: load_tm(l) for l in LANGS}
    log = {'списки': 0, 'подзаголовки': 0, 'кавычки': 0, 'гео': 0, 'переводов перенесено': 0, 'переводов потеряно': 0}
    files = {p['path']: f for f in glob.glob(os.path.join(PAGES, 'ru/*.json')) for p in [json.load(open(f, encoding='utf-8'))]}

    def carry(old, new_pieces, transform):
        """перенести перевод old→new: transform(перевод) должен дать столько же кусков"""
        for l in LANGS:
            v = tms[l].get(old)
            if v is None: continue
            try:
                tv = transform(v, l)
            except Exception:
                tv = None
            if tv is not None and len(tv) == len(new_pieces):
                for n, t in zip(new_pieces, tv):
                    if n != old: tms[l][n] = t
                log['переводов перенесено'] += 1
            else:
                log['переводов потеряно'] += 1

    for (l, path), p in list(P.items()):
        if l != 'ru': continue
        page_geo_seen = False
        new_sections = []
        for s in p['sections']:
            blocks = []
            for b in s['blocks']:
                if b['type'] != 'text':
                    blocks.append(b); continue
                parts_out = []
                for part in b['parts']:
                    if part['t'] != 'p':
                        items = []
                        for i in part['items']:
                            q = quotes(i)
                            if q != i: carry(i, [q], lambda v, l: [quotes(v)]); log['кавычки'] += 1
                            items.append(q)
                        parts_out.append({'t': part['t'], 'items': items}); continue
                    h0 = part['html']; h = h0
                    # 4) гео-скобка
                    geo_stripped = False
                    if 'DUMSKAYA DESIGN' + GEO['ru'] in h:
                        if page_geo_seen:
                            h = h.replace('DUMSKAYA DESIGN' + GEO['ru'], 'DUMSKAYA DESIGN'); log['гео'] += 1; geo_stripped = True
                        page_geo_seen = True
                    # 3) кавычки
                    hq = quotes(h)
                    if hq != h: log['кавычки'] += 1
                    h = hq
                    if h != h0:
                        def tr_same(v, l, geo_stripped=geo_stripped):
                            if geo_stripped: v = v.replace('DUMSKAYA DESIGN' + GEO[l], 'DUMSKAYA DESIGN')
                            return [quotes(v)]
                        carry(h0, [h], tr_same)
                    # 1) списки
                    if BULLET.match(h) or BULLET.match(re.sub(r'^<strong>', '', h)):
                        item = strip_bullet(h)
                        carry(h, [item], lambda v, l: [strip_bullet(v)])
                        if parts_out and parts_out[-1]['t'] == 'ul': parts_out[-1]['items'].append(item)
                        else: parts_out.append({'t': 'ul', 'items': [item]})
                        log['списки'] += 1; continue
                    # 2) склеенный подзаголовок
                    g = split_glued(h)
                    if g:
                        carry(h, list(g), lambda v, l: list(split_glued(v)) if split_glued(v) else None)
                        if parts_out: blocks.append({'type': 'text', 'parts': parts_out}); parts_out = []
                        blocks.append({'type': 'heading', 'level': 3, 'text': g[0]})
                        parts_out.append({'t': 'p', 'html': g[1]}); log['подзаголовки'] += 1; continue
                    parts_out.append({'t': 'p', 'html': h})
                if parts_out: blocks.append({'type': 'text', 'parts': parts_out})
            new_sections.append({**s, 'blocks': blocks})
        p['sections'] = new_sections
        json.dump(p, open(files[path], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for l in LANGS: save_tm(l, tms[l])
    print(log)

if __name__ == '__main__':
    main()
