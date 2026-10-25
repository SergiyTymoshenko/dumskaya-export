#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IndexNow — сами сообщаем поисковикам о новых, изменённых и удалённых страницах сайтов (решено 25.10.2026).

Раз в час (и через минуту после каждого перезапуска сервиса заявок — он и запускает эту проверку) для каждого сайта:
  1) берёт список страниц из sitemap.xml в папке сайта на сервере — то, что выложено с Мака;
  2) у каждой страницы считает отпечаток содержимого: заголовок, описание, канонический адрес, языковые версии,
     разметка JSON-LD и основная часть страницы (<main>). Шапка, меню, подвал, оформление и скрипты не считаются —
     правка дизайна или меню не отправляет заново все страницы;
  3) сравнивает с тем, что уже отправлено (~/dumskaya/indexnow/<домен>.json), и отправляет новые, изменённые и пропавшие
     из карты сайта адреса в Bing, Яндекс и Seznam. Они передают адреса остальным участникам IndexNow (Naver, Yep,
     Internet Archive, Amazon). Google IndexNow не поддерживает — для него карта сайта и Search Console, как раньше.

Отправляем, только если сайт открыт на домене (режим live в ~/dumskaya/mode или home-mode) и ключ
https://<домен>/<ключ>.txt отвечает самим ключом. Поэтому dumskaya-home.com начнёт отправлять сам, когда каталог
откроется на домене, а пока он в режиме просмотра — ждёт. В первый раз отправляются все страницы сайта.
Ключ — файл public/<ключ>.txt (сайт студии) и home/public/<ключ>.txt (каталог). Ключ не секрет: он открыт на сайте.
Не принял ни один поисковик — повтор через час; если не получается больше суток — одно сообщение разработчику в бот.
Посмотреть — «Графики» → «Сервер и ИИ», карточка «Поисковики».

На сервере (ssh eurox):
   python3 ~/dumskaya/deploy/indexnow.py --status    — что и когда отправлено
   python3 ~/dumskaya/deploy/indexnow.py --dry-run   — что отправилось бы сейчас (ничего не отправляет и не меняет)
   python3 ~/dumskaya/deploy/indexnow.py --now       — проверить и отправить сейчас, не дожидаясь часа
   python3 ~/dumskaya/deploy/indexnow.py --now --all — отправить заново все страницы (обычно не нужно)
Только стандартная библиотека Python 3."""
import fcntl
import hashlib
import html
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bratislava")
except Exception:  # noqa: BLE001  pragma: no cover
    TZ = timezone(timedelta(hours=1))

APP = os.path.expanduser("~/dumskaya")
STATE_DIR = os.environ.get("INDEXNOW_DIR", os.path.join(APP, "indexnow"))
SITES = [
    {"host": "dumskaya-design.com", "name": "Сайт студии", "mode": os.path.join(APP, "mode"),
     "root": os.environ.get("SITE_DIR", "/var/www/dumskaya/site")},
    {"host": "dumskaya-home.com", "name": "Каталог DUMSKAYA HOME", "mode": os.path.join(APP, "home-mode"),
     "root": os.environ.get("HOME_SITE_DIR", "/var/www/dumskaya-home/site")},
]
# адреса из https://www.indexnow.org/searchengines.json (25.10.2026); каждый передаёт адреса остальным участникам
ENGINES = [("Bing", "https://www.bing.com/indexnow"), ("Яндекс", "https://yandex.com/indexnow"),
           ("Seznam", "https://search.seznam.cz/indexnow")]
EVERY = 3600                 # раз в час
BATCH = 10000                # больше адресов в одном запросе протокол не принимает
ALERT_AFTER = 24 * 3600      # не получается сутки — сообщение разработчику (один раз, до первой удачной отправки)
MIN_PAGES = 10               # карта сайта короче или без главной — похоже на выкладку в процессе: пропускаем этот час
TIMEOUT = 30
UA = "DUMSKAYA-IndexNow/1.0 (+https://dumskaya-design.com)"
KEY_RE = re.compile(r"^[0-9a-f]{32}\.txt$")

BOT = None                   # бот студии (ставит lead_service.py) — для сообщения об ошибке
_lock = threading.Lock()
_last = 0.0


# ---------- отпечаток страницы ----------
_S = re.S | re.I
TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", _S)
META = re.compile(r'<meta\s[^>]*name="(?:description|robots)"[^>]*>', _S)
LINKS = re.compile(r'<link\s[^>]*rel="(?:canonical|alternate)"[^>]*>', _S)
LDJSON = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', _S)
MAIN = re.compile(r"<main\b[^>]*>(.*)</main>", _S)
BODY = re.compile(r"<body\b[^>]*>(.*)</body>", _S)
DROP = [re.compile(r"<script\b.*?</script>", _S), re.compile(r"<style\b.*?</style>", _S),
        re.compile(r"<header\b.*?</header>", _S), re.compile(r"<footer\b.*?</footer>", _S)]
CID = re.compile(r'\sdata-astro-cid-[a-z0-9]+(?:="[^"]*")?', re.I)      # метки оформления Astro
ASTRO = re.compile(r"/_astro/[^\"'\s)>]+")                              # файлы оформления: имя меняется со стилем
SPACE = re.compile(r"\s+")


def signature(text):
    """Отпечаток того, что видят поисковики: заголовок, описание, адреса, разметка и основная часть страницы."""
    head = text[:text.find("</head>")] if "</head>" in text else text
    parts = [m.group(1).strip() for m in TITLE.finditer(head)][:1]
    parts += META.findall(head) + LINKS.findall(head) + [m.group(1).strip() for m in LDJSON.finditer(text)]
    m = MAIN.search(text) or BODY.search(text)
    body = m.group(1) if m else text
    for rx in DROP if m is not None and m.re is BODY else DROP[:2]:
        body = rx.sub(" ", body)
    body = ASTRO.sub("/_astro/", CID.sub("", body))
    parts.append(body)
    return hashlib.sha256(SPACE.sub(" ", "\n".join(parts)).strip().encode("utf-8")).hexdigest()[:24]


# ---------- сайт на диске ----------
def find_key(root):
    """Ключ IndexNow — файл <32 hex>.txt в корне сайта, внутри — сам ключ."""
    try:
        names = sorted(n for n in os.listdir(root) if KEY_RE.match(n))
    except OSError:
        return None
    for n in names:
        try:
            with open(os.path.join(root, n), encoding="utf-8") as f:
                if f.read().strip() == n[:-4]:
                    return n[:-4]
        except OSError:
            pass
    return None


def sitemap_urls(root, host):
    """Адреса страниц из sitemap.xml в папке сайта (только этого домена, без повторов)."""
    try:
        with open(os.path.join(root, "sitemap.xml"), encoding="utf-8") as f:
            xml = f.read()
    except OSError:
        return None
    base = f"https://{host}/"
    out, seen = [], set()
    for m in re.finditer(r"<loc>\s*(.*?)\s*</loc>", xml, re.S):
        u = html.unescape(m.group(1))
        if (u == base or u.startswith(base)) and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def page_file(root, url):
    """Файл страницы: / → index.html, /адрес → адрес.html (сборка Astro с format: 'file')."""
    path = urllib.parse.unquote(urllib.parse.urlsplit(url).path).strip("/")
    rootp = os.path.realpath(root)
    for rel in (("index.html",) if not path else (path + ".html", os.path.join(path, "index.html"))):
        f = os.path.realpath(os.path.join(rootp, rel))
        if f.startswith(rootp + os.sep) and os.path.isfile(f):
            return f
    return None


def fingerprints(root, urls, cache):
    """Отпечатки страниц; файл перечитывается, только если у него изменились время или размер (cache обновляется)."""
    sigs, missing, fresh = {}, [], {}
    for u in urls:
        f = page_file(root, u)
        if not f:
            missing.append(u)
            continue
        try:
            st = os.stat(f)
            c = cache.get(u)
            if c and c[0] == st.st_mtime_ns and c[1] == st.st_size:
                sig = c[2]
            else:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    sig = signature(fh.read())
            fresh[u] = [st.st_mtime_ns, st.st_size, sig]
            sigs[u] = sig
        except OSError:
            missing.append(u)
    return sigs, missing, fresh


# ---------- состояние ----------
def state_path(host):
    return os.path.join(STATE_DIR, host + ".json")


def load(host):
    try:
        with open(state_path(host), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
    st.setdefault("sent", {})          # адрес → отпечаток, который поисковики уже получили
    st.setdefault("cache", {})         # адрес → [время файла, размер, отпечаток] — чтобы не перечитывать всё каждый час
    st.setdefault("total", 0)
    return st


SUMMARY = ("status", "note", "checked", "pages", "pending", "missing", "last_sent", "last_count", "last_parts", "total",
           "results", "fail_since")


def save(host, st):
    """Полное состояние (большое у каталога) и короткая сводка для страницы «Сервер и ИИ» — рядом."""
    os.makedirs(STATE_DIR, exist_ok=True)
    for path, data in ((state_path(host), st), (state_path(host)[:-5] + ".summary.json", {k: st.get(k) for k in SUMMARY})):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)


def read_mode(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or "preview"
    except OSError:
        return "preview"


# ---------- сеть ----------
def key_online(host, key):
    """Поисковик проверит ключ по https://<домен>/<ключ>.txt — проверяем так же, с сервера."""
    url = f"https://{host}/{key}.txt"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read(200).decode("utf-8", "replace").strip()
            if r.status == 200 and body == key:
                return True, ""
            return False, f"{url} отвечает не ключом (код {r.status})"
    except urllib.error.HTTPError as e:
        return False, f"{url} — код {e.code}"
    except Exception as e:  # noqa: BLE001
        return False, f"сайт не открывается на домене ({type(e).__name__})"


def post(api, host, key, urls):
    """Один запрос IndexNow; 200 и 202 — принято (202 — ключ ещё проверяется). Возвращает (код, текст ошибки)."""
    data = json.dumps({"host": host, "key": key, "keyLocation": f"https://{host}/{key}.txt", "urlList": urls}).encode("utf-8")
    req = urllib.request.Request(api, data=data, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        why = {400: "неверный запрос", 403: "ключ не принят", 422: "адреса не этого сайта или ключ не совпал",
               429: "слишком часто"}.get(e.code, "")
        return e.code, why
    except Exception as e:  # noqa: BLE001
        return 0, f"нет связи ({type(e).__name__})"


def submit(host, key, urls):
    """Отправить адреса (не больше BATCH) всем трём поисковикам. Возвращает {поисковик: [код, ошибка]}."""
    return {name: list(post(api, host, key, urls)) for name, api in ENGINES}


# ---------- проверка сайта ----------
def run_site(site, log=print, dry=False, resend=False):
    """Проверить один сайт и отправить изменения. Возвращает итог для вывода (dict)."""
    host, root = site["host"], site["root"]
    st = load(host)
    if resend:
        st["sent"] = {}
    now = int(time.time())
    out = {"host": host}

    def finish(status, note=""):
        st["status"], st["note"], st["checked"] = status, note, now
        out.update(status=status, note=note)
        if not dry:
            save(host, st)
        return out

    if read_mode(site["mode"]) != "live":
        return finish("preview", "сайт ещё не открыт на домене (режим просмотра) — начнём, когда откроется")
    key = find_key(root)
    if not key:
        return finish("nokey", "в папке сайта нет файла ключа — выложите сайт заново с Мака")
    urls = sitemap_urls(root, host)
    if urls is None:
        return finish("wait", "в папке сайта нет sitemap.xml — проверим через час")
    if len(urls) < MIN_PAGES or f"https://{host}/" not in urls:
        return finish("wait", f"в карте сайта {len(urls)} адресов и нет главной — похоже, идёт выкладка; проверим через час")

    sigs, missing, fresh = fingerprints(root, urls, st["cache"])
    st["cache"] = fresh
    sent, current = st["sent"], set(urls)
    new = [u for u in urls if u in sigs and u not in sent]
    changed = [u for u in urls if u in sigs and u in sent and sent[u] != sigs[u]]
    gone = [u for u in sent if u not in current]
    todo = new + changed + gone
    st["pages"], st["pending"], st["missing"] = len(urls), len(todo), len(missing)
    out.update(pages=len(urls), new=new, changed=changed, gone=gone, missing=missing)
    note = f"нет файлов у {len(missing)} адресов карты сайта" if missing else ""
    if not todo:
        st.pop("fail_since", None)
        st["alerted"] = False
        return finish("ok", note)
    if dry:
        return finish("dry", note)

    ok, why = key_online(host, key)
    # за час — не больше BATCH адресов (один запрос): остальное — в следующий час, чтобы не получить «слишком часто»
    batch = todo[:BATCH]
    results = submit(host, key, batch) if ok else {}
    st["results"] = results
    if any(code in (200, 202) for code, _ in results.values()):
        part = set(batch)
        n_new, n_chg, n_gone = (sum(u in part for u in x) for x in (new, changed, gone))
        for u in new + changed:
            if u in part:
                sent[u] = sigs[u]
        for u in gone:
            if u in part:
                sent.pop(u, None)
        left = len(todo) - len(batch)
        st.update(last_sent=now, last_count=len(batch), last_parts=[n_new, n_chg, n_gone],
                  total=st["total"] + len(batch), pending=left, alerted=False)
        st.pop("fail_since", None)
        refused = [f"{n}: {c or ''} {w}".strip() for n, (c, w) in results.items() if c not in (200, 202)]
        log(f"IndexNow {host}: отправлено {len(batch)} (новых {n_new}, изменённых {n_chg}, удалённых {n_gone})"
            + (f"; ещё {left} — в следующий час" if left else "")
            + (f"; не приняли — {'; '.join(refused)}" if refused else ""))
        return finish("ok", "; ".join(x for x in (note, f"ещё {left} адресов — в следующий час" if left else "",
                                                  ("не приняли — " + "; ".join(refused)) if refused else "") if x))

    st.setdefault("fail_since", now)
    err = why or "; ".join(f"{n}: {c or ''} {w}".strip() for n, (c, w) in results.items())
    log(f"IndexNow {host}: не отправлено ({err}) — повтор через час")
    if now - st["fail_since"] >= ALERT_AFTER and not st.get("alerted") and BOT is not None:
        try:
            BOT.notify_owner(f"⚠️ <b>IndexNow</b>: больше суток не получается сообщить поисковикам о страницах "
                             f"{html.escape(host)} ({len(todo)} адресов ждут).\n{html.escape(err)}\n"
                             f"Подробно — «Графики» → «Сервер и ИИ», карточка «Поисковики».")
            st["alerted"] = True
        except Exception as e:  # noqa: BLE001
            log(f"IndexNow: сообщение в бот не отправлено: {type(e).__name__}: {e}")
    return finish("error", err)


def run_all(log=print, dry=False, resend=False):
    """Все сайты по очереди; второй запуск одновременно (например, --now во время часовой проверки) ждать не будет."""
    if not _lock.acquire(blocking=False):
        return None
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, ".lock"), "w") as lf:
            try:
                fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                log("IndexNow: проверка уже идёт (сервис заявок) — попробуйте через минуту")
                return None
            outs = []
            for site in SITES:
                try:
                    outs.append(run_site(site, log=log, dry=dry, resend=resend))
                except Exception as e:  # noqa: BLE001
                    log(f"IndexNow {site['host']}: ошибка {type(e).__name__}: {e}")
                    outs.append({"host": site["host"], "status": "error", "note": f"{type(e).__name__}: {e}"})
            return outs
    finally:
        _lock.release()


def tick(log=print):
    """Из сервиса заявок раз в минуту: раз в час запускает проверку в своём потоке (статистику не задерживает)."""
    global _last
    if time.time() - _last < EVERY or _lock.locked():
        return
    _last = time.time()
    threading.Thread(target=run_all, kwargs={"log": log}, name="indexnow", daemon=True).start()


def status():
    """Для страницы «Сервер и ИИ»: по сайту — состояние, когда и сколько отправлено, ответы поисковиков."""
    out = []
    for site in SITES:
        try:
            with open(state_path(site["host"])[:-5] + ".summary.json", encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            st = {}
        out.append({"host": site["host"], "name": site["name"], "status": st.get("status") or "never",
                    "note": st.get("note") or "", "checked": st.get("checked"), "pages": st.get("pages"),
                    "pending": st.get("pending") or 0, "last_sent": st.get("last_sent"), "last_count": st.get("last_count"),
                    "last_parts": st.get("last_parts"), "total": st.get("total") or 0, "results": st.get("results") or {},
                    "fail_since": st.get("fail_since"), "engines": [n for n, _ in ENGINES]})
    return out


# ---------- вручную на сервере ----------
def _when(ts):
    return datetime.fromtimestamp(ts, TZ).strftime("%d.%m.%Y %H:%M") if ts else "—"


def main(argv):
    if "--status" in argv or len(argv) == 1:
        for s in status():
            print(f"{s['name']} ({s['host']}): {s['status']}" + (f" — {s['note']}" if s["note"] else ""))
            print(f"  проверено: {_when(s['checked'])}, страниц в карте сайта: {s['pages'] if s['pages'] is not None else '—'}, "
                  f"ждут отправки: {s['pending']}")
            if s["last_sent"]:
                n, c, g = s["last_parts"] or (0, 0, 0)
                print(f"  последняя отправка: {_when(s['last_sent'])} — {s['last_count']} (новых {n}, изменённых {c}, удалённых {g}); "
                      f"всего отправлено: {s['total']}")
            if s["results"]:
                print("  ответы: " + ", ".join(f"{k} {v[0] or 'нет связи'}" + (f" ({v[1]})" if v[1] else "") for k, v in s["results"].items()))
        return 0
    dry = "--dry-run" in argv
    if not dry and "--now" not in argv:
        print(__doc__)
        return 1
    outs = run_all(log=lambda m: print(m, flush=True), dry=dry, resend="--all" in argv)
    if outs is None:
        return 1
    for o in outs:
        print(f"{o['host']}: {o['status']}" + (f" — {o['note']}" if o.get("note") else ""))
        if dry and "new" in o:
            for label, key in (("новые", "new"), ("изменённые", "changed"), ("удалённые", "gone"), ("нет файла", "missing")):
                items = o.get(key) or []
                if items:
                    print(f"  {label}: {len(items)}")
                    for u in items[:15]:
                        print("    " + u)
                    if len(items) > 15:
                        print(f"    … ещё {len(items) - 15}")
            if not (o["new"] or o["changed"] or o["gone"]):
                print("  отправлять нечего — изменений нет")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
