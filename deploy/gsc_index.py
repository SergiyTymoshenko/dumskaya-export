#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Взял ли Google страницы в индекс — по Search Console API (URL Inspection), обоих сайтов (решено 27.10.2026).

Раз в день (после 6:00 по Братиславе) сервис заявок проверяет страницы из карт сайтов: dumskaya-design.com целиком,
у каталога dumskaya-home.com — страницы товаров по выложенным фабрикам (адреса — из content/home/frozen.json, его
кладёт на сервер выкладка каталога в ~/dumskaya/home-catalog/) и остальные страницы каталога. Google разрешает
2000 проверок в день на сайт — проверяем до 1800: сначала ещё не проверенные, потом не взятые в индекс (раз в 2 дня),
взятые — раз в 2 недели. Итоги — ~/dumskaya/gsc/<домен>.json.
В утреннее сообщение (site_stats.py) — строка «🔎 В индексе Google: …» по фабрикам. Когда у последней выложенной
фабрики в индексе 60 % страниц и больше, бот один раз предлагает выкладывать следующую.

Доступ — служебный аккаунт Google Cloud (ключ JSON) с ограниченным доступом к обоим сайтам в Search Console:
~/dumskaya/gsc-key.json (chmod 600). Ключа нет — ничего не делает. Подпись запроса за токеном (RS256) — openssl.
Только стандартная библиотека Python 3 и openssl.

На сервере:
   python3 ~/dumskaya/deploy/gsc_index.py --status        — что в индексе по сайтам и фабрикам
   python3 ~/dumskaya/deploy/gsc_index.py --now           — проверить сейчас (не дожидаясь утра)
   python3 ~/dumskaya/deploy/gsc_index.py --url <адрес>   — одна страница: что о ней знает Google
   python3 ~/dumskaya/deploy/gsc_index.py --sitemaps      — отправить карты сайта в Google сейчас (нужен «Полный доступ»)
"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bratislava")
except Exception:  # noqa: BLE001
    TZ = timezone(timedelta(hours=1))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indexnow  # noqa: E402  (карты сайтов и папки сайтов — те же)

APP = os.path.expanduser("~/dumskaya")
KEY_FILE = os.environ.get("GSC_KEY", os.path.join(APP, "gsc-key.json"))
STATE_DIR = os.environ.get("GSC_DIR", os.path.join(APP, "gsc"))
CATALOG_DIR = os.environ.get("HOME_CATALOG_DIR", os.path.join(APP, "home-catalog"))
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
SCOPE_WRITE = "https://www.googleapis.com/auth/webmasters"   # только для отправки карт сайта (нужен «Полный доступ»)
SITEMAP_EVERY = 3600          # раз в час: изменились ли карты сайта после выкладки
SITEMAP_RESUBMIT = 7 * 86400  # и раз в неделю — повторно на всякий случай
TOKEN_URL = "https://oauth2.googleapis.com/token"
SITES_URL = "https://www.googleapis.com/webmasters/v3/sites"
INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
DAILY = 1800                  # Google разрешает 2000 проверок в день на сайт
RUN_HOUR = 6
RECHECK_NO = 2 * 86400        # не в индексе — проверить снова через 2 дня
RECHECK_YES = 14 * 86400      # в индексе — раз в 2 недели
SUGGEST_AT = 0.6              # доля страниц последней фабрики в индексе — пора выкладывать следующую
WORKERS = 4                   # проверок одновременно: Google отвечает медленно, предел — 600 в минуту
LANGS = ("ru", "de", "fr", "es")

BOT = None                    # бот студии (ставит lead_service.py) — для предложения выкладывать дальше
_lock = threading.Lock()
_tok = {}


# ---------- доступ ----------
def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def have_key():
    return os.path.exists(KEY_FILE)


def token(scope=SCOPE):
    """Токен доступа (на час) по ключу служебного аккаунта: JWT, подписанный RS256 через openssl."""
    t = _tok.get(scope)
    if t and time.time() < t["exp"] - 120:
        return t["v"]
    with open(KEY_FILE, encoding="utf-8") as fh:
        key = json.load(fh)
    now = int(time.time())
    head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claim = _b64(json.dumps({"iss": key["client_email"], "scope": scope, "aud": TOKEN_URL, "iat": now, "exp": now + 3600}).encode())
    msg = f"{head}.{claim}".encode()
    os.makedirs(STATE_DIR, exist_ok=True)
    fd, pem = tempfile.mkstemp(dir=STATE_DIR, suffix=".pem")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(key["private_key"])
        os.chmod(pem, 0o600)
        sig = subprocess.run(["openssl", "dgst", "-sha256", "-sign", pem], input=msg, capture_output=True, check=True).stdout
    finally:
        os.remove(pem)
    body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                   "assertion": f"{head}.{claim}.{_b64(sig)}"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=body), timeout=30) as r:
        d = json.load(r)
    _tok[scope] = {"v": d["access_token"], "exp": now + int(d.get("expires_in", 3600))}
    return d["access_token"]


def api(url, body=None, method=None, scope=SCOPE):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Authorization": "Bearer " + token(scope), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def property_for(host, props):
    """Сайт в Search Console для домена: «sc-domain:домен» или «https://домен/» — какой открыт служебному аккаунту."""
    for p in (f"sc-domain:{host}", f"https://{host}/", f"https://www.{host}/"):
        if p in props:
            return p
    return None


def inspect(prop, url):
    """{indexed, state, verdict, crawled, canonical} по одной странице."""
    d = api(INSPECT_URL, {"inspectionUrl": url, "siteUrl": prop, "languageCode": "ru"})
    ir = d.get("inspectionResult") or {}
    r = ir.get("indexStatusResult") or {}
    rich = []                                          # расширенные результаты: что Google нашёл в разметке и с какими проблемами
    for item in (ir.get("richResultsResult") or {}).get("detectedItems") or []:
        issues = [i.get("issueMessage") for x in item.get("items") or [] for i in x.get("issues") or []]
        rich.append({"type": item.get("richResultType") or "", "issues": sorted(set(filter(None, issues)))[:5]})
    return {"indexed": r.get("verdict") == "PASS", "state": r.get("coverageState") or "", "verdict": r.get("verdict") or "",
            "crawled": r.get("lastCrawlTime"), "canonical": r.get("googleCanonical") or "", "checked": int(time.time()),
            "fetch": r.get("pageFetchState") or "", "robots": r.get("robotsTxtState") or "", "rich": rich}


# ---------- какие страницы и чьи ----------
def factories():
    """{адрес страницы без домена: фабрика} — страницы товаров выложенных фабрик и [(фабрика, с какого дня)]."""
    try:
        frozen = json.load(open(os.path.join(CATALOG_DIR, "frozen.json"), encoding="utf-8"))
        pub = json.load(open(os.path.join(CATALOG_DIR, "publish.json"), encoding="utf-8")).get("factories") or {}
    except (OSError, ValueError):
        return {}, []
    out = {}
    for x in frozen.values():
        for p in (x.get("path") or {}).values():
            seg = [s for s in p.strip("/").split("/") if s]
            brand = seg[1] if seg and seg[0] in LANGS and len(seg) > 1 else (seg[0] if seg else "")
            out[p.rstrip("/") or "/"] = brand
    order = sorted(((f, v.get("since") or "") for f, v in pub.items()), key=lambda x: x[1])
    return out, order


def state_path(host):
    return os.path.join(STATE_DIR, f"{host}.json")


def load(host):
    try:
        with open(state_path(host), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"pages": {}, "suggested": [], "runs": {}}


def save(host, st):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(state_path(host) + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False)
    os.replace(state_path(host) + ".tmp", state_path(host))


def todo(urls, pages, now):
    """Очередь проверки: новые → не в индексе (раз в 2 дня) → в индексе (раз в 2 недели), старые проверки — раньше."""
    def due(u):
        p = pages.get(u)
        if not p:
            return (0, 0)
        age = now - p.get("checked", 0)
        if not p.get("indexed") and age >= RECHECK_NO:
            return (1, p.get("checked", 0))
        if p.get("indexed") and age >= RECHECK_YES:
            return (2, p.get("checked", 0))
        return None
    q = [(due(u), u) for u in urls]
    return [u for d, u in sorted(x for x in q if x[0] is not None)]


def run_site(site, prop, log=print, limit=DAILY):
    host, root = site["host"], site["root"]
    urls = indexnow.sitemap_urls(root, host)
    if not urls:
        return {"host": host, "status": "wait", "note": "в папке сайта нет sitemap.xml"}
    st = load(host)
    pages, now, done = st["pages"], time.time(), 0
    for u in [u for u in list(pages) if u not in set(urls)]:
        del pages[u]                                  # страницы больше нет в карте сайта
    queue = todo(urls, pages, now)[:limit]
    errors, stop, i = 0, None, 0
    # Google отвечает по одной странице 5–15 секунд — проверяем по WORKERS сразу (предел Google — 600 в минуту)
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(inspect, prop, u): u for u in queue}
        for fut in as_completed(futs):
            u, i = futs[fut], i + 1
            if stop:
                fut.cancel()
                continue
            try:
                pages[u] = fut.result()
                done += 1
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    stop = "limit"
                    log(f"индекс Google {host}: дневной предел проверок исчерпан, продолжу завтра")
                elif e.code in (401, 403):
                    stop = "denied"
                else:
                    log(f"индекс Google {host}: {u} — ответ {e.code}")
                    errors += 1
            except (OSError, ValueError) as e:
                log(f"индекс Google {host}: {u} — {type(e).__name__}: {e}")
                errors += 1
            if i % 25 == 0:                           # ход проверки — виден в «Графиках» и --status, не только в конце
                save(host, st)
                _run_note(progress={"host": host, "done": i, "todo": len(queue), "errors": errors})
        if stop:
            for f in futs:
                f.cancel()
    if stop == "denied":
        save(host, st)
        return {"host": host, "status": "error", "note": f"Search Console не пускает служебный аккаунт к {host}"}
    day = datetime.now(TZ).date().isoformat()
    st["runs"][day] = done
    st["runs"] = dict(sorted(st["runs"].items())[-30:])
    st["checked"] = int(now)
    # снимок дня: в индексе / проверено / всего — по сайту и фабрикам (прогресс индексации по дням), хранится бессрочно
    st.setdefault("history", {})[day] = {n: [y, c, t] for n, y, c, t in groups(host, st)}
    save(host, st)
    return {"host": host, "status": "ok", "checked": done, "errors": errors}


# ---------- поиск Google: показы, клики, запросы, страницы, страны, устройства; карты сайта ----------
SEARCH_DAYS = 90              # Google хранит 16 месяцев; данные за последние 2–3 дня ещё неполные


def search_path(host):
    return os.path.join(STATE_DIR, f"{host}-search.json")


def _sq(prop, body):
    url = f"https://www.googleapis.com/webmasters/v3/sites/{urllib.parse.quote(prop, safe='')}/searchAnalytics/query"
    return api(url, body).get("rows") or []


def fetch_search(prop, host, log=print):
    """Статистика поиска Google за 90 дней (по дням) и за 28 дней (запросы, страницы, страны, устройства) + карты сайта."""
    today = datetime.now(TZ).date()
    end = (today - timedelta(days=1)).isoformat()
    d90, d28 = (today - timedelta(days=SEARCH_DAYS)).isoformat(), (today - timedelta(days=28)).isoformat()
    row = lambda r: {"keys": r.get("keys") or [], "clicks": r.get("clicks", 0), "impressions": r.get("impressions", 0),  # noqa: E731
                     "ctr": r.get("ctr", 0), "position": r.get("position", 0)}
    p56 = (today - timedelta(days=56)).isoformat()
    p29 = (today - timedelta(days=29)).isoformat()
    out = {"fetched": int(time.time()), "start": d90, "end": end}
    jobs = [("dates", ["date"], d90, end, 1000, None), ("queries", ["query"], d28, end, 1000, None),
            ("pages", ["page"], d28, end, 1000, None), ("countries", ["country"], d28, end, 100, None),
            ("devices", ["device"], d28, end, 10, None), ("totals", [], d28, end, 1, None),
            ("prev_totals", [], p56, p29, 1, None),                           # прошлые 28 дней — для сравнения
            ("query_pages", ["query", "page"], d28, end, 500, None),         # какая страница по какому запросу
            ("appearance", ["searchAppearance"], d28, end, 50, None)]
    for t in ("image", "video", "discover", "news"):                      # Картинки, Видео, Discover, Новости
        jobs.append((f"type_{t}", [], d28, end, 1, t))
    jobs.append(("image_pages", ["page"], d28, end, 200, "image"))
    for name, dims, start, stop, limit, typ in jobs:
        body = {"startDate": start, "endDate": stop, "dimensions": dims, "rowLimit": limit, "dataState": "all"}
        if typ:
            body["type"] = typ
        try:
            out[name] = [row(r) for r in _sq(prop, body)]
        except urllib.error.HTTPError as e:
            if e.code != 400:                          # 400 — такого типа поиска у сайта нет (например, news)
                log(f"индекс Google {host}: статистика поиска ({name}) — ответ {e.code}")
            out[name] = []
    try:
        sm = api(f"https://www.googleapis.com/webmasters/v3/sites/{urllib.parse.quote(prop, safe='')}/sitemaps").get("sitemap") or []
        out["sitemaps"] = [{"path": x.get("path"), "submitted": x.get("lastSubmitted"), "downloaded": x.get("lastDownloaded"),
                            "pending": bool(x.get("isPending")), "warnings": int(x.get("warnings") or 0), "errors": int(x.get("errors") or 0),
                            "urls": sum(int(c.get("submitted") or 0) for c in x.get("contents") or [])} for x in sm]
    except urllib.error.HTTPError as e:
        log(f"индекс Google {host}: карты сайта — ответ {e.code}")
        out["sitemaps"] = []
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(search_path(host) + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    os.replace(search_path(host) + ".tmp", search_path(host))
    return out


def load_search(host):
    try:
        return json.load(open(search_path(host), encoding="utf-8"))
    except (OSError, ValueError):
        return None


def groups(host, st=None):
    """Итог по сайту: [(подпись, в индексе, проверено, всего в карте сайта)] — у каталога по фабрикам."""
    st = st or load(host)
    site = next(s for s in indexnow.SITES if s["host"] == host)
    urls = indexnow.sitemap_urls(site["root"], host)
    pages = st["pages"]
    path = lambda u: urllib.parse.urlsplit(u).path.rstrip("/") or "/"  # noqa: E731
    if host != "dumskaya-home.com":
        return [("Сайт студии", sum(1 for u in urls if (pages.get(u) or {}).get("indexed")), sum(1 for u in urls if u in pages), len(urls))]
    fmap, order = factories()
    buckets = {}
    for u in urls:
        f = fmap.get(path(u)) or "_other"
        b = buckets.setdefault(f, [0, 0, 0])
        b[2] += 1
        if u in pages:
            b[1] += 1
            b[0] += bool(pages[u].get("indexed"))
    names = {f: f.capitalize() for f in buckets}
    names["_other"] = "разделы магазина"
    keys = [f for f, _ in order if f in buckets] + (["_other"] if "_other" in buckets else [])
    return [(names[f], *buckets[f]) for f in keys]


def morning_lines():
    """Строка в утреннее сообщение (site_stats.py) или []: ключа нет или ещё ничего не проверено."""
    if not have_key():
        return []
    parts = []
    for site in indexnow.SITES:
        if not os.path.exists(state_path(site["host"])):
            continue
        for name, yes, checked, total in groups(site["host"]):
            if checked:
                parts.append(f"{name} {yes} из {total}" + (f" (проверено {checked})" if checked < total else ""))
    return ["🔎 В индексе Google: " + " · ".join(parts)] if parts else []


STATE_RU = {
    "Submitted and indexed": "в индексе",
    "Indexed, not submitted in sitemap": "в индексе, но не из карты сайта",
    "Crawled - currently not indexed": "просканирована, но не взята в индекс",
    "Discovered - currently not indexed": "известна, Google ещё не сканировал",
    "URL is unknown to Google": "Google ещё не знает страницу",
    "Duplicate, Google chose different canonical than user": "дубль: Google выбрал другой основной адрес",
    "Duplicate without user-selected canonical": "дубль без основного адреса",
    "Alternate page with proper canonical tag": "другая версия, основной адрес указан",
    "Excluded by ‘noindex’ tag": "закрыта от индекса (noindex)",
    "Page with redirect": "переадресация",
    "Not found (404)": "не найдена (404)",
    "Soft 404": "похожа на пустую страницу (soft 404)",
    "Blocked by robots.txt": "закрыта в robots.txt",
    "Server error (5xx)": "ошибка сервера",
}


def state_ru(s):
    return STATE_RU.get(s) or STATE_RU.get((s or "").replace("'", "‘")) or s or "нет сведений"


def web_data(site="all"):
    """Данные карточки «Индекс Google» в «Графиках»: по сайту и фабрикам, причины, страницы не в индексе."""
    hosts = {"studio": ["dumskaya-design.com"], "home": ["dumskaya-home.com"]}.get(site, [s["host"] for s in indexnow.SITES])
    out = {"key": have_key(), "run": last_run(), "daily": DAILY, "sites": [], "submitted": _sm_state()}
    if not out["key"]:
        return out
    fmap, _ = factories()
    for host in hosts:
        if not os.path.exists(state_path(host)):
            continue
        st = load(host)
        pages = st["pages"]
        reasons = Counter(state_ru(p.get("state")) for p in pages.values() if not p.get("indexed"))
        miss = []
        for u, p in sorted(pages.items()):
            if p.get("indexed"):
                continue
            path = urllib.parse.urlsplit(u).path.rstrip("/") or "/"
            miss.append({"url": u, "path": path, "group": (fmap.get(path) or "").capitalize(), "state": state_ru(p.get("state")),
                         "crawled": (p.get("crawled") or "")[:10] or None, "checked": p.get("checked")})
        out["sites"].append({"host": host, "checked": st.get("checked"),
                             "groups": [{"name": n, "yes": y, "checked": c, "total": t} for n, y, c, t in groups(host, st)],
                             "reasons": reasons.most_common(), "missing": miss[:80], "missing_total": len(miss),
                             "today": (st.get("runs") or {}).get(datetime.now(TZ).date().isoformat(), 0),
                             "history": dict(sorted((st.get("history") or {}).items())[-120:]),
                             "rich": rich_view(pages),
                             "search": search_view(host, fmap)})
    for host in hosts:                                # статистика поиска есть, а проверка страниц ещё не дошла до сайта
        if not any(x["host"] == host for x in out["sites"]) and load_search(host):
            out["sites"].append({"host": host, "checked": None, "groups": [], "reasons": [], "missing": [], "missing_total": 0,
                                 "today": 0, "history": {}, "search": search_view(host, fmap)})
    return out


COUNTRY_RU = {"svk": "Словакия", "aut": "Австрия", "deu": "Германия", "cze": "Чехия", "ukr": "Украина", "pol": "Польша",
              "hun": "Венгрия", "ita": "Италия", "usa": "США", "gbr": "Великобритания", "fra": "Франция", "esp": "Испания",
              "che": "Швейцария", "nld": "Нидерланды", "bel": "Бельгия", "isr": "Израиль", "are": "ОАЭ", "kaz": "Казахстан",
              "rus": "Россия", "blr": "Беларусь", "mda": "Молдова", "rou": "Румыния", "bgr": "Болгария", "srb": "Сербия",
              "hrv": "Хорватия", "svn": "Словения", "ltu": "Литва", "lva": "Латвия", "est": "Эстония", "geo": "Грузия",
              "arm": "Армения", "aze": "Азербайджан", "tur": "Турция", "cyp": "Кипр", "grc": "Греция", "prt": "Португалия",
              "swe": "Швеция", "nor": "Норвегия", "dnk": "Дания", "fin": "Финляндия", "irl": "Ирландия", "can": "Канада",
              "mco": "Монако", "lux": "Люксембург", "sau": "Саудовская Аравия", "qat": "Катар", "ind": "Индия", "chn": "Китай"}
DEVICE_RU = {"MOBILE": "телефон", "DESKTOP": "компьютер", "TABLET": "планшет"}


def search_view(host, fmap=None):
    """Статистика поиска для «Графиков»: итоги 28 дней, по дням (90), запросы, страницы, страны, устройства, по фабрикам."""
    d = load_search(host)
    if not d:
        return None
    path = lambda u: urllib.parse.urlsplit(u).path.rstrip("/") or "/"  # noqa: E731
    tot = (d.get("totals") or [{}])[0] if d.get("totals") else {"clicks": 0, "impressions": 0, "ctr": 0, "position": 0}
    by_f = {}
    for r in d.get("pages") or []:
        f = ((fmap or {}).get(path(r["keys"][0])) or ("" if host != "dumskaya-home.com" else "_other"))
        if f:
            b = by_f.setdefault(f, [0, 0])
            b[0] += r["clicks"]
            b[1] += r["impressions"]
    fn = lambda f: "разделы магазина" if f == "_other" else f.capitalize()  # noqa: E731
    return {"fetched": d.get("fetched"), "start": d.get("start"), "end": d.get("end"),
            "totals": {k: tot.get(k, 0) for k in ("clicks", "impressions", "ctr", "position")},
            "dates": [{"date": r["keys"][0], "clicks": r["clicks"], "impressions": r["impressions"], "position": round(r["position"], 1)}
                      for r in d.get("dates") or []],
            "queries": [[r["keys"][0], r["clicks"], r["impressions"], round(r["position"], 1)] for r in (d.get("queries") or [])[:40]],
            "pages": [[path(r["keys"][0]), r["clicks"], r["impressions"], round(r["position"], 1)] for r in (d.get("pages") or [])[:30]],
            "countries": [[COUNTRY_RU.get(r["keys"][0], r["keys"][0].upper()), r["clicks"], r["impressions"]] for r in (d.get("countries") or [])[:15]],
            "devices": [[DEVICE_RU.get(r["keys"][0], r["keys"][0].lower()), r["clicks"], r["impressions"]] for r in d.get("devices") or []],
            "factories": sorted([[fn(f), c, i] for f, (c, i) in by_f.items()], key=lambda x: -x[2]),
            "sitemaps": d.get("sitemaps") or [],
            "prev": {k: ((d.get("prev_totals") or [{}])[0] or {}).get(k, 0) for k in ("clicks", "impressions", "ctr", "position")}
            if d.get("prev_totals") else None,
            "types": [[n, (d.get(f"type_{k}") or [{}])[0].get("clicks", 0) if d.get(f"type_{k}") else 0,
                       (d.get(f"type_{k}") or [{}])[0].get("impressions", 0) if d.get(f"type_{k}") else 0]
                      for k, n in (("image", "Картинки"), ("video", "Видео"), ("discover", "Discover"), ("news", "Новости"))]
            + [["Обычный поиск", tot.get("clicks", 0), tot.get("impressions", 0)]],
            "langs": langs_of(d.get("pages") or [], path),
            "all_pages": [[path(r["keys"][0]), r["clicks"], r["impressions"], round(r["ctr"] * 100, 1), round(r["position"], 1)]
                          for r in (d.get("pages") or [])[:300]],
            "image_pages": [[path(r["keys"][0]), r["clicks"], r["impressions"]] for r in (d.get("image_pages") or [])[:30]],
            "query_pages": [[r["keys"][0], path(r["keys"][1]), r["clicks"], r["impressions"], round(r["position"], 1)]
                            for r in (d.get("query_pages") or [])[:150]],
            "appearance": [[APPEAR_RU.get(r["keys"][0], r["keys"][0]), r["clicks"], r["impressions"]] for r in d.get("appearance") or []],
            "queries_all": len(d.get("queries") or [])}


APPEAR_RU = {"BREADCRUMB": "хлебные крошки", "IMAGE_PACK": "блок картинок", "TRANSLATED_RESULT": "переведённый результат",
             "VIDEO": "видео", "FAQ_RICH_RESULT": "FAQ", "REVIEW_SNIPPET": "отзывы", "SITELINKS": "быстрые ссылки",
             "MERCHANT_LISTINGS": "товары (Merchant)", "PRODUCT_SNIPPETS": "сведения о товаре", "AMP_ARTICLE": "AMP"}


def langs_of(rows, path):
    """Показы и клики по языку страницы (первая часть адреса: /ru/…, /de/…; без неё — основной язык сайта)."""
    out = {}
    for r in rows:
        seg = path(r["keys"][0]).strip("/").split("/")[0]
        lang = seg.upper() if seg in ("ru", "ua", "uk", "en", "sk", "de", "fr", "es") else "основной"
        b = out.setdefault(lang, [0, 0])
        b[0] += r["clicks"]
        b[1] += r["impressions"]
    return sorted([[k, c, i] for k, (c, i) in out.items()], key=lambda x: -x[2])


def rich_view(pages):
    """Расширенные результаты по проверенным страницам: тип разметки → страниц, с проблемами, частые проблемы."""
    agg = {}
    for p in pages.values():
        for r in p.get("rich") or []:
            a = agg.setdefault(r["type"], [0, 0, Counter()])
            a[0] += 1
            if r["issues"]:
                a[1] += 1
                a[2].update(r["issues"])
    return [{"type": RICH_RU.get(t, t), "pages": n, "with_issues": bad, "issues": c.most_common(3)}
            for t, (n, bad, c) in sorted(agg.items(), key=lambda kv: -kv[1][0])]


RICH_RU = {"Breadcrumbs": "Хлебные крошки", "Image metadata": "Метаданные изображений", "Product snippets": "Сведения о товаре",
           "Merchant listings": "Товары (Merchant)", "FAQ": "FAQ", "Organization": "Организация", "Videos": "Видео",
           "Review snippets": "Отзывы", "Local business": "Местная организация", "Article": "Статья"}


def suggest(log=print):
    """Последняя выложенная фабрика в индексе на 60 % и больше — один раз предложить выкладывать следующую."""
    _, order = factories()
    if not order:
        return None
    last = order[-1][0]
    st = load("dumskaya-home.com")
    if last in st.get("suggested", []):
        return None
    g = {n.lower(): (yes, total) for n, yes, _, total in groups("dumskaya-home.com", st)}
    yes, total = g.get(last, (0, 0))
    if not total or yes / total < SUGGEST_AT:
        return None
    text = (f"🔎 Google взял в индекс {round(yes / total * 100)}% страниц {last.capitalize()} ({yes} из {total}). "
            "Можно выкладывать следующую фабрику — напишите Claude, какую: он подготовит тексты и выкладку.")
    st.setdefault("suggested", []).append(last)
    save("dumskaya-home.com", st)
    if BOT is not None:
        BOT.notify(text, roles=("owner",))
    log(text)
    return text


RUN_FILE = os.path.join(STATE_DIR, "run.json")


def _run_note(**kw):
    """Как прошла последняя проверка (для --status и «Графиков»): начало, конец, итоги по сайтам или ошибка."""
    try:
        old = json.load(open(RUN_FILE, encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    old.update(kw)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(RUN_FILE + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(old, fh, ensure_ascii=False)
    os.replace(RUN_FILE + ".tmp", RUN_FILE)


def last_run():
    try:
        return json.load(open(RUN_FILE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run_all(log=print, limit=DAILY):
    if not have_key() or not _lock.acquire(blocking=False):
        return None
    try:
        _run_note(started=int(time.time()), finished=None, error=None, sites=None)
        try:
            props = {x["siteUrl"] for x in (api(SITES_URL).get("siteEntry") or [])}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            note = ("Search Console API не включён в проекте Google Cloud" if "has not been used" in body or "disabled" in body
                    else f"Search Console ответил {e.code}: {body}")
            log(f"индекс Google: {note}")
            _run_note(finished=int(time.time()), error=note)
            return None
        except (urllib.error.URLError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as e:
            log(f"индекс Google: Search Console не ответил — {type(e).__name__}: {e}")
            _run_note(finished=int(time.time()), error=f"Search Console не ответил — {type(e).__name__}: {e}")
            return None
        if not props:
            note = "служебный аккаунт пока не добавлен ни к одному сайту в Search Console"
            _run_note(finished=int(time.time()), error=note)
            log(f"индекс Google: {note}")
            return None
        outs = []
        for site in indexnow.SITES:
            if indexnow.read_mode(site["mode"]) != "live":
                continue
            prop = property_for(site["host"], props)
            if not prop:
                outs.append({"host": site["host"], "status": "error", "note": "служебный аккаунт не добавлен в Search Console этого сайта"})
                continue
            _run_note(current=site["host"], progress=None)
            try:                                      # статистика поиска — отдельный лимит Google, быстро
                fetch_search(prop, site["host"], log=log)
            except Exception as e:  # noqa: BLE001
                log(f"индекс Google {site['host']}: статистика поиска не получена — {type(e).__name__}: {e}")
            outs.append(run_site(site, prop, log=log, limit=limit))
        suggest(log=log)
        _run_note(finished=int(time.time()), current=None, progress=None, sites=outs)
        return outs
    except Exception as e:  # noqa: BLE001
        _run_note(finished=int(time.time()), current=None, error=f"{type(e).__name__}: {e}")
        raise
    finally:
        _lock.release()


# ---------- карты сайта: изменились после выкладки — отправить в Google ----------
SM_FILE = os.path.join(STATE_DIR, "sitemaps.json")


def _sm_state():
    try:
        return json.load(open(SM_FILE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def sitemap_hash(root):
    """Отпечаток всех карт сайта в папке (sitemap.xml и файлы его индекса): меняется, когда выкладка их изменила."""
    import hashlib
    h = hashlib.sha256()
    for f in sorted(x for x in os.listdir(root) if re.fullmatch(r"sitemap[\w-]*\.xml", x)) if os.path.isdir(root) else []:
        with open(os.path.join(root, f), "rb") as fh:
            h.update(f.encode() + b"\0" + fh.read())
    return h.hexdigest()


def submit_sitemaps(log=print, force=False):
    """Отправить карты сайта, если они изменились (или прошла неделя). Нужен «Полный доступ» служебного аккаунта."""
    st, now = _sm_state(), time.time()
    props = None
    for site in indexnow.SITES:
        host, root = site["host"], site["root"]
        if indexnow.read_mode(site["mode"]) != "live" or not os.path.exists(os.path.join(root, "sitemap.xml")):
            continue
        h = sitemap_hash(root)
        rec = st.get(host) or {}
        if not force and rec.get("hash") == h and now - rec.get("sent", 0) < SITEMAP_RESUBMIT:
            continue
        if props is None:
            props = {x["siteUrl"] for x in (api(SITES_URL).get("siteEntry") or [])}
        prop = property_for(host, props)
        if not prop:
            st[host] = dict(rec, note="служебный аккаунт не добавлен в Search Console этого сайта", tried=int(now))
            continue
        feed = f"https://{host}/sitemap.xml"
        try:
            api(f"https://www.googleapis.com/webmasters/v3/sites/{urllib.parse.quote(prop, safe='')}/sitemaps/"
                f"{urllib.parse.quote(feed, safe='')}", method="PUT", scope=SCOPE_WRITE)
            st[host] = {"hash": h, "sent": int(now), "feed": feed, "note": ""}
            log(f"индекс Google {host}: карта сайта отправлена в Google")
        except urllib.error.HTTPError as e:
            note = ("нужен «Полный доступ» служебного аккаунта в Search Console (сейчас «Ограниченный»)" if e.code == 403
                    else f"Google ответил {e.code}")
            st[host] = dict(rec, note=note, tried=int(now))
            log(f"индекс Google {host}: карта сайта не отправлена — {note}")
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(SM_FILE + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False)
    os.replace(SM_FILE + ".tmp", SM_FILE)
    return st


_day = {"v": None}
_sm = {"last": 0.0}


def tick(log=print):
    """Из сервиса заявок раз в минуту: раз в час — карты сайта (изменились — отправить), раз в день после 6:00 —
    проверка страниц и статистика поиска; всё в своих потоках."""
    if not have_key():
        return
    if time.time() - _sm["last"] >= SITEMAP_EVERY:
        _sm["last"] = time.time()

        def sm():
            try:
                submit_sitemaps(log=log)
            except Exception as e:  # noqa: BLE001
                log(f"индекс Google: карты сайта — ошибка {type(e).__name__}: {e}")
        threading.Thread(target=sm, name="gsc-sitemaps", daemon=True).start()
    now = datetime.now(TZ)
    if now.hour < RUN_HOUR or _day["v"] == now.date() or _lock.locked():
        return
    _day["v"] = now.date()
    threading.Thread(target=run_all, kwargs={"log": log}, name="gsc-index", daemon=True).start()


def main(argv):
    if not have_key():
        print(f"нет ключа {KEY_FILE} — проверка индекса Google выключена")
        return 1
    if argv[:1] == ["--url"] and len(argv) > 1:
        props = {x["siteUrl"] for x in (api(SITES_URL).get("siteEntry") or [])}
        host = urllib.parse.urlsplit(argv[1]).hostname or ""
        prop = property_for(host.removeprefix("www."), props)
        print(json.dumps(inspect(prop, argv[1]) if prop else {"error": f"нет доступа к {host}", "sites": sorted(props)},
                         ensure_ascii=False, indent=1))
        return 0
    if argv[:1] == ["--sitemaps"]:
        print(json.dumps(submit_sitemaps(force=True), ensure_ascii=False, indent=1))
        return 0
    if argv[:1] == ["--now"]:
        print(json.dumps(run_all(), ensure_ascii=False, indent=1))
    r = last_run()
    if r:
        fmt = lambda t: datetime.fromtimestamp(t, TZ).strftime("%d.%m %H:%M") if t else "—"  # noqa: E731
        print(f"последняя проверка: начата {fmt(r.get('started'))}, " + (f"закончена {fmt(r['finished'])}" if r.get("finished")
              else f"идёт ({r.get('current') or 'начало'})") + (f" · ошибка: {r['error']}" if r.get("error") else ""))
        pg = r.get("progress")
        if pg and not r.get("finished"):
            print(f"  сейчас: {pg['host']} — проверено {pg['done']} из {pg['todo']}, ошибок {pg['errors']}")
    for site in indexnow.SITES:
        sv = search_view(site["host"])
        if sv:
            t = sv["totals"]
            print(f"{site['host']} — поиск Google за 28 дней: показов {t['impressions']}, кликов {t['clicks']}, "
                  f"средняя позиция {round(t['position'], 1) if t['position'] else '—'}; карт сайта {len(sv['sitemaps'])}")
    for site in indexnow.SITES:
        if os.path.exists(state_path(site["host"])):
            st = load(site["host"])
            print(site["host"], "— проверено", datetime.fromtimestamp(st["checked"], TZ).strftime("%d.%m %H:%M") if st.get("checked") else "— (идёт первая проверка)")
            for name, yes, checked, total in groups(site["host"], st):
                print(f"  {name}: в индексе {yes} из {total}, проверено {checked}")
    print("\n".join(morning_lines()) or "ещё ничего не проверено")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
