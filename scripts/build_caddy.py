#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""content/redirects.json → deploy/caddy/dumskaya-redirects.snippet (map + redir для Caddy)."""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
red = json.load(open(os.path.join(ROOT, "content", "redirects.json"), encoding="utf-8"))
def q(s):
    if any(c in s for c in ' "{}\\#') or not s:
        raise SystemExit(f"Недопустимый символ в адресе редиректа: {s!r}")
    return s
PREFIXES = [("/pl-pl/", "/en")]
lines = ["# Сгенерировано scripts/build_caddy.py — не править вручную.", "map {path} {dd_redirect} {"]
for k, v in sorted(red.items()):
    lines.append(f"\t{q(k)} {q(v)}")
lines += ["\tdefault \"\"", "}", "@dd_redirect expression `{dd_redirect} != \"\"`", "redir @dd_redirect {dd_redirect} 301", ""]
# старые разделы сайта, которых больше нет: адрес, которого нет в списке выше, — на страницу раздела, а не «не найдено»
# (польской версии нет — всё /pl-pl/… на английскую главную; решено 25.10.2026)
for i, (prefix, to) in enumerate(PREFIXES, 1):
    lines += [f"@dd_prefix_{i} {{", f"\tpath {q(prefix)}*", "\texpression `{dd_redirect} == \"\"`", "}", f"redir @dd_prefix_{i} {q(to)} 301", ""]
out = os.path.join(ROOT, "deploy", "caddy", "dumskaya-redirects.snippet")
open(out, "w", encoding="utf-8").write("\n".join(lines))
print(f"редиректов: {len(red)} → {os.path.relpath(out, ROOT)}")
