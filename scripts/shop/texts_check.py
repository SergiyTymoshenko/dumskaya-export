#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка своих текстов товаров DUMSKAYA HOME перед выкладкой фабрики (content/TEXT_STYLE.md).

   python3 scripts/shop/texts_check.py poliform                  — content/home/texts/poliform.json
   python3 scripts/shop/texts_check.py poliform part.json        — другой файл ({артикул: {en, ru, de, fr, es}})
   python3 scripts/shop/texts_check.py poliform part.json --only  — только артикулы из файла (без «нет текста»)

Ошибки (код выхода 1):
  • нет текста на каком-то из пяти языков у товара, который пойдёт на сайт; артикул не из этой фабрики;
  • шаблонные обороты (scripts/text_markers.py) и невидимые символы;
  • кириллица не в русском тексте;
  • цифры, которых нет в данных фабрики (размеры, годы, число отделок и исполнений считаются из базы) — защита от выдумок;
  • близко к тексту фабрики: шесть слов подряд как у фабрики (en и ru) или больше 15 % совпадающих четвёрок слов;
  • цены, скидки, «официальный дилер», «в наличии», гарантии, «лучший», Россия;
  • нет названия модели.
Предупреждения: длина вне обычной, «Poliform» больше двух раз, много тире, одинаковые предложения у разных товаров."""
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "shop"))
import text_markers as TM  # noqa: E402
import catalog_index as CI  # noqa: E402

LANGS = ["en", "ru", "de", "fr", "es"]
MARKERS = {"en": TM.EN, "ru": TM.RU, "de": TM.DE, "fr": TM.FR, "es": TM.ES}
WORDS = {"en": (40, 160), "ru": (30, 150), "de": (35, 160), "fr": (45, 190), "es": (45, 190)}
CYR = re.compile(r"[А-Яа-яЁё]")
BAN = {
    "en": r"\bprices?\b|€|\$|\bdiscount|\bdealer|\bin stock\b|\bwarrant|\bguarantee|\bbest\b|\bmost popular\b|\bRussia",
    "ru": r"\bцен[аыуе]?\b|\bцены\b|€|\$|скидк|дилер|в наличии|гаранти|\bлучш|самый популярн|\bРосси",
    "de": r"\bPreis|€|\$|Rabatt|Händler|\bauf Lager\b|lagernd|Garantie|\bbeste[nrs]?\b|Russland",
    "fr": r"\bprix\b|€|\$|\bremise|revendeur|\ben stock\b|\bgarantie|\bmeilleur|\bRussie",
    "es": r"\bprecios?\b|€|\$|descuento|distribuidor|\ben stock\b|garantía|\bmejor(es)?\b|\bRusia",
}
NUM = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)?")


def words(s):
    return re.findall(r"[\w’'-]+", s.lower())


def shingles(ws, n):
    return {" ".join(ws[i:i + n]) for i in range(len(ws) - n + 1)}


def allowed_numbers(p, sisters=()):
    """Все числа из данных фабрики по товару (и по товарам той же коллекции — с ними текст сравнивает) и посчитанные из базы количества."""
    src = " ".join(json.dumps(q["_src"].get("versions") or [], ensure_ascii=False) for q in sisters)
    src += " " + json.dumps(p["_src"], ensure_ascii=False) + " " + json.dumps(p["name"], ensure_ascii=False)
    nums = {n.replace(",", ".") for n in NUM.findall(src)}
    fin = p["_src"].get("finishes") or {}
    counts = {len(v) for v in fin.values()} | {sum(len(v) for v in fin.values()), len(fin),
                                               len(p["_src"].get("versions") or []), len(p["images"]), len(p["drawings"])}
    # сумма групп одного вида (матовые + глянцевые лаки и т. п.) — по любым двум группам
    vals = [len(v) for v in fin.values()]
    counts |= {a + b for i, a in enumerate(vals) for b in vals[i + 1:]}
    nums |= {str(c) for c in counts}
    # миллиметры ↔ сантиметры
    for n in list(nums):
        try:
            x = float(n)
        except ValueError:
            continue
        for y in (x / 10, x * 10):
            nums.add(str(int(y)) if y == int(y) else str(round(y, 1)))
    return nums


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    factory = sys.argv[1]
    path = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else os.path.join(ROOT, "content/home/texts", f"{factory}.json")
    only = "--only" in sys.argv
    texts = json.load(open(path, encoding="utf-8"))
    prods, _, _ = CI.build()
    mine = {p["sku"]: p for p in prods if p["factory"] == factory}
    live = {k: p for k, p in mine.items() if not p.get("hidden") and not p.get("duplicate_of")}
    brand = CI.MFR[factory]["name"]
    errs, warns = [], []
    sent_use = defaultdict(set)
    for sku in sorted(set(live) | set(texts)):
        if sku not in mine:
            errs.append(f"{sku}: такого товара у фабрики нет")
            continue
        if sku not in texts:
            if not only and sku in live:
                errs.append(f"{sku}: нет текста")
            continue
        p, t = mine[sku], texts[sku]
        nums = allowed_numbers(p, [q for q in mine.values() if q["collection"] == p["collection"] and q is not p])
        src_en, src_ru = words(p["_src"].get("text", {}).get("en", "")), words(p["_src"].get("text", {}).get("ru", ""))
        model = p["model"].lower()
        for l in LANGS:
            s = (t.get(l) or "").strip()
            tag = f"{sku} [{l}]"
            if not s:
                errs.append(f"{tag}: нет текста")
                continue
            hits = TM.scan(s, MARKERS[l])
            if hits:
                errs.append(f"{tag}: шаблонные обороты: {', '.join(hits)}")
            if l != "ru" and CYR.search(s):
                errs.append(f"{tag}: кириллица")
            ban = re.findall(BAN[l], s, re.I)
            if ban:
                errs.append(f"{tag}: нельзя: {', '.join(sorted(set(ban)))}")
            bad = [n for n in NUM.findall(s) if n.replace(",", ".") not in nums]
            if bad:
                errs.append(f"{tag}: цифр нет в данных фабрики: {', '.join(bad)}")
            if model.split()[0] not in s.lower():
                errs.append(f"{tag}: нет названия модели «{p['model']}»")
            ws = words(s)
            lo, hi = WORDS[l]
            if not lo <= len(ws) <= hi:
                warns.append(f"{tag}: {len(ws)} слов (обычно {lo}–{hi})")
            src = src_en if l == "en" else src_ru if l == "ru" else None
            if src:
                six = shingles(ws, 6) & shingles(src, 6)
                if six:
                    errs.append(f"{tag}: как у фабрики: «{sorted(six)[0]}»")
                four = shingles(ws, 4)
                if four:
                    share = len(four & shingles(src, 4)) / len(four)
                    if share > 0.15:
                        errs.append(f"{tag}: близко к тексту фабрики ({share:.0%} совпадающих четвёрок слов)")
            if s.count(brand) > 2:
                warns.append(f"{tag}: «{brand}» {s.count(brand)} раза")
            if s.count("—") + s.count("–") > 3:
                warns.append(f"{tag}: тире {s.count('—') + s.count('–')} раз")
            for sent in re.split(r"(?<=[.!?])\s+", s):
                key = re.sub(re.escape(p["model"]), "X", sent, flags=re.I).strip().lower()
                if len(key.split()) >= 5:
                    sent_use[(l, key)].add(sku)
    rep = [(k, v) for k, v in sent_use.items() if len(v) > 2]
    for (l, key), v in sorted(rep, key=lambda x: -len(x[1]))[:40]:
        warns.append(f"[{l}] одно и то же предложение у {len(v)} товаров: «{key[:90]}»")
    for e in errs:
        print("  ✗", e)
    for w in warns:
        print("  ·", w)
    have = sum(1 for k in live if k in texts and all((texts[k].get(l) or "").strip() for l in LANGS))
    print(f"{brand}: текстов {have} из {len(live)}, ошибок: {len(errs)}, предупреждений: {len(warns)}")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
