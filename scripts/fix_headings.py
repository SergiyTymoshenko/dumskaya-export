#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Один H1 на страницу: лишние заголовки первого уровня → H2; из H1 убирается «| DUMSKAYA DESIGN»."""
import glob, json, os, re
C = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "content")
SUFFIX = re.compile(r"\s*[|—-]\s*DUMSKAYA DESIGN\s*$")
fixed = demoted = 0
for f in glob.glob(os.path.join(C, "pages", "**", "*.json"), recursive=True):
    p = json.load(open(f, encoding="utf-8"))
    before = json.dumps(p, ensure_ascii=False)
    p["h1"] = SUFFIX.sub("", p["h1"]).strip()
    seen = False
    for s in p["sections"]:
        for b in s["blocks"]:
            if b["type"] == "heading" and b["level"] == 1:
                b["text"] = SUFFIX.sub("", b["text"]).strip()
                if seen:
                    b["level"] = 2
                    demoted += 1
                seen = True
    if json.dumps(p, ensure_ascii=False) != before:
        json.dump(p, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        fixed += 1
print(f"страниц исправлено: {fixed}, лишних H1 → H2: {demoted}")
