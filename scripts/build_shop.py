#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Список товаров магазина для бота заявок: deploy/shop-products.json (артикул → название, страница, партнёр).

Кнопка «Узнать цену» на товаре передаёт в форму артикул (TDD-001 и т. п.). По этому списку бот на сервере
понимает, чей товар: если у товара указан партнёр (поле "partner": <номер партнёра из бота> в
content/pages/ru/shop/<товар>.json), заявка уходит людям этого партнёра, а разработчику и дизайнеру —
уведомление. Без поля "partner" товар студии — заявка как обычно.
Запускается при выкладке (scripts/deploy.sh); файл не хранится в git.
   python3 scripts/build_shop.py"""
import glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out, errs = {}, []
for f in sorted(glob.glob(os.path.join(ROOT, "content/pages/ru/shop/*.json"))):
    p = json.load(open(f, encoding="utf-8"))
    m = re.search(r"\((TDD-[\w-]+|[A-Z]{2,5}-\d+)\)", p.get("title", ""))
    if not m:
        continue
    code = m.group(1).upper()
    name = re.sub(r"\s*\|\s*DUMSKAYA DESIGN\s*$", "", p["title"])
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name)
    partner = p.get("partner")
    if partner is not None and not str(partner).isdigit():
        errs.append(f"{p['path']}: partner должен быть номером партнёра из бота, сейчас {partner!r}")
    if code in out:
        errs.append(f"артикул {code} повторяется: {out[code]['path']} и {p['path']}")
    out[code] = {"name": name, "path": p["path"], "partner": int(partner) if str(partner or "").isdigit() else None}
dst = os.path.join(ROOT, "deploy", "shop-products.json")
json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
own = sum(1 for v in out.values() if v["partner"])
print(f"товары для бота: {len(out)} (партнёрских: {own})")
for e in errs:
    print("  ✗", e)
sys.exit(1 if errs else 0)
