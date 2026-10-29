"""Спам в форме заявки (deploy/lead_filter.py, решено 29.10.2026): заблокированные отправители и предложения IT-услуг
не приходят в бот, не попадают в «Студию» и в статистику; «🚫 Спам» блокирует отправителя, возврат — разблокирует;
настоящие заявки проходят. Telegram подменён, перевод — без сети.

   python3 scripts/tests/test_lead_filter.py      — в конце «OK: N проверок»"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402
import lead_filter as F  # noqa: E402
import lead_service  # noqa: E402
import site_stats  # noqa: E402

ok = 0


def check(cond, what):
    global ok
    if not cond:
        raise AssertionError(what)
    ok += 1


F.BLOCK_FILE = os.path.join(H.TMP, "dumskaya", "blocked.json")
F.BLOCKED_LOG = os.path.join(H.TMP, "dumskaya", "leads-blocked.jsonl")
F.LEADS_FILE = lead_service.LEADS_FILE
site_stats.LEADS_FILE = lead_service.LEADS_FILE
lead_service.translate_lead = lambda lead, log=print: lead.update(           # перевод без сети: валлийский узнаём сами
    {"message_lang": "cy", "message_ru": "Привет, я хотел узнать вашу цену."} if "roeddwn" in lead["message"] else {}) or lead

# ---------- 1. правила ----------
robert = {"name": "Robertwrasy", "contact": "aveyekoha655@gmail.com", "message": "Hi, roeddwn i eisiau gwybod eich pris."}
seo = {"name": "Carlton Donaghy", "contact": "domains@search-dumskaya-home.com", "model": "value",
       "message": "Hello\n\nList dumskaya-home.com in Google's Search Index and have it be visible in Google search results!\n\nAdd dumskaya-home.com today: domainsubmit.site"}
check(F.reason(robert) == "отправитель заблокирован" and F.reason(seo) == "отправитель заблокирован", "оба со скриншотов — заблокированы")
fresh = lambda **k: dict({"name": "X", "contact": "x@example.org", "message": ""}, **k)  # noqa: E731
for msg in ("List your site in Google's Search Index today", "We offer SEO services to rank higher on Google",
            "Our agency does web design and development for interior studios", "I can bring targeted traffic to your website",
            "Get quality backlinks and guest post placements", "Add yoursite.com: domainsubmit.site", "Предлагаем продвижение сайта в поиске",
            "Разработка сайтов под ключ, создание сайта за 3 дня", "Добавим ваш сайт в индекс Google"):
    check(F.reason(fresh(message=msg)) and F.reason(fresh(message=msg)).startswith("предложение IT-услуг"), f"IT-услуги: {msg}")
check(F.reason(fresh(contact="sales@dumskaya-design-seo.net", message="Hi")) == "почта с домена, похожего на наш", "домен под нас — спам")
check(F.reason(fresh(message="Hi, roeddwn i", message_lang="cy")) == "рассылка на языке «cy»", "валлийская рассылка «узнать цену»")
for msg in ("Dobrý deň, potrebujem dizajn interiéru bytu 80 m² v Bratislave, koľko to stojí?",
            "Здравствуйте! Нужен дизайн-проект квартиры 127 м², сколько стоит пакет «Премиум»?",
            "Hello, we bought a house in Vienna and need a kitchen and wardrobes, can you send prices?",
            "Добрый день, интересует диван Viktor, доставка в Вену. Телефон +43 660 000 0000",
            "Grüß Gott, wir suchen eine Innenarchitektin für unsere Wohnung in Wien."):
    check(F.reason(fresh(message=msg)) is None, f"настоящая заявка проходит: {msg[:40]}")
check(F.reason(fresh(contact="irina@dumskaya-design.com", message="проверка")) is None, "наш собственный домен — не «похожий»")

# ---------- 2. форма: спам не уходит в бот и в «Студию» ----------
srv = H.serve(18797)


def post(d, ip):
    req = urllib.request.Request("http://127.0.0.1:18797/api/lead", data=json.dumps(d).encode(),
                                 headers={"Content-Type": "application/json", "X-Forwarded-For": ip})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, json.loads(r.read())


n_calls, n_leads = len(H.CALLS), H.crm.one("SELECT COUNT(*) AS n FROM leads")["n"]
code, d = post(dict(robert, page="/", lang="ru"), "9.9.9.1")
check(code == 200 and d["ok"], "спамеру — обычный ответ «спасибо»")
code, d = post(dict(fresh(contact="seo@agency.example", message="We will submit your website to Google search index and boost ranking"), page="/", lang="en"), "9.9.9.2")
code, d = post(dict(fresh(contact="cy@spam.example", message="Hi, roeddwn i eisiau gwybod eich pris."), page="/", lang="ru"), "9.9.9.3")
time.sleep(0.5)
msgs = [p for m, p in H.CALLS[n_calls:] if m == "sendMessage"]
check(not msgs, f"в бот ничего не пришло: {[m.get('text', '')[:40] for m in msgs]}")
check(H.crm.one("SELECT COUNT(*) AS n FROM leads")["n"] == n_leads, "в «Студию» спам не записан")
saved = open(lead_service.LEADS_FILE, encoding="utf-8").read() if os.path.exists(lead_service.LEADS_FILE) else ""
check("aveyekoha655" not in saved and "seo@agency" not in saved and "cy@spam" not in saved, "в файл заявок (и в статистику) спам не попал")
log = [json.loads(x) for x in open(F.BLOCKED_LOG, encoding="utf-8")]
check([x["blocked"] for x in log] == ["отправитель заблокирован", "предложение IT-услуг («submit your website»)", "рассылка на языке «cy»"],
      f"отсеянное — в отдельном журнале с причиной {[x['blocked'] for x in log]}")
code, d = post({"name": "Анна", "contact": "+421 900 123 456", "message": "Нужен дизайн кухни 12 м², сколько стоит?", "page": "/", "lang": "ru"}, "9.9.9.4")
time.sleep(0.5)
check(code == 200 and any("Нужен дизайн кухни" in p.get("text", "") for m, p in H.CALLS[n_calls:] if m == "sendMessage"), "настоящая заявка — в бот")
real = H.crm.one("SELECT id, status FROM leads WHERE contact='+421 900 123 456'")
check(real and real["status"] == "new", "и в «Студию»")

# ---------- 3. «Спам» блокирует отправителя, возврат — разблокирует ----------
H.crm.set_lead_status(real["id"], "spam", "Ирина")
check("+421900123456" in F.load()["contacts"] and "9.9.9.4" in F.load()["ips"], "отметили «Спам» — контакт и IP заблокированы")
n_calls = len(H.CALLS)
post({"name": "Анна", "contact": "+421 900 123 456", "message": "Ещё раз про кухню", "page": "/", "lang": "ru"}, "9.9.9.4")
time.sleep(0.5)
check(not [p for m, p in H.CALLS[n_calls:] if m == "sendMessage"], "следующая заявка от него — уже не приходит")
H.crm.set_lead_status(real["id"], "lead", "Ирина")
check("+421900123456" not in F.load()["contacts"] and "9.9.9.4" not in F.load()["ips"], "вернули из спама — разблокирован")
F.unblock("aveyekoha655@gmail.com")
check("aveyekoha655@gmail.com" not in F.load()["contacts"], "из начального списка тоже можно снять — и это запоминается")
F.block("aveyekoha655@gmail.com")

# ---------- 4. статистика и уже пришедшие заявки ----------
now = time.time()
with open(lead_service.LEADS_FILE, "a", encoding="utf-8") as fh:         # пришли до фильтра — уже лежат в файле
    for x in (robert, seo):
        fh.write(json.dumps(dict(x, time=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - 60)), ip="7.7.7.7",
                                 page="/", site="dumskaya-design.com"), ensure_ascii=False) + "\n")
got = site_stats.leads_between(now - 3600, now + 60)
check(len(got) == 1, f"в статистике — только настоящая заявка, спам не считается: {len(got)}")
lid = H.crm.add_lead(dict(robert, time="2026-10-29T18:32:00+00:00", page="/", lang="ru"))
check(lead_service.mark_spam(H.crm) >= 1 and H.crm.one("SELECT status FROM leads WHERE id=?", lid)["status"] == "spam",
      "уже пришедшая спам-заявка в «Студии» — в «Спам» сама")
srv.shutdown()
print(f"OK: {ok} проверок")
