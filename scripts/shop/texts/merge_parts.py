#!/usr/bin/env python3
"""Запуск: python3 scripts/shop/texts/merge_parts.py <фабрика>. Сводит партии текстов (content/home/texts/parts/<фабрика>-NN.json) в content/home/texts/<фабрика>.json
и правки данных (…-fixes.json) — в content/home/overrides.json (с пометкой фабрики и даты в _why)."""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PARTS = os.path.join(ROOT, "content/home/texts/parts")
import datetime
DAY = datetime.date.today().strftime("%d.%m.%Y")
NAMES = {"giorgetti": "Giorgetti", "lago": "Lago", "misuraemme": "MisuraEmme", "rimadesio": "Rimadesio"}

ov_path = os.path.join(ROOT, "content/home/overrides.json")
ov = json.load(open(ov_path, encoding="utf-8"))
report = {}
for f in sys.argv[1:] or NAMES:
    texts, fixes = {}, {}
    for p in sorted(glob.glob(os.path.join(PARTS, f"{f}-[0-9][0-9].json"))):
        texts.update(json.load(open(p, encoding="utf-8")))
        fx = p[:-5] + "-fixes.json"
        if os.path.exists(fx):
            fixes.update(json.load(open(fx, encoding="utf-8")))
    out = os.path.join(ROOT, "content/home/texts", f"{f}.json")
    json.dump(dict(sorted(texts.items())), open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for sku, fx in fixes.items():
        fx = dict(fx)
        why = fx.pop("_why", "")
        cur = dict(ov.get(sku) or {})
        cur.update(fx)
        cur["_why"] = f"{NAMES[f]}, {DAY}: {why}".strip()
        ov[sku] = cur
    report[f] = (len(texts), len(fixes))
json.dump(ov, open(ov_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(report)
