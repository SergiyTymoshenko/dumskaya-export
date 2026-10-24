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
import html
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from urllib.parse import unquote, urlsplit

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bratislava")
except Exception:  # noqa: BLE001
    TZ = timezone(timedelta(hours=1))

APP = os.path.expanduser("~/dumskaya")
LOG_GLOB = os.environ.get("SITE_LOG_GLOB", "/var/log/caddy/dumskaya*.log*")
SITE_DIR = os.environ.get("SITE_DIR", "/var/www/dumskaya/site")
LEADS_FILE = os.environ.get("LEADS_FILE", os.path.join(APP, "leads.jsonl"))
STATS_DIR = os.environ.get("STATS_DIR", os.path.join(APP, "stats"))
REPORT_HOUR = 9
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
                out.append({"page": d.get("page", ""), "lang": d.get("lang", "ru"), "model": d.get("model", "")})
    except OSError:
        pass
    return out


def aggregate(since_ts, until_ts):
    """Итоги за период: только числа и адреса страниц, без IP."""
    visitors = {}                                  # ключ (IP+браузер) → {src, dev, langs}
    views, lang_views, notfound = Counter(), Counter(), Counter()
    google, google_lang, bing, requests = 0, Counter(), 0, 0
    for ts, e in entries(since_ts, until_ts):
        requests += 1
        r = e.get("request") or {}
        if r.get("method") != "GET":
            continue
        h = r.get("headers") or {}
        ua = header(h, "User-Agent")
        path = unquote(urlsplit(r.get("uri") or "/").path) or "/"
        path = path.rstrip("/") or "/"
        if path.startswith(("/img/", "/_astro/", "/api/")) or ASSET.search(path):
            continue
        status = e.get("status")
        if "Googlebot" in ua:
            if status in (200, 304):
                google += 1
                google_lang[lang_of(path)] += 1
            continue
        if "bingbot" in ua.lower():
            if status in (200, 304):
                bing += 1
            continue
        human = (ua.startswith("Mozilla/") and not BOT.search(ua) and header(h, "Accept-Language")
                 and "prefetch" not in (header(h, "Sec-Purpose") + header(h, "Purpose")).lower())
        if not human:
            continue
        if status == 404:
            if not JUNK.search(path):
                notfound[path] += 1
            continue
        if status not in (200, 304):
            continue
        key = (r.get("client_ip") or r.get("remote_ip") or "") + "|" + ua
        v = visitors.get(key)
        if v is None:
            v = visitors[key] = {"src": source(header(h, "Referer")), "dev": device(ua), "langs": set()}
        v["langs"].add(lang_of(path))
        views[path] += 1
        lang_views[lang_of(path)] += 1
    leads = leads_between(since_ts, until_ts)
    return {
        "requests": requests,                      # 0 — за этот период журнала нет (ещё не вёлся или удалён)
        "visitors": len(visitors),
        "views": sum(views.values()),
        "lang_visitors": dict(Counter(l for v in visitors.values() for l in v["langs"])),
        "lang_views": dict(lang_views),
        "sources": dict(Counter(v["src"] for v in visitors.values())),
        "devices": dict(Counter(v["dev"] for v in visitors.values())),
        "pages": dict(views.most_common(50)),
        "notfound": dict(notfound.most_common(20)),
        "google": google, "google_lang": dict(google_lang), "bing": bing,
        "leads": len(leads), "lead_pages": dict(Counter(x["page"] for x in leads if x["page"])),
    }


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
    for f in glob.glob(os.path.join(STATS_DIR, "*.json")):
        if os.path.basename(f)[:10] < cutoff:
            try:
                os.remove(f)
            except OSError:
                pass


def day_stats(d, store=True):
    """Итоги прошедшего дня: из сохранённого файла или из журнала (и сохранить); None — данных за день нет."""
    agg = load_day(d)
    if agg is None:
        agg = aggregate(*day_bounds(d))
        if not agg["requests"]:
            return None
        if store and d < today():
            save_day(d, agg)
    return agg


def merge(aggs):
    """Сумма дней; None — если хотя бы за один день нет данных."""
    aggs = list(aggs)
    if not aggs or any(a is None for a in aggs):
        return None
    out = {"visitors": 0, "views": 0, "google": 0, "bing": 0, "leads": 0}
    for k in ("lang_visitors", "lang_views", "sources", "devices", "pages", "notfound", "google_lang", "lead_pages"):
        out[k] = Counter()
    for a in aggs:
        for k in ("visitors", "views", "google", "bing", "leads"):
            out[k] += a.get(k, 0)
        for k in ("lang_visitors", "lang_views", "sources", "devices", "pages", "notfound", "google_lang", "lead_pages"):
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


def line(counter, order=None, limit=6):
    items = list(counter.items())
    if order:
        items = [(k, counter.get(k, 0)) for k in order if counter.get(k)]
    else:
        items.sort(key=lambda kv: -kv[1])
    if not items:
        return "—"
    rest = sum(v for _, v in items[limit:])
    parts = [f"{esc(k)} {v}" for k, v in items[:limit]]
    if rest:
        parts.append(f"другие {rest}")
    return " · ".join(parts)


def delta(cur, prev):
    if prev is None:
        return ""
    d = cur - prev
    return f" ({'+' if d > 0 else ''}{d})" if d else " (без изменений)"


def body(a, prev=None, top=7):
    langs = {LANG_NAMES[k]: v for k, v in (a.get("lang_visitors") or {}).items()}
    out = [f"Посетители: <b>{a['visitors']}</b>{delta(a['visitors'], prev and prev['visitors'])} · "
           f"просмотров: {a['views']}{delta(a['views'], prev and prev['views'])}"]
    if a["visitors"]:
        out.append(f"Языки: {line(Counter(langs), order=list(LANG_NAMES.values()))}")
        out.append(f"Откуда: {line(Counter(a.get('sources') or {}))}")
        out.append(f"Устройства: {line(Counter(a.get('devices') or {}))}")
    leads = a.get("leads", 0)
    lp = Counter(a.get("lead_pages") or {})
    out.append(f"Заявки: <b>{leads}</b>{delta(leads, prev and prev.get('leads'))}"
               + (f" — {', '.join(esc(title_of(p)) for p, _ in lp.most_common(3))}" if lp else ""))
    pages = Counter(a.get("pages") or {}).most_common(top)
    if pages:
        out.append("\nПопулярные страницы:")
        out += [f"{i}. {esc(title_of(p))} — {n}" for i, (p, n) in enumerate(pages, 1)]
    nf = Counter(a.get("notfound") or {}).most_common(5)
    if nf:
        out.append("\nНе найдено (404): " + "; ".join(f"{esc(p)} — {n}" for p, n in nf))
    gl = Counter(a.get("google_lang") or {})
    new = " · ".join(f"{LANG_NAMES[k]} {gl[k]}" for k in ("sk", "de") if gl.get(k))
    out.append(f"\nРобот Google: {a.get('google', 0)} стр." + (f" (из них {new})" if new else "")
               + f" · Bing: {a.get('bing', 0)}")
    return "\n".join(out)


def day_name(d):
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}"


def daily_report(d):
    a = day_stats(d)
    if a is None:
        return f"📊 <b>Сайт за {day_name(d)}</b>\nЗа этот день в журнале сайта нет записей."
    prev = day_stats(d - timedelta(days=1))
    return f"📊 <b>Сайт за {day_name(d)}</b>\n" + body(a, prev)


def weekly_report(monday):
    """Неделя с понедельника monday по воскресенье — со сравнением с предыдущей."""
    days = [monday + timedelta(days=i) for i in range(7)]
    cur = [day_stats(d) for d in days]
    a = merge(x for x in cur if x is not None)
    b = merge(day_stats(d - timedelta(days=7)) for d in days)
    sun = days[-1]
    head = f"📈 <b>Сайт за неделю {monday.day} {MONTHS[monday.month - 1]} — {sun.day} {MONTHS[sun.month - 1]}</b>\n"
    if a is None:
        return head + "За эту неделю в журнале сайта нет записей."
    missing = sum(1 for x in cur if x is None)
    note = ["посетители — сумма по дням"]
    if missing:
        note.append(f"нет данных за {missing} дн.")
    note.append("в скобках — разница с прошлой неделей" if b else "сравнения с прошлой неделей пока нет")
    return head + f"<i>{'; '.join(note)}</i>\n" + body(a, b, top=10)


def today_report():
    d = today()
    start, _ = day_bounds(d)
    a = aggregate(start, time.time() + 1)
    y = day_stats(d - timedelta(days=1))
    hh = datetime.now(TZ).strftime("%H:%M")
    tail = (f"\n\nВчера: посетителей {y['visitors']}, просмотров {y['views']}, заявок {y.get('leads', 0)}"
            if y else "")
    return f"📊 <b>Сайт сегодня, до {hh}</b>\n" + body(a) + tail


NO_ACCESS = ("Не могу прочитать журнал сайта ({}) — у сервиса нет доступа. Выложите сайт ещё раз "
             "(npm run deploy спросит пароль sudo и откроет журнал для чтения).")


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

    def command(self):
        """Текст для команды /stats."""
        try:
            return today_report()
        except PermissionError:
            return NO_ACCESS.format(esc(LOG_GLOB))
        except Exception as e:  # noqa: BLE001
            self.log(f"статистика: ошибка {type(e).__name__}: {e}")
            return "Не получилось посчитать посетителей — ошибка записана в журнал сервиса."

    def tick(self):
        if not self.live_fn():
            return
        now = self.clock()
        d = now.date()
        last = self.bot.s.get("stats:daily") or ""
        if now.hour < REPORT_HOUR or last == d.isoformat():
            return
        y = d - timedelta(days=1)
        try:
            # дни, пропущенные, пока сервис не работал, — сохранить итоги, пока журнал их ещё помнит
            for k in range(7, 1, -1):
                if load_day(d - timedelta(days=k)) is None:
                    day_stats(d - timedelta(days=k))
            texts = [daily_report(y)]
            if d.weekday() == 0:
                texts.append(weekly_report(d - timedelta(days=7)))
        except PermissionError:
            texts = [NO_ACCESS.format(esc(LOG_GLOB))]
        self.bot.s.put("stats:daily", d.isoformat())
        for t in texts:
            self.bot.notify(t, roles=("owner",))

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
