#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Google Analytics 4 обоих сайтов — в «Графиках» бота и в утреннем сообщении (решено 29.10.2026).

Доступ — тот же служебный аккаунт Google Cloud, что у индекса Google (ключ ~/dumskaya/gsc-key.json, gsc_index.py):
владелец добавил его в ресурсы Google Analytics с ролью «Читатель». Нужны включённые в том же проекте Google Cloud
«Google Analytics Data API» (отчёты) и «Google Analytics Admin API» (найти ресурсы сайтов по их ключам G-…).
Ресурсы находятся сами по ключу потока данных: студия — G-23669WVTEG, каталог — G-WK9L25MVGN; если Admin API выключен —
номер ресурса можно вписать: python3 ga_stats.py --set home 560736295.

Что показываем (только посетители, которые приняли cookie: аналитика загружается после «Принять»):
  • за период «Графиков» — пользователи (новые), сеансы и вовлечённые, просмотры, время вовлечения, по дням (часам,
    месяцам), каналы (поиск Google, прямые, соцсети…), источники, страницы входа, популярные страницы, страны, города,
    устройства, события (заявки, нажатия на контакты…);
  • «1 час» — сейчас на сайте за 30 минут (отчёт в реальном времени);
  • утром — строка за вчера по каждому сайту (по понедельникам — и за неделю).
Отчёты кэшируются (сейчас — минута, сутки — 10 минут, дни — 30 минут, год и всё время — 6 часов): «Графики» можно
открывать сколько угодно, лимиты Google не тратятся. Данные Google за вчера к утру почти полные, днём ещё уточняются.
Ключ и токены не печатаются и не отдаются в «Графики». Только стандартная библиотека Python 3 и openssl (через gsc_index).

На сервере:
   python3 ~/dumskaya/deploy/ga_stats.py --status          — доступ, ресурсы, цифры за вчера и 7 дней
   python3 ~/dumskaya/deploy/ga_stats.py --set home 123    — номер ресурса вручную (studio или home; «-» — снова искать)
   python3 ~/dumskaya/deploy/ga_stats.py --morning         — какие строки уйдут в утреннее сообщение
"""
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bratislava")
except Exception:  # noqa: BLE001
    TZ = timezone(timedelta(hours=1))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsc_index  # noqa: E402  (ключ служебного аккаунта, токен, ответы-ошибки без открытых соединений)

APP = os.path.expanduser("~/dumskaya")
STATE_DIR = os.environ.get("GA_DIR", os.path.join(APP, "ga"))
SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
DATA = "https://analyticsdata.googleapis.com/v1beta"
ADMIN = "https://analyticsadmin.googleapis.com/v1beta"
TIMEOUT = 30
SITES = (("studio", "dumskaya-design.com", "G-23669WVTEG", "студия"), ("home", "dumskaya-home.com", "G-WK9L25MVGN", "магазин"))
FIND_EVERY = 86400                 # ресурсы искать заново раз в сутки (и сразу после ошибки доступа)
TTL = {"1h": 60, "24h": 600, "7": 1800, "30": 1800, "90": 1800, "365": 6 * 3600, "all": 6 * 3600}
START_ALL = "2020-01-01"           # «всё время»: раньше ресурсов GA4 у сайтов не было

CHANNELS = {"Organic Search": "Поиск (Google и др.)", "Direct": "Прямые заходы", "Referral": "Ссылки с других сайтов",
            "Organic Social": "Соцсети", "Paid Search": "Реклама в поиске", "Paid Social": "Реклама в соцсетях",
            "Email": "Письма", "Display": "Медийная реклама", "Organic Video": "Видео", "Paid Video": "Реклама в видео",
            "Organic Shopping": "Покупки (бесплатно)", "Paid Shopping": "Покупки (реклама)", "Cross-network": "Реклама Google (разные сети)",
            "Affiliates": "Партнёры", "SMS": "SMS", "Audio": "Аудио", "Mobile Push Notifications": "Уведомления",
            "Paid Other": "Другая реклама", "Unassigned": "Не определено", "(not set)": "Не определено"}
DEVICES = {"desktop": "Компьютер", "mobile": "Телефон", "tablet": "Планшет", "smart tv": "Телевизор"}
EVENTS = {"generate_lead": "Заявки с сайта", "contact_click": "Нажатия на контакты", "click": "Переходы на другие сайты",
          "file_download": "Скачивания файлов", "form_start": "Начали заполнять форму", "form_submit": "Отправили форму",
          "scroll": "Дочитали страницу до конца", "view_search_results": "Поиск по сайту", "video_start": "Смотрели видео"}
_C = (("SK", "Slovakia", "Словакия"), ("AT", "Austria", "Австрия"), ("UA", "Ukraine", "Украина"), ("DE", "Germany", "Германия"),
      ("CZ", "Czechia", "Чехия"), ("PL", "Poland", "Польша"), ("HU", "Hungary", "Венгрия"), ("US", "United States", "США"),
      ("GB", "United Kingdom", "Великобритания"), ("IT", "Italy", "Италия"), ("ES", "Spain", "Испания"), ("FR", "France", "Франция"),
      ("NL", "Netherlands", "Нидерланды"), ("BE", "Belgium", "Бельгия"), ("CH", "Switzerland", "Швейцария"), ("RO", "Romania", "Румыния"),
      ("BG", "Bulgaria", "Болгария"), ("HR", "Croatia", "Хорватия"), ("SI", "Slovenia", "Словения"), ("RS", "Serbia", "Сербия"),
      ("TR", "Türkiye", "Турция"), ("IE", "Ireland", "Ирландия"), ("PT", "Portugal", "Португалия"), ("DK", "Denmark", "Дания"),
      ("SE", "Sweden", "Швеция"), ("NO", "Norway", "Норвегия"), ("FI", "Finland", "Финляндия"), ("EE", "Estonia", "Эстония"),
      ("LV", "Latvia", "Латвия"), ("LT", "Lithuania", "Литва"), ("IL", "Israel", "Израиль"), ("CA", "Canada", "Канада"),
      ("AE", "United Arab Emirates", "ОАЭ"), ("MD", "Moldova", "Молдова"), ("BY", "Belarus", "Беларусь"), ("RU", "Russia", "Россия"),
      ("KZ", "Kazakhstan", "Казахстан"), ("GE", "Georgia", "Грузия"), ("GR", "Greece", "Греция"), ("CY", "Cyprus", "Кипр"),
      ("MT", "Malta", "Мальта"), ("LU", "Luxembourg", "Люксембург"), ("IN", "India", "Индия"), ("CN", "China", "Китай"),
      ("SG", "Singapore", "Сингапур"), ("ME", "Montenegro", "Черногория"), ("BA", "Bosnia & Herzegovina", "Босния и Герцеговина"),
      ("AL", "Albania", "Албания"), ("MK", "North Macedonia", "Северная Македония"), ("IS", "Iceland", "Исландия"))
COUNTRIES = {c: ru for c, _en, ru in _C}
COUNTRIES_EN = {en: ru for _c, en, ru in _C}
KNOWN = {"home": "560736295"}      # ресурс каталога (README, 28.10.2026) — если Admin API недоступен
NOT_SET = {"(not set)", "(other)", ""}

_lock = threading.Lock()
_cache = {}


def plural(n, one, few, many):
    n = abs(int(n)) % 100
    return many if 11 <= n <= 19 else one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many


def today():
    return datetime.now(TZ).date()


# ---------- доступ ----------
class GAError(Exception):
    """Ошибка Google Analytics — с понятным текстом на русском (что сделать)."""


def email():
    try:
        with open(gsc_index.KEY_FILE, encoding="utf-8") as fh:
            return json.load(fh).get("client_email") or ""
    except (OSError, ValueError):
        return ""


def explain(code, body, what=""):
    """Текст ошибки Google → что сделать, по-русски. Ключей и токенов в тексте нет (их там и не бывает)."""
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")
    try:
        err = json.loads(body or "{}").get("error") or {}
    except ValueError:
        err = {}
    if not isinstance(err, dict):
        err = {"message": str(err)}
    msg = str(err.get("message") or body or "")[:400]
    status = err.get("status") or ""
    reasons = {d.get("reason") for d in err.get("details") or [] if isinstance(d, dict)}
    if "SERVICE_DISABLED" in reasons or "has not been used in project" in msg or "is disabled" in msg:
        api = "Google Analytics Admin API" if "analyticsadmin" in msg or "Admin API" in msg else "Google Analytics Data API"
        link = re.search(r"https://console\.(?:developers|cloud)\.google\.com/apis/api/[^\s\"']+", msg)
        return (f"в Google Cloud не включён {api} — включите его в том же проекте, где ключ индекса Google: "
                + (f"{link.group(0)} → «Enable»" if link else f"console.cloud.google.com → «APIs & Services» → «Library» → {api} → «Enable»")
                + ", через 5 минут заработает")
    if code == 403 or status == "PERMISSION_DENIED":
        who = email() or "служебный аккаунт"
        return (f"у {who} нет доступа к ресурсу Google Analytics{(' ' + what) if what else ''} — Google Analytics → «Администратор» → "
                "«Управление доступом к ресурсу» → «+» → этот адрес, роль «Читатель»")
    if code == 429 or status == "RESOURCE_EXHAUSTED":
        return "Google временно ограничил число запросов к Analytics — цифры появятся позже сами"
    if code == 400 and "property" in msg.lower():
        return f"Google не нашёл ресурс{(' ' + what) if what else ''}: {msg}"
    return f"ответ Google {code}: {msg}" if code else msg


def call(url, body=None, what=""):
    """Запрос к Analytics с токеном служебного аккаунта; ошибка — GAError с понятным текстом."""
    if not gsc_index.have_key():
        raise GAError("на сервере нет ключа служебного аккаунта Google (~/dumskaya/gsc-key.json)")
    try:
        tok = gsc_index.token(SCOPE)
    except urllib.error.HTTPError as e:
        raw = e.read() if hasattr(e, "read") else b""
        raise GAError("Google не выдал доступ к Analytics: " + explain(e.code, raw, what)) from None
    except (OSError, ValueError, KeyError) as e:
        raise GAError(f"ключ Google не прочитался: {type(e).__name__}") from None
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    try:
        raw = gsc_index._fetch(req, TIMEOUT)
    except urllib.error.HTTPError as e:
        raise GAError(explain(e.code, e.read(), what)) from None
    except OSError as e:
        raise GAError(f"Google Analytics не ответил: {type(e).__name__}") from None
    return json.loads(raw) if raw.strip() else {}


# ---------- какие ресурсы у сайтов ----------
def _props_path():
    return os.path.join(STATE_DIR, "properties.json")


def _load_props():
    try:
        with open(_props_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_props(d):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(_props_path() + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1)
    os.replace(_props_path() + ".tmp", _props_path())


def find(force=False):
    """{"sites": {studio|home: {"property": "123", "name": …}}, "manual": {…}, "error": …} — по ключам потоков G-…
    (Admin API: список ресурсов, у каждого — потоки данных); номера, вписанные вручную, важнее найденных."""
    with _lock:
        st = _load_props()
        fresh = FIND_EVERY if (st.get("sites") or not st.get("error")) else 600     # после ошибки — снова через 10 минут
        if not force and st.get("at", 0) > time.time() - fresh:
            return st
        found, err = {}, None
        try:
            props, token = [], ""
            while True:
                d = call(f"{ADMIN}/accountSummaries?pageSize=200" + (f"&pageToken={token}" if token else ""))
                for acc in d.get("accountSummaries") or []:
                    props += [(p.get("property") or "", p.get("displayName") or "") for p in acc.get("propertySummaries") or []]
                token = d.get("nextPageToken") or ""
                if not token:
                    break
            want = {mid: key for key, _host, mid, _n in SITES}
            hosts = {host: key for key, host, _mid, _n in SITES}
            for prop, name in props:
                streams = call(f"{ADMIN}/{prop}/dataStreams").get("dataStreams") or []
                for s in streams:
                    w = s.get("webStreamData") or {}
                    key = want.get(w.get("measurementId") or "") or hosts.get(re.sub(r"^https?://(www\.)?", "", w.get("defaultUri") or "").strip("/"))
                    if key and key not in found:
                        found[key] = {"property": prop.split("/")[-1], "name": name, "stream": w.get("measurementId") or ""}
            if not props:
                err = (f"служебному аккаунту {email() or ''} не открыт ни один ресурс Google Analytics — добавьте его "
                       "в ресурсы сайтов: «Администратор» → «Управление доступом к ресурсу», роль «Читатель»").replace("  ", " ")
        except GAError as e:
            err = str(e)
        st = {"at": int(time.time()), "sites": found, "manual": st.get("manual") or {}, "error": err}
        _save_props(st)
        return st


def property_of(key):
    """Номер ресурса сайта (вписанный вручную или найденный) или None."""
    st = find()
    return ((st.get("manual") or {}).get(key) or ((st.get("sites") or {}).get(key) or {}).get("property")
            or (KNOWN.get(key) if st.get("error") else None))


def set_property(key, value):
    st = _load_props()
    manual = st.get("manual") or {}
    if value in ("-", "", None):
        manual.pop(key, None)
    else:
        if not str(value).isdigit():
            raise ValueError("номер ресурса — только цифры (Google Analytics → «Администратор» → «Сведения о ресурсе»)")
        manual[key] = str(value)
    st["manual"], st["at"] = manual, 0                 # и найти остальное заново
    _save_props(st)
    _cache.clear()


# ---------- отчёты ----------
def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    return int(f) if f.is_integer() else f


def rows(resp, dims, mets):
    """Ответ runReport → [{dim: значение, met: число}]."""
    out = []
    for r in resp.get("rows") or []:
        x = {d: (r.get("dimensionValues") or [{}] * len(dims))[i].get("value", "") for i, d in enumerate(dims)}
        x.update({m: _num((r.get("metricValues") or [{}] * len(mets))[i].get("value")) for i, m in enumerate(mets)})
        out.append(x)
    return out


def ranges(period):
    """(текущий период, прошлый или None, единица ряда) для runReport — даты по часовому поясу ресурса.
    «24 часа»: ряд по часам за вчера и сегодня, итоги — сегодня (с полуночи) рядом со вчера."""
    if period == "24h":
        return {"startDate": "yesterday", "endDate": "today"}, {"startDate": "yesterday", "endDate": "yesterday"}, "hour"
    if period == "all":
        return {"startDate": START_ALL, "endDate": "today"}, None, "month"
    n = int(period) if str(period).isdigit() else 7
    cur = {"startDate": f"{n - 1}daysAgo" if n > 1 else "today", "endDate": "today"}
    prev = {"startDate": f"{2 * n - 1}daysAgo", "endDate": f"{n}daysAgo"}
    return cur, prev, "month" if n >= 365 else "day"


TOTAL_METRICS = ["activeUsers", "newUsers", "sessions", "engagedSessions", "screenPageViews", "userEngagementDuration"]


def _totals(r):
    if not r:
        return None
    users = r.get("activeUsers", 0)
    return {"users": users, "new_users": r.get("newUsers", 0), "sessions": r.get("sessions", 0),
            "engaged": r.get("engagedSessions", 0), "views": r.get("screenPageViews", 0),
            "avg_time": round(r.get("userEngagementDuration", 0) / users) if users else None}


def _label_country(code, name):
    return COUNTRIES.get(code) or COUNTRIES_EN.get(name) or (name if name not in NOT_SET else "Не определено")


def report(prop, period):
    """Отчёт ресурса за период «Графиков» (кроме «1 час») — двумя пачками запросов (batchRunReports, по 5)."""
    cur, prev, unit = ranges(period)
    dr = ([{"startDate": "today", "endDate": "today"}] if period == "24h" else [cur]) + ([prev] if prev else [])
    dim_series = {"hour": "dateHour", "day": "date", "month": "yearMonth"}[unit]
    top = lambda d, m, n=15: {"dateRanges": [cur], "dimensions": [{"name": x} for x in d], "metrics": [{"name": x} for x in m],  # noqa: E731
                              "orderBys": [{"metric": {"metricName": m[0]}, "desc": True}], "limit": n}
    a = [{"dateRanges": dr, "metrics": [{"name": x} for x in TOTAL_METRICS]},
         {"dateRanges": [cur], "dimensions": [{"name": dim_series}], "metrics": [{"name": x} for x in ("activeUsers", "sessions", "screenPageViews")],
          "orderBys": [{"dimension": {"dimensionName": dim_series}}], "limit": 2000},
         top(["sessionDefaultChannelGroup"], ["sessions", "activeUsers"], 20),
         top(["sessionSourceMedium"], ["sessions", "activeUsers"]),
         top(["landingPage"], ["sessions", "engagedSessions"])]
    b = [top(["pagePath", "pageTitle"], ["screenPageViews", "activeUsers", "userEngagementDuration"], 20),
         top(["countryId", "country"], ["activeUsers"]),
         top(["city"], ["activeUsers"]),
         top(["deviceCategory"], ["activeUsers"], 5),
         top(["eventName"], ["eventCount"], 40)]
    got = []
    for part in (a, b):
        got += call(f"{DATA}/properties/{prop}:batchRunReports", {"requests": part}, prop).get("reports") or []
    if len(got) < 10:
        raise GAError("Google вернул неполный отчёт — попробуйте открыть «Графики» ещё раз")
    tot = rows(got[0], ["dateRange"] if prev else [], TOTAL_METRICS)
    pick = lambda k: next((x for x in tot if x.get("dateRange", "date_range_0") == k), None)  # noqa: E731
    out = {"unit": unit, "totals": _totals(pick("date_range_0") if prev else (tot[0] if tot else {})) or _totals({"activeUsers": 0}),
           "prev": (_totals(pick("date_range_1")) or _totals({"activeUsers": 0})) if prev else None,
           "compare": "yesterday" if period == "24h" else "prev" if prev else None}
    series = rows(got[1], [dim_series], ["activeUsers", "sessions", "screenPageViews"])
    tzname = (got[1].get("metadata") or {}).get("timeZone") or ""
    out["series"] = _fill(series, dim_series, unit, period, tzname)
    out["channels"] = [[CHANNELS.get(r["sessionDefaultChannelGroup"], r["sessionDefaultChannelGroup"]), r["sessions"], r["activeUsers"]]
                       for r in rows(got[2], ["sessionDefaultChannelGroup"], ["sessions", "activeUsers"]) if r["sessions"]]
    out["sources"] = [[_src(r["sessionSourceMedium"]), r["sessions"], r["activeUsers"]]
                      for r in rows(got[3], ["sessionSourceMedium"], ["sessions", "activeUsers"]) if r["sessions"]]
    out["landing"] = [[r["landingPage"] if r["landingPage"] not in NOT_SET else "Не определено", r["sessions"], r["engagedSessions"]]
                      for r in rows(got[4], ["landingPage"], ["sessions", "engagedSessions"]) if r["sessions"]]
    out["pages"] = [[r["pagePath"], r["screenPageViews"], round(r["userEngagementDuration"] / r["activeUsers"]) if r["activeUsers"] else None,
                     r["pageTitle"] if r["pageTitle"] not in NOT_SET else ""]
                    for r in rows(got[5], ["pagePath", "pageTitle"], ["screenPageViews", "activeUsers", "userEngagementDuration"]) if r["screenPageViews"]]
    out["countries"] = [[_label_country(r["countryId"], r["country"]), r["activeUsers"]]
                        for r in rows(got[6], ["countryId", "country"], ["activeUsers"]) if r["activeUsers"]]
    out["cities"] = [[r["city"] if r["city"] not in NOT_SET else "Не определено", r["activeUsers"]]
                     for r in rows(got[7], ["city"], ["activeUsers"]) if r["activeUsers"]]
    out["devices"] = [[DEVICES.get(r["deviceCategory"], r["deviceCategory"] or "Не определено"), r["activeUsers"]]
                      for r in rows(got[8], ["deviceCategory"], ["activeUsers"]) if r["activeUsers"]]
    ev = {r["eventName"]: r["eventCount"] for r in rows(got[9], ["eventName"], ["eventCount"])}
    out["events"] = [[name, ev[k]] for k, name in EVENTS.items() if ev.get(k)]
    out["leads"], out["contacts"] = ev.get("generate_lead", 0), ev.get("contact_click", 0)
    return out


def _src(s):
    s = s or ""
    if s in NOT_SET:
        return "Не определено"
    return s.replace("(direct) / (none)", "прямые заходы").replace(" / organic", " · поиск").replace(" / referral", " · ссылка") \
            .replace(" / cpc", " · реклама").replace(" / (not set)", "")


def _zone(name):
    try:
        return ZoneInfo(name) if name else TZ
    except Exception:  # noqa: BLE001
        return TZ


def _fill(series, dim, unit, period, tzname=""):
    """Ряд без пропусков: дни и месяцы без посетителей Google не присылает — ставим нули. Даты — «ГГГГ-ММ-ДД»,
    по часовому поясу ресурса (его сообщает Google)."""
    def key(v):
        if unit == "hour":
            return f"{v[:4]}-{v[4:6]}-{v[6:8]}T{v[8:10]}"
        if unit == "month":
            return f"{v[:4]}-{v[4:6]}-01"
        return f"{v[:4]}-{v[4:6]}-{v[6:8]}"
    got = {key(r[dim]): r for r in series if r.get(dim)}
    zone = _zone(tzname)
    t = datetime.now(zone).date()
    if unit == "hour":
        now = datetime.now(zone).replace(minute=0, second=0, microsecond=0)
        want = [(now - timedelta(hours=k)).strftime("%Y-%m-%dT%H") for k in range(23, -1, -1)]
    elif unit == "day":
        n = int(period) if str(period).isdigit() else 7
        want = [(t - timedelta(days=k)).isoformat() for k in range(n - 1, -1, -1)]
    else:
        first = min(got) if got else t.replace(day=1).isoformat()
        if period == "365":
            first = max(first, (t - timedelta(days=364)).replace(day=1).isoformat())
        want, y, m = [], int(first[:4]), int(first[5:7])
        while (y, m) <= (t.year, t.month):
            want.append(f"{y:04d}-{m:02d}-01")
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    out = []
    for k in want:
        r = got.get(k) or {}
        x = {"date": k[:10], "users": r.get("activeUsers", 0), "sessions": r.get("sessions", 0), "views": r.get("screenPageViews", 0)}
        if unit == "hour":
            x["hour"] = int(k[11:13])
        out.append(x)
    if out:
        out[-1]["partial"] = True                     # текущий час, день или месяц ещё идёт
    return out


def realtime(prop):
    """Сейчас на сайте — последние 30 минут (отчёт в реальном времени)."""
    def rt(dims, n=10):
        body = {"metrics": [{"name": "activeUsers"}], "limit": n}
        if dims:
            body["dimensions"] = [{"name": d} for d in dims]
            body["orderBys"] = [{"metric": {"metricName": "activeUsers"}, "desc": True}]
        return rows(call(f"{DATA}/properties/{prop}:runRealtimeReport", body, prop), dims, ["activeUsers"])
    tot = rt([])
    return {"unit": "realtime", "users": tot[0]["activeUsers"] if tot else 0,
            "pages": [[r["unifiedScreenName"] if r["unifiedScreenName"] not in NOT_SET else "Не определено", r["activeUsers"]]
                      for r in rt(["unifiedScreenName"])],
            "countries": [[_label_country("", r["country"]), r["activeUsers"]] for r in rt(["country"])],
            "devices": [[DEVICES.get(r["deviceCategory"], r["deviceCategory"]), r["activeUsers"]] for r in rt(["deviceCategory"], 5)]}


def site_report(key, period):
    """Карточка одного сайта: {"key", "host", "name", "property", …отчёт} или {"error"} — с кэшем на TTL."""
    host, name = next((h, n) for k, h, _m, n in SITES if k == key)
    out = {"key": key, "host": host, "name": name}
    prop = property_of(key)
    if not prop:
        st = find()
        out["error"] = st.get("error") or (f"ресурс Google Analytics сайта {host} не найден: служебному аккаунту {email()} не дан доступ "
                                           "к этому ресурсу (роль «Читатель»)")
        return out
    out["property"] = prop
    ck = (prop, period)
    hit = _cache.get(ck)
    if hit and hit[0] > time.time() - TTL.get(period, 1800):
        out.update(hit[1])
        return out
    try:
        data = realtime(prop) if period == "1h" else report(prop, period)
        data["fetched"] = int(time.time())
    except GAError as e:
        if "нет доступа" in str(e) or "не нашёл ресурс" in str(e):
            st = _load_props()                         # ресурс могли пересоздать — в следующий раз искать заново
            st["at"] = 0
            _save_props(st)
        out["error"] = str(e)
        return out
    except (KeyError, IndexError, TypeError, ValueError) as e:
        out["error"] = f"Google ответил не так, как ожидалось ({type(e).__name__}) — попробуйте позже"
        return out
    _cache[ck] = (time.time(), data)
    if len(_cache) > 64:                               # старые периоды — из памяти
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:16]:
            _cache.pop(k, None)
    out.update(data)
    return out


def web_data(site="studio", period="7"):
    """Карточка «Google Analytics» в «Графиках»: один сайт или оба («all»)."""
    keys = [k for k, *_ in SITES] if site == "all" else [site if site in ("studio", "home") else "studio"]
    out = {"key": gsc_index.have_key(), "period": period, "sites": []}
    if not out["key"]:
        return out
    out["sites"] = [site_report(k, period) for k in keys]
    return out


# ---------- утро ----------
def _arrow(cur, prev):
    if prev is None or cur == prev:
        return ""
    return f" {'▲' if cur > prev else '▼'}{abs(cur - prev)}"


def _short(t, prev):
    u, s = t["users"], t["sessions"]
    return (f"<b>{u}</b> {plural(u, 'пользователь', 'пользователя', 'пользователей')}{_arrow(u, prev and prev['users'])}"
            + (f" (новых {t['new_users']})" if t["new_users"] and t["new_users"] != u else "")
            + f" · {s} {plural(s, 'сеанс', 'сеанса', 'сеансов')}")


def morning_lines(d=None):
    """Строки в утреннее сообщение: «📊 Google Analytics · студия: 18 пользователей ▲3 (новых 15) · 22 сеанса ·
    поиск 9, прямые 7» за вчера; по понедельникам — и за неделю. Нет ключа — []; нет доступа — одна строка с причиной."""
    if not gsc_index.have_key():
        return []
    d = d or today()
    week = d.weekday() == 0
    lines, errors = [], []
    for key, host, _mid, name in SITES:
        prop = property_of(key)
        if not prop:
            continue
        try:
            reqs = [{"dateRanges": [{"startDate": "yesterday", "endDate": "yesterday"}, {"startDate": "2daysAgo", "endDate": "2daysAgo"}],
                     "metrics": [{"name": x} for x in TOTAL_METRICS]},
                    {"dateRanges": [{"startDate": "yesterday", "endDate": "yesterday"}], "dimensions": [{"name": "sessionDefaultChannelGroup"}],
                     "metrics": [{"name": "sessions"}], "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}], "limit": 3}]
            if week:
                reqs.append({"dateRanges": [{"startDate": "7daysAgo", "endDate": "yesterday"}, {"startDate": "14daysAgo", "endDate": "8daysAgo"}],
                             "metrics": [{"name": x} for x in TOTAL_METRICS]})
            got = call(f"{DATA}/properties/{prop}:batchRunReports", {"requests": reqs}, prop).get("reports") or []
        except GAError as e:
            errors.append(f"{name}: {e}")
            continue
        tot = {r["dateRange"]: r for r in rows(got[0], ["dateRange"], TOTAL_METRICS)} if got else {}
        y, p = _totals(tot.get("date_range_0")), _totals(tot.get("date_range_1"))
        if not y and not p:
            continue                                   # данных ещё нет (сайт не на домене или никто не принимал cookie)
        if not y:
            lines.append(f"📊 Google Analytics · {name}: вчера данных нет (позавчера — {p['users']})")
            continue
        ch = [f"{CHANNELS.get(r['sessionDefaultChannelGroup'], r['sessionDefaultChannelGroup']).lower()} {r['sessions']}"
              for r in rows(got[1], ["sessionDefaultChannelGroup"], ["sessions"]) if r["sessions"]] if len(got) > 1 else []
        line = f"📊 Google Analytics · {name}: " + _short(y, p) + (" · " + ", ".join(ch) if ch else "")
        if week and len(got) > 2:
            wt = {r["dateRange"]: r for r in rows(got[2], ["dateRange"], TOTAL_METRICS)}
            w, wp = _totals(wt.get("date_range_0")), _totals(wt.get("date_range_1"))
            if w:
                line += "\n   за неделю: " + _short(w, wp)
        lines.append(line)
    if errors and not lines:
        lines.append("📊 Google Analytics: " + "; ".join(errors[:2]))
    elif errors:
        lines.append("📊 Google Analytics — не всё: " + "; ".join(errors[:2]))
    if not lines:
        st = find()
        if st.get("error"):
            lines.append("📊 Google Analytics: " + st["error"])
    return lines


# ---------- с сервера ----------
def status():
    print("Google Analytics 4 · " + datetime.now(TZ).strftime("%d.%m.%Y %H:%M"))
    if not gsc_index.have_key():
        print("✗ нет ключа служебного аккаунта (~/dumskaya/gsc-key.json) — тот же ключ, что у индекса Google")
        return 1
    print(f"служебный аккаунт: {email()}")
    st = find(force=True)
    if st.get("error"):
        print("✗ поиск ресурсов: " + st["error"])
    for key, host, mid, name in SITES:
        man = (st.get("manual") or {}).get(key)
        f = (st.get("sites") or {}).get(key)
        prop = man or (f or {}).get("property")
        print(f"\n{host} ({mid}): " + (f"ресурс {prop}" + (" (вписан вручную)" if man else f" «{f.get('name', '')}»") if prop else "ресурс не найден"))
        if not prop:
            continue
        for period, title in (("1h", "сейчас (30 минут)"), ("7", "7 дней")):
            r = site_report(key, period)
            if r.get("error"):
                print(f"  ✗ {title}: {r['error']}")
                continue
            if period == "1h":
                print(f"  ✓ {title}: на сайте {r['users']}")
            else:
                t = r["totals"]
                print(f"  ✓ {title}: пользователей {t['users']} (новых {t['new_users']}), сеансов {t['sessions']}, "
                      f"просмотров {t['views']}" + (f", заявок {r['leads']}" if r.get("leads") else "")
                      + (f", нажатий на контакты {r['contacts']}" if r.get("contacts") else ""))
                if r["channels"]:
                    print("    каналы: " + ", ".join(f"{c[0]} {c[1]}" for c in r["channels"][:5]))
    print("\nутренние строки:")
    for ln in morning_lines():
        print("  " + re.sub(r"</?b>", "", ln))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--set"] and len(a) == 3 and a[1] in ("studio", "home"):
        try:
            set_property(a[1], a[2])
        except ValueError as e:
            sys.exit(f"✗ {e}")
        print(f"✓ {a[1]}: " + ("ищу ресурс сам" if a[2] == "-" else f"ресурс {a[2]}"))
        sys.exit(status())
    if a[:1] == ["--morning"]:
        print("\n".join(re.sub(r"</?b>", "", x) for x in morning_lines()) or "строк нет")
        sys.exit(0)
    if a[:1] in (["--status"], []):
        sys.exit(status())
    print(__doc__)
