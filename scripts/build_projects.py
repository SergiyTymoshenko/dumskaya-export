#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Собирает content/projects.json — карточки проектов для портфолио и главной.

Берёт подписи карточек со страниц портфолио на трёх языках и применяет гео-правило:
  • Варшава и Москва убираются из подписи, если на самой странице проекта (H1)
    город не назван явно; Краков, Познань и другие города остаются.
Запускать после import_weblium.py. Ручные правки — в content/projects-overrides.json.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = os.path.join(ROOT, "content")
LANGS = ("ru", "ua", "en")
PORTFOLIO = {"ru": "proekty-interior-design", "ua": "realizovani-dyzain-proekty-ta-arkhitekturni-rishennia",
             "en": "portfolio-interior-design-projects"}

# города, которые убираем, если проект явно не назван «варшавским» / «московским»
DROP = {
    "ru": r"(?:,?\s*(?:в|во)\s+(?:Варшаве|Москве))|(?:,?\s*(?:Варшава|Москва)(?:,?\s*Польша)?)",
    "ua": r"(?:,?\s*(?:у|в)\s+(?:Варшаві|Москві))|(?:,?\s*(?:Варшава|Москва)(?:,?\s*Польща)?)",
    "en": r"(?:,?\s*in\s+(?:Warsaw|Moscow))|(?:,?\s*(?:Warsaw|Moscow)(?:,?\s*Poland)?)",
}
EXPLICIT = re.compile(r"Варшав|Warsaw|Варшав", re.I)


def load(lang, slug):
    with open(os.path.join(C, "pages", lang, slug + ".json"), encoding="utf-8") as f:
        return json.load(f)


def cards(page):
    for s in page["sections"]:
        heads = [b.get("text", "") for b in s["blocks"] if b["type"] == "heading"]
        if any(re.match(r"(Услуги|Послуги|Our services|Interior design studio services|Services)", h) for h in heads):
            continue
        for b in s["blocks"]:
            if b["type"] == "cards":
                yield from b["items"]


def neutral(text, lang):
    t = re.sub(DROP[lang], "", text, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,")
    t = re.sub(r"\s+,", ",", t)
    return t


def area_of(text):
    m = re.search(r"(\d{2,4})\s*(?:м²|м2|m²|m2|sqm|кв)", text)
    return int(m.group(1)) if m else None


def main():
    order = json.load(open(os.path.join(C, "projects-order.json"), encoding="utf-8"))
    titles = {l: {c["href"]: c for c in cards(load(l, PORTFOLIO[l])) if c["href"]} for l in LANGS}
    ov_path = os.path.join(C, "projects-overrides.json")
    overrides = json.load(open(ov_path, encoding="utf-8")) if os.path.exists(ov_path) else {}
    out = []
    for item in order:
        ru_path = item["path"]
        ru = load("ru", ru_path.strip("/"))
        explicit = bool(EXPLICIT.search(ru["h1"]))
        rec = {"path": ru_path, "group": item["group"], "alternates": ru["alternates"],
               "cover": None, "title": {}, "explicit_warsaw": explicit}
        for l in LANGS:
            p = ru["alternates"].get(l)
            card = titles[l].get(p) if p else None
            if not card:
                continue
            t = card["title"]
            rec["title"][l] = t if explicit else neutral(t, l)
            if l == "ru" and card.get("image"):
                rec["cover"] = card["image"]["id"]
        rec["area"] = area_of(rec["title"].get("ru", "") or ru["h1"])
        rec.update(overrides.get(ru_path, {}))
        out.append(rec)
    with open(os.path.join(C, "projects.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    changed = sum(1 for r in out if not r["explicit_warsaw"])
    print(f"проектов: {len(out)}")


if __name__ == "__main__":
    main()
