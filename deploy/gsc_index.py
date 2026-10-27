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
"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
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
TOKEN_URL = "https://oauth2.googleapis.com/token"
SITES_URL = "https://www.googleapis.com/webmasters/v3/sites"
INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
DAILY = 1800                  # Google разрешает 2000 проверок в день на сайт
RUN_HOUR = 6
RECHECK_NO = 2 * 86400        # не в индексе — проверить снова через 2 дня
RECHECK_YES = 14 * 86400      # в индексе — раз в 2 недели
SUGGEST_AT = 0.6              # доля страниц последней фабрики в индексе — пора выкладывать следующую
PAUSE = 0.15                  # не чаще ~400 запросов в минуту (предел Google — 600)
LANGS = ("ru", "de", "fr", "es")

BOT = None                    # бот студии (ставит lead_service.py) — для предложения выкладывать дальше
_lock = threading.Lock()
_tok = {"v": None, "exp": 0}


# ---------- доступ ----------
def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def have_key():
    return os.path.exists(KEY_FILE)


def token():
    """Токен доступа (на час) по ключу служебного аккаунта: JWT, подписанный RS256 через openssl."""
    if _tok["v"] and time.time() < _tok["exp"] - 120:
        return _tok["v"]
    with open(KEY_FILE, encoding="utf-8") as fh:
        key = json.load(fh)
    now = int(time.time())
    head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claim = _b64(json.dumps({"iss": key["client_email"], "scope": SCOPE, "aud": TOKEN_URL, "iat": now, "exp": now + 3600}).encode())
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
    _tok.update(v=d["access_token"], exp=now + int(d.get("expires_in", 3600)))
    return _tok["v"]


def api(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + token(), "Content-Type": "application/json"})
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
    r = (d.get("inspectionResult") or {}).get("indexStatusResult") or {}
    return {"indexed": r.get("verdict") == "PASS", "state": r.get("coverageState") or "", "verdict": r.get("verdict") or "",
            "crawled": r.get("lastCrawlTime"), "canonical": r.get("googleCanonical") or "", "checked": int(time.time())}


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
    for u in todo(urls, pages, now)[:limit]:
        try:
            pages[u] = inspect(prop, u)
            done += 1
        except urllib.error.HTTPError as e:
            if e.code == 429:
                log(f"индекс Google {host}: дневной предел проверок исчерпан, продолжу завтра")
                break
            if e.code in (401, 403):
                save(host, st)
                return {"host": host, "status": "error", "note": f"Search Console не пускает служебный аккаунт к {host} ({e.code})"}
            log(f"индекс Google {host}: {u} — ответ {e.code}")
        except (OSError, ValueError) as e:
            log(f"индекс Google {host}: {u} — {type(e).__name__}: {e}")
        time.sleep(PAUSE)
    st["runs"][datetime.now(TZ).date().isoformat()] = done
    st["runs"] = dict(sorted(st["runs"].items())[-30:])
    st["checked"] = int(now)
    save(host, st)
    return {"host": host, "status": "ok", "checked": done}


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
    out = {"key": have_key(), "run": last_run(), "daily": DAILY, "sites": []}
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
                             "today": (st.get("runs") or {}).get(datetime.now(TZ).date().isoformat(), 0)})
    return out


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
            _run_note(current=site["host"])
            outs.append(run_site(site, prop, log=log, limit=limit))
        suggest(log=log)
        _run_note(finished=int(time.time()), current=None, sites=outs)
        return outs
    except Exception as e:  # noqa: BLE001
        _run_note(finished=int(time.time()), current=None, error=f"{type(e).__name__}: {e}")
        raise
    finally:
        _lock.release()


_day = {"v": None}


def tick(log=print):
    """Из сервиса заявок раз в минуту: раз в день после 6:00 — проверка в своём потоке."""
    if not have_key():
        return
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
    if argv[:1] == ["--now"]:
        print(json.dumps(run_all(), ensure_ascii=False, indent=1))
    r = last_run()
    if r:
        fmt = lambda t: datetime.fromtimestamp(t, TZ).strftime("%d.%m %H:%M") if t else "—"  # noqa: E731
        print(f"последняя проверка: начата {fmt(r.get('started'))}, " + (f"закончена {fmt(r['finished'])}" if r.get("finished")
              else f"идёт ({r.get('current') or 'начало'})") + (f" · ошибка: {r['error']}" if r.get("error") else ""))
    for site in indexnow.SITES:
        if os.path.exists(state_path(site["host"])):
            st = load(site["host"])
            print(site["host"], "— проверено", datetime.fromtimestamp(st.get("checked", 0), TZ).strftime("%d.%m %H:%M"))
            for name, yes, checked, total in groups(site["host"], st):
                print(f"  {name}: в индексе {yes} из {total}, проверено {checked}")
    print("\n".join(morning_lines()) or "ещё ничего не проверено")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
