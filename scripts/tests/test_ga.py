"""Проверка Google Analytics 4 (deploy/ga_stats.py, решено 29.10.2026): ресурсы сайтов находятся по ключам G-…,
отчёт за периоды «Графиков» (итоги и сравнение, ряд без пропусков, каналы, источники, страницы, страны, устройства,
события), «сейчас на сайте», кэш, понятные ошибки (API выключен, нет доступа), номер ресурса вручную, утренние строки,
адрес /api/stats/ga только для разработчика и дизайнера. Google подменён — сеть не нужна.

   python3 scripts/tests/test_ga.py      — в конце «OK: N проверок»"""
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402
import gsc_index  # noqa: E402
import ga_stats as GA  # noqa: E402

ok = 0


def check(cond, what):
    global ok
    if not cond:
        raise AssertionError(what)
    ok += 1


CALLS = []
FAIL = {}                     # часть адреса → (код, тело ошибки)
EMAIL = "reader@dumskaya.iam.gserviceaccount.com"
now = datetime.now(GA.TZ)
ymd = lambda d: d.strftime("%Y%m%d")                    # noqa: E731


def report_for(req):
    dims = [d["name"] for d in req.get("dimensions") or []]
    mets = [m["name"] for m in req.get("metrics") or []]
    nr = len(req.get("dateRanges") or [])

    def row(dv, mv):
        return {"dimensionValues": [{"value": v} for v in dv], "metricValues": [{"value": str(v)} for v in mv]}
    if not dims:
        if nr > 1:
            base = {"activeUsers": 40, "newUsers": 31, "sessions": 52, "engagedSessions": 39, "screenPageViews": 140,
                    "userEngagementDuration": 4800, "keyEvents": 3}
            prev = {k: int(v * 0.75) for k, v in base.items()}
            rr = [row(["date_range_0"], [base[m] for m in mets]), row(["date_range_1"], [prev[m] for m in mets])]
        else:
            rr = [row([], [40 if m == "activeUsers" else 10 for m in mets])]
    elif dims == ["date"]:
        rr = [row([ymd(now - timedelta(days=k))], [5 + k, 6 + k, 20]) for k in (0, 2, 3)]     # вчера — без посетителей
    elif dims == ["dateHour"]:
        rr = [row([(now - timedelta(hours=k)).strftime("%Y%m%d%H")], [2, 3, 7]) for k in (0, 1, 5)]
    elif dims == ["yearMonth"]:
        rr = [row([now.strftime("%Y%m")], [33, 40, 120])]
    else:
        canned = {
            "sessionDefaultChannelGroup": [(["Organic Search"], [20, 18]), (["Direct"], [10, 9]), (["Unassigned"], [1, 1])],
            "sessionSourceMedium": [(["google / organic"], [20, 18]), (["(direct) / (none)"], [10, 9])],
            "landingPage": [(["/"], [12, 9]), (["(not set)"], [1, 0])],
            "pagePath": [(["/", "Студия дизайна интерьера в Братиславе"], [30, 20, 1200]), (["/kontakty", "(not set)"], [8, 6, 0])],
            "countryId": [(["SK", "Slovakia"], [25]), (["AT", "Austria"], [10]), (["", "(not set)"], [1])],
            "city": [(["Bratislava"], [20]), (["(not set)"], [3])],
            "deviceCategory": [(["mobile"], [25]), (["desktop"], [15])],
            "eventName": [(["page_view"], [80]), (["generate_lead"], [2]), (["contact_click"], [5]), (["scroll"], [30]), (["session_start"], [50])],
        }[dims[0]]
        rr = [row(d, m) for d, m in canned]
    return {"rows": rr, "metadata": {"timeZone": "Europe/Bratislava"}}


def realtime_for(req):
    dims = [d["name"] for d in req.get("dimensions") or []]
    v = {(): [([], [3])], ("unifiedScreenName",): [(["Главная"], [2]), (["Контакты"], [1])],
         ("country",): [(["Slovakia"], [2]), (["Austria"], [1])], ("deviceCategory",): [(["mobile"], [2]), (["desktop"], [1])]}[tuple(dims)]
    return {"rows": [{"dimensionValues": [{"value": x} for x in d], "metricValues": [{"value": str(x)} for x in m]} for d, m in v]}


def fake_fetch(req, timeout):
    url = req.full_url
    CALLS.append(url)
    for part, (code, body) in FAIL.items():
        if part in url:
            raise urllib.error.HTTPError(url, code, "err", {}, io.BytesIO(json.dumps(body).encode()))
    body = json.loads(req.data) if req.data else {}
    if "accountSummaries" in url:
        d = {"accountSummaries": [{"account": "accounts/1", "propertySummaries": [
            {"property": "properties/111", "displayName": "dumskaya-design.com"}, {"property": "properties/222", "displayName": "DUMSKAYA HOME"},
            {"property": "properties/333", "displayName": "чужой сайт"}]}]}
    elif "/dataStreams" in url:
        mid = {"111": "G-23669WVTEG", "222": "G-WK9L25MVGN", "333": "G-OTHER"}[url.split("/properties/")[1].split("/")[0]]
        d = {"dataStreams": [{"type": "WEB_DATA_STREAM", "webStreamData": {"measurementId": mid, "defaultUri": "https://example.org"}}]}
    elif url.endswith(":batchRunReports"):
        check(len(body["requests"]) <= 5, "в пачке не больше 5 отчётов (так позволяет Google)")
        d = {"reports": [report_for(r) for r in body["requests"]]}
    elif url.endswith(":runRealtimeReport"):
        d = realtime_for(body)
    else:
        raise AssertionError("неожиданный адрес " + url)
    return json.dumps(d).encode()


gsc_index._fetch = fake_fetch
gsc_index.token = lambda scope=None: "test-token"
GA._cache.clear()

# ---------- 1. ключа нет — ничего не делаем ----------
check(not gsc_index.have_key(), "на стенде ключа нет")
check(GA.web_data("studio", "7") == {"key": False, "period": "7", "sites": []} and GA.morning_lines() == [] and not CALLS,
      "без ключа — карточка «выключено», утром строк нет, к Google не обращаемся")

# ---------- 2. ресурсы находятся по ключам G-… ----------
os.makedirs(os.path.dirname(gsc_index.KEY_FILE), exist_ok=True)
json.dump({"client_email": EMAIL, "private_key": "x"}, open(gsc_index.KEY_FILE, "w"))
st = GA.find(force=True)
check(st["sites"]["studio"]["property"] == "111" and st["sites"]["home"]["property"] == "222" and not st["error"],
      f"ресурсы найдены по ключам потоков: {st}")
n = len(CALLS)
check(GA.property_of("studio") == "111" and GA.property_of("home") == "222" and len(CALLS) == n, "найденное запоминается — Admin API не дёргаем каждый раз")

# ---------- 3. отчёт за 7 дней ----------
n = len(CALLS)
d = GA.web_data("studio", "7")
x = d["sites"][0]
check(d["key"] and x["host"] == "dumskaya-design.com" and x["property"] == "111" and not x.get("error"), "карточка студии")
check(len(CALLS) - n == 2, "отчёт — двумя пачками запросов")
check(x["totals"]["users"] == 40 and x["prev"]["users"] == 30 and x["totals"]["new_users"] == 31 and x["totals"]["avg_time"] == 120
      and x["compare"] == "prev", f"итоги и прошлый период: {x['totals']} / {x['prev']}")
s = x["series"]
check(len(s) == 7 and s[-1]["partial"] and s[-2]["users"] == 0 and s[-1]["users"] == 5 and s[-3]["users"] == 7,
      f"ряд по дням без пропусков: день без посетителей — 0, сегодня идёт {s}")
check(x["channels"] == [["Поиск (Google и др.)", 20, 18], ["Прямые заходы", 10, 9], ["Не определено", 1, 1]], f"каналы по-русски {x['channels']}")
check(x["sources"][0][0] == "google · поиск" and x["sources"][1][0] == "прямые заходы", f"источники {x['sources']}")
check(x["landing"][1][0] == "Не определено", "страница входа «(not set)» — «Не определено»")
check(x["pages"][0] == ["/", 30, 60, "Студия дизайна интерьера в Братиславе"] and x["pages"][1][3] == "", f"страницы: просмотры, время, заголовок {x['pages']}")
check(x["countries"][:2] == [["Словакия", 25], ["Австрия", 10]] and x["countries"][2][0] == "Не определено", f"страны {x['countries']}")
check(x["cities"] == [["Bratislava", 20], ["Не определено", 3]] and x["devices"] == [["Телефон", 25], ["Компьютер", 15]], "города и устройства")
check(x["events"] == [["Заявки с сайта", 2], ["Нажатия на контакты", 5], ["Дочитали страницу до конца", 30]] and x["leads"] == 2 and x["contacts"] == 5,
      f"действия: заявки, контакты; служебные события не показываем {x['events']}")
n = len(CALLS)
GA.web_data("studio", "7")
check(len(CALLS) == n, "повторное открытие «Графиков» — из кэша, без запросов к Google")

# ---------- 4. другие периоды ----------
x = GA.web_data("studio", "24h")["sites"][0]
check(x["compare"] == "yesterday" and x["unit"] == "hour" and len(x["series"]) == 24 and x["series"][-1]["hour"] == now.hour
      and x["series"][-1]["users"] == 2 and x["series"][-3]["users"] == 0, "24 часа: по часам, итоги — сегодня рядом со вчера")
x = GA.web_data("studio", "365")["sites"][0]
check(x["unit"] == "month" and x["series"][-1]["date"] == now.strftime("%Y-%m-01") and x["series"][-1]["users"] == 33 and x["prev"], "год — по месяцам, со сравнением")
x = GA.web_data("studio", "all")["sites"][0]
check(x["unit"] == "month" and x["prev"] is None and x["compare"] is None, "всё время — без сравнения")
x = GA.web_data("studio", "1h")["sites"][0]
check(x["unit"] == "realtime" and x["users"] == 3 and x["countries"] == [["Словакия", 2], ["Австрия", 1]] and x["pages"][0] == ["Главная", 2],
      f"сейчас на сайте: 30 минут, страны по-русски {x}")
both = GA.web_data("all", "30")
check([s["host"] for s in both["sites"]] == ["dumskaya-design.com", "dumskaya-home.com"] and both["sites"][1]["property"] == "222", "«Оба» — оба сайта")

# ---------- 5. понятные ошибки ----------
GA._cache.clear()
FAIL[":batchRunReports"] = (403, {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "Google Analytics Data API has not been used in project 4242 before or it is disabled. Enable it by visiting https://console.developers.google.com/apis/api/analyticsdata.googleapis.com/overview?project=4242 then retry.",
                                            "details": [{"reason": "SERVICE_DISABLED"}]}})
e = GA.web_data("studio", "7")["sites"][0]["error"]
check("не включён Google Analytics Data API" in e and "analyticsdata.googleapis.com/overview?project=4242" in e and "Enable" in e,
      f"API выключен — что включить и где: {e}")
FAIL[":batchRunReports"] = (403, {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "User does not have sufficient permissions for this property."}})
e = GA.web_data("studio", "30")["sites"][0]["error"]
check(EMAIL in e and "«Читатель»" in e and "Управление доступом к ресурсу" in e, f"нет доступа — кому и как дать: {e}")
check(GA._load_props()["at"] == 0, "после «нет доступа» ресурсы ищутся заново")
FAIL.clear()
FAIL["accountSummaries"] = (403, {"error": {"code": 403, "message": "Google Analytics Admin API has not been used in project 4242 before or it is disabled.",
                                            "details": [{"reason": "SERVICE_DISABLED"}]}})
GA._cache.clear()
st = GA.find(force=True)
check("Google Analytics Admin API" in st["error"] and GA.property_of("home") == "560736295" and GA.property_of("studio") is None,
      "Admin API выключен — каталог по известному номеру, у студии — причина")
x = GA.web_data("studio", "7")["sites"][0]
check("Admin API" in x["error"], "в карточке студии — что включить")
GA.set_property("studio", "999")
check(GA.property_of("studio") == "999", "номер ресурса вручную")
try:
    GA.set_property("home", "abc")
    bad = False
except ValueError:
    bad = True
check(bad, "номер ресурса — только цифры")
GA.set_property("studio", "-")
FAIL.clear()
GA.find(force=True)
check(GA.property_of("studio") == "111", "«-» — снова искать самому")

# ---------- 6. утро ----------
GA._cache.clear()
monday = now.date() - timedelta(days=now.weekday())
lines = GA.morning_lines(monday + timedelta(days=1))
check(len(lines) == 2 and lines[0].startswith("📊 Google Analytics · студия: <b>40</b> пользователей ▲10 (новых 31) · 52 сеанса")
      and "поиск (google и др.) 20, прямые заходы 10" in lines[0] and "за неделю" not in lines[0], f"утром — строка за вчера по каждому сайту {lines}")
lines = GA.morning_lines(monday)
check("за неделю: <b>40</b>" in lines[0], "по понедельникам — и за неделю")
FAIL[":batchRunReports"] = (429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota"}})
lines = GA.morning_lines(monday + timedelta(days=2))
check(len(lines) == 1 and "временно ограничил" in lines[0], f"Google ограничил запросы — одна строка с причиной {lines}")
FAIL.clear()

# ---------- 7. адрес в «Графиках» ----------
srv = H.serve(18793)


def get(uid, q):
    req = urllib.request.Request("http://127.0.0.1:18793/api/stats/ga?" + q, headers={"X-Telegram-Init-Data": H.init_data(uid)})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


code, d = get(H.IRINA, "site=home&p=7")
check(code == 200 and d["sites"][0]["host"] == "dumskaya-home.com" and d["sites"][0]["totals"]["users"] == 40, "дизайнеру — карточка каталога")
code, d = get(H.OWNER, "site=studio&p=weird")
check(code == 200 and d["period"] == "7", "непонятный период — 7 дней")
dump = json.dumps(d, ensure_ascii=False)
check("test-token" not in dump and "private_key" not in dump, "ни токена, ни ключа в ответе")
check(get(H.CLIENT, "site=studio&p=7")[0] == 403, "заказчику — нет")
srv.shutdown()

print(f"OK: {ok} проверок")
