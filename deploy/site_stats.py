#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Посетители сайта по журналу Caddy — без скриптов на страницах и без cookie: сайт не замедляется,
согласие посетителя не нужно.

Caddy записывает каждый запрос в /var/log/caddy/dumskaya.log (и в старые сжатые части журнала рядом).
Здесь эти записи разбираются:
  • просмотр страницы — GET страницы сайта (не фото, не стили, не /api) с ответом 200 или 304;
  • посетитель — браузер (Mozilla…, есть Accept-Language, не робот и не предзагрузка ссылки);
    уникальность — IP + браузер в пределах дня (только в памяти, в отчёты и файлы не попадает);
    за неделю — сумма посетителей по дням (человек, заходивший в два дня, считается дважды);
  • источник — откуда пришёл посетитель (Referer первого просмотра за день): Google, Bing, Instagram…;
  • роботы считаются отдельно: Googlebot (в том числе по языкам), Bingbot;
  • заявки — из ~/dumskaya/leads.jsonl (пробные заявки с сервера не считаются);
  • 404 — адреса, которые не нашлись (без мусора сканеров вроде .php и wp-).

Графики — мини-приложение в боте (кнопка «Графики», stats_app.html), периоды:
  • «1 час» — каждый посетитель отдельно: страницы по порядку, время на каждой, откуда пришёл, устройство,
    язык браузера, город по IP (geo.py, база на самом сервере). Строится на лету из журнала; время на странице
    и нажатия на контакты приходят со страниц сайта (/api/hit) и держатся только в памяти сервиса, сутки;
  • «24 часа» — по часам, со сравнением с предыдущими сутками;
  • 7, 30, 90 дней — по дням. Итоги дней сохраняются в ~/dumskaya/stats/<дата>.json (только цифры, без IP),
    поэтому длинные периоды не зависят от того, сколько хранится журнал; хранятся бессрочно;
  • «Год» (52 недели) и «Всё время» — по неделям, когда данных больше двух лет — по месяцам.
Утром в 9:00 (Братислава) разработчику — одна строка за вчера и кнопка «Графики».

Работает в процессе сервиса заявок вместе с ботом (lead_service.py), только в режиме live.
Только стандартная библиотека Python 3.
   python3 site_stats.py [ГГГГ-ММ-ДД]      — отчёт за день (по умолчанию за сегодня) в консоль
"""
import glob
import gzip
import hashlib
import hmac
import html
import ipaddress
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qsl, unquote, urlsplit

try:                                                # город по IP — для режима «1 час» (geo.py рядом)
    import geo
except ImportError:                                 # pragma: no cover
    geo = None

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bratislava")
except Exception:  # noqa: BLE001
    TZ = timezone(timedelta(hours=1))

APP = os.path.expanduser("~/dumskaya")
LOG_GLOB = os.environ.get("SITE_LOG_GLOB", "/var/log/caddy/dumskaya*.log*")
SITE_DIR = os.environ.get("SITE_DIR", "/var/www/dumskaya/site")
LEADS_FILE = os.environ.get("LEADS_FILE", os.path.join(APP, "leads.jsonl"))
HITS_FILE = os.environ.get("HITS_FILE", os.path.join(APP, "hits.jsonl"))   # нажатия на телефон, e-mail, мессенджеры
TIMES_FILE = os.environ.get("TIMES_FILE", os.path.join(APP, "times.jsonl"))   # сколько секунд страница была на экране
TIMES_KEEP_DAYS = 90          # столько же, сколько журнал: при пересчёте дней время на сайте не теряется
PAGE_CAP = 5 * 60             # страница дольше 5 минут считается за 5: дальше это уже забытая на экране вкладка
CONTACTS = {"tel": "телефон", "mail": "e-mail", "whatsapp": "WhatsApp", "telegram": "Telegram"}
STATS_DIR = os.environ.get("STATS_DIR", os.path.join(APP, "stats"))
EXCLUDE_FILE = os.path.join(STATS_DIR, "exclude.json")   # «свои» адреса (дома у студии) — их визиты не считаются
OWN_FILE = os.path.join(STATS_DIR, "own_devices.json")    # откуда студия открывала «Графики» — эти визиты тоже свои
OWN_WINDOW = 3 * 3600                                     # …за 3 часа до и после открытия
VERSION_FILE = os.path.join(STATS_DIR, "version")
STATS_VERSION = "5"           # сменить — итоги дней, которые журнал ещё помнит, пересчитаются
                              # (2: отсев сканеров; 3: время на сайте и роботы без оформления и времени;
                              #  4: страница — не больше 5 минут; 5: роботы без оформления и заголовков — и в старых днях)
SECRET_FILE = os.path.join(STATS_DIR, "secret")           # соль для обезличенного ключа посетителя, с сервера не уходит
REPORT_HOUR = 9
APP_URL = os.environ.get("STATS_APP_URL", "https://dumskaya-design.com/api/stats/app")   # мини-приложение с графиками

LANG_NAMES = {"ru": "RU", "ua": "UA", "en": "EN", "sk": "SK", "de": "DE"}
WEEKDAYS = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]

ASSET = re.compile(r"\.(css|js|mjs|map|png|jpe?g|webp|avif|gif|svg|ico|woff2?|ttf|otf|xml|txt|json|webmanifest|"
                   r"pdf|mp4|webm|zip|gz)$", re.I)
JUNK = re.compile(r"\.(php\d?|aspx?|jsp|cgi|env|ini|sql|bak|old|yml|yaml|git|ds_store)\b|wp-|wordpress|/\.|"
                  r"admin|xmlrpc|phpmyadmin|cgi-bin|/vendor/|/\.well-known/", re.I)
# адреса входа в админки и служебные файлы: на сайте их нет, ищут их только сканеры уязвимостей
PROBE = re.compile(r"(^|/)(log-?in|log-?on|sign-?in|sign-?up|register|auth|oauth2?|sso|users?|accounts?|admin\w*|"
                   r"console|dashboard|panel|cpanel|webadmin|manager|portal|ci|cd|jenkins|gitlab|actuator|api-docs|"
                   r"swagger(-ui)?|graphql|telescope|_ignition|debug|phpinfo|server-(status|info)|owa|ecp|boaform|"
                   r"hnap1|solr|geoserver|druid|nacos|cgi-bin|shell|cmd|config|backups?|phpmyadmin|pma|mysql|xmlrpc|"
                   r"wp-\w*|wordpress|vendor|\.git|\.svn|\.env|\.aws|\.ssh)(/|\.|$)", re.I)
BURST = (10, 15)              # 10 страниц за 15 секунд — так листает только программа
BOT = re.compile(r"bot\b|bot/|crawl|spider|slurp|scrap|preview|monitor|uptime|lighthouse|pagespeed|headless|"
                 r"phantom|python|curl|wget|httpclient|okhttp|axios|go-http|java/|libwww|perl|ruby|php/|node-fetch|"
                 r"scan|ahrefs|semrush|mj12|dotbot|petal|bytespider|yandex|baidu|sogou|facebookexternalhit|"
                 r"meta-externalagent|whatsapp|telegram|discord|slack|twitter|linkedin|embedly|gpt|claude|"
                 r"anthropic|perplexity|ccbot|cohere|dataforseo|seznam|qwant|applebot|amazonbot|censys|zgrab|"
                 r"masscan|nikto|sqlmap|dumskaya-", re.I)
SOURCES = [(r"(^|\.)google\.", "Google"), (r"(^|\.)bing\.com$", "Bing"), (r"(^|\.)yandex\.", "Яндекс"),
           (r"(^|\.)duckduckgo\.com$", "DuckDuckGo"), (r"(^|\.)seznam\.cz$", "Seznam"),
           (r"(^|\.)instagram\.com$", "Instagram"), (r"(^|\.)(facebook\.com|fb\.com|fb\.me)$", "Facebook"),
           (r"(^|\.)(t\.me|telegram\.org)$", "Telegram"), (r"(^|\.)(chatgpt\.com|openai\.com)$", "ChatGPT"),
           (r"(^|\.)perplexity\.ai$", "Perplexity"), (r"(^|\.)youtube\.com$", "YouTube"),
           (r"(^|\.)pinterest\.", "Pinterest"), (r"(^|\.)houzz\.", "Houzz"), (r"(^|\.)linkedin\.com$", "LinkedIn")]
# метки в адресе первой страницы: реклама и ссылки без Referer (из приложений, ChatGPT)
AD_MARKS = (("gclid", "Google (реклама)"), ("gbraid", "Google (реклама)"), ("wbraid", "Google (реклама)"),
            ("msclkid", "Bing (реклама)"))
UTM_NAMES = {"ig": "Instagram", "instagram": "Instagram", "facebook": "Facebook", "fb": "Facebook",
             "telegram": "Telegram", "tg": "Telegram", "google": "Google", "chatgpt": "ChatGPT",
             "chatgpt.com": "ChatGPT", "whatsapp": "WhatsApp", "perplexity": "Perplexity", "bing": "Bing"}
BROWSERS = [(r"Instagram", "Instagram"), (r"FBAN|FBAV|FB_IAB", "Facebook"), (r"Edg(e|A|iOS)?/", "Edge"),
            (r"OPR/|OPT/|Opera", "Opera"), (r"YaBrowser", "Яндекс Браузер"), (r"SamsungBrowser", "Samsung Internet"),
            (r"Firefox/|FxiOS", "Firefox"), (r"Chrome/|CriOS", "Chrome"), (r"Safari/", "Safari")]
LANG_RU = {"ru": "русский", "uk": "украинский", "en": "английский", "sk": "словацкий", "de": "немецкий",
           "cs": "чешский", "pl": "польский", "hu": "венгерский", "it": "итальянский", "fr": "французский",
           "es": "испанский", "pt": "португальский", "be": "белорусский", "kk": "казахский", "he": "иврит",
           "tr": "турецкий", "ro": "румынский", "bg": "болгарский", "sr": "сербский", "hr": "хорватский",
           "sl": "словенский", "nl": "нидерландский", "ar": "арабский", "zh": "китайский", "ja": "японский",
           "ka": "грузинский", "lt": "литовский", "lv": "латышский", "et": "эстонский", "fi": "финский",
           "sv": "шведский", "da": "датский", "no": "норвежский", "nb": "норвежский", "el": "греческий"}
SESSION_GAP = 30 * 60          # перерыв дольше получаса — уже другой заход
LIVE_WINDOW = 3600             # «1 час»


# ---------- разбор журнала ----------
def lang_of(path):
    for l in ("ua", "en", "sk", "de"):
        if path == f"/{l}" or path.startswith(f"/{l}/"):
            return l
    return "ru"


def header(h, name):
    v = h.get(name)
    if v is None:                                   # на всякий случай — другое написание
        for k, vv in h.items():
            if k.lower() == name.lower():
                v = vv
                break
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def device(ua):
    if re.search(r"iPad|Tablet", ua) or ("Android" in ua and "Mobile" not in ua):
        return "планшет"
    if re.search(r"Mobi|iPhone|Android", ua):
        return "телефон"
    return "компьютер"


def source(ref, uri=""):
    """Откуда пришёл посетитель: по Referer, а без него — по меткам в адресе (gclid, fbclid, utm_source)."""
    q = dict(parse_qsl(urlsplit(uri).query)) if uri and "?" in uri else {}
    for k, name in AD_MARKS:
        if k in q:
            return name
    host = (urlsplit(ref).hostname or "").lower() if ref else ""
    if host.startswith("www."):
        host = host[4:]
    if host and not host.endswith("dumskaya-design.com"):  # свой адрес — переход внутри сайта (вкладка со вчера)
        for rx, name in SOURCES:
            if re.search(rx, host):
                return name
        return host
    if "fbclid" in q:
        return "Facebook / Instagram"
    utm = (q.get("utm_source") or "").strip().lower()[:40]
    if utm:
        return UTM_NAMES.get(utm, utm)
    return "прямые заходы"


def ua_info(ua):
    """(«телефон», «iPhone», «Safari») — устройство, система, браузер."""
    os_name = ("iPhone" if "iPhone" in ua else "iPad" if "iPad" in ua else "Android" if "Android" in ua else
               "Windows" if "Windows" in ua else "Mac" if "Macintosh" in ua or "Mac OS X" in ua else
               "ChromeOS" if "CrOS" in ua else "Linux" if "Linux" in ua else "")
    browser = next((name for rx, name in BROWSERS if re.search(rx, ua)), "")
    return device(ua), os_name, browser


def browser_lang(accept_language):
    """Первый язык из Accept-Language: «ru-RU,ru;q=0.9» → «русский»."""
    first = (accept_language or "").split(",")[0].split(";")[0].strip().lower()
    code = first.split("-")[0]
    return LANG_RU.get(code, first)


def norm_path(p):
    p = unquote(urlsplit(p or "/").path) or "/"
    return p.rstrip("/") or "/"


def log_files(since_ts):
    """Части журнала, в которых могут быть записи начиная с since_ts (старые сжатые — тоже)."""
    out = []
    for f in glob.glob(LOG_GLOB):
        try:
            if os.path.getmtime(f) >= since_ts:
                out.append(f)
        except OSError:
            pass
    return sorted(out, key=os.path.getmtime)


TS_RX = re.compile(rb'"ts":\s*([0-9]{9,}(?:\.[0-9]+)?)')


def _line_ts(raw):
    """Время записи без разбора всей строки JSON (Caddy пишет "ts" в начале); None — не нашлось."""
    m = TS_RX.search(raw, 0, 300)
    return float(m.group(1)) if m else None


def _seek(fh, since_ts):
    """Несжатая часть журнала идёт по времени — двоичным поиском сразу к записям не старше since_ts."""
    fh.seek(0, 2)
    lo, hi = 0, fh.tell()
    while hi - lo > 65536:
        mid = (lo + hi) // 2
        fh.seek(mid)
        fh.readline()                               # остаток строки, в середину которой попали
        ts = None
        for _ in range(20):
            line = fh.readline()
            if not line:
                break
            ts = _line_ts(line)
            if ts is not None:
                break
        if ts is not None and ts < since_ts - 120:  # запас на записи, пришедшие не по порядку
            lo = mid
        else:
            hi = mid
    fh.seek(lo)
    if lo:
        fh.readline()


def entries(since_ts, until_ts):
    """Записи журнала за период; PermissionError — если журнал недоступен для чтения."""
    files = log_files(since_ts)
    if not files and glob.glob(LOG_GLOB) == [] and not os.access(os.path.dirname(LOG_GLOB) or "/", os.R_OK):
        raise PermissionError(os.path.dirname(LOG_GLOB))
    for f in files:
        gz = f.endswith(".gz")
        try:
            fh = gzip.open(f, "rb") if gz else open(f, "rb")
        except PermissionError:
            raise
        except OSError:                             # часть журнала успели удалить при ротации
            continue
        with fh:
            if not gz:
                _seek(fh, since_ts)
            for raw in fh:
                if b'"request"' not in raw:
                    continue
                ts = _line_ts(raw)
                if ts is not None and not since_ts <= ts < until_ts:
                    if not gz and ts >= until_ts + 120:
                        break                       # дальше в этой части только записи новее периода
                    continue
                try:
                    e = json.loads(raw)
                except ValueError:
                    continue
                ts = e.get("ts")
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    except ValueError:
                        continue
                if isinstance(ts, (int, float)) and since_ts <= ts < until_ts:
                    yield ts, e


# ---------- свои адреса (не считать) ----------
_excl = {"mtime": None, "nets": [], "items": []}
_excl_hit = {}


def excluded_list():
    """Адреса, визиты с которых не считаются: [{net, who, added, seen}] из ~/dumskaya/stats/exclude.json."""
    try:
        mtime = os.stat(EXCLUDE_FILE).st_mtime
    except OSError:
        mtime = None
    if mtime != _excl["mtime"]:
        items = []
        if mtime is not None:
            try:
                with open(EXCLUDE_FILE, encoding="utf-8") as fh:
                    items = json.load(fh)
            except (OSError, ValueError):
                items = []
        nets = []
        for it in items:
            try:
                nets.append(ipaddress.ip_network(it["net"], strict=False))
            except (ValueError, KeyError, TypeError):
                pass
        _excl.update(mtime=mtime, nets=nets, items=items)
        _excl_hit.clear()
    return _excl["items"]


def is_excluded(ip):
    if not ip:
        return False
    excluded_list()
    if not _excl["nets"]:
        return False
    hit = _excl_hit.get(ip)
    if hit is None:
        try:
            a = ipaddress.ip_address(ip)
            hit = any(a in n for n in _excl["nets"])
        except ValueError:
            hit = False
        _excl_hit[ip] = hit
    return hit


def net_of(ip):
    """IPv4 — сам адрес; IPv6 — сеть /64 (адреса устройств внутри дома меняются, сеть — нет)."""
    a = ipaddress.ip_address(ip)
    return str(ipaddress.ip_network(f"{a}/{32 if a.version == 4 else 64}", strict=False))


def _save_excluded(items, recount=True):
    os.makedirs(STATS_DIR, exist_ok=True)
    tmp = EXCLUDE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, EXCLUDE_FILE)
    if recount:
        forget_recent()


def exclude_add(ip, who):
    net, stamp = net_of(ip), datetime.now(TZ).strftime("%Y-%m-%d")
    items = [dict(x) for x in excluded_list()]
    for x in items:
        if x.get("net") == net:
            x["seen"] = stamp
            _save_excluded(items, recount=False)
            return items
    items.append({"net": net, "who": who, "added": stamp, "seen": stamp})
    _save_excluded(items)
    return items


def exclude_remove(net):
    items = [dict(x) for x in excluded_list() if x.get("net") != net]
    _save_excluded(items)
    return items


def touch_seen(ip):
    """Отметить, что свой адрес снова встречался (видно, какой адрес давно не попадался — значит, сменился)."""
    if not is_excluded(ip):
        return
    stamp = datetime.now(TZ).strftime("%Y-%m-%d")
    items = [dict(x) for x in excluded_list()]
    changed = False
    for x in items:
        try:
            if ipaddress.ip_address(ip) in ipaddress.ip_network(x["net"], strict=False) and x.get("seen") != stamp:
                x["seen"], changed = stamp, True
        except (ValueError, KeyError, TypeError):
            pass
    if changed:
        _save_excluded(items, recount=False)


_own = {"mtime": None, "items": [], "hit": {}}


def _own_items():
    try:
        mtime = os.stat(OWN_FILE).st_mtime
    except OSError:
        mtime = None
    if mtime != _own["mtime"]:
        items = []
        if mtime is not None:
            try:
                with open(OWN_FILE, encoding="utf-8") as fh:
                    items = json.load(fh)
            except (OSError, ValueError):
                items = []
        _own.update(mtime=mtime, items=items, hit={})
    return _own["items"]


def is_own(ip, ts=None):
    """Визит студии: адрес из «Не считать нас» или адрес, с которого разработчик или дизайнер открывал «Графики»
    (за 3 часа до и после: телефон с мобильным интернетом не добавишь в «Не считать нас» — адрес общий и меняется)."""
    if not ip:
        return False
    if is_excluded(ip):
        return True
    items = _own_items()
    if not items:
        return False
    spans = _own["hit"].get(ip)
    if spans is None:
        spans = []
        try:
            a = ipaddress.ip_address(ip)
            for x in items:
                try:
                    if a in ipaddress.ip_network(x["net"], strict=False):
                        spans.append((float(x["from"]) - OWN_WINDOW, float(x["to"]) + OWN_WINDOW))
                except (ValueError, KeyError, TypeError):
                    pass
        except ValueError:
            pass
        _own["hit"][ip] = spans
    ts = time.time() if ts is None else ts
    return any(lo <= ts <= hi for lo, hi in spans)


def mark_own(ip, who=""):
    """Разработчик или дизайнер открыл «Графики» с этого адреса (IPv6 — сеть /64): его визиты на сайт
    за 3 часа до и после не считаются. Пишет ~/dumskaya/stats/own_devices.json не чаще раза в 5 минут."""
    try:
        net = net_of(ip)
    except ValueError:
        return
    now = time.time()
    items = [dict(x) for x in _own_items() if now - float(x.get("to", 0)) < 100 * 86400]
    for x in items:
        if x.get("net") == net and now - float(x["to"]) <= 2 * OWN_WINDOW:    # то же окно продолжается
            if now - float(x["to"]) < 300:
                return
            x["to"] = int(now)
            break
    else:
        items.append({"net": net, "from": int(now), "to": int(now), "who": who})
        y = datetime.fromtimestamp(now - OWN_WINDOW, TZ).date()      # окно задело вчера — вчерашний итог пересчитать
        if y < today():
            try:
                os.remove(day_file(y))
            except OSError:
                pass
    os.makedirs(STATS_DIR, exist_ok=True)
    with open(OWN_FILE + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)
    os.replace(OWN_FILE + ".tmp", OWN_FILE)


def is_robot(hits):
    """Программа, а не человек, хотя назвалась браузером: искала адреса админок (/login, /console, .env…)
    или открыла 10 страниц за 15 секунд. hits — [(время, вид, страница)] одного IP + браузера."""
    if any(k == "probe" for _, k, _ in hits):
        return True
    n, span = BURST
    ts = sorted(t for t, _, _ in hits)
    return any(ts[i + n - 1] - ts[i] <= span for i in range(len(ts) - n + 1))


def logs_start():
    """Время первой записи в самой старой части журнала (до него журнала уже нет)."""
    for f in sorted(glob.glob(LOG_GLOB), key=os.path.getmtime):
        opener = gzip.open if f.endswith(".gz") else open
        try:
            with opener(f, "rt", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        ts = json.loads(line).get("ts")
                    except ValueError:
                        continue
                    if isinstance(ts, (int, float)):
                        return ts
        except OSError:
            continue
    return None


def forget_recent():
    """Список своих адресов изменился — итоги дней, которые журнал ещё помнит, посчитать заново."""
    start = logs_start()
    _empty.clear()
    if start is None:
        return
    for f in glob.glob(os.path.join(STATS_DIR, "[0-9]*.json")):
        try:
            d = date.fromisoformat(os.path.basename(f)[:10])
        except ValueError:
            continue
        if day_bounds(d)[1] > start:            # день (хотя бы частично) ещё есть в журнале
            try:
                os.remove(f)
            except OSError:
                pass


def leads_between(since_ts, until_ts):
    out = []
    try:
        with open(LEADS_FILE, encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                    ts = datetime.fromisoformat(d["time"]).timestamp()
                except (ValueError, KeyError, TypeError):
                    continue
                if not since_ts <= ts < until_ts:
                    continue
                if d.get("ip") in ("127.0.0.1", "::1") or str(d.get("name", "")).startswith("Проверка"):
                    continue                                  # пробные заявки мастера настройки и сторожа
                if is_own(d.get("ip"), ts):
                    continue                                  # заявка со своего адреса (проверка формы)
                out.append({"page": d.get("page", ""), "lang": d.get("lang", "ru"), "model": d.get("model", ""),
                            "ts": ts, "ip": d.get("ip", "")})
    except OSError:
        pass
    return out


def hits_between(since_ts, until_ts, with_ts=False):
    """Нажатия на контакты за период: [(тип, страница)] или [(время, тип, страница)]
    (пишет /api/hit; без IP, свои адреса не записываются)."""
    out = []
    try:
        with open(HITS_FILE, encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                    ts = float(d["ts"])
                except (ValueError, KeyError, TypeError):
                    continue
                if since_ts <= ts < until_ts and d.get("t") in CONTACTS:
                    item = (d["t"], str(d.get("p") or ""))
                    out.append((ts,) + item if with_ts else item)
    except OSError:
        pass
    return out


def record_hit(kind, path, ip="", ua=""):
    """Записать нажатие (вызывает сервис заявок после своих проверок): тип, страница и обезличенный ключ посетителя."""
    d = {"ts": int(time.time()), "t": kind, "p": path}
    if ip:
        d["v"] = vkey(ip, ua)
    _append(HITS_FILE, d)


# ---------- события со страниц: время на странице и нажатия — с обезличенным ключом посетителя ----------
_write_lock = threading.Lock()
_salt = {"v": None}


def vkey(ip, ua):
    """Обезличенный ключ посетителя (IP + браузер → 16 знаков хеша с солью этого сервера): по нему время на странице
    связывается с просмотрами из журнала, но сам IP в файлы времени и нажатий не пишется."""
    if _salt["v"] is None:
        try:
            with open(SECRET_FILE, encoding="utf-8") as fh:
                _salt["v"] = fh.read().strip()
        except OSError:
            _salt["v"] = ""
        if len(_salt["v"]) < 32:
            _salt["v"] = os.urandom(24).hex()
            os.makedirs(STATS_DIR, exist_ok=True)
            fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(_salt["v"])
    return hashlib.sha256(f"{_salt['v']}|{ip}|{ua}".encode()).hexdigest()[:16]


def _append(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _write_lock, open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def record_time(path, secs, ip, ua):
    """Страница сообщила, сколько секунд была на экране (её закрыли или свернули)."""
    _append(TIMES_FILE, {"ts": int(time.time()), "p": norm_path(path), "s": int(secs), "v": vkey(ip, ua)})


def prune_times(now=None):
    """Оставить в файле времени последние TIMES_KEEP_DAYS дней."""
    cutoff = (now or time.time()) - TIMES_KEEP_DAYS * 86400
    try:
        with _write_lock:
            with open(TIMES_FILE, encoding="utf-8") as fh:
                keep = [line for line in fh if _line_ts(line.encode()) is None or _line_ts(line.encode()) >= cutoff]
            with open(TIMES_FILE + ".tmp", "w", encoding="utf-8") as fh:
                fh.writelines(keep)
            os.replace(TIMES_FILE + ".tmp", TIMES_FILE)
    except OSError:
        pass


def beacon_start():
    """Когда со страниц начало приходить время (первая запись файла времени) или None — ещё не приходило."""
    try:
        with open(TIMES_FILE, "rb") as fh:
            for line in fh:
                ts = _line_ts(line)
                if ts is not None:
                    return ts
    except OSError:
        pass
    return None


def events_between(since_ts, until_ts):
    """События со страниц за период: [(время, ключ, вид, страница, секунды)]; вид — time или тип контакта."""
    out = []
    for path in (TIMES_FILE, HITS_FILE):
        try:
            with open(path, "rb") as fh:
                for line in fh:
                    t = _line_ts(line)
                    if t is not None and not since_ts <= t < until_ts:
                        continue
                    try:
                        d = json.loads(line)
                        ts = float(d["ts"])
                    except (ValueError, KeyError, TypeError):
                        continue
                    if not since_ts <= ts < until_ts or not d.get("v"):
                        continue
                    kind = "time" if path == TIMES_FILE else d.get("t")
                    if kind == "time" or kind in CONTACTS:
                        out.append((ts, d["v"], kind, str(d.get("p") or "/"), int(d.get("s") or 0)))
        except OSError:
            pass
    return sorted(out)


def beacons_by_key(events):
    """{ключ: [(время, страница, секунды)]} — только сообщения о времени на странице."""
    out = {}
    for ts, v, kind, path, secs in events:
        if kind == "time":
            out.setdefault(v, []).append((ts, path, secs))
    return out


def page_times(views, beacons):
    """Секунды на каждом просмотре: views — [(время, страница)] по порядку, beacons — [(время, страница, секунды)].
    Страница присылает, сколько всего была на экране, — берётся наибольшее до следующего открытия той же страницы."""
    out = []
    for i, (ts, path) in enumerate(views):
        nxt = next((v[0] for v in views[i + 1:] if v[1] == path), float("inf"))
        out.append(max((s for t, p, s in beacons if p == path and ts - 2 <= t < nxt), default=0) or None)
    return out


_ua_ok = {}
PENDING = 30 * 60             # столько ждём от страницы сообщения о времени, прежде чем решить, что это робот


def browser_ua(ua):
    """Подпись браузера (Mozilla…), а не робота; результат запоминается для каждой подписи."""
    ok = _ua_ok.get(ua)
    if ok is None:
        if len(_ua_ok) > 20000:
            _ua_ok.clear()
        ok = _ua_ok[ua] = ua.startswith("Mozilla/") and not BOT.search(ua)
    return ok


def is_human(ua, h):
    return (browser_ua(ua) and bool(header(h, "Accept-Language"))
            and "prefetch" not in (header(h, "Sec-Purpose") + header(h, "Purpose")).lower())


def parse(e):
    """Запись журнала → (вид, ip, браузер, страница, заголовки, адрес с параметрами) или None.
    Вид: view — открыта страница; 404 — страница не нашлась; probe — запрос адреса админки или служебного файла
    (так делают только сканеры); asset — браузер загрузил оформление или фото (/_astro, /img);
    google, bing — роботы поисковиков прочитали страницу."""
    r = e.get("request") or {}
    if r.get("method") != "GET":
        return None
    uri = r.get("uri") or "/"
    path = norm_path(uri)
    ip = r.get("client_ip") or r.get("remote_ip") or ""
    h = r.get("headers") or {}
    ua = header(h, "User-Agent")
    status = e.get("status")
    if path.startswith(("/_astro/", "/img/")):
        return ("asset", ip, ua, path, h, uri) if status in (200, 206, 304) and browser_ua(ua) else None
    if path.startswith("/api/") or ASSET.search(path):
        return None
    if "Googlebot" in ua or "bingbot" in ua.lower():
        return ("google" if "Googlebot" in ua else "bing", ip, ua, path, h, uri) if status in (200, 304) else None
    if not is_human(ua, h):
        return None
    if status == 404:
        probe = PROBE.search(path) or (JUNK.search(path) and "/.well-known/" not in path)
        return ("probe" if probe else "404", ip, ua, path, h, uri)
    if status not in (200, 304):
        return None
    return ("view", ip, ua, path, h, uri)


def navigates(h):
    """Настоящий браузер при переходе на страницу присылает заголовки Sec-Fetch-* (Chrome, Firefox, Safari 16.4+)."""
    return bool(header(h, "Sec-Fetch-Mode") or header(h, "Sec-Fetch-Dest"))


def quiet_robot(v, beacons, now, timed=True):
    """Не загрузил ни оформления, ни фото и не прислал время на странице — так ведут себя программы, а не браузеры.
    Без заголовков перехода браузера (Sec-Fetch-*) — робот сразу: этот признак работает и для дней, когда страницы
    ещё не присылали время (timed=False). С заголовками — робот, если и через 30 минут после последней страницы
    времени нет; только когда время уже присылают (вернувшийся посетитель берёт оформление из кэша, но время присылает)."""
    if v["assets"] or beacons:
        return False
    if not v["nav"]:
        return True
    last = max((t for t, k, _ in v["hits"] if k in ("view", "404")), default=0)
    return timed and now - last > PENDING


def split_key(k):
    ip, _, ua = k.partition("|")
    return ip, ua


class Agg:
    """Накопитель итогов за один период (час, день или «сегодня до текущего часа»): только числа, без IP.
    Кто робот, решается в конце (result), по всем запросам этого IP + браузера за период."""

    def __init__(self):
        self.keys = {}                              # ключ (IP+браузер) → {src, dev, hits, assets, nav}; только в памяти
        self.google, self.google_lang, self.bing, self.requests = 0, Counter(), 0, 0
        self.own = 0                                # просмотры студии (не считаются)

    def add(self, e, ts=None):
        self.requests += 1
        p = parse(e)
        if not p:
            return
        kind, ip, ua, path, h, uri = p
        if kind == "google":
            self.google += 1
            self.google_lang[lang_of(path)] += 1
            return
        if kind == "bing":
            self.bing += 1
            return
        if is_own(ip, ts):
            self.own += kind == "view"
            return
        v = self.keys.get(ip + "|" + ua)
        if v is None:
            v = self.keys[ip + "|" + ua] = {"src": None, "dev": device(ua), "hits": [], "assets": False, "nav": False}
        if kind == "asset":
            v["assets"] = True
            return
        if kind == "view" and v["src"] is None:
            v["src"] = source(header(h, "Referer"), uri)
        if kind != "probe" and navigates(h):
            v["nav"] = True
        v["hits"].append((ts or 0, kind, path))

    def robots(self, times=None, now=None):
        """Ключи роботов: сканеры (is_robot) и «молчащие» программы (quiet_robot); правило «30 минут без времени» —
        только для тех, кто заходил, когда страницы уже присылали время (раньше его не было ни у кого)."""
        now, times, since = now or time.time(), times or {}, beacon_start()
        out = set()
        for k, v in self.keys.items():
            if not v["hits"]:
                continue
            timed = since is not None and min(t for t, _, _ in v["hits"]) >= since
            if is_robot(v["hits"]) or quiet_robot(v, times.get(vkey(*split_key(k))), now, timed):
                out.add(k)
        return out

    def result(self, leads, hits=(), robots=None, times=None, now=None):
        times = times or {}
        robots = self.robots(times, now) if robots is None else robots
        views, lang_views, notfound = Counter(), Counter(), Counter()
        lang_visitors, sources, devices = Counter(), Counter(), Counter()
        page_time = {}
        visitors = bots = time_total = time_visitors = 0
        for k, v in self.keys.items():
            if not v["hits"]:
                continue
            if k in robots:
                bots += 1
                continue
            notfound.update(p for _, kind, p in v["hits"] if kind == "404")
            seen = [(t, p) for t, kind, p in v["hits"] if kind == "view"]
            if not seen:
                continue
            visitors += 1
            views.update(p for _, p in seen)
            lang_views.update(lang_of(p) for _, p in seen)
            lang_visitors.update({lang_of(p) for _, p in seen})
            sources[v["src"]] += 1
            devices[v["dev"]] += 1
            secs = page_times(seen, times.get(vkey(*split_key(k)), [])) if times else []
            known = [(p, min(x, PAGE_CAP)) for (_, p), x in zip(seen, secs) if x]
            if known:                               # время — только по тем, чья страница его прислала
                time_visitors += 1
                time_total += sum(x for _, x in known)
                for p, x in known:
                    pt = page_time.setdefault(p, [0, 0])
                    pt[0] += x
                    pt[1] += 1
        top = dict(views.most_common(50))
        return {
            "requests": self.requests,              # 0 — за этот период журнала нет (ещё не вёлся или удалён)
            "visitors": visitors,
            "views": sum(views.values()),
            "lang_visitors": dict(lang_visitors),
            "lang_views": dict(lang_views),
            "sources": dict(sources),
            "devices": dict(devices),
            "pages": top,
            "notfound": dict(notfound.most_common(20)),
            "bots": bots,                           # отсеянные программы, назвавшиеся браузером
            "time_total": time_total, "time_visitors": time_visitors,   # секунды на сайте и сколько посетителей с временем
            "page_time": {p: page_time[p] for p in top if p in page_time},   # страница → [секунды, просмотров с временем]
            "google": self.google, "google_lang": dict(self.google_lang), "bing": self.bing, "own": self.own,
            "leads": len(leads), "lead_pages": dict(Counter(x["page"] for x in leads if x["page"])),
            "contacts": dict(Counter(t for t, _ in hits)),
            "contact_pages": dict(Counter(p for _, p in hits if p).most_common(30)),
        }


def aggregate(since_ts, until_ts):
    """Итоги за период одним проходом по журналу."""
    a = Agg()
    for ts, e in entries(since_ts, until_ts):
        a.add(e, ts)
    times = beacons_by_key(events_between(since_ts, until_ts + 3600))
    return a.result(leads_between(since_ts, until_ts), hits_between(since_ts, until_ts), times=times, now=time.time())


def aggregate_days(days):
    """Итоги нескольких дней за один проход по журналу: {день: итоги}."""
    if not days:
        return {}
    bounds = {d: day_bounds(d) for d in days}
    aggs = {d: Agg() for d in days}
    lo, hi = min(b[0] for b in bounds.values()), max(b[1] for b in bounds.values())
    for ts, e in entries(lo, hi):
        d = datetime.fromtimestamp(ts, TZ).date()
        if d in aggs:
            aggs[d].add(e, ts)
    times, now = beacons_by_key(events_between(lo, hi + 3600)), time.time()
    return {d: aggs[d].result(leads_between(*bounds[d]), hits_between(*bounds[d]), times=times, now=now) for d in days}


# ---------- дни и хранение ----------
def day_bounds(d):
    start = datetime(d.year, d.month, d.day, tzinfo=TZ)
    end = datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=TZ)
    return start.timestamp(), end.timestamp()


def today():
    return datetime.now(TZ).date()


def day_file(d):
    return os.path.join(STATS_DIR, f"{d.isoformat()}.json")


def load_day(d):
    try:
        with open(day_file(d), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def save_day(d, agg):
    os.makedirs(STATS_DIR, exist_ok=True)
    tmp = day_file(d) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(agg, fh, ensure_ascii=False)
    os.replace(tmp, day_file(d))               # итоги дней хранятся бессрочно — для «Года» и «Всего времени»


_empty = {}                                         # дни без записей в журнале: {день: дата проверки}
_checked = {"version": False}


def _upgrade():
    """Правила подсчёта изменились (STATS_VERSION) — дни, которые журнал ещё помнит, посчитать заново."""
    if _checked["version"]:
        return
    _checked["version"] = True
    try:
        with open(VERSION_FILE, encoding="utf-8") as fh:
            if fh.read().strip() == STATS_VERSION:
                return
    except OSError:
        pass
    forget_recent()
    os.makedirs(STATS_DIR, exist_ok=True)
    with open(VERSION_FILE, "w", encoding="utf-8") as fh:
        fh.write(STATS_VERSION)


def days_stats(days):
    """Итоги прошедших дней {день: итоги или None, если данных нет}: сохранённые файлы, недостающие —
    из журнала одним проходом (и сохранить). Сегодняшний день не сохраняется — он ещё не закончился."""
    _upgrade()
    t = today()
    out, missing = {}, []
    for d in days:
        agg = load_day(d)
        if agg is not None:
            out[d] = agg
        elif _empty.get(d) == t:
            out[d] = None
        else:
            missing.append(d)
    if missing:                                     # дни раньше начала журнала — считать не из чего, журнал не читаем
        ls = logs_start()
        for d in [d for d in missing if ls is None or day_bounds(d)[1] <= ls]:
            out[d] = None
            _empty[d] = t
            missing.remove(d)
    for d, agg in aggregate_days(missing).items():
        if not agg["requests"]:
            out[d] = None
            _empty[d] = t
            continue
        if d < t:
            save_day(d, agg)
        out[d] = agg
    return out


def day_stats(d):
    """Итоги одного дня или None — данных за день нет."""
    return days_stats([d])[d]


MERGE_DICTS = ("lang_visitors", "lang_views", "sources", "devices", "pages", "notfound", "google_lang", "lead_pages",
               "contacts", "contact_pages")


def merge(aggs):
    """Сумма дней; None — если хотя бы за один день нет данных."""
    aggs = list(aggs)
    if not aggs or any(a is None for a in aggs):
        return None
    sums = ("visitors", "views", "google", "bing", "leads", "own", "time_total", "time_visitors")
    out = dict.fromkeys(sums, 0)
    for k in MERGE_DICTS:
        out[k] = Counter()
    out["page_time"] = {}
    for a in aggs:
        for k in sums:
            out[k] += a.get(k, 0)
        for k in MERGE_DICTS:
            out[k].update(a.get(k) or {})
        for p, (secs, n) in (a.get("page_time") or {}).items():
            pt = out["page_time"].setdefault(p, [0, 0])
            pt[0] += secs
            pt[1] += n
    return out


def avg_time(a):
    """Среднее время на сайте одного посетителя, секунды (по тем, чьи страницы прислали время), или None."""
    n = (a or {}).get("time_visitors") or 0
    return round(a["time_total"] / n) if n else None


# ---------- текст отчёта ----------
_titles = {}


def title_of(path):
    """Заголовок страницы из файла сайта (без « | DUMSKAYA…»), иначе адрес."""
    if path in _titles:
        return _titles[path]
    f = os.path.join(SITE_DIR, "index.html" if path == "/" else path.lstrip("/") + ".html")
    t = path
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            m = re.search(r"<title>(.*?)</title>", fh.read(20000), re.S)
        if m:
            t = html.unescape(re.sub(r"\s*\|\s*DUMSKAYA.*$", "", m.group(1)).strip()) or path
    except OSError:
        pass
    lang = lang_of(path)
    if lang != "ru" and t != path:
        t = f"{LANG_NAMES[lang]} · {t}"
    _titles[path] = t
    return t


def esc(s):
    return html.escape(str(s), quote=False)


SPARK = "▁▂▃▄▅▆▇█"
EIGHTHS = " ▏▎▍▌▋▊▉█"


def spark(values):
    """▁▃▅█ по дням; нет данных — «·»."""
    nums = [v for v in values if v is not None]
    top = max(nums) if nums else 0
    return "".join("·" if v is None else SPARK[0] if not top else SPARK[min(7, round(v / top * 7))] for v in values)


def bar(v, top, width=10):
    """Полоса из блоков длиной до width знаков (с точностью до 1/8)."""
    if not top or v <= 0:
        return ""
    units = max(1, round(v / top * width * 8))
    return "█" * (units // 8) + (EIGHTHS[units % 8] if units % 8 else "")


def bars(counter, order=None, limit=6, other="другие"):
    """Блок <pre> с полосами: подпись, полоса, число."""
    items = [(k, counter.get(k, 0)) for k in order if counter.get(k)] if order else \
        sorted(counter.items(), key=lambda kv: -kv[1])
    if not items:
        return ""
    rest = sum(v for _, v in items[limit:])
    items = items[:limit] + ([(other, rest)] if rest else [])
    top = max(v for _, v in items)
    w = min(14, max(len(str(k)) for k, _ in items))
    rows = [f"{str(k)[:w].ljust(w)} {bar(v, top).ljust(10)} {v}" for k, v in items]
    return "<pre>" + esc("\n".join(rows)) + "</pre>"


def delta(cur, prev):
    if prev is None:
        return ""
    d = cur - prev
    return f"  {'▲' if d > 0 else '▼'} {abs(d)}" if d else "  = как раньше"


def body(a, prev=None, top=7, trend=None, trend_label=""):
    out = [f"👥 Посетители: <b>{a['visitors']}</b>{delta(a['visitors'], prev and prev['visitors'])}",
           f"👁 Просмотры: <b>{a['views']}</b>{delta(a['views'], prev and prev['views'])}"]
    leads = a.get("leads", 0)
    lp = Counter(a.get("lead_pages") or {})
    out.append(f"✉️ Заявки: <b>{leads}</b>{delta(leads, prev and prev.get('leads'))}"
               + (f" — {', '.join(esc(title_of(p)) for p, _ in lp.most_common(3))}" if lp else ""))
    c = Counter(a.get("contacts") or {})
    n = sum(c.values())
    pn = sum((prev.get("contacts") or {}).values()) if prev and "contacts" in prev else None
    line_c = f"📞 Нажатия на контакты: <b>{n}</b>{delta(n, pn)}"
    if n:
        line_c += " — " + " · ".join(f"{CONTACTS[k]} {c[k]}" for k in CONTACTS if c.get(k))
        cp = Counter(a.get("contact_pages") or {}).most_common(2)
        if cp:
            line_c += "\n      чаще со страниц: " + ", ".join(esc(title_of(p)) for p, _ in cp)
    out.append(line_c)
    if trend:
        out.append(f"\n<code>{trend}</code> {esc(trend_label)}")
    if a["visitors"]:
        langs = Counter({LANG_NAMES[k]: v for k, v in (a.get("lang_visitors") or {}).items()})
        out.append("\n<b>Языки</b>" + bars(langs, order=list(LANG_NAMES.values())))
        out.append("<b>Откуда</b>" + bars(Counter(a.get("sources") or {}), limit=5))
        dev = Counter(a.get("devices") or {})
        out.append("Устройства: " + " · ".join(f"{esc(k)} {v}" for k, v in dev.most_common()))
    pages = Counter(a.get("pages") or {}).most_common(top)
    if pages:
        out.append("\n<b>Популярные страницы</b>")
        out += [f"{i}. {esc(title_of(p))} — {n}" for i, (p, n) in enumerate(pages, 1)]
    nf = Counter(a.get("notfound") or {}).most_common(5)
    if nf:
        out.append("\n⚠️ Не найдено (404): " + "; ".join(f"{esc(p)} — {n}" for p, n in nf))
    gl = Counter(a.get("google_lang") or {})
    new = " · ".join(f"{LANG_NAMES[k]} {gl[k]}" for k in ("sk", "de") if gl.get(k))
    out.append(f"\n🤖 Робот Google: {a.get('google', 0)} стр." + (f" (из них {new})" if new else "")
               + f" · Bing: {a.get('bing', 0)}")
    if a.get("own"):
        out.append(f"🏠 Свои просмотры не учтены: {a['own']}")
    return "\n".join(out)


def trend_of(last_day, n=14):
    """Посетители за n дней, заканчивая last_day, — строка ▁▃▅█ и подпись."""
    days = [last_day - timedelta(days=i) for i in range(n - 1, -1, -1)]
    got = days_stats(days)
    vals = [got[d]["visitors"] if got[d] else None for d in days]
    if sum(1 for v in vals if v is not None) < 2:
        return None, ""
    return spark(vals), f"посетители за {n} дней"


def day_name(d):
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}"


def daily_report(d):
    a = day_stats(d)
    if a is None:
        return f"📊 <b>Сайт за {day_name(d)}</b>\nЗа этот день в журнале сайта нет записей."
    prev = day_stats(d - timedelta(days=1))
    tr, label = trend_of(d)
    return f"📊 <b>Сайт за {day_name(d)}</b>\n\n" + body(a, prev, trend=tr, trend_label=label)


def weekly_report(monday):
    """Неделя с понедельника monday по воскресенье — со сравнением с предыдущей."""
    days = [monday + timedelta(days=i) for i in range(7)]
    got = days_stats(days + [d - timedelta(days=7) for d in days])
    cur = [got[d] for d in days]
    a = merge(x for x in cur if x is not None)
    b = merge(got[d - timedelta(days=7)] for d in days)
    sun = days[-1]
    head = f"📈 <b>Сайт за неделю {monday.day} {MONTHS[monday.month - 1]} — {sun.day} {MONTHS[sun.month - 1]}</b>\n"
    if a is None:
        return head + "За эту неделю в журнале сайта нет записей."
    missing = sum(1 for x in cur if x is None)
    note = ["посетители — сумма по дням"]
    if missing:
        note.append(f"нет данных за {missing} дн.")
    note.append("▲▼ — разница с прошлой неделей" if b else "сравнения с прошлой неделей пока нет")
    wd = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    vals = [x["visitors"] if x else 0 for x in cur]
    daily = "<b>По дням</b><pre>" + esc("\n".join(
        f"{wd[i]} {bar(v, max(vals) or 1).ljust(10)} {v if cur[i] else '—'}" for i, v in enumerate(vals))) + "</pre>"
    return head + f"<i>{'; '.join(note)}</i>\n\n" + body(a, b, top=10) + "\n\n" + daily


def today_report():
    d = today()
    start, _ = day_bounds(d)
    a = aggregate(start, time.time() + 1)
    y = day_stats(d - timedelta(days=1))
    hh = datetime.now(TZ).strftime("%H:%M")
    tail = (f"\n\nВчера: посетителей {y['visitors']}, просмотров {y['views']}, заявок {y.get('leads', 0)}"
            if y else "")
    tr, label = trend_of(d - timedelta(days=1))
    return f"📊 <b>Сайт сегодня, до {hh}</b>\n\n" + body(a, trend=tr, trend_label=label + " (до вчера)" if tr else "") + tail


# ---------- мини-приложение с графиками ----------
def check_init_data(init_data, token, max_age=86400):
    """Telegram ID из подписанных данных запуска мини-приложения или None (подпись — HMAC от токена бота)."""
    try:
        pairs = dict(parse_qsl(init_data or "", keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    got = pairs.pop("hash", "")
    if not got or not token:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(secret, check.encode(), hashlib.sha256).hexdigest(), got):
        return None
    try:
        if time.time() - int(pairs.get("auth_date", "0")) > max_age:
            return None
        return int(json.loads(pairs.get("user") or "{}").get("id"))
    except (ValueError, TypeError):
        return None


def me_data(ip):
    """Для блока «Не считать нас»: адрес, с которого открыто приложение, и список своих адресов."""
    touch_seen(ip)
    try:
        net = net_of(ip)
    except ValueError:
        net = ""
    return {"ip": ip, "net": net, "excluded": is_excluded(ip), "items": excluded_list()}


def _row(a, **extra):
    """Строка графика (день или час) из итогов периода; a=None — данных нет."""
    a = a or {}
    gl = a.get("google_lang") or {}
    return dict(extra, visitors=a.get("visitors", 0), views=a.get("views", 0), leads=a.get("leads", 0),
                google=a.get("google", 0), contacts=sum((a.get("contacts") or {}).values()),
                google_sk=gl.get("sk", 0), google_de=gl.get("de", 0), avg_time=avg_time(a))


def _top(counter, k=8, other="другие"):
    items = Counter(counter).most_common()
    rest = sum(v for _, v in items[k:])
    return [list(x) for x in items[:k]] + ([[other, rest]] if rest else [])


def _total(tot):
    """Итоги периода для плиток и карточек (tot — результат merge или None)."""
    total = {"visitors": 0, "views": 0, "leads": 0, "google": 0, "own": 0, "contacts": 0, "contact_types": [],
             "contact_pages": [], "langs": [], "sources": [], "devices": [], "pages": [], "notfound": [], "leads_pages": [],
             "avg_time": None, "time_visitors": 0}

    def page_avg(p):                                # среднее время на странице — когда оно пришло хотя бы 3 раза
        secs, n = tot["page_time"].get(p, (0, 0))
        return round(secs / n) if n >= 3 else None

    if tot:
        total.update(
            visitors=tot["visitors"], views=tot["views"], leads=tot["leads"], google=tot["google"], own=tot["own"],
            avg_time=avg_time(tot), time_visitors=tot["time_visitors"],
            langs=[[LANG_NAMES[k], tot["lang_visitors"][k]] for k in LANG_NAMES if tot["lang_visitors"].get(k)],
            sources=_top(tot["sources"]), devices=_top(tot["devices"]),
            pages=[[title_of(p), v, page_avg(p)] for p, v in tot["pages"].most_common(15)],
            notfound=[[p, v] for p, v in tot["notfound"].most_common(10)],
            leads_pages=[[title_of(p), v] for p, v in tot["lead_pages"].most_common(8)],
            contacts=sum(tot["contacts"].values()),
            contact_types=[[CONTACTS[k], tot["contacts"][k]] for k in CONTACTS if tot["contacts"].get(k)],
            contact_pages=[[title_of(p), v] for p, v in tot["contact_pages"].most_common(8)])
    return total


def _prev(pv, contacts_known=True):
    if not pv:
        return None
    return dict({k: pv[k] for k in ("visitors", "views", "leads", "google")},
                contacts=sum(pv["contacts"].values()) if contacts_known else None, avg_time=avg_time(pv))


def _stamp(now=None):
    now = now or time.time()
    return {"generated": datetime.fromtimestamp(now, TZ).strftime("%H:%M"), "generated_ts": int(now)}


def web_data(n):
    """Данные для графиков: n дней, последний — сегодня (неполный), и сравнение с предыдущими n днями."""
    n = n if n in (7, 30, 90) else 7
    t = today()
    days = [t - timedelta(days=i) for i in range(n - 1, -1, -1)]
    prev_days = [d - timedelta(days=n) for d in days]
    got = days_stats(days[:-1] + prev_days)
    start, _ = day_bounds(t)
    got[t] = aggregate(start, time.time() + 1)
    if not got[t]["requests"]:
        got[t] = None
    rows = [_row(got[d], date=d.isoformat(), missing=got[d] is None, partial=d == t) for d in days]
    cur = [got[d] for d in days if got[d]]
    prev = [got[d] for d in prev_days]
    tot = merge(cur) if cur else None
    pv = merge(prev) if prev and all(prev) else None          # сравниваем, только если за прошлый период есть все дни
    return dict(_stamp(), period=str(n), unit="day", rows=rows, coverage=len(cur), total=_total(tot),
                prev=_prev(pv, all("contacts" in x for x in prev) if pv else False))


def web_hours(now=None):
    """24 часа по часам: текущий час (неполный) и 23 предыдущих; сравнение — с таким же отрезком перед ними.
    Часы — по границам часа (у Братиславы и Флориды смещение от UTC целое, границы совпадают)."""
    now = now or time.time()
    start = int(now // 3600) * 3600 - 23 * 3600
    pstart = start - (now - start)
    buckets, cur, prev, whole = [Agg() for _ in range(24)], Agg(), Agg(), Agg()
    for ts, e in entries(pstart, now + 1):
        whole.add(e, ts)
        if ts >= start:
            cur.add(e, ts)
            buckets[min(23, int((ts - start) // 3600))].add(e, ts)
        else:
            prev.add(e, ts)
    times = beacons_by_key(events_between(pstart, now + 1))
    robots = whole.robots(times, now)                          # кто робот — по всем двум суткам, а не по одному часу
    leads, hits = leads_between(pstart, now + 1), hits_between(pstart, now + 1, with_ts=True)
    rows = []
    ls = logs_start()
    for i, b in enumerate(buckets):
        bs = start + i * 3600
        r = b.result([x for x in leads if bs <= x["ts"] < bs + 3600], [(t, p) for ts, t, p in hits if bs <= ts < bs + 3600],
                     robots, times)
        rows.append(_row(r, ts=bs, missing=ls is None or bs + 3600 <= ls, partial=i == 23))
    tot = merge([cur.result([x for x in leads if x["ts"] >= start], [(t, p) for ts, t, p in hits if ts >= start],
                            robots, times)])
    pv = None
    if ls is not None and ls <= pstart + 300:                  # журнал помнит и предыдущие сутки целиком
        pv = merge([prev.result([x for x in leads if x["ts"] < start], [(t, p) for ts, t, p in hits if ts < start],
                                robots, times)])
    return dict(_stamp(now), period="24h", unit="hour", rows=rows, coverage=sum(not r["missing"] for r in rows),
                total=_total(tot), prev=_prev(pv))


def _session(info, views, evs, leads, before, now):
    """Карточка одного захода посетителя: страницы по порядку со временем на каждой и события на них."""
    ip, ua, accept = info
    pages = []
    for i, (ts, path, kind, uri, ref) in enumerate(views):
        nxt = views[i + 1][0] if i + 1 < len(views) else None
        nxt_same = next((v[0] for v in views[i + 1:] if v[1] == path), float("inf"))
        # время, пока страница была на экране, — присылает сама страница, когда её закрывают или сворачивают
        shown = max((s for t, k, p, s in evs if k == "time" and p == path and ts - 2 <= t < nxt_same), default=0)
        if shown:
            secs, approx = shown, False
        elif nxt is not None and nxt - ts < SESSION_GAP:
            secs, approx = int(nxt - ts), True        # примерно: до открытия следующей страницы
        else:
            secs, approx = None, False
        capped = secs is not None and secs > PAGE_CAP   # дольше 5 минут — считаем за 5 (забытая вкладка)
        pages.append({"ts": int(ts), "path": path, "nf": kind == "404", "secs": min(secs, PAGE_CAP) if capped else secs,
                      "capped": capped, "approx": approx, "title": path if kind == "404" else title_of(path), "events": []})

    def page_at(t, path=None):
        best = None
        for i, v in enumerate(views):
            if v[0] <= t + 2 and (path is None or v[1] == path):
                best = i
        return best

    for t, k, p, s in evs:
        if k in CONTACTS:
            i = page_at(t, p)
            i = page_at(t) if i is None else i
            if i is not None:
                pages[i]["events"].append({"t": k, "ts": int(t)})
    for x in leads:
        i = page_at(x["ts"], norm_path(x["page"]))
        i = page_at(x["ts"]) if i is None else i
        if i is not None:
            pages[i]["events"].append({"t": "lead", "ts": int(x["ts"])})
    end = max([views[-1][0]] + [t for t, *_ in evs] + [x["ts"] for x in leads])
    last = pages[-1]
    dev, os_name, browser = ua_info(ua)
    first = views[0]
    return {"start": int(first[0]), "end": int(end),
            "active": last["secs"] is None and now - views[-1][0] < 15 * 60,   # последнюю страницу ещё не закрыли
            "geo": geo.lookup(ip) if geo else None, "device": dev, "os": os_name, "browser": browser,
            "lang": browser_lang(accept), "source": source(first[4], first[3]),
            "total": sum(p["secs"] or 0 for p in pages), "before": before, "pages": pages,
            "timed": sum(p["secs"] for p in pages if p["secs"] and not p["approx"])}


def web_live(now=None):
    """«1 час»: каждый посетитель отдельно — заходы, в которых что-то происходило за последний час
    (заход целиком, даже если начался раньше). Строится из журнала за сутки; IP наружу не отдаётся."""
    now = now or time.time()
    since = now - 86400
    views, info, meta, own = {}, {}, {}, set()
    for ts, e in entries(since, now + 1):
        p = parse(e)
        if not p or p[0] not in ("view", "404", "probe", "asset"):
            continue
        kind, ip, ua, path, h, uri = p
        key = ip + "|" + ua
        if is_own(ip, ts):                                    # студия: «Не считать нас» и телефоны, где открывали «Графики»
            if ts >= now - LIVE_WINDOW and kind != "asset":
                own.add(key)
            continue
        m = meta.setdefault(key, {"hits": [], "assets": False, "nav": False})
        if kind == "asset":
            m["assets"] = True
            continue
        m["hits"].append((ts, kind, path))
        if kind != "probe":
            m["nav"] = m["nav"] or navigates(h)
            views.setdefault(key, []).append((ts, path, kind, uri, header(h, "Referer")))
            info.setdefault(key, (ip, ua, header(h, "Accept-Language")))
    events = {}                                               # обезличенный ключ → [(время, вид, страница, секунды)]
    for t, v, kind, path, secs in events_between(since, now + 1):
        events.setdefault(v, []).append((t, kind, path, secs))
    started = beacon_start()
    for key in list(views):                                   # роботы, назвавшиеся браузером, — не посетители
        m = meta[key]
        beacons = [x for x in events.get(vkey(*split_key(key)), []) if x[1] == "time"]
        timed = started is not None and min(t for t, _, _ in m["hits"]) >= started
        if is_robot(m["hits"]) or quiet_robot(m, beacons, now, timed):
            del views[key]
    leads = leads_between(since, now + 1)
    sessions, last = [], None
    for key, vs in views.items():
        vs.sort(key=lambda v: v[0])
        groups = [[vs[0]]]
        for v in vs[1:]:
            if v[0] - groups[-1][-1][0] > SESSION_GAP:
                groups.append([v])
            else:
                groups[-1].append(v)
        if last is None or vs[-1][0] > last[0]:
            last = (vs[-1][0], info[key][0])
        evs = sorted(events.get(vkey(*split_key(key)), []))
        lds = [x for x in leads if x["ip"] == info[key][0]]
        for gi, g in enumerate(groups):
            lo, hi = g[0][0] - 5, groups[gi + 1][0][0] if gi + 1 < len(groups) else float("inf")
            gev = [x for x in evs if lo <= x[0] < hi]
            paths = {v[1] for v in g}             # заявка с того же адреса — этого человека, если он был на её странице
            gld = [x for x in lds if lo <= x["ts"] < hi and (not x["page"] or norm_path(x["page"]) in paths)]
            end = max([g[-1][0]] + [x[0] for x in gev] + [x["ts"] for x in gld])
            if end >= now - LIVE_WINDOW:
                sessions.append(_session(info[key], g, gev, gld, gi, now))
    sessions.sort(key=lambda s: -s["end"])
    hour = now - LIVE_WINDOW
    summary = {"visitors": len(sessions), "active": sum(s["active"] for s in sessions),
               "views": sum(1 for s in sessions for p in s["pages"] if p["ts"] >= hour),
               "contacts": sum(1 for s in sessions for p in s["pages"] for x in p["events"] if x["t"] in CONTACTS and x["ts"] >= hour),
               "leads": sum(1 for s in sessions for p in s["pages"] for x in p["events"] if x["t"] == "lead" and x["ts"] >= hour)}
    timed = [s["timed"] for s in sessions if s["timed"]]
    summary["avg_time"] = round(sum(timed) / len(timed)) if timed else None     # по тем, чьи страницы прислали время
    lastv = None
    if not sessions and last:
        g = geo.lookup(last[1]) if geo else None
        lastv = {"ts": int(last[0]), "place": g["place"] if g else ""}
    return dict(_stamp(now), period="1h", sessions=sessions[:60], summary=summary, own=len(own), last=lastv,
                geo=bool(geo and geo.available()), credit=geo.CREDIT if geo else "")


def first_day():
    """Первый день, за который есть данные: самый ранний сохранённый итог или начало журнала."""
    found = []
    for f in glob.glob(os.path.join(STATS_DIR, "[0-9]*.json")):
        try:
            found.append(date.fromisoformat(os.path.basename(f)[:10]))
        except ValueError:
            pass
    ls = logs_start()
    if ls is not None:
        found.append(datetime.fromtimestamp(ls, TZ).date())
    return min(found) if found else None


def web_long(period):
    """«Год» (52 недели и текущая) и «Всё время» (с первого дня данных): по неделям, а когда данных больше двух лет —
    по месяцам. Посетители недели или месяца — сумма по дням. Год сравнивается с предыдущими 52 неделями."""
    t = today()
    monday = t - timedelta(days=t.weekday())
    if period == "365":
        first, unit = monday - timedelta(weeks=51), "week"
    else:
        f = first_day() or t
        unit = "week" if (t - f).days <= 2 * 366 else "month"
        first = f - timedelta(days=f.weekday()) if unit == "week" else f.replace(day=1)
    days = [first + timedelta(days=i) for i in range((t - first).days + 1)]
    prev_days = [d - timedelta(weeks=52) for d in days] if period == "365" else []
    got = days_stats(days[:-1] + prev_days)
    start, _ = day_bounds(t)
    got[t] = aggregate(start, time.time() + 1)
    if not got[t]["requests"]:
        got[t] = None
    groups = {}
    for d in days:
        b = d - timedelta(days=d.weekday()) if unit == "week" else d.replace(day=1)
        groups.setdefault(b, []).append(d)
    rows = []
    for b, ds in groups.items():
        have = [got[d] for d in ds if got[d]]
        end = b + timedelta(days=6) if unit == "week" else (b.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        rows.append(_row(merge(have) if have else None, date=b.isoformat(), end=end.isoformat(), missing=not have,
                         partial=t in ds, days=len(have), span=(end - b).days + 1))
    cur = [got[d] for d in days if got[d]]
    prev = [got[d] for d in prev_days]
    pv = merge(prev) if prev and all(prev) else None
    return dict(_stamp(), period=period, unit=unit, rows=rows, coverage=len(cur), span=len(days),
                first=days[0].isoformat(), total=_total(merge(cur) if cur else None),
                prev=_prev(pv, all("contacts" in x for x in prev) if pv else False))


def web(period):
    """Данные мини-приложения за период: 1h, 24h, 7, 30, 90 (дней), 365 (год) или all (всё время)."""
    if period == "1h":
        return web_live()
    if period == "24h":
        return web_hours()
    if period in ("365", "all"):
        return web_long(period)
    return web_data(int(period) if str(period).isdigit() else 7)


def plural(n, one, few, many):
    n = abs(n) % 100
    if 11 <= n <= 19:
        return many
    return one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many


def arrow(cur, prev):
    if prev is None or cur == prev:
        return ""
    return f" {'▲' if cur > prev else '▼'}{abs(cur - prev)}"


def summary(a, prev=None):
    """«34 посетителя ▲6 · 1 заявка · 3 нажатия на контакты» — для утреннего сообщения."""
    c, pc = sum((a.get("contacts") or {}).values()), None
    if prev and "contacts" in prev:
        pc = sum((prev.get("contacts") or {}).values())
    v, l = a["visitors"], a.get("leads", 0)
    return (f"<b>{v}</b> {plural(v, 'посетитель', 'посетителя', 'посетителей')}{arrow(v, prev and prev['visitors'])} · "
            f"{l} {plural(l, 'заявка', 'заявки', 'заявок')}{arrow(l, prev and prev.get('leads'))} · "
            f"{c} {plural(c, 'нажатие', 'нажатия', 'нажатий')} на контакты{arrow(c, pc)}")


def morning_note(d):
    """Утреннее сообщение: одна строка за вчера (по понедельникам — и за неделю), подробности — в «Графиках»."""
    y = d - timedelta(days=1)
    got = days_stats([y - timedelta(days=k) for k in range(14)])
    a, prev = got[y], got[y - timedelta(days=1)]
    lines = [f"📈 Сайт за {day_name(y)}: " + (summary(a, prev) if a else "в журнале нет записей")]
    if d.weekday() == 0:
        week = [got[y - timedelta(days=k)] for k in range(7)]
        before = [got[y - timedelta(days=k)] for k in range(7, 14)]
        cur = merge(x for x in week if x) if any(week) else None
        if cur:
            lines.append("За неделю: " + summary(cur, merge(before) if all(before) else None))
    lines.append("Графики — кнопкой ниже.")
    return "\n".join(lines)


NO_ACCESS = ("Не могу прочитать журнал сайта ({}) — у сервиса нет доступа. Выложите сайт ещё раз "
             "(npm run deploy спросит пароль sudo и откроет журнал для чтения).")


BUTTON = [[("📈 Графики", {"web_app": {"url": APP_URL}})]]


# ---------- расписание ----------
class SiteStats:
    def __init__(self, bot, log=print, live_fn=None, clock=None):
        self.bot, self.log = bot, log
        self.live_fn = live_fn or self.is_live
        self.clock = clock or (lambda: datetime.now(TZ))
        self.stop = threading.Event()

    @staticmethod
    def is_live():
        try:
            return open(os.path.join(APP, "mode")).read().strip() == "live"
        except OSError:
            return False

    def tick(self):
        if not self.live_fn():
            return
        now = self.clock()
        d = now.date()
        last = self.bot.s.get("stats:daily") or ""
        if now.hour < REPORT_HOUR or last == d.isoformat():
            return
        try:
            # дни, пропущенные, пока сервис не работал, — сохранить итоги, пока журнал их ещё помнит
            days_stats([d - timedelta(days=k) for k in range(7, 1, -1)])
            text = morning_note(d)
        except PermissionError:
            text = NO_ACCESS.format(esc(LOG_GLOB))
        self.bot.s.put("stats:daily", d.isoformat())
        self.bot.notify(text, roles=("owner",), rows=BUTTON)
        prune_times()                               # раз в день: время на страницах старше 90 дней — удалить

    def start(self):
        t = threading.Thread(target=self.loop, name="site-stats", daemon=True)
        t.start()
        return t

    def loop(self):
        self.stop.wait(60)
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001
                self.log(f"статистика: ошибка {type(e).__name__}: {e}")
            if geo and self.live_fn():
                try:                                # база городов: раз в месяц свежий выпуск (сама решает, пора ли)
                    geo.update(log=self.log)
                except Exception as e:  # noqa: BLE001
                    self.log(f"гео: ошибка {type(e).__name__}: {e}")
            self.stop.wait(60)


if __name__ == "__main__":
    d = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else today()
    text = today_report() if d == today() else daily_report(d)
    print(re.sub(r"</?[bi]>", "", text))
