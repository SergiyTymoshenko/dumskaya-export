#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка собранного сайта (папка dist/) перед выкладкой:
  • все внутренние ссылки ведут на существующие страницы (не на редиректы и не в 404);
  • hreflang взаимные, у каждой страницы есть x-default и canonical на себя;
  • ровно один H1, есть title ≤ 60 и description ≤ 155;
  • JSON-LD парсится;
  • ни одна страница не попала в список редиректов (иначе она была бы недоступна);
  • Варшава/Москва не встречаются в видимом тексте страниц, кроме явно варшавских проектов.
  python3 scripts/check_site.py
"""
import glob, json, os, re, sys
from html.parser import HTMLParser
from urllib.parse import urlparse, unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
SITE = "https://dumskaya-design.com"


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.h1, self.alts, self.canon, self.title, self.desc, self.ld = [], 0, {}, None, "", None, []
        self._t = self._ld = False
        self.text = []
        self._skip = 0

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag in ("script", "style"):
            self._skip += 1
            if tag == "script" and a.get("type") == "application/ld+json":
                self._ld = True
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "h1":
            self.h1 += 1
        if tag == "title":
            self._t = True
        if tag == "link" and a.get("rel") == "canonical":
            self.canon = a.get("href")
        if tag == "link" and a.get("rel") == "alternate" and a.get("hreflang"):
            self.alts[a["hreflang"]] = a["href"]
        if tag == "meta" and a.get("name") == "description":
            self.desc = a.get("content")
        if tag == "img" and a.get("alt") is not None:
            self.text.append(a.get("alt"))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1
            self._ld = False
        if tag == "title":
            self._t = False

    def handle_data(self, d):
        if self._t:
            self.title += d
        if self._ld:
            self.ld.append(d)
        elif not self._skip:
            self.text.append(d)


def url_of(f):
    rel = os.path.relpath(f, DIST)
    if rel == "index.html":
        return "/"
    return "/" + unquote(rel[:-5])


def main():
    files = [f for f in glob.glob(os.path.join(DIST, "**", "*.html"), recursive=True) if not f.endswith("404.html")]
    pages = {url_of(f): f for f in files}
    redirects = json.load(open(os.path.join(ROOT, "content", "redirects.json"), encoding="utf-8"))
    projects = json.load(open(os.path.join(ROOT, "content", "projects.json"), encoding="utf-8"))
    explicit = {v for p in projects if p.get("explicit_warsaw") for v in p["alternates"].values()}
    errs, warn = [], []
    parsed = {}
    for u, f in pages.items():
        p = P()
        p.feed(open(f, encoding="utf-8").read())
        parsed[u] = p
    for u, p in parsed.items():
        if p.h1 != 1:
            errs.append(f"H1 x{p.h1}: {u}")
        t = p.title.strip()
        if not t or len(t) > 60:
            errs.append(f"title {len(t)}: {u}")
        if not p.desc or len(p.desc) > 155:
            errs.append(f"description {len(p.desc or '')}: {u}")
        if p.canon != SITE + u and not (u == "/" and p.canon == SITE + "/"):
            errs.append(f"canonical {p.canon}: {u}")
        if "x-default" not in p.alts:
            errs.append(f"нет x-default: {u}")
        for lang, href in p.alts.items():
            v = urlparse(href).path or "/"
            if v not in parsed:
                errs.append(f"hreflang {lang} → нет страницы {v}: {u}")
            elif lang != "x-default" and SITE + u not in [h for h in parsed[v].alts.values()] and SITE + "/" != SITE + u:
                errs.append(f"hreflang не взаимный {u} ↔ {v}")
        for raw in p.links:
            if raw.startswith(("mailto:", "tel:", "#", "http://", "https://")) and not raw.startswith(SITE):
                continue
            v = urlparse(raw.replace(SITE, "")).path or "/"
            if v.startswith("/img/") or v.startswith("/_astro/") or v.startswith("/api/"):
                continue
            if v in redirects:
                errs.append(f"ссылка на старый адрес {v}: {u}")
            elif v not in parsed:
                errs.append(f"битая ссылка {v}: {u}")
        for block in p.ld:
            try:
                json.loads(block)
            except Exception as e:
                errs.append(f"JSON-LD не читается: {u}: {e}")
        if u not in explicit:
            txt = " ".join(p.text)
            m = re.search(r"\w*(Варшав|Warsaw|Warszaw|Москв|Moscow|Польш|Польщ|Poland)\w*", txt)
            if m:
                ctx = txt[max(0, m.start() - 60): m.end() + 30].replace("\n", " ")
                warn.append(f"гео в тексте {u}: …{ctx}…")
    clash = [u for u in pages if u in redirects]
    for u in clash:
        errs.append(f"страница стоит в редиректах: {u}")
    for k, v in redirects.items():
        if v not in pages:
            errs.append(f"редирект ведёт в никуда: {k} → {v}")
    print(f"страниц: {len(pages)}, редиректов: {len(redirects)}")
    print(f"ошибок: {len(errs)}, предупреждений: {len(warn)}")
    for e in sorted(set(errs))[:80]:
        print("  ✗", e)
    for w in warn[:40]:
        print("  ⚠", w)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
