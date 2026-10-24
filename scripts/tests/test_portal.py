"""Проверка кабинетов заказчика и подрядчика: приглашения, права (без бонусов и закупок), переписка с переводом,
подтверждение сумм, напоминания об оплате, адреса /api/portal и /api/crm. Временные базы, Telegram подменён.

   python3 scripts/tests/test_portal.py      — на Маке или в любой папке с репозиторием; в конце «OK: N проверок»"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402
import portal_bot  # noqa: E402

ok = 0


def check(cond, what):
    global ok
    if not cond:
        raise AssertionError(what)
    ok += 1


def sent(method="sendMessage", to=None, since=0):
    return [p for m, p in H.CALLS[since:] if m == method and (to is None or p.get("chat_id") == to)]


def wait_calls(n0, pred, timeout=5):
    t = time.time()
    while time.time() - t < timeout:
        if pred():
            return True
        time.sleep(0.05)
    return False


env = H.seed()
pid = env["pid"]

# ---------- приглашение заказчика: ссылка, вход, язык, кнопка «Мой проект» ----------
inv = H.portal.make_invite("client", env["a"]["id"], pid, "sk", "Ирина")
check(len(inv["token"]) >= 16 and inv["lang"] == "sk", "приглашение")
txt = H.bot.invite_text("sk", "client", "Anna", "Byt", "https://t.me/x?start=pj_" + inv["token"])
check("Dobrý deň" in txt and "14 dní" in txt, "текст приглашения по-словацки")
n = len(H.CALLS)
H.update(H.CLIENT, "/start pj_" + inv["token"], first="Anna", lang="sk")
u = H.bot.user(H.CLIENT)
check(u and u["role"] == "client" and u["status"] == "active", "заказчик принят по ссылке")
check(H.crm.one("SELECT tg_id FROM clients WHERE id=?", env["a"]["id"])["tg_id"] == H.CLIENT, "Telegram привязан к заказчику")
menu = [p for m, p in H.CALLS[n:] if m == "setChatMenuButton" and p["chat_id"] == H.CLIENT]
check(menu and menu[-1]["menu_button"]["text"] == "Môj projekt" and menu[-1]["menu_button"]["web_app"]["url"].endswith("/api/portal/app"),
      "кнопка «Môj projekt» ведёт в кабинет")
welcome = sent(to=H.CLIENT, since=n)
check(welcome and "Dobrý deň, Anna" in welcome[0]["text"], "приветствие по-словацки")
check(any("подключился к кабинету" in p["text"] for p in sent(to=H.IRINA, since=n)), "Ирине — кто подключился")
n = len(H.CALLS)
H.update(H.CLIENT2, "/start pj_" + inv["token"], first="Mallory", lang="en")
check(H.bot.user(H.CLIENT2) is None or H.bot.user(H.CLIENT2)["status"] != "active", "повторно ссылка не работает")
check("no longer valid" in sent(to=H.CLIENT2, since=n)[0]["text"], "недействительная ссылка — на языке человека")
# ссылка дизайнеру не тратится
inv2 = H.portal.make_invite("contractor", env["k1"]["id"], pid, "uk", "Ирина")
H.update(H.IRINA, "/start pj_" + inv2["token"], first="Ирина", lang="ru")
check(H.portal.invite(inv2["token"]) is not None, "Ирина открыла ссылку подрядчика — ссылка осталась")
H.update(H.CREW, "/start pj_" + inv2["token"], first="Михайло", lang="uk")
check(H.bot.user(H.CREW)["role"] == "crew", "подрядчик принят по ссылке")
check(not H.portal.make_invite("client", env["b"]["id"], pid, "ru", "Ирина") is None, "второй заказчик — ссылка")

# ---------- права: что видит заказчик и подрядчик ----------
cv = H.portal.client_view(pid, H.CLIENT)
blob = json.dumps(cv, ensure_ascii=False)
for bad in ('"buy', '"commission"', '"pct"', '"supplier"', '"margin"', '"received"', "Baxter", "schet-baxter", '"note":'):
    check(bad not in blob, f"заказчик не видит {bad}")
check({f["category"] for f in cv["files"]} <= set(H.crm.lists()["client_cats"]) and any(f["category"] == "brief" for f in cv["files"]),
      "заказчик видит разделы, кроме «Другое»")
check(cv["money"]["total_debt"] == round(6350 - 5175 + 1000 + 450 + 1600, 2), f"всего к оплате {cv['money']}")
check([o["status"] for o in cv["orders"]] == ["ordered", "done"], "статусы товаров")
check(any(s["kind"] == "monthly" and s["debt"] == 1000 for s in cv["services"]), "сопровождение: долг за октябрь")
k = H.portal.contractor_ids(H.CREW, pid)
xv = H.portal.contractor_view(pid, k)
blob = json.dumps(xv, ensure_ascii=False)
check(len(xv["mine"]) == 1 and xv["mine"][0]["money"]["expected"] == 3250, "подрядчик видит свой подряд и 10 %")
for bad in ("Lukáš", "Кухня и шкафы", "brief", "oprosnik", "schet", '"paid"', "Viktor", "Авторское"):
    check(bad not in blob, f"подрядчик не видит {bad}")
check(any(c["phone"] == "+421 905 111 222" for c in xv["clients"]), "подрядчик видит контакты заказчика")
check(H.portal.client_of(H.CREW, pid) is None, "подрядчик — не заказчик")

# ---------- переписка: заказчик пишет в бот, Ирине — с переводом; ответ свайпом — заказчику на его языке ----------
portal_bot.translate_provider = lambda: "deepl"


def fake_tr(text, target):
    if target == "ru" and "sedačka" in text:
        return "sk", "Перевод: " + text
    if target == "sk" and "Диван" in text:
        return "ru", "Preklad: " + text
    return None


portal_bot.translate_text = fake_tr
n = len(H.CALLS)
H.update(H.CLIENT, "Dobrý deň, sedačka môže prísť aj v sobotu?", first="Anna", lang="sk")
check(wait_calls(n, lambda: any("Перевод на русский" in p.get("text", "") for p in sent(to=H.IRINA, since=n))), "Ирине — с переводом на русский")
to_irina = [p for p in sent(to=H.IRINA, since=n) if "Перевод" in p.get("text", "")][0]
check("потяните сообщение влево" in to_irina["text"] and "со словацкого" in to_irina["text"], "подсказка про свайп и язык оригинала")
check(wait_calls(n, lambda: any("Odoslané" in p.get("text", "") for p in sent(to=H.CLIENT, since=n))), "заказчику — «отправлено»")
check(not any(p for p in sent(to=H.CREW, since=n)), "подрядчику переписка не приходит")
row = H.bot.s.one("SELECT key FROM state WHERE key LIKE ? ORDER BY rowid DESC LIMIT 1", f"chatmap:{H.IRINA}:%")
mid_for_irina = int(row["key"].split(":")[2])
n = len(H.CALLS)
H.update(H.IRINA, "Диван приедет в субботу утром.", first="Ирина", lang="ru", reply_to=mid_for_irina)
check(wait_calls(n, lambda: any("Preklad" in p.get("text", "") for p in sent(to=H.CLIENT, since=n))), "ответ Ирины — заказчику по-словацки")
check(any("Preložené automaticky" in p.get("text", "") for p in sent(to=H.CLIENT, since=n)), "пометка об автопереводе")
check(wait_calls(n, lambda: any("Отправлено" in p.get("text", "") for p in sent(to=H.IRINA, since=n))), "Ирине — кому доставлено")
last = H.crm.one("SELECT * FROM messages WHERE project_id=? ORDER BY id DESC LIMIT 1", pid)
check(last["author_kind"] == "studio" and "sk" in json.loads(last["tr"]), "перевод сохранён в переписке")
check(H.crm.chat_summary(pid)["count"] >= 4, "переписка в «Студии»")

# ---------- суммы подрядчика: вносит подрядчик → заказчик подтверждает ----------
n = len(H.CALLS)
r = H.portal.contractor_stage(H.CREW, {"project_id": pid, "link_id": env["l1"], "title": "Электрика", "amount": "4200", "currency": "EUR"}, "Михайло")
st = H.crm.one("SELECT * FROM stages WHERE id=?", r["stage_id"])
check(st["src"] == "contractor" and st["pct"] == 10 and st["commission"] == 420, "этап подрядчика: 10 % по умолчанию")
H.bot.portal_event("stage_saved", stage_id=r["stage_id"], was=None, by="Михайло", by_contractor=True)
ask = [p for p in sent(to=H.CLIENT, since=n) if "Potvrďte cenu" in p.get("text", "")]
check(ask and ask[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"pc:{st['id']}", "заказчику — «Potvrdzujem»")
check(any("внёс сумму работ" in p["text"] for p in sent(to=H.IRINA, since=n)), "Ирине — подрядчик внёс сумму")
n = len(H.CALLS)
H.update(H.CLIENT, data=f"pc:{st['id']}", first="Anna", lang="sk")
check(H.crm.one("SELECT confirmed_by FROM stages WHERE id=?", st["id"])["confirmed_by"] == "Anna", "заказчик подтвердил кнопкой")
check(any("підтвердив суму" in p.get("text", "") for p in sent(to=H.CREW, since=n)), "подрядчику — по-украински, что подтверждено")
check(any("подтвердил" in p.get("text", "") for p in sent(to=H.IRINA, since=n)), "Ирине — подтверждено")
try:
    H.portal.contractor_stage(H.CREW, {"id": st["id"], "project_id": pid, "link_id": env["l1"], "title": "Электрика", "amount": "5000"}, "Михайло")
    check(False, "подтверждённое подрядчик менять не может")
except H.crm_api.CrmError:
    ok += 1
H.crm.save_stage({"id": st["id"], "project_id": pid, "link_id": env["l1"], "title": "Электрика", "amount": 4600, "currency": "EUR",
                  "mode": "pct", "pct": 10}, "Ирина")
check(H.crm.one("SELECT confirmed FROM stages WHERE id=?", st["id"])["confirmed"] is None, "студия изменила сумму — подтверждение снято")
try:
    H.portal.client_stage(H.CREW, st["id"], "confirm", "", "x")
    check(False, "подрядчик не может подтверждать")
except H.crm_api.CrmError:
    ok += 1

# ---------- товар, услуга, подрядчик добавлен — сообщения ----------
n = len(H.CALLS)
H.bot.portal_event("order_new", order_id=env["o1"])
check(any("Nový tovar" in p.get("text", "") and "3 200 €" in p["text"] for p in sent(to=H.CLIENT, since=n)), "новый товар — заказчику")
check(not any("2 350" in p.get("text", "") for p in sent(since=n)), "закупка в сообщениях не видна")
H.bot.portal_event("order_delivered", order_id=env["o1"])
check(any("Zostáva doplatiť" in p.get("text", "") and "1 600 €" in p["text"] for p in sent(to=H.CLIENT, since=n)), "доставлен — сколько доплатить")

# ---------- напоминания об оплате ----------
due = H.portal.due_reminders(date(2026, 10, 24))
check(any(x["service"]["title"] == "Авторское сопровождение" and x["due"] == "2026-10-15" and x["stage"] == "overdue" for x in due),
      f"просрочен октябрь {due}")
check(not any(x["due"] < "2026-08-15" for x in due), "до внесения услуги — не напоминаем")
n = len(H.CALLS)
sent_n = H.bot.portal_reminders(now=datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc))      # 11:00 в Братиславе
check(sent_n >= 1, "напоминание отправлено")
check(any("Platba zatiaľ neprišla" in p.get("text", "") for p in sent(to=H.CLIENT, since=n)), "заказчику — напоминание по-словацки")
check(any("Не оплачено 7 дней" in p.get("text", "") for p in sent(to=H.IRINA, since=n)), "Ирине — напоминание")
n = len(H.CALLS)
check(H.bot.portal_reminders(now=datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)) == 0, "второй раз не повторяется")
check(H.bot.portal_reminders(now=datetime(2026, 10, 24, 21, 0, tzinfo=timezone.utc)) == 0, "ночью не напоминает")

# ---------- HTTP: кабинет и «Студия» ----------
srv = H.serve(8196)
BASE = "http://127.0.0.1:8196"


def call(path, uid, body=None, lang="sk"):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-Telegram-Init-Data": H.init_data(uid, lang=lang), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


code, me = call("/api/portal/me", H.CLIENT)
check(code == 200 and me["lang"] == "sk" and me["projects"][0]["id"] == pid, "кабинет: мои проекты")
code, pv = call(f"/api/portal/project?id={pid}", H.CLIENT)
check(code == 200 and pv["role"] == "client" and "buy" not in json.dumps(pv), "кабинет заказчика по HTTP")
code, x = call(f"/api/portal/project?id={pid}", H.CREW, lang="uk")
check(code == 200 and x["role"] == "contractor", "кабинет подрядчика по HTTP")
code, x = call(f"/api/portal/chat?project={pid}", H.CREW, lang="uk")
check(code == 403, "подрядчику переписка закрыта")
code, x = call(f"/api/portal/project?id={pid}", 999)
check(code == 403, "чужому — нет доступа")
code, chat = call(f"/api/portal/chat?project={pid}", H.CLIENT)
check(code == 200 and any(m["tr"] and m["tr"].startswith("Preklad") for m in chat["messages"]), "заказчик видит перевод")
code, r = call("/api/portal/chat", H.CLIENT, {"project_id": pid, "text": "Ďakujem!"})
check(code == 200, "заказчик пишет из кабинета")
check(H.portal.unread(pid, H.CLIENT) == 0, "прочитано")
code, x = call(f"/api/portal/project?id={pid}&preview=client", H.IRINA, lang="ru")
check(code == 200 and x.get("preview"), "Ирина: как видит заказчик")
code, x = call(f"/api/portal/project?id={pid}&preview=contractor&link={env['l1']}", H.IRINA, lang="ru")
check(code == 200 and x["role"] == "contractor", "Ирина: как видит подрядчик")
code, x = call(f"/api/portal/project?id={pid}&preview=client", H.CLIENT)
check(code == 200 and not x.get("preview"), "заказчику превью не даётся (свой кабинет)")
code, x = call(f"/api/portal/project?id={pid}", 1, lang="ru")
check(code == 403, "разработчику кабинеты не отдаются")
code, x = call("/api/portal/stage", H.CLIENT, {"action": "dispute", "id": st["id"], "note": "Mali sme dohodnutých 4 200 €"})
check(code == 200 and H.crm.one("SELECT disputed FROM stages WHERE id=?", st["id"])["disputed"], "заказчик: не согласен")
code, x = call("/api/portal/ui", H.CLIENT, {"lang": "de", "size": "l"})
check(code == 200 and x["lang"] == "de" and x["size"] == "l", "язык и размер — свои")
# «Студия» Ирины: приглашение, товар, услуга, переписка
code, x = call("/api/crm/invite", H.IRINA, {"kind": "client", "ref_id": env["b"]["id"], "project_id": pid, "lang": "de"}, lang="ru")
check(code == 200 and x["link"].startswith("https://t.me/dumskaya_test_bot?start=pj_") and "Guten Tag" in x["text"], "Ирина: ссылка для заказчика")
code, x = call("/api/crm/save", H.IRINA, {"entity": "service", "data": {"project_id": pid, "title": "Доп. визуализации", "kind": "once",
                                                                         "amount": 300, "start": date.today().isoformat(), "notify": True}}, lang="ru")
check(code == 200 and any(s["title"] == "Доп. визуализации" for s in x["services"]), "Ирина: доп. услуга")
code, x = call(f"/api/crm/project?id={pid}", H.IRINA, lang="ru")
check(code == 200 and len(x["people"]) == 2 and x["chat"]["count"] >= 5 and x["orders"] and x["services"], "Ирина: проект целиком")
code, x = call(f"/api/crm/project?id={pid}", H.CLIENT)
check(code == 403, "заказчику «Студия» закрыта")
code, x = call("/api/crm/unlink", H.IRINA, {"kind": "contractor", "ref_id": env["k1"]["id"], "project_id": pid}, lang="ru")
check(code == 200, "Ирина закрыла кабинет подрядчику")
time.sleep(0.5)
check(H.bot.user(H.CREW)["status"] == "removed", "подрядчик без проектов — доступ к боту закрыт")
code, x = call(f"/api/portal/project?id={pid}", H.CREW, lang="uk")
check(code == 403, "подрядчик больше не видит проект")
st0 = H.crm.stats("all")
check(st0["payments"] == 3175 + 2000 + 2000 and st0["margin"] == 850 + 280, f"доход: оплаты без товаров, наценка товаров {st0['payments']} {st0['margin']}")
srv.shutdown()
print(f"OK: {ok} проверок")
