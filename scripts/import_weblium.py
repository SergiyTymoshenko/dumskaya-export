#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Разовый импорт выгрузки Weblium (папка dumskaya-export) в данные нового сайта.

  python3 scripts/import_weblium.py ~/Documents/dumskaya-export

Пишет:
  content/pages/<lang>/<slug>.json  — страница: адрес, мета-теги, языковые пары, блоки контента
  content/images.json               — картинки: исходный файл, размер, alt на трёх языках
  content/site.json                 — меню, контакты, соцсети

После импорта источником правды становится папка content/: тексты правятся там.
"""
import csv
import html
import json
import os
import re
import sys
from collections import OrderedDict

from bs4 import BeautifulSoup, NavigableString, Tag

LANGS = ("ru", "ua", "en")
IMG_RE = re.compile(r"res\d*\.weblium\.site/res/[^/\"'\s]+/([0-9a-f]{24})")
ECOM_RE = re.compile(r"e-c\.storage\.googleapis\.com/res/([0-9a-f-]{36})")
HOST = "https://dumskaya-design.com"


def clean(t):
    return re.sub(r"\s+", " ", (t or "").replace("\xa0", " ")).strip()


def lang_of(path):
    first = path.strip("/").split("/", 1)[0]
    return first if first in ("en", "ua") else "ru"


def slug_of(path):
    lang = lang_of(path)
    parts = [p for p in path.strip("/").split("/") if p]
    if lang != "ru":
        parts = parts[1:]
    return "/".join(parts) or "_home"


def norm_href(href):
    if not href:
        return None
    href = href.strip()
    if href.startswith(("tel:", "mailto:", "http://", "https://")):
        if href.startswith(HOST):
            href = href[len(HOST):] or "/"
        else:
            return href
    if href.startswith("#") or href.startswith("javascript:"):
        return None
    href = href.split("#")[0].split("?")[0]
    if len(href) > 1:
        href = href.rstrip("/")
    return href or "/"


def image_id(tag):
    blob = " ".join(v if isinstance(v, str) else " ".join(v) for v in tag.attrs.values())
    for t in [tag] + tag.find_all(["img", "source"]):
        blob += " " + " ".join(v if isinstance(v, str) else " ".join(v) for v in t.attrs.values())
    m = IMG_RE.search(blob) or ECOM_RE.search(blob)
    return m.group(1) if m else None


def image_alt(tag):
    img = tag if tag.name == "img" else tag.find("img")
    if not img:
        return ""
    return clean(img.get("alt") or img.get("aria-label") or "")


def inline_html(node):
    """Текст абзаца с минимальной разметкой: <strong>, <em>, <a>, переносы строк."""
    out = []
    for ch in node.children:
        if isinstance(ch, NavigableString):
            out.append(html.escape(str(ch).replace("\xa0", " "), quote=False))
            continue
        if not isinstance(ch, Tag):
            continue
        if ch.name == "br":
            out.append("\n")
            continue
        inner = inline_html(ch)
        style = (ch.get("style") or "").replace(" ", "")
        if ch.name in ("strong", "b") or "font-weight:bold" in style or "font-weight:700" in style:
            inner = f"<strong>{inner}</strong>" if inner.strip() else inner
        if ch.name in ("em", "i") or "font-style:italic" in style:
            inner = f"<em>{inner}</em>" if inner.strip() else inner
        if ch.name == "a":
            href = norm_href(ch.get("href"))
            if href and inner.strip():
                inner = f'<a href="{html.escape(href)}">{inner}</a>'
        out.append(inner)
    return "".join(out)


def tidy(h):
    h = re.sub(r"[ \t]+", " ", h)
    h = re.sub(r" *\n *", "\n", h)
    h = re.sub(r"</strong>\s*<strong>", " ", h)
    return h.strip()


BULLET = re.compile(r"^\s*[●•▪◦–—-]\s*")


def text_parts(node):
    """Абзацы и списки из текстового компонента Weblium."""
    parts = []
    blocks = node.select(".w-text-block") or [node]
    lists = node.find_all(["ul", "ol"])
    if lists and not node.select(".w-text-block"):
        for l in lists:
            parts.append({"t": "ul" if l.name == "ul" else "ol",
                          "items": [tidy(inline_html(li)) for li in l.find_all("li") if clean(li.get_text())]})
        return parts
    for b in blocks:
        if b.find_parent(["ul", "ol"]) and b.find_parent(["ul", "ol"]) in node.descendants:
            pass
        raw = tidy(inline_html(b))
        if not clean(re.sub(r"<[^>]+>", "", raw)):
            continue
        # разрезаем по переносам строк и по маркерам «●» внутри строки
        raw = re.sub(r"\s*[●•]\s*", "\n● ", raw)
        lines = [l.strip() for l in raw.split("\n") if clean(re.sub(r"<[^>]+>", "", l))]
        for line in lines:
            if re.sub(r"<[^>]+>", "", line).lstrip().startswith("●"):
                item = BULLET.sub("", line, count=1)
                if parts and parts[-1]["t"] == "ul":
                    parts[-1]["items"].append(item)
                else:
                    parts.append({"t": "ul", "items": [item]})
            else:
                parts.append({"t": "p", "html": line})
    return parts


class BlockParser:
    def __init__(self):
        self.blocks = []
        self.seen_imgs = set()

    def add(self, b):
        self.blocks.append(b)

    def add_image(self, iid, alt):
        if not iid or iid in self.seen_imgs:
            return
        self.seen_imgs.add(iid)
        if self.blocks and self.blocks[-1]["type"] == "gallery":
            self.blocks[-1]["images"].append({"id": iid, "alt": alt})
        else:
            self.add({"type": "gallery", "images": [{"id": iid, "alt": alt}]})

    def cards(self, coll):
        inner = coll.select_one(".w-grid__inner") or coll
        items = []
        for it in inner.find_all(recursive=False):
            pic = it.select_one("[data-component=picture]")
            link = it.select_one("a[href]")
            title = clean(" ".join(t.get_text(" ") for t in it.select("[data-component=text]")))
            iid = image_id(pic) if pic else None
            if iid:
                self.seen_imgs.add(iid)
            items.append({"title": title, "href": norm_href(link.get("href")) if link else None,
                          "image": {"id": iid, "alt": image_alt(pic)} if iid else None})
        items = [i for i in items if i["title"] or i["image"]]
        if items:
            self.add({"type": "cards", "items": items})

    def walk(self, node):
        for ch in node.children:
            if not isinstance(ch, Tag):
                continue
            dc = ch.get("data-component")
            if ch.name in ("script", "style", "noscript", "svg", "form", "iframe"):
                if ch.name == "form":
                    self.add({"type": "form"})
                continue
            if dc == "collection":
                self.cards(ch)
                continue
            if re.fullmatch(r"h[1-6]", ch.name or ""):
                t = clean(ch.get_text(" "))
                if t:
                    self.add({"type": "heading", "level": int(ch.name[1]), "text": t})
                continue
            if dc == "text":
                parts = text_parts(ch)
                if parts:
                    if self.blocks and self.blocks[-1]["type"] == "text":
                        self.blocks[-1]["parts"].extend(parts)
                    else:
                        self.add({"type": "text", "parts": parts})
                continue
            if dc == "picture" or ch.name == "img":
                self.add_image(image_id(ch), image_alt(ch))
                continue
            if dc == "button" or (ch.name == "a" and "w-button" in (ch.get("class") or [])):
                href = norm_href(ch.get("href"))
                t = clean(ch.get_text(" "))
                if t:
                    if self.blocks and self.blocks[-1]["type"] == "buttons":
                        self.blocks[-1]["items"].append({"text": t, "href": href})
                    else:
                        self.add({"type": "buttons", "items": [{"text": t, "href": href}]})
                continue
            style = ch.get("style") or ""
            if "url(" in style and dc == "background":
                m = IMG_RE.search(style)
                if m:
                    self.add_image(m.group(1), "")
            self.walk(ch)


def parse_page(path_html):
    with open(path_html, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    sections = []
    for b in soup.select("div.block-wrapper"):
        if b.find_parent("div", class_="block-wrapper"):
            continue
        if b.select_one('[data-block-content-type="header"]') or b.select_one(".w-section--footer"):
            continue
        bp = BlockParser()
        style = b.get("style") or ""
        bg = IMG_RE.search(style)
        if bg:
            bp.add_image(bg.group(1), "")
        bp.walk(b)
        if bp.blocks:
            sections.append({"id": (b.get("id") or "").replace("blockId-", ""), "blocks": bp.blocks})
    return soup, sections


SERVICES_HEAD = re.compile(r"^(Услуги студии|Послуги студії|Interior design studio services|Our services|Services)", re.I)


def classify(ru_path):
    p = ru_path
    if p == "/":
        return "home"
    if p == "/shop" or p.startswith("/shop/"):
        return "shop"
    if p in ("/proekty-interior-design",):
        return "portfolio"
    if p.startswith("/contact"):
        return "contact"
    if re.search(r"kuhni-pod-zakaz-k-\d+", p):
        return "kitchen"
    if re.search(r"kak-pravilno|why-you-need|osnovnye-principy|transformaciya", p):
        return "article"
    if re.search(r"package|^/price-|custom-furniture-bratislava-design", p):
        return "price"
    return None  # проект или услуга — решаем по портфолио


def main():
    if len(sys.argv) < 2:
        sys.exit("Укажите папку выгрузки: python3 scripts/import_weblium.py ~/Documents/dumskaya-export")
    src = os.path.abspath(os.path.expanduser(sys.argv[1]))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, "content")
    os.makedirs(out, exist_ok=True)

    urls = [r for r in csv.DictReader(open(os.path.join(src, "urls.csv"), encoding="utf-8-sig"))
            if str(r["код ответа"]) == "200" and r["файл HTML"] and "{" not in r["путь"]]
    by_path = {r["путь"]: r for r in urls}

    # группы «одна страница на трёх языках»
    group_of = {}
    for r in urls:
        alts = {"ru": r["версия ru"], "ua": r["версия ua"], "en": r["версия en"]}
        alts[r["язык"]] = r["путь"]
        key = alts["ru"] or r["путь"]
        group_of[r["путь"]] = {k: v for k, v in alts.items() if v and v in by_path}
    # магазин без hreflang — связываем по одинаковому адресу без языкового префикса
    for r in urls:
        if re.match(r"^(/ua|/en)?/shop(/|$)", r["путь"]):
            rest = re.sub(r"^/(ua|en)(?=/)", "", r["путь"])
            group_of[r["путь"]] = {l: (rest if l == "ru" else f"/{l}{rest}") for l in LANGS
                                   if (rest if l == "ru" else f"/{l}{rest}") in by_path}

    # проекты = карточки на странице портфолио (на русском), с группой
    portfolio_html = os.path.join(src, by_path["/proekty-interior-design"]["файл HTML"])
    _, psections = parse_page(portfolio_html)
    project_paths, project_group = [], {}
    group_names = ["residential", "commercial", "architecture"]
    gi = 0
    for sec in psections:
        for b in sec["blocks"]:
            if b["type"] == "cards" and not any(SERVICES_HEAD.match(x.get("text", "")) for x in sec["blocks"] if x["type"] == "heading"):
                for it in b["items"]:
                    if it["href"] in by_path:
                        project_paths.append(it["href"])
                        project_group[it["href"]] = group_names[min(gi, 2)]
                gi += 1

    images = {}
    for r in csv.DictReader(open(os.path.join(src, "images.csv"), encoding="utf-8-sig")):
        if not r["файл"]:
            continue
        iid = os.path.splitext(os.path.basename(r["файл"]))[0]
        images[iid] = OrderedDict(
            file=r["файл"], width=int(r["ширина"] or 0), height=int(r["высота"] or 0),
            bytes=int(r["размер, байт"] or 0), type=r["тип"],
            alt=OrderedDict((l, r[f"alt {l}"]) for l in LANGS))

    count = 0
    for r in urls:
        path, lang = r["путь"], r["язык"]
        alts = group_of.get(path, {lang: path})
        ru_path = alts.get("ru", path)
        kind = classify(ru_path)
        if kind is None:
            kind = "project" if ru_path in project_group else "service"
        soup, sections = parse_page(os.path.join(src, r["файл HTML"]))
        page = OrderedDict(
            path=path, lang=lang, type=kind,
            group=project_group.get(ru_path),
            title=r["title"], description=r["description"], h1=r["h1"],
            og_image=(IMG_RE.search(r["og:image"] or "") or [None, None])[1] if r["og:image"] else None,
            alternates=OrderedDict((l, alts[l]) for l in LANGS if l in alts),
            sections=sections)
        d = os.path.join(out, "pages", lang)
        os.makedirs(os.path.dirname(os.path.join(d, slug_of(path) + ".json")), exist_ok=True)
        with open(os.path.join(d, slug_of(path) + ".json"), "w", encoding="utf-8") as f:
            json.dump(page, f, ensure_ascii=False, indent=1)
        count += 1

    with open(os.path.join(out, "images.json"), "w", encoding="utf-8") as f:
        json.dump(images, f, ensure_ascii=False, indent=0)
    with open(os.path.join(out, "projects-order.json"), "w", encoding="utf-8") as f:
        json.dump([{"path": p, "group": project_group[p]} for p in project_paths], f, ensure_ascii=False, indent=1)
    print(f"страниц: {count}, картинок: {len(images)}, проектов в портфолио: {len(project_paths)}")


if __name__ == "__main__":
    main()
