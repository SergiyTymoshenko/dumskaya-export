#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Даёт каждой картинке понятное имя файла по странице, где она стоит:
  apartment-interior-design-bratislava-58m-03
Имя берётся по русскому адресу первой страницы, на которой картинка встречается
(сначала проекты, потом остальные страницы). Слова «warsaw/varshava/poland»
из имён убираются — правило «нейтрально, если город не указан явно».
Результат: content/image-names.json (id → имя).
"""
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = os.path.join(ROOT, "content")

GEO_DROP = re.compile(r"-?(warsaw|varshava|warszawa|poland|polsha|polshcha|moscow|moskva)(?=-|$)")


def ids_in(page):
    for s in page["sections"]:
        for b in s["blocks"]:
            if b["type"] == "gallery":
                for i in b["images"]:
                    yield i["id"]
            elif b["type"] == "cards":
                for it in b["items"]:
                    if it.get("image"):
                        yield it["image"]["id"]


def base_name(page, explicit_warsaw=False):
    slug = page["path"].strip("/") or "home"
    slug = slug.replace("/", "-")
    if not explicit_warsaw:
        slug = GEO_DROP.sub("", slug)
    slug = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")
    return slug[:70].rstrip("-")


def gallery_ids(page):
    for s in page["sections"]:
        for b in s["blocks"]:
            if b["type"] == "gallery":
                for i in b["images"]:
                    yield i["id"]


def card_items(page):
    for s in page["sections"]:
        for b in s["blocks"]:
            if b["type"] == "cards":
                for it in b["items"]:
                    if it.get("image"):
                        yield it


def main():
    projects = {p["path"]: p for p in json.load(open(os.path.join(C, "projects.json"), encoding="utf-8"))}
    load = lambda pat: [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(C, "pages", pat, "**", "*.json"), recursive=True))]
    ru = load("ru")
    ru.sort(key=lambda p: (p["type"] != "project", p["type"] != "kitchen", p["path"]))
    others = load("ua") + load("en")
    by_path = {p["path"]: p for p in ru + others}
    names, used = {}, set()

    def name_for(page):
        rp = page["alternates"].get("ru") or page["path"]
        return base_name({"path": rp}, projects.get(rp, {}).get("explicit_warsaw", False))

    def assign(iid, base, suffix=None):
        if iid in names:
            return
        n = 1
        name = f"{base}-{suffix}" if suffix else f"{base}-{n:02d}"
        while name in used:
            n += 1
            name = f"{base}-{suffix}-{n}" if suffix else f"{base}-{n:02d}"
        names[iid] = name
        used.add(name)

    # 1–2. фото в галереях страниц: сначала проекты и кухни, потом остальные, потом ua/en
    for page in ru + others:
        base = name_for(page)
        counter = sum(1 for v in used if v.startswith(base + "-") and v[len(base) + 1:].isdigit())
        for iid in gallery_ids(page):
            if iid in names:
                continue
            counter += 1
            name = f"{base}-{counter:02d}"
            while name in used:
                counter += 1
                name = f"{base}-{counter:02d}"
            names[iid] = name
            used.add(name)
    # 3. картинки карточек — по странице, на которую ведёт карточка
    for page in ru + others:
        for it in card_items(page):
            target = by_path.get(it.get("href") or "")
            base = name_for(target) if target else name_for(page)
            assign(it["image"]["id"], base, "cover")
    # 4. обложки проектов и og-картинки
    for p in projects.values():
        if p.get("cover"):
            assign(p["cover"], base_name({"path": p["path"]}, p.get("explicit_warsaw")), "cover")
    for page in ru + others:
        if page.get("og_image"):
            assign(page["og_image"], name_for(page), "og")
    names["65d3aa3656ff01000f88c35d"] = names.get("65d3aa3656ff01000f88c35d") or "dumskaya-design-logo"
    with open(os.path.join(C, "image-names.json"), "w", encoding="utf-8") as f:
        json.dump(names, f, ensure_ascii=False, indent=0)
    print(f"имён картинок: {len(names)}")


if __name__ == "__main__":
    main()
