"""Проверка карты сайта и llms.txt сборки — общая для scripts/check_site.py (студия) и check_home.py (каталог).

Карта сайта (sitemap.xml или индекс sitemapindex и его файлы): XML читается; у каждого <url> есть <loc> этого сайта
и <lastmod> в формате W3C (ГГГГ-ММ-ДД или полная дата со временем и часовым поясом); у адреса есть страница в сборке;
адреса не повторяются; в файле не больше 50 000 адресов.
llms.txt и llms-full.txt: каждая ссылка на сайт — канонический адрес из карты сайта (страница есть, не старый адрес
из редиректов, опубликована) или служебный файл (карта сайта, llms-full.txt)."""
import os
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
W3C = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2}))?$")
MAX_URLS = 50000


def check_sitemaps(dist, base, pages, errs):
    """Проверить карту сайта сборки. pages — адреса страниц сборки (/путь). Возвращает {путь: lastmod} или {}."""
    top = os.path.join(dist, "sitemap.xml")
    try:
        root = ET.parse(top).getroot()
    except (OSError, ET.ParseError) as e:
        errs.append(f"sitemap.xml не читается: {e}")
        return {}
    files = [("sitemap.xml", root)]
    if root.tag == NS + "sitemapindex":
        files = []
        for sm in root.findall(NS + "sitemap"):
            loc = (sm.findtext(NS + "loc") or "").strip()
            lm = (sm.findtext(NS + "lastmod") or "").strip()
            name = urlsplit(loc).path.lstrip("/")
            if not loc.startswith(base + "/") or "/" in name or not name.endswith(".xml"):
                errs.append(f"sitemap.xml: в индексе чужой или неверный адрес {loc}")
                continue
            if not W3C.match(lm):
                errs.append(f"sitemap.xml: у {name} нет <lastmod> или он не в формате W3C ({lm or 'пусто'})")
            try:
                files.append((name, ET.parse(os.path.join(dist, name)).getroot()))
            except (OSError, ET.ParseError) as e:
                errs.append(f"{name} (из индекса sitemap.xml) не читается: {e}")
        if not files:
            errs.append("sitemap.xml: индекс пустой")
    out = {}
    for name, rt in files:
        if rt.tag != NS + "urlset":
            errs.append(f"{name}: ожидался <urlset>")
            continue
        urls = rt.findall(NS + "url")
        if len(urls) > MAX_URLS:
            errs.append(f"{name}: {len(urls)} адресов — больше {MAX_URLS}")
        for u in urls:
            loc = (u.findtext(NS + "loc") or "").strip()
            lm = (u.findtext(NS + "lastmod") or "").strip()
            if not (loc == base + "/" or loc.startswith(base + "/")):
                errs.append(f"{name}: чужой адрес {loc}")
                continue
            path = urlsplit(loc).path or "/"
            if path in out:
                errs.append(f"{name}: адрес повторяется {path}")
            if not W3C.match(lm):
                errs.append(f"{name}: нет <lastmod> или он не в формате W3C ({lm or 'пусто'}): {path}")
            if path not in pages:
                errs.append(f"{name}: нет страницы в сборке: {path}")
            out[path] = lm
    return out


LINK = re.compile(r"\]\((https?://[^)\s]+)\)")


def check_llms(dist, base, sitemap, redirects, errs, files=("llms.txt", "llms-full.txt"), extra=("/sitemap.xml", "/llms-full.txt", "/llms.txt")):
    """Ссылки llms-файлов на сайт: только адреса из карты сайта (или служебные файлы), не старые адреса из редиректов.
    Возвращает {файл: множество путей сайта, на которые он ссылается}."""
    out = {}
    for name in files:
        f = os.path.join(dist, name)
        if not os.path.exists(f):
            if name == "llms.txt":
                errs.append("нет llms.txt")
            continue
        text = open(f, encoding="utf-8").read()
        if not text.startswith("# "):
            errs.append(f"{name}: должен начинаться с заголовка «# название» (llmstxt.org)")
        if name == "llms.txt" and not re.search(r"^> \S", text, re.M):
            errs.append(f"{name}: нет краткого описания в цитате «> …» (llmstxt.org)")
        seen = set()
        for url in LINK.findall(text) + re.findall(r"(?<![(\[])\b(https://" + re.escape(base.split("//")[1]) + r"[^\s)\]]*)", text):
            if not url.startswith(base):
                continue
            path = urlsplit(url).path or "/"
            seen.add(path)
            if path in extra:
                if not os.path.exists(os.path.join(dist, path.lstrip("/"))):
                    errs.append(f"{name}: ссылка на файл, которого нет в сборке: {path}")
                continue
            if path in redirects:
                errs.append(f"{name}: ссылка на старый адрес (редирект) {path}")
            elif path not in sitemap:
                errs.append(f"{name}: ссылка не на страницу из карты сайта (нет страницы или не опубликована): {path}")
        out[name] = seen
    return out
