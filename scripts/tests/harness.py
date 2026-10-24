"""Тестовый стенд для scripts/tests/test_portal.py: сервис заявок с ботом, учётом и кабинетами на временных базах,
Telegram подменён (ничего никуда не отправляется). Только стандартная библиотека Python."""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import threading
import time
import urllib.parse
from datetime import date, timedelta

TMP = tempfile.mkdtemp(prefix="dd-test-")
os.environ["HOME"] = TMP
os.environ["TELEGRAM_BOT_TOKEN"] = TOKEN = "123456:TEST-TOKEN"
os.environ["BOT_OWNER_ID"] = "1"
os.environ["BOT_DB"] = os.path.join(TMP, "dumskaya", "bot.db")
os.environ["CRM_DB"] = os.path.join(TMP, "dumskaya", "crm.db")
os.environ["CRM_FILES"] = os.path.join(TMP, "dumskaya", "crm", "files")
os.environ["BACKUP_DIR"] = os.path.join(TMP, "dumskaya", "backups")
os.environ["LEADS_FILE"] = os.path.join(TMP, "dumskaya", "leads.jsonl")
os.makedirs(os.path.join(TMP, "dumskaya", "stats"), exist_ok=True)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "deploy"))

import lead_service  # noqa: E402
import crm_api  # noqa: E402
import portal_api  # noqa: E402
from bot import Bot  # noqa: E402
from crm import Crm  # noqa: E402
from crm_portal import Portal  # noqa: E402
from site_stats import check_init_data  # noqa: E402

CALLS = []
_mid = [1000]


def fake_api(self, method, **params):
    CALLS.append((method, params))
    if method == "getMe":
        return {"ok": True, "result": {"username": "dumskaya_test_bot"}}
    if method in ("sendMessage", "sendPhoto", "sendDocument", "editMessageText"):
        _mid[0] += 1
        return {"ok": True, "result": {"message_id": _mid[0]}}
    if method == "getFile":
        return {"ok": True, "result": {"file_path": "x/y.jpg"}}
    return {"ok": True, "result": True}


def fake_send_file_r(self, chat_id, f, path, caption=None, rows=None, silent=False):
    """Файл в Telegram (на самом деле — запрос с файлом напрямую): только записываем."""
    _mid[0] += 1
    method = "sendPhoto" if (f.get("mime") or "").startswith("image/") else "sendDocument"
    CALLS.append((method, {"chat_id": chat_id, "caption": caption or f["name"], "disable_notification": silent, "file": f["name"],
                           "reply_markup": self.kb(rows) if rows else None}))
    return True, "", _mid[0]


Bot.api = fake_api
Bot.send_file_r = fake_send_file_r
Bot.stats_app_url = lambda self: "https://dumskaya-design.com/api/stats/app"


class FakeRates:
    def rate(self, cur, day):
        return {"UAH": 48.0, "USD": 1.1, "PLN": 4.3}.get(cur, 1.0), day, "ЕЦБ"


bot = Bot(TOKEN, "1", os.environ["BOT_DB"], log=lambda *a: None)
bot.username = "dumskaya_test_bot"
crm = Crm(path=os.environ["CRM_DB"], rates=FakeRates(), files_dir=os.environ["CRM_FILES"], backup_dir=os.environ["BACKUP_DIR"])
portal = Portal(crm)
bot.crm, bot.portal = crm, portal
lead_service.BOT = bot
lead_service.TG_TOKEN = TOKEN
crm_api.CRM, crm_api.BOT, crm_api.PORTAL = crm, bot, portal
portal_api.CRM, portal_api.BOT, portal_api.PORTAL, portal_api.CHECK, portal_api.TOKEN = crm, bot, portal, check_init_data, TOKEN

IRINA, CLIENT, CLIENT2, CREW, CREW2, WORKER, WORKER2, OWNER = 2, 100, 101, 200, 201, 300, 301, 1
ASSIST, SUPP, SUPPW = 400, 500, 501      # сотрудник студии; поставщик плитки и его менеджер
bot.s.run("INSERT INTO users(tg_id, name, role, status, created, updated) VALUES(?, 'Ирина', 'designer', 'active', '', '')", IRINA)


def init_data(uid, first="Test", lang="ru"):
    user = json.dumps({"id": uid, "first_name": first, "language_code": lang}, separators=(",", ":"))
    pairs = {"auth_date": str(int(time.time())), "query_id": "AAA", "user": user}
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(pairs)


def update(uid, text="", first="Анна", lang="sk", reply_to=None, photo=None, data=None, msg_id=None):
    """Входящее сообщение или нажатие кнопки — как от Telegram."""
    frm = {"id": uid, "is_bot": False, "first_name": first, "language_code": lang}
    if data is not None:
        return bot.handle({"callback_query": {"id": "cq", "from": frm, "data": data,
                                              "message": {"message_id": msg_id or 1, "chat": {"id": uid, "type": "private"}, "text": ""}}})
    m = {"message_id": 1, "chat": {"id": uid, "type": "private"}, "from": frm, "text": text}
    if reply_to:
        m["reply_to_message"] = {"message_id": reply_to}
    if photo:
        m["photo"] = photo
    return bot.handle({"message": m})


def seed(full=True):
    """Проект с двумя заказчиками, подрядчиками, этапами, товарами, услугами, файлами и разговором со студией."""
    w = "Ирина"
    p = crm.save_project({"title": "Квартира 127 м², Ружинов", "number": "2026-014", "city": "Братислава", "country": "Словакия",
                          "address": "Ružinovská 12", "area": 127, "tariff": "Премиум", "total_eur": 6350, "status": "active",
                          "started": "2026-07-01"}, w)["project"]
    pid = p["id"]
    a = crm.save_client({"name": "Anna Nováková", "phone": "+421 905 111 222", "email": "anna@example.sk", "contact_pref": "WhatsApp"}, w)
    b = crm.save_client({"name": "Peter Novák", "phone": "+421 905 333 444"}, w)
    crm.add_project_client({"project_id": pid, "client_id": a["id"]}, w)
    crm.add_project_client({"project_id": pid, "client_id": b["id"]}, w)
    k1 = crm.save_contractor({"name": "Михаил Бондаренко", "trade": "Прораб", "company": "MB Stav s.r.o.", "phone": "+421 911 222 333",
                              "messenger": "@mb_stav", "contact_pref": "Telegram"}, w)
    k2 = crm.save_contractor({"name": "Lukáš Horváth", "trade": "Мебельщик", "phone": "+421 944 555 666", "email": "lukas@nabytok.sk"}, w)
    l1 = crm.link_contractor({"project_id": pid, "contractor_id": k1["id"], "trade": "Прораб"}, w)["saved_id"]
    l2 = crm.link_contractor({"project_id": pid, "contractor_id": k2["id"], "trade": "Мебельщик"}, w)["saved_id"]
    if not full:
        return locals()
    s1 = crm.save_stage({"project_id": pid, "link_id": l1, "title": "Черновые работы", "day": "2026-08-01", "amount": 18000,
                         "currency": "EUR", "mode": "pct", "pct": 10}, w)["saved_id"]
    crm.save_stage({"project_id": pid, "link_id": l1, "title": "Чистовые работы", "day": "2026-09-10", "amount": 14500,
                    "currency": "EUR", "mode": "pct", "pct": 10}, w)
    crm.save_stage({"project_id": pid, "link_id": l2, "title": "Кухня и шкафы", "day": "2026-09-20", "amount": 21400,
                    "currency": "EUR", "mode": "pct", "pct": 10}, w)
    crm.run("UPDATE stages SET confirmed='2026-08-02T10:00:00+00:00', confirmed_by='Anna Nováková' WHERE id=?", s1)
    crm.save_op({"project_id": pid, "kind": "commission", "day": "2026-08-20", "amount": 1800, "currency": "EUR", "link_id": l1, "stage_id": s1}, w)
    crm.save_op({"project_id": pid, "kind": "payment", "day": "2026-07-01", "amount": 3175, "currency": "EUR", "method": "Банковский перевод"}, w)
    crm.save_op({"project_id": pid, "kind": "payment", "day": "2026-09-01", "amount": 2000, "currency": "EUR", "method": "Банковский перевод"}, w)
    sv = crm.save_service({"project_id": pid, "title": "Авторское сопровождение", "kind": "monthly", "amount": 1000, "start": "2026-08-15"}, w)["saved_id"]
    crm.run("UPDATE services SET created='2026-08-10T10:00:00+00:00' WHERE id=?", sv)
    crm.save_op({"project_id": pid, "kind": "payment", "day": "2026-08-15", "amount": 1000, "currency": "EUR", "service_id": sv}, w)
    crm.save_op({"project_id": pid, "kind": "payment", "day": "2026-09-16", "amount": 1000, "currency": "EUR", "service_id": sv}, w)
    crm.save_service({"project_id": pid, "title": "Рабочие чертежи кухни", "kind": "once", "amount": 450,
                      "start": (date.today() + timedelta(days=10)).isoformat()}, w)
    o1 = crm.save_order({"project_id": pid, "title": "Диван Viktor, ткань Velvet Grey", "code": "DF-S5012", "qty": 1, "price": 3200,
                         "currency": "EUR", "buy": 2350, "supplier": "Baxter", "day": "2026-09-05", "planned": "2026-11-20",
                         "note_client": "Ткань Velvet Grey, ножки — латунь"}, w)["saved_id"]
    crm.save_op({"project_id": pid, "kind": "payment", "day": "2026-09-06", "amount": 1600, "currency": "EUR", "order_id": o1}, w)
    o2 = crm.save_order({"project_id": pid, "title": "Подвесной светильник DL-S1047", "qty": 2, "price": 980, "currency": "EUR", "buy": 700,
                         "day": "2026-09-12", "planned": "2026-10-10", "delivered": "2026-10-12"}, w)["saved_id"]
    crm.save_op({"project_id": pid, "kind": "payment", "day": "2026-09-12", "amount": 980, "currency": "EUR", "order_id": o2}, w)
    from io import BytesIO
    png = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                        "1f15c4890000000d49444154789c6360f8cfc0f01f0005fe02fea7d6a4"
                        "0000000049454e44ae426082")
    for cat, name in (("measure", "obmernyj-plan.pdf"), ("visual", "gostinaya-kuhnya-01.png"), ("visual", "spalnya-01.png"),
                      ("before", "do-01.png"), ("docs", "razvertki-kuhni.pdf"), ("other", "schet-baxter-zakupka.pdf"), ("brief", "oprosnik.pdf")):
        data = png if name.endswith(".png") else b"%PDF-1.4 test"
        crm.add_file(pid, cat, name, BytesIO(data), len(data), "image/png" if name.endswith(".png") else "application/pdf", w)
    th = portal.ensure_thread(pid, "client")
    portal.post(th["id"], "client", CLIENT, "Anna Nováková", "Dobrý deň, kedy presne príde sedačka? Budeme doma od 15:00.")
    m1 = portal.post(th["id"], "studio", IRINA, "Ирина Думская", "Добрый день! Диван приедет 20 ноября, между 15 и 18 часами.")
    portal.set_translation(m1["id"], "sk", "Dobrý deň! Sedačka príde 20. novembra medzi 15:00 a 18:00.", "ru")
    m0 = crm.one("SELECT id FROM messages WHERE project_id=? ORDER BY id LIMIT 1", pid)
    portal.set_translation(m0["id"], "ru", "Добрый день, когда точно приедет диван? Мы будем дома с 15:00.", "sk")
    return locals()


def link_people(env, team=True):
    """Привязать Telegram (как будто прошли по ссылкам): Анна — заказчик, Михаил — подрядчик (прораб); с team — ещё
    Лукаш (мебельщик) с технологом и плиточник из бригады Михаила, все на этом объекте, и наблюдатель «Разработчик ПО»."""
    crm.run("UPDATE clients SET tg_id=?, tg_name='Anna' WHERE id=?", CLIENT, env["a"]["id"])
    crm.run("UPDATE contractors SET tg_id=?, tg_name='Михаил' WHERE id=?", CREW, env["k1"]["id"])
    people = [(CLIENT, "client", "Anna", "sk"), (CREW, "crew", "Михаил", "uk")]
    if team:
        crm.run("UPDATE contractors SET tg_id=?, tg_name='Lukáš' WHERE id=?", CREW2, env["k2"]["id"])
        env["w1"] = portal.crew_add(env["k1"]["id"], {"name": "Олег Кравец", "position": "плиточник", "phone": "+421 948 100 200"}, "Михаил")
        env["w2"] = portal.crew_add(env["k2"]["id"], {"name": "Jana Kováčová", "position": "технолог", "phone": "+421 948 300 400"}, "Lukáš")
        crm.run("UPDATE crew SET tg_id=?, tg_name='Олег' WHERE id=?", WORKER, env["w1"])
        crm.run("UPDATE crew SET tg_id=?, tg_name='Jana' WHERE id=?", WORKER2, env["w2"])
        portal.crew_assign(env["pid"], env["w1"], True, "Михаил")
        portal.crew_assign(env["pid"], env["w2"], True, "Lukáš")
        portal.ensure_observer(OWNER)
        people += [(CREW2, "crew", "Lukáš", "sk"), (WORKER, "worker", "Олег", "ru"), (WORKER2, "worker", "Jana", "sk")]
    for uid, role, name, lang in people:
        bot.s.run("INSERT OR REPLACE INTO users(tg_id, name, role, status, created, updated) VALUES(?, ?, ?, 'active', '', '')", uid, name, role)
        bot.s.put(f"tg:lang:{uid}", lang)


def serve(port):
    from http.server import ThreadingHTTPServer
    srv = ThreadingHTTPServer(("127.0.0.1", port), lead_service.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
