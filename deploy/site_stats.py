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

Отчёт за вчера — разработчику в бот каждый день в 9:00 (Братислава), по понедельникам ещё и за прошлую
неделю со сравнением. Итоги дней сохраняются в ~/dumskaya/stats/<дата>.json (только цифры, без IP) —
недельный отчёт не зависит от того, сколько хранится журнал. Команда /stats — сегодня до текущего часа
и вчера (разработчику и дизайнеру студии).

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
CONTACTS = {"tel": "телефон", "mail": "e-mail", "whatsapp": "WhatsApp", "telegram": "Telegram"}
STATS_DIR = os.environ.get("STATS_DIR", os.path.join(APP, "stats"))
EXCLUDE_FILE = os.path.join(STATS_DIR, "exclude.json")   # «свои» адреса (дома у студии) — их визиты не считаются
REPORT_HOUR = 9
APP_URL = os.environ.get("STATS_APP_URL", "https://dumskaya-design.com/api/stats/app")   # мини-приложение с графиками
KEEP_DAYS = 800

LANG_NAMES = {"ru": "RU", "ua": "UA", "en": "EN", "sk": "SK", "de": "DE"}
WEEKDAYS = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]

ASSET = re.compile(r"\.(css|js|mjs|map|png|jpe?g|webp|avif|gif|svg|ico|woff2?|ttf|otf|xml|txt|json|webmanifest|"
                   r"pdf|mp4|webm|zip|gz)$", re.I)
JUNK = re.compile(r"\.(php\d?|aspx?|jsp|cgi|env|ini|sql|bak|old|yml|yaml|git|ds_store)\b|wp-|wordpress|/\.|"
                  r"admin|xmlrpc|phpmyadmin|cgi-bin|/vendor/|/\.well-known/", re.I)
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


def source(ref):
    if not ref:
        return "прямые заходы"
    host = (urlsplit(ref).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host or host.endswith("dumskaya-design.com"):
        return "прямые заходы"                       # переход внутри сайта (например, вкладка открыта со вчера)
    for rx, name in SOURCES:
        if re.search(rx, host):
            return name
    return host


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


def entries(since_ts, until_ts):
    """Записи журнала за период; PermissionError — если журнал недоступен для чтения."""
    files = log_files(since_ts)
    if not files and glob.glob(LOG_GLOB) == [] and not os.access(os.path.dirname(LOG_GLOB) or "/", os.R_OK):
        raise PermissionError(os.path.dirname(LOG_GLOB))
    for f in files:
        opener = gzip.open if f.endswith(".gz") else open
        with opener(f, "rt", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"request"' not in line:
                    continue
                try:
                    e = json.loads(line)
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
                if is_excluded(d.get("ip")):
                    continue                                  # заявка со своего адреса (проверка формы)
                out.append({"page": d.get("page", ""), "lang": d.get("lang", "ru"), "model": d.get("model", "")})
    except OSError:
        pass
    return out


def hits_between(since_ts, until_ts):
    """Нажатия на контакты за период: [(тип, страница)] (пишет /api/hit; без IP, свои адреса не записываются)."""
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
                    out.append((d["t"], str(d.get("p") or "")))
    except OSError:
        pass
    return out


def record_hit(kind, path):
    """Записать нажатие (вызывает сервис заявок после своих проверок)."""
    os.makedirs(os.path.dirname(HITS_FILE), exist_ok=True)
    with open(HITS_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": int(time.time()), "t": kind, "p": path}, ensure_ascii=False) + "\n")


class Agg:
    """Накопитель итогов за один период (день или «сегодня до текущего часа»): только числа, без IP."""

    def __init__(self):
        self.visitors = {}                          # ключ (IP+браузер) → {src, dev, langs}; только в памяти
        self.views, self.lang_views, self.notfound = Counter(), Counter(), Counter()
        self.google, self.google_lang, self.bing, self.requests = 0, Counter(), 0, 0
        self.own = 0                                # просмотры со своих адресов (не считаются)

    def add(self, e):
        self.requests += 1
        r = e.get("request") or {}
        if r.get("method") != "GET":
            return
        ip = r.get("client_ip") or r.get("remote_ip") or ""
        h = r.get("headers") or {}
        ua = header(h, "User-Agent")
        path = unquote(urlsplit(r.get("uri") or "/").path) or "/"
        path = path.rstrip("/") or "/"
        if path.startswith(("/img/", "/_astro/", "/api/")) or ASSET.search(path):
            return
        status = e.get("status")
        if "Googlebot" in ua:
            if status in (200, 304):
                self.google += 1
                self.google_lang[lang_of(path)] += 1
            return
        if "bingbot" in ua.lower():
            if status in (200, 304):
                self.bing += 1
            return
        human = (ua.startswith("Mozilla/") and not BOT.search(ua) and header(h, "Accept-Language")
                 and "prefetch" not in (header(h, "Sec-Purpose") + header(h, "Purpose")).lower())
        if not human:
            return
        if status == 404 and is_excluded(ip):
            return
        if status == 404:
            if not JUNK.search(path):
                self.notfound[path] += 1
            return
        if status not in (200, 304):
            return
        if is_excluded(ip):
            self.own += 1
            return
        key = ip + "|" + ua
        v = self.visitors.get(key)
        if v is None:
            v = self.visitors[key] = {"src": source(header(h, "Referer")), "dev": device(ua), "langs": set()}
        v["langs"].add(lang_of(path))
        self.views[path] += 1
        self.lang_views[lang_of(path)] += 1

    def result(self, leads, hits=()):
        vs = self.visitors.values()
        return {
            "requests": self.requests,              # 0 — за этот период журнала нет (ещё не вёлся или удалён)
            "visitors": len(self.visitors),
            "views": sum(self.views.values()),
            "lang_visitors": dict(Counter(l for v in vs for l in v["langs"])),
            "lang_views": dict(self.lang_views),
            "sources": dict(Counter(v["src"] for v in vs)),
            "devices": dict(Counter(v["dev"] for v in vs)),
            "pages": dict(self.views.most_common(50)),
            "notfound": dict(self.notfound.most_common(20)),
            "google": self.google, "google_lang": dict(self.google_lang), "bing": self.bing, "own": self.own,
            "leads": len(leads), "lead_pages": dict(Counter(x["page"] for x in leads if x["page"])),
            "contacts": dict(Counter(t for t, _ in hits)),
            "contact_pages": dict(Counter(p for _, p in hits if p).most_common(30)),
        }


def aggregate(since_ts, until_ts):
    """Итоги за период одним проходом по журналу."""
    a = Agg()
    for _, e in entries(since_ts, until_ts):
        a.add(e)
    return a.result(leads_between(since_ts, until_ts), hits_between(since_ts, until_ts))


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
            aggs[d].add(e)
    return {d: aggs[d].result(leads_between(*bounds[d]), hits_between(*bounds[d])) for d in days}


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
    os.replace(tmp, day_file(d))
    cutoff = (d - timedelta(days=KEEP_DAYS)).isoformat()
    for f in glob.glob(os.path.join(STATS_DIR, "[0-9]*.json")):
        if os.path.basename(f)[:10] < cutoff:
            try:
                os.remove(f)
            except OSError:
                pass


_empty = {}                                         # дни без записей в журнале: {день: дата проверки}


def days_stats(days):
    """Итоги прошедших дней {день: итоги или None, если данных нет}: сохранённые файлы, недостающие —
    из журнала одним проходом (и сохранить). Сегодняшний день не сохраняется — он ещё не закончился."""
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
    out = {"visitors": 0, "views": 0, "google": 0, "bing": 0, "leads": 0, "own": 0}
    for k in MERGE_DICTS:
        out[k] = Counter()
    for a in aggs:
        for k in ("visitors", "views", "google", "bing", "leads", "own"):
            out[k] += a.get(k, 0)
        for k in MERGE_DICTS:
            out[k].update(a.get(k) or {})
    return out


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
    rows = []
    for d in days:
        a = got[d]
        gl = (a or {}).get("google_lang") or {}
        rows.append({"date": d.isoformat(), "missing": a is None, "partial": d == t,
                     "visitors": (a or {}).get("visitors", 0), "views": (a or {}).get("views", 0),
                     "leads": (a or {}).get("leads", 0), "google": (a or {}).get("google", 0),
                     "contacts": sum(((a or {}).get("contacts") or {}).values()),
                     "google_sk": gl.get("sk", 0), "google_de": gl.get("de", 0)})
    cur = [got[d] for d in days if got[d]]
    prev = [got[d] for d in prev_days]
    tot = merge(cur) if cur else None
    pv = merge(prev) if prev and all(prev) else None          # сравниваем, только если за прошлый период есть все дни

    def top(counter, k=8, other="другие"):
        items = Counter(counter).most_common()
        rest = sum(v for _, v in items[k:])
        return [list(x) for x in items[:k]] + ([[other, rest]] if rest else [])

    total = {"visitors": 0, "views": 0, "leads": 0, "google": 0, "own": 0, "contacts": 0, "contact_types": [],
             "contact_pages": [], "langs": [], "sources": [], "devices": [], "pages": [], "notfound": [], "leads_pages": []}
    if tot:
        total.update(
            visitors=tot["visitors"], views=tot["views"], leads=tot["leads"], google=tot["google"], own=tot["own"],
            langs=[[LANG_NAMES[k], tot["lang_visitors"][k]] for k in LANG_NAMES if tot["lang_visitors"].get(k)],
            sources=top(tot["sources"]), devices=top(tot["devices"]),
            pages=[[title_of(p), v] for p, v in tot["pages"].most_common(15)],
            notfound=[[p, v] for p, v in tot["notfound"].most_common(10)],
            leads_pages=[[title_of(p), v] for p, v in tot["lead_pages"].most_common(8)],
            contacts=sum(tot["contacts"].values()),
            contact_types=[[CONTACTS[k], tot["contacts"][k]] for k in CONTACTS if tot["contacts"].get(k)],
            contact_pages=[[title_of(p), v] for p, v in tot["contact_pages"].most_common(8)])
    return {"days": rows, "coverage": len(cur), "total": total,
            "prev": dict({k: pv[k] for k in ("visitors", "views", "leads", "google")},
                         contacts=sum(pv["contacts"].values()) if all("contacts" in x for x in prev) else None) if pv else None,
            "generated": datetime.now(TZ).strftime("%H:%M")}


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
            self.stop.wait(60)


if __name__ == "__main__":
    d = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else today()
    text = today_report() if d == today() else daily_report(d)
    print(re.sub(r"</?[bi]>", "", text))
