#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Гео-чистка контента: Варшава / Польша / Москва убираются из текстов, подписей карточек
и alt-текстов фото — кроме страниц явно варшавских проектов (в H1 есть «Варшава»).
Краков, Познань и другие города остаются.

Повторяющиеся alt на одной странице получают номер фото, чтобы каждое фото
описывалось отдельно. Итоговые alt переносятся и в content/images.json
(оттуда они попадают в метаданные файлов).

  python3 scripts/geo_clean.py
"""
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = os.path.join(ROOT, "content")

# точечные правки текста: (язык, адрес или None для всех, было, стало)
MANUAL = [
    ("ru", "/priemka-kvartiry-ot-zastrojshchika", "приемки недвижимости в Варшаве", "приемки недвижимости в Братиславе"),
    ("ua", None, "приймання нерухомості у Варшаві", "приймання нерухомості у Братиславі"),
    ("ru", None, "Дизайн интерьера частного дома в Москве, мебель на заказ и ремонт под ключ, 230 м²",
     "Дизайн интерьера частного дома 230 м², мебель на заказ и ремонт под ключ"),
    ("ru", None, "частного дома площадью 230 м² в Москве,", "частного дома площадью 230 м²,"),
    ("en", None, "Private House Interior Design in Moscow, ", "Private House Interior Design, "),
    ("en", None, "230 m² private house in Moscow,", "230 m² private house,"),
]

DROP = {
    "ru": [r",?\s*(?:в|во|по)\s+(?:Варшаве|Москве|Польше)\b", r",?\s*(?:Варшава|Москва|Польша|Подмосковье)\b",
           r",?\s*варшавск\w*", r",?\s*(?:Варшаве|Москве|Варшаву)\b"],
    "ua": [r",?\s*(?:у|в)\s+(?:Варшаві|Москві|Польщі)\b", r",?\s*(?:Варшава|Москва|Польща|Польша)\b"],
    "en": [r",?\s*in\s+(?:Warsaw|Moscow|Poland)\b", r",?\s*(?:Warsaw|Moscow|Poland)\b"],
}
GEO = re.compile(r"варшав|warsaw|warszaw|польш|польщ|poland|москв|moscow", re.I)
PHOTO = {"ru": "фото", "ua": "фото", "en": "photo"}
# русский текст в украинском alt: буквы, которых нет в украинском, или русские слова
RUSSIAN = re.compile(r"[ыэъё]|интерьер|квартир[аыу]\b|изготовлени|мебел[ьи]\b|под заказ", re.I)


def neutral(text, lang):
    if not text or not GEO.search(text):
        return text
    t = text
    for rx in DROP["ru"] + DROP["ua"] + DROP["en"]:
        t = re.sub(rx, "", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    t = re.sub(r"([,\-–—])\s*([,\-–—])+", r"\1", t)
    t = re.sub(r"^[\s,\-–—]+|[\s,\-–—]+$", "", t)
    return t


def main():
    projects = json.load(open(os.path.join(C, "projects.json"), encoding="utf-8"))
    explicit = set()
    for p in projects:
        if p.get("explicit_warsaw"):
            explicit.update(p["alternates"].values())
    files = glob.glob(os.path.join(C, "pages", "**", "*.json"), recursive=True)
    images = json.load(open(os.path.join(C, "images.json"), encoding="utf-8"))
    alt_out = {}
    stats = {"text": 0, "card": 0, "alt": 0, "numbered": 0}
    # сначала проекты: их alt важнее для images.json
    order = sorted(files, key=lambda f: 0 if json.load(open(f, encoding="utf-8"))["type"] == "project" else 1)
    for f in order:
        p = json.load(open(f, encoding="utf-8"))
        lang, keep = p["lang"], p["path"] in explicit
        raw = json.dumps(p, ensure_ascii=False)
        for l, path, a, b in MANUAL:
            if l == lang and (path is None or path == p["path"]) and a in raw:
                raw = raw.replace(a, b)
                stats["text"] += 1
        p = json.loads(raw)
        if not keep:
            for k in ("h1",):
                p[k] = neutral(p[k], lang)
        gallery_alts = []
        for s in p["sections"]:
            for b in s["blocks"]:
                if b["type"] == "cards":
                    for c in b["items"]:
                        if c.get("image") and c["href"] in explicit and lang != "ru" and re.search(r"[А-Яа-яІіЇїЄє]", c["image"]["alt"]) and (lang == "en" or RUSSIAN.search(c["image"]["alt"])):
                            c["image"]["alt"] = c["title"]
                        if c["href"] in explicit:
                            continue
                        new = neutral(c["title"], lang)
                        if new != c["title"]:
                            c["title"] = new
                            stats["card"] += 1
                        if c.get("image") and ((lang == "ua" and RUSSIAN.search(c["image"]["alt"])) or
                                               (lang == "en" and re.search(r"[А-Яа-яІіЇїЄє]", c["image"]["alt"]))):
                            c["image"]["alt"] = c["title"]
                        if c.get("image"):
                            na = neutral(c["image"]["alt"], lang)
                            if na != c["image"]["alt"]:
                                c["image"]["alt"] = na
                                stats["alt"] += 1
                elif b["type"] == "gallery":
                    for i in b["images"]:
                        if not keep:
                            na = neutral(i["alt"], lang)
                            if na != i["alt"]:
                                i["alt"] = na
                                stats["alt"] += 1
                        gallery_alts.append(i)
                elif b["type"] == "heading" and not keep:
                    b["text"] = neutral(b["text"], lang)
                elif b["type"] == "text" and not keep:
                    for part in b["parts"]:
                        if part["t"] == "p":
                            new = neutral(part["html"], lang)
                            if new != part["html"]:
                                part["html"] = new
                                stats["text"] += 1
                        else:
                            part["items"] = [neutral(x, lang) for x in part["items"]]
        # одинаковые или пустые alt на странице → нумеруем фото с названием проекта
        base_name = p["h1"] or p["title"].split("|")[0].strip()
        ru_path = p["alternates"].get("ru")
        proj = next((x for x in projects if x["path"] == ru_path), None)
        if proj and proj["title"].get(lang):
            base_name = proj["title"][lang]
        counts = {}
        for i in gallery_alts:
            counts[i["alt"]] = counts.get(i["alt"], 0) + 1
        n = 0
        for i in gallery_alts:
            n += 1
            if lang == "ua" and RUSSIAN.search(i["alt"]):
                i["alt"] = f"Дизайн інтер’єру — {base_name}, фото {n}"
                stats["numbered"] += 1
            elif not i["alt"] or (lang == "en" and re.search(r"[А-Яа-яЁёІіЇїЄєҐґ]", i["alt"])):
                i["alt"] = f"{base_name} — {PHOTO[lang]} {n}"
                stats["numbered"] += 1
            elif counts[i["alt"]] > 1:
                i["alt"] = f"{i['alt']} — {base_name}, {PHOTO[lang]} {n}" if proj else f"{i['alt']} — {PHOTO[lang]} {n}"
                stats["numbered"] += 1
            alt_out.setdefault((i["id"], lang), i["alt"])
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(p, fh, ensure_ascii=False, indent=1)
    for (iid, lang), alt in alt_out.items():
        if iid in images:
            images[iid]["alt"][lang] = alt
    for iid, meta in images.items():
        for lang in ("ru", "ua", "en"):
            if (iid, lang) not in alt_out:
                meta["alt"][lang] = neutral(meta["alt"].get(lang) or "", lang)
    json.dump(images, open(os.path.join(C, "images.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(stats)


if __name__ == "__main__":
    main()
