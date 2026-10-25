#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Исходники фабрик для магазина: данные сайтов фабрик + скачанные файлы → content/shop/sources/<фабрика>/.

   python3 scripts/shop/factories/make_sources.py <папка с данными> [фабрика ...]

В папке с данными:
  <фабрика>.json          — что собрали краулеры этой папки (olev.json + olev_ds.json, baxter.json, flexform.json,
                            molteni2.json, maxalto.json, delta.json, minotti.json);
  dl-<фабрика>.tsv        — список скачанного: «путь в выгрузке<TAB>адрес» (его же качает dl.sh на Маке);
  manifest-<фабрика>.json — размеры фото и текст PDF (manifest.py на Маке);
  drawings-<фабрика>.json — чертежи, вырезанные из техкарт (drawings.py на Маке).
Пишет:
  site.json  — товары с сайта фабрики (тексты, характеристики, исполнения, ссылки);
  files.json — адрес → файл в выгрузке (+ размеры фото / число страниц PDF), чертежи из техкарт и то, что
               прочитано из текста техкарт (коды исполнений, материалы, отделки).
Тексты PDF целиком в репозиторий не попадают."""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FACTORIES = ["olev", "baxter", "flexform", "molteni", "maxalto", "delta", "minotti"]
SITE_FILE = {"molteni": "molteni2.json"}


def load(work, name, default=None):
    p = os.path.join(work, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def norm_url(u):
    return (u or "").replace("|", "%7C")


def clean(s):
    """Текст с сайта: снять внешние кавычки JSON-строки, лигатуры PDF, лишние пробелы."""
    if not isinstance(s, str):
        return s
    s = s.strip()
    if len(s) > 1 and s[0] == '"' and s[-1] == '"':
        try:
            s = json.loads(s)
        except ValueError:
            s = s[1:-1]
    s = s.replace("ﬁ", "fi").replace("ﬂ", "fl").replace("û", "fi").replace(" ", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def lines_of(t):
    return [l.strip() for l in (t or "").replace("ﬁ", "fi").replace("ﬂ", "fl").replace("û", "fi").split("\n") if l.strip()]


# ---------- что читаем из текста техкарт ----------
IT_LABELS = {"struttura", "imbottitura", "molleggio", "cuscinatura", "piedi", "decoro", "rivestimento", "piano", "base",
             "gambe", "seduta", "schienale", "braccioli", "telaio", "materasso", "cuscini", "finitura", "finiture", "paralume",
             "diffusore", "corpo", "vetro", "sorgente luminosa", "lampadina", "montatura", "cornice", "specchio", "top",
             "basamento", "fusto", "ripiani", "ante", "cassetti", "maniglie", "imbottitura seduta", "imbottitura schienale"}


IT_FIN = re.compile(r"^(resina|metallo|frassino|faggio|legno|pelle|marmo|ottone|montone|noce|rovere|vetro|ferro|acciaio|alluminio|"
                    r"tessuto|velluto|cuoio|bronzo|rame|pietra|travertino|onice|laccat[oa]|tint[oa]|cristallo|ceramica|corda)\b")


def baxter_sheet(texts):
    """Техкарта Baxter: английские строки «Frame: …» (после итальянских) и отделки (пары ит./англ.)."""
    tech, fin = [], []
    for t in texts:
        L = lines_of(t)
        seen_it, eng = False, False
        for i, l in enumerate(L):
            m = re.match(r"^([A-Za-zÀ-ÿ' ]{2,30}):", l)
            if m and m.group(1).strip().lower() in IT_LABELS:
                seen_it = True
                eng = False
                continue
            if m and seen_it:
                eng = True
            if l.upper().startswith("FINITURE DISPONIBILI"):
                eng = False
                rest = []
                for x in L[i + 1:]:
                    if re.search(r"\d+ ?x ?\d+|^[A-Z .'’-]{4,}$", x):
                        break
                    rest.append(x)
                if len(rest) % 2 == 0:
                    fin += [rest[j + 1] for j in range(0, len(rest), 2)]
                break
            if eng and IT_FIN.match(l):                    # дальше — отделки парами «ит. / англ.» без заголовка
                rest = L[i:]
                fin += [rest[j + 1] for j in range(0, len(rest) - 1, 2) if IT_FIN.match(rest[j])]
                break
            if eng:
                tech.append(l)
        if tech or fin:
            break
    return {"tech_en": "\n".join(tech), "finishes_en": list(dict.fromkeys(fin))}


MOLTENI_JUNK = re.compile(r"—$|^\d+—?$|^\d{4}$|Dimensions in (centi|milli)meters|latest product information|^the latest|"
                          r"moltenigroup\.com|^DATASHEET$|^REGISTERED$|^DESIGN$|right to discontinue")


def molteni_sheet(texts):
    tech, fin = [], []
    for t in texts:
        L = lines_of(t)
        if "FINISHES" in L and not fin:
            fin = [l for l in L[:L.index("FINISHES")] if not re.match(r"^\d", l)]
        if "TECHNICAL INFORMATION" in L and not tech:
            i = L.index("TECHNICAL INFORMATION") + 1
            for l in L[i:]:
                if l == "DIMENSIONS":
                    break
                if not MOLTENI_JUNK.search(l):
                    tech.append(l)
    fin = [l for l in fin if not MOLTENI_JUNK.search(l)]
    return {"tech_en": "\n".join(tech), "finishes_en": fin}


def maxalto_sheet(texts):
    tech, on = [], False
    for t in texts:
        for l in lines_of(t):
            if l == "Technical information":
                on = True
                continue
            if l == "Technical drawings":
                on = False
                break
            if on and not re.match(r"^\d+$|^\d+/\d+/\d+$", l):
                tech.append(l)
    # пары «название — материал»
    pairs = [f"{tech[i]}: {tech[i + 1]}" for i in range(0, len(tech) - 1, 2)] if len(tech) % 2 == 0 else tech
    return {"tech_en": "\n".join(pairs)}


def flexform_sheet(texts):
    codes = []
    for t in texts:
        for code, name in re.findall(r"COD\.\s*([0-9A-Z]{5,8})\s+([^\n]+)", t.replace("ﬁ", "fi")):
            if code not in [c["code"] for c in codes]:
                codes.append({"code": code, "name_en": name.strip().capitalize()})
    return {"codes": codes}


def minotti_sheet(texts):
    """Техкарта Minotti: английская колонка описания (manifest.py берёт её отдельно) — абзацы «Structure: …»;
    подписи отделок КАПСОМ (парами ит./англ.) в конце колонки отбрасываем."""
    L = [l for t in texts for l in lines_of(t)]
    while L and re.fullmatch(r"[^a-z]{2,}", L[-1]):
        L.pop()
    out = []
    for l in L:
        head = re.match(r"^[A-Z][A-Za-z /()-]{2,40}:", l) or re.fullmatch(r"[A-Z0-9 ’'&/()-]{4,}", l)
        if not out or head or re.search(r"[.:;]$", out[-1]) and re.match(r"^[A-Z]", l):
            out.append(l)
        elif out[-1].endswith("-") and re.match(r"^[a-z]", l):
            out[-1] = out[-1][:-1] + l
        else:
            out[-1] += " " + l
    return {"tech_en": "\n".join(out)}


SHEET = {"baxter": baxter_sheet, "molteni": molteni_sheet, "maxalto": maxalto_sheet, "flexform": flexform_sheet,
         "minotti": minotti_sheet}


def files_json(work, f):
    rows = [l.rstrip("\n").split("\t") for l in open(os.path.join(work, f"dl-{f}.tsv"), encoding="utf-8") if "\t" in l]
    man = load(work, f"manifest-{f}.json", {"images": {}, "pdfs": {}})
    drw = load(work, f"drawings-{f}.json", {})
    files, sheets, missing = {}, {}, 0
    for dest, url in rows:
        if dest in man["images"] and isinstance(man["images"][dest], list):
            w, h, b = man["images"][dest]
            files[url] = {"file": dest, "width": w, "height": h, "bytes": b}
        elif dest in man["pdfs"] and "pages" in man["pdfs"][dest]:
            p = man["pdfs"][dest]
            files[url] = {"file": dest, "pages": p["pages"], "bytes": p["bytes"]}
            info = SHEET[f](p.get("text_en" if f == "minotti" else "text") or []) if f in SHEET else {}
            info["drawings"] = [d for d in drw.get(dest) or [] if isinstance(d, dict)]
            sheets[dest] = {k: v for k, v in info.items() if v}
        else:
            missing += 1
    return {"files": files, "sheets": sheets}, missing


# ---------- данные сайтов (компактно) ----------
def site_olev(work):
    ds = load(work, "olev_ds.json", {})
    out = []
    for p in load(work, "olev.json"):
        q = {k: p.get(k) for k in ("url", "slug", "title", "category", "types", "place", "designer")}
        q["sections"] = [[clean(h), clean(t)] for h, t in p.get("sections") or []]
        q["images"] = p.get("images") or []
        q["files"] = [{"kind": x["kind"], "url": norm_url(x["url"])} for x in p.get("files") or []]
        q["datasheets"] = [{"url": norm_url(d["url"]), "pages": d.get("pages")} for d in ds.get(p["slug"]) or []]
        out.append(q)
    return out


def site_baxter(work):
    out = []
    for p in load(work, "baxter.json"):
        q = {k: p.get(k) for k in ("url", "url_ru", "slug", "model", "title", "designer", "indoor", "outdoor", "new",
                                   "category_slug", "images", "tech_sheets", "has_2d3d_login", "has_bim_login")}
        q["text_en"], q["text_ru"] = clean(p.get("text_en")), clean(p.get("text_ru"))
        q["versions"] = [{"code": v.get("code"), "name_en": clean(v.get("name_en")), "name_ru": clean(v.get("name_ru")),
                          "dims_cm": v.get("dims_cm"), "materials": v.get("materials") or []} for v in p.get("versions") or []]
        out.append(q)
    return out


def site_flexform(work):
    out = []
    for p in load(work, "flexform.json"):
        q = {k: p.get(k) for k in ("url", "url_ru", "id", "title", "model", "year", "designers", "category", "category_ru",
                                   "collection", "new", "images", "datasheets", "file_2d")}
        for k in ("text_en", "text_ru", "tech_en", "tech_ru"):
            q[k] = clean(p.get(k))
        out.append(q)
    return out


def site_molteni(work):
    out = []
    for p in load(work, "molteni2.json"):
        q = {k: p.get(k) for k in ("url", "slug", "title", "kind_hint", "category", "collection", "designers", "datasheets")}
        q["kind_hint"] = (q["kind_hint"] or "").strip() or None
        q["text_en"] = clean(p.get("text_en"))
        q["images"] = [x["dl"] for x in p.get("images") or []]
        out.append(q)
    return out


def site_maxalto(work):
    out = []
    for p in load(work, "maxalto.json"):
        q = {k: p.get(k) for k in ("url", "slug", "title", "category", "year", "designer", "images", "product_pdf", "dimensions_page")}
        q["text_en"] = clean(p.get("text_en"))
        out.append(q)
    return out


def site_delta(work):
    out = []
    for p in load(work, "delta.json", []):
        if p.get("error"):
            continue
        q = {k: v for k, v in p.items() if k not in ("projects", "variants")}
        q["variants"] = [{"sku": v.get("sku"), "base": v.get("base"), "colour": v.get("colour"),
                          "props": {k: x for k, x in (v.get("props") or {}).items() if k != "Certificates"}} for v in p.get("variants") or []]
        out.append(q)
    return out


def site_minotti(work):
    out = []
    for p in load(work, "minotti.json"):
        q = {k: p.get(k) for k in ("url", "slug", "title", "category", "list_heads", "designers", "place", "new", "images",
                                   "has_2d3d_login")}
        q["tagline"], q["text_en"] = clean(p.get("tagline")), clean(p.get("text_en"))
        q["tech_sheets"] = [s["url"] for s in p.get("tech_sheets") or []]
        q["versions"] = [{"name_en": clean(v.get("name_en")), "drawing": v.get("drawing")} for v in p.get("versions") or []]
        q["arrangements"] = [{"url": a["url"], "items": [clean(x) for x in a.get("items") or []]} for a in p.get("arrangements") or []]
        out.append(q)
    return out


def main():
    work = sys.argv[1]
    which = sys.argv[2:] or FACTORIES
    for f in which:
        if not os.path.exists(os.path.join(work, f"dl-{f}.tsv")):
            print(f"{f}: нет dl-{f}.tsv — пропуск")
            continue
        dst = os.path.join(ROOT, "content/shop/sources", f)
        os.makedirs(dst, exist_ok=True)
        site = globals()[f"site_{f}"](work)
        fj, missing = files_json(work, f)
        json.dump(site, open(os.path.join(dst, "site.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(fj, open(os.path.join(dst, "files.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{f}: товаров {len(site)}, файлов {len(fj['files'])}, техкарт {len(fj['sheets'])}, "
              f"чертежей {sum(len(s.get('drawings') or []) for s in fj['sheets'].values())}"
              + (f", не найдено в выгрузке: {missing}" if missing else ""))


if __name__ == "__main__":
    main()
