#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка сборки dumskaya-home.com (home/dist) перед выкладкой: python3 scripts/check_home.py

Ошибки (выкладка останавливается): у страницы нет title, description или h1, h1 больше одного, title повторяется,
нет canonical или языковых версий (hreflang у каждой — на все 5 языков и x-default, и они ссылаются друг на друга),
внутренняя ссылка или фото ведут в никуда, в тексте «undefined», «NaN», «[object Object]».
Предупреждения: нет своего текста у товара выложенной фабрики, шаблонные обороты (content/TEXT_STYLE.md) в своих текстах."""
import glob
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "home/dist")
LANGS = ["en", "ru", "de", "fr", "es"]
errs, warns = [], []


def url_of(f):
    rel = os.path.relpath(f, DIST)
    return "/" if rel == "index.html" else "/" + rel[:-5]


pages = {url_of(f): open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(DIST, "**/*.html"), recursive=True)}
files = {"/" + os.path.relpath(f, DIST) for f in glob.glob(os.path.join(DIST, "**/*"), recursive=True) if os.path.isfile(f)}
titles = Counter()
alts = {}
for u, h in pages.items():
    if u == "/404":
        continue
    t = re.search(r"<title>([^<]*)</title>", h)
    if not t or not t.group(1).strip():
        errs.append(f"{u}: нет title")
    else:
        titles[html.unescape(t.group(1))] += 1
    if not re.search(r'<meta name="description" content="[^"]+"', h) and not u.endswith(("/privacy", "/datenschutz", "/confidentialite", "/privacidad")):
        errs.append(f"{u}: нет description")
    n1 = len(re.findall(r"<h1[\s>]", h))
    if n1 != 1:
        errs.append(f"{u}: h1 — {n1}")
    if f'<link rel="canonical" href="https://dumskaya-home.com{u}"' not in h:
        errs.append(f"{u}: canonical не на себя")
    hl = dict(re.findall(r'<link rel="alternate" hreflang="([a-z-]+)" href="https://dumskaya-home.com([^"]*)"', h))
    if set(hl) != set(LANGS) | {"x-default"}:
        errs.append(f"{u}: языковые версии {sorted(hl)}")
    alts[u] = hl
    for bad in ("undefined", "NaN", "[object Object]"):
        if re.search(r">[^<]*\b" + re.escape(bad) + r"\b[^<]*<", h):
            errs.append(f"{u}: в тексте «{bad}»")
    for href in set(re.findall(r'(?:href|src)="(/[^"#?]*)', h)):
        if href.startswith("/api/"):
            continue
        if href not in files and href.rstrip("/") not in pages and href not in pages:
            errs.append(f"{u}: ссылка в никуда {href}")
    for s in set(re.findall(r'srcset="([^"]+)"', h)):
        for part in s.split(","):
            p = part.strip().split(" ")[0]
            if p.startswith("/") and p not in files:
                errs.append(f"{u}: нет фото {p}")
for t, n in titles.items():
    if n > 1:
        errs.append(f"title повторяется {n} раз: {t}")
for u, hl in alts.items():                         # версии ссылаются друг на друга
    for l, v in hl.items():
        if l != "x-default" and v in alts and alts[v].get(LANGS[0]) != hl.get(LANGS[0]):
            errs.append(f"{u}: версия {l} ({v}) ссылается на другие страницы")
# свои тексты выложенных фабрик
cat = json.load(open(os.path.join(ROOT, "home/data/catalog.json"), encoding="utf-8"))
style = open(os.path.join(ROOT, "content/TEXT_STYLE.md"), encoding="utf-8").read()
markers = [m for m in re.findall(r"«([^»]{3,40})»", style.split("## Чего не писать")[-1]) if "X" not in m and "…" not in m]
no_text = defaultdict(int)
for p in cat["products"]:
    if not p.get("published"):
        continue
    for l in LANGS:
        t = (p.get("text") or {}).get(l, "")
        if not t:
            no_text[p["factory"]] += 1
            continue
        low = t.lower()
        for m in markers:
            if re.search(r"(?<!\w)" + re.escape(m.lower()) + r"(?!\w)", low):
                warns.append(f"{p['sku']} ({l}): шаблонный оборот «{m}»")
for f, n in no_text.items():
    warns.append(f"{f}: без своего текста — {n} (товар × язык)")
print(f"страниц: {len(pages)}, файлов: {len(files)}")
print(f"ошибок: {len(errs)}, предупреждений: {len(warns)}")
for e in errs[:60]:
    print("  ✗", e)
for w in warns[:40]:
    print("  ·", w)
sys.exit(1 if errs else 0)
