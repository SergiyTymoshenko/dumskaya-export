"""Проверка кабинетов: заказчик, подрядчик и поставщик, работник подрядчика, сотрудник студии, наблюдатель «Разработчик ПО» — приглашения, права
(деньги, документы, разговоры), разговоры с переводом и уведомлениями, группы, бригада, подтверждение сумм, напоминания
об оплате, адреса /api/portal и /api/crm. Временные базы, Telegram подменён.

   python3 scripts/tests/test_portal.py      — на Маке или в любой папке с репозиторием; в конце «OK: N проверок»"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402
import portal_bot  # noqa: E402
from crm import CrmError  # noqa: E402

ok = 0
OBS = "Разработчик ПО"


def check(cond, what):
    global ok
    if not cond:
        raise AssertionError(what)
    ok += 1


def raises(fn, what):
    global ok
    try:
        fn()
    except CrmError:
        ok += 1
        return
    raise AssertionError(what)


def sent(method="sendMessage", to=None, since=0):
    return [p for m, p in H.CALLS[since:] if m == method and (to is None or p.get("chat_id") == to)]


def msgs(to, since):
    return [p for m, p in H.CALLS[since:] if m in ("sendMessage", "sendPhoto", "sendDocument") and p.get("chat_id") == to]


def texts(to, since):
    return [p.get("text") or p.get("caption") or "" for p in msgs(to, since)]


def wait(pred, timeout=5):
    t = time.time()
    while time.time() - t < timeout:
        if pred():
            return True
        time.sleep(0.05)
    return False


def settle():
    """Рассылка идёт в фоне — дождаться, пока новых вызовов Telegram не станет."""
    n = -1
    while n != len(H.CALLS):
        n = len(H.CALLS)
        time.sleep(0.3)


env = H.seed()
pid = env["pid"]
P = H.portal

# ---------- приглашение заказчика: ссылка, вход, язык, кнопка «Мой проект» ----------
inv = P.make_invite("client", env["a"]["id"], pid, "sk", "Ирина")
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
check(any("Dobrý deň, Anna" in x for x in texts(H.CLIENT, n)), "приветствие по-словацки")
check(any("подключился к кабинету" in p["text"] for p in sent(to=H.IRINA, since=n)), "Ирине — кто подключился")
n = len(H.CALLS)
H.update(H.CLIENT2, "/start pj_" + inv["token"], first="Mallory", lang="en")
check(H.bot.user(H.CLIENT2) is None or H.bot.user(H.CLIENT2)["status"] != "active", "повторно ссылка не работает")
check("no longer valid" in sent(to=H.CLIENT2, since=n)[0]["text"], "недействительная ссылка — на языке человека")

# ---------- подрядчик: ссылка один раз, без проекта; дальше видит все проекты, куда добавят ----------
inv2 = P.make_invite("contractor", env["k1"]["id"], None, "uk", "Ирина")
check(inv2["project_id"] is None, "ссылка подрядчику — без проекта")
txt = H.bot.invite_text("uk", "contractor", "Михайло", "", "https://t.me/x?start=pj_" + inv2["token"])
check("Підключитися треба один раз" in txt, "текст: подключиться один раз")
H.update(H.IRINA, "/start pj_" + inv2["token"], first="Ирина", lang="ru")
check(P.invite(inv2["token"]) is not None, "Ирина открыла ссылку подрядчика — ссылка осталась")
n = len(H.CALLS)
H.update(H.CREW, "/start pj_" + inv2["token"], first="Михайло", lang="uk")
check(H.bot.user(H.CREW)["role"] == "crew", "подрядчик принят по ссылке")
check(any("кабінет підрядника" in x and "Бригада" in x for x in texts(H.CREW, n)), "подрядчику — приветствие про бригаду")
check([(p["id"], p["roles"]) for p in P.projects_for(H.CREW)] == [(pid, ["contractor"])], "подрядчик видит проект, где он есть")
p2 = H.crm.save_project({"title": "Дом в Сенце", "city": "Сенец", "total_eur": 9000, "status": "active"}, "Ирина")["project"]
n = len(H.CALLS)
l3 = H.crm.link_contractor({"project_id": p2["id"], "contractor_id": env["k1"]["id"], "trade": "Прораб"}, "Ирина")["saved_id"]
H.bot.portal_event("link_new", link_id=l3)
check(any("Вас додали до проєкту" in x for x in texts(H.CREW, n)), "новый проект — подрядчику сообщение, без новой ссылки")
check({p["id"] for p in P.projects_for(H.CREW)} == {pid, p2["id"]}, "второй проект появился сам")
check(P.make_invite("client", env["b"]["id"], pid, "ru", "Ирина"), "второй заказчик — ссылка")
raises(lambda: P.make_invite("client", env["b"]["id"], p2["id"], "ru", "Ирина"), "заказчику не из проекта ссылку не дать")
inv3 = P.make_invite("contractor", env["k2"]["id"], pid, "sk", "Ирина")
H.update(H.CREW2, "/start pj_" + inv3["token"], first="Lukáš", lang="sk")
check(H.bot.user(H.CREW2)["role"] == "crew", "второй подрядчик (мебельщик) подключён")

# ---------- права: что видит заказчик и подрядчик ----------
cv = P.client_view(pid, H.CLIENT)
blob = json.dumps(cv, ensure_ascii=False)
for bad in ('"buy', '"commission"', '"pct"', '"supplier"', '"margin"', '"received"', "Baxter", "schet-baxter", '"note":'):
    check(bad not in blob, f"заказчик не видит {bad}")
check({f["category"] for f in cv["files"]} <= set(H.crm.lists()["client_cats"]) and any(f["category"] == "brief" for f in cv["files"]),
      "заказчик видит разделы, кроме «Другое»")
check(cv["money"]["total_debt"] == round(6350 - 5175 + 1000 + 450 + 1600, 2), f"всего к оплате {cv['money']}")
check([o["status"] for o in cv["orders"]] == ["ordered", "done"], "статусы товаров")
check(any(s["kind"] == "monthly" and s["debt"] == 1000 for s in cv["services"]), "сопровождение: долг за октябрь")
check({c["name"] for c in cv["contractors"]} == {"Михаил Бондаренко", "Lukáš Horváth"} and all(c["can_write"] for c in cv["contractors"]),
      "заказчик видит подрядчиков и может им написать")
xv = P.contractor_view(pid, P.contractor_ids(H.CREW, pid), H.CREW)
blob = json.dumps(xv, ensure_ascii=False)
check(len(xv["mine"]) == 1 and xv["mine"][0]["money"]["expected"] == 3250, "подрядчик видит свой подряд и 10 %")
for bad in ("Lukáš", "Кухня и шкафы", "brief", "oprosnik", "schet", '"paid"', "Viktor", "Авторское"):
    check(bad not in blob, f"подрядчик не видит {bad}")
check(any(c["phone"] == "+421 905 111 222" for c in xv["clients"]), "подрядчик видит контакты заказчика")
check(P.client_of(H.CREW, pid) is None, "подрядчик — не заказчик")

# ---------- HTTP-стенд ----------
srv = H.serve(8196)
BASE = "http://127.0.0.1:8196"


def call(path, uid, body=None, lang="sk", raw=None, ctype="application/json"):
    data = raw if raw is not None else json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers={"X-Telegram-Init-Data": H.init_data(uid, lang=lang), "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


# ---------- бригада: подрядчик подключает работников и выбирает, кто на каком объекте ----------
code, r = call("/api/portal/team", H.CREW, {"action": "add", "contractor_id": env["k1"]["id"], "name": "Олег Кравец", "position": "плиточник",
                                            "phone": "+421 948 100 200"}, lang="uk")
check(code == 200 and r["team"][0]["name"] == "Олег Кравец" and not r["team"][0]["tg"], "подрядчик добавил работника")
w1 = r["crew_id"]
code, r = call("/api/portal/team", H.CREW2, {"action": "add", "contractor_id": env["k1"]["id"], "name": "Чужой"})
check(code == 400, "в чужую бригаду добавить нельзя")
code, r = call("/api/portal/team", H.CREW, {"action": "invite", "crew_id": w1, "lang": "ru"}, lang="uk")
check(code == 200 and r["link"].startswith("https://t.me/dumskaya_test_bot?start=pj_") and "Михаил Бондаренко приглашает" in r["text"],
      "ссылка работнику — от имени подрядчика")
n = len(H.CALLS)
H.update(H.WORKER, "/start pj_" + r["link"].split("pj_")[1], first="Олег", lang="ru")
check(H.bot.user(H.WORKER)["role"] == "worker", "работник принят по ссылке")
check(any("кабинет работника" in x for x in texts(H.WORKER, n)), "работнику — приветствие")
check(any("у боті" in x for x in texts(H.CREW, n)), "подрядчику — работник подключился (по-украински)")
check(any("из бригады подрядчика" in x for x in texts(H.IRINA, n)), "Ирине — работник подключился")
code, me = call("/api/portal/me", H.WORKER, lang="ru")
check(code == 200 and me["projects"] == [] and me["crews"][0]["head"] == "Михаил Бондаренко", "работник без объектов — кабинет есть, проектов нет")
n = len(H.CALLS)
code, r = call("/api/portal/team", H.CREW, {"action": "assign", "crew_id": w1, "project_id": pid, "on": True}, lang="uk")
check(code == 200 and r["team"][0]["projects"][0]["id"] == pid, "подрядчик отметил работника на объекте")
check(wait(lambda: any("Вас отметили на объекте" in x for x in texts(H.WORKER, n))), "работнику — его отметили на объекте")
check([p["id"] for p in P.projects_for(H.WORKER)] == [pid], "работник видит только объект, куда его отправили")
w2 = P.crew_add(env["k2"]["id"], {"name": "Jana Kováčová", "position": "технолог"}, "Lukáš")
inv4 = P.make_invite("crew", w2, None, "sk", "Lukáš")
H.update(H.WORKER2, "/start pj_" + inv4["token"], first="Jana", lang="sk")
P.crew_assign(pid, w2, True, "Lukáš")
check(H.bot.user(H.WORKER2)["role"] == "worker", "технолог мебельщика подключён")

# ---------- работник: проект без денег ----------
wv = P.worker_view(pid, P.crew_ids(H.WORKER, pid), H.WORKER)
blob = json.dumps(wv, ensure_ascii=False)
for bad in ('"total_eur"', '"amount"', '"commission"', '"pct"', '"paid"', "6350", "3250", "+421 905 111 222", "anna@example.sk", "oprosnik", "schet"):
    check(bad not in blob, f"работник не видит {bad}")
check(wv["heads"][0]["name"] == "Михаил Бондаренко" and wv["heads"][0]["phone"], "работник видит контакты своего подрядчика")
check(any(f["category"] == "visual" for f in wv["files"]), "работник видит визуализации")
code, x = call(f"/api/portal/project?id={pid}", H.WORKER, lang="ru")
check(code == 200 and x["role"] == "worker" and "total_eur" not in json.dumps(x), "кабинет работника по HTTP — без денег")
code, x = call(f"/api/portal/project?id={pid}&as=contractor", H.WORKER, lang="ru")
check(code == 200 and x["role"] == "worker", "работник не может открыть кабинет подрядчика")
code, x = call(f"/api/portal/project?id={p2['id']}", H.WORKER, lang="ru")
check(code == 403, "работник не видит чужой объект")

# ---------- разговоры: кто какие видит ----------
vC, vK, vL, vW, vJ = (P.viewer(H.CLIENT, pid), P.viewer(H.CREW, pid), P.viewer(H.CREW2, pid), P.viewer(H.WORKER, pid), P.viewer(H.WORKER2, pid))


def kinds(v):
    return sorted((t["kind"], (t["contractor"] or {}).get("id"), (t["crew"] or {}).get("id"), bool(t.get("start"))) for t in P.threads_for(v, pid))


check(kinds(vW) == [("worker", None, w1, False)], "работник: только свой разговор со студией")
check(kinds(vC) == sorted([("client", None, None, False), ("pc", env["k1"]["id"], None, True), ("pc", env["k2"]["id"], None, True)]),
      f"заказчик: студия и «написать подрядчику» {kinds(vC)}")
check(kinds(vK) == [("org", env["k1"]["id"], None, False), ("worker", None, w1, False)], f"подрядчик: студия и разговор его работника {kinds(vK)}")
tW = P.ensure_thread(pid, "worker", crew_id=w1)
check(P.access(vK, tW) == "read" and P.access(vW, tW) == "write" and P.access(vL, tW) is None and P.access(vC, tW) is None,
      "разговор студии с работником: работник пишет, его подрядчик читает, остальные не видят")

# ---------- заказчик пишет в бот → Ирине с переводом; ответ свайпом → заказчику на его языке ----------
portal_bot.translate_provider = lambda: "openai"


def fake_tr(text, target):
    if target == "ru" and any(w in text for w in ("sedačka", "Dobrý", "kuchyň", "Fasády", "dverám")):
        return "sk", "Перевод: " + text
    if target == "sk" and any(w in text for w in ("Диван", "Кухня", "Вариант")):
        return "ru", "Preklad: " + text
    return None


portal_bot.translate_text = fake_tr
n = len(H.CALLS)
H.update(H.CLIENT, "Dobrý deň, sedačka môže prísť aj v sobotu?", first="Anna", lang="sk")
check(wait(lambda: any("Перевод на русский" in x for x in texts(H.IRINA, n))), "Ирине — с переводом на русский")
to_irina = [p for p in sent(to=H.IRINA, since=n) if "Перевод" in p.get("text", "")][0]
check("потяните сообщение влево" in to_irina["text"] and "со словацкого" in to_irina["text"] and not to_irina.get("disable_notification"),
      "подсказка про свайп, язык оригинала, со звуком")
check(wait(lambda: any("Odoslané" in x for x in texts(H.CLIENT, n))), "заказчику — «отправлено»")
settle()
check(not texts(H.CREW, n) and not texts(H.WORKER, n) and not texts(H.OWNER, n), "подрядчику и работнику разговор заказчика со студией не приходит")
row = H.bot.s.one("SELECT key FROM state WHERE key LIKE ? ORDER BY rowid DESC LIMIT 1", f"chatmap:{H.IRINA}:%")
n = len(H.CALLS)
H.update(H.IRINA, "Диван приедет в субботу утром.", first="Ирина", lang="ru", reply_to=int(row["key"].split(":")[2]))
check(wait(lambda: any("Preklad" in x for x in texts(H.CLIENT, n))), "ответ Ирины — заказчику по-словацки")
check(any("Preložené automaticky" in x for x in texts(H.CLIENT, n)), "пометка об автопереводе")
check(wait(lambda: any("Отправлено" in x for x in texts(H.IRINA, n))), "Ирине — кому доставлено")
tC = P.ensure_thread(pid, "client")
last = H.crm.one("SELECT * FROM messages WHERE thread_id=? ORDER BY id DESC LIMIT 1", tC["id"])
check(last["author_kind"] == "studio" and "sk" in json.loads(last["tr"]), "перевод сохранён в разговоре")

# ---------- заказчик пишет подрядчику: студия видит тихо и не участвует, пока не ответит ----------
code, t1 = call("/api/portal/thread", H.CLIENT, {"project_id": pid, "kind": "pc", "contractor_id": env["k2"]["id"]})
check(code == 200 and t1["kind"] == "pc" and t1["contractor"]["name"] == "Lukáš Horváth", "заказчик начал разговор с мебельщиком")
code, x = call("/api/portal/thread", H.CLIENT, {"project_id": pid, "kind": "worker", "crew_id": w2})
check(code == 403, "работнику подрядчика заказчик написать не может")
settle()
n = len(H.CALLS)
code, x = call("/api/portal/chat", H.CLIENT, {"thread_id": t1["id"], "text": "Dobrý deň, kuchyňa bude hotová do konca novembra?"})
check(code == 200, "заказчик пишет подрядчику")
check(wait(lambda: any("kuchyňa" in x for x in texts(H.CREW2, n))), "мебельщику — сообщение заказчика")
to_l = [p for p in sent(to=H.CREW2, since=n) if "kuchyňa" in p.get("text", "")][0]
check(not to_l.get("disable_notification") and "· klient" in to_l["text"], "мебельщику — со звуком, с пометкой «заказчик»")
check(wait(lambda: any("не участвуете" in x for x in texts(H.IRINA, n))), "Ирине — видит разговор заказчика с подрядчиком")
to_i = [p for p in sent(to=H.IRINA, since=n) if "не участвуете" in p.get("text", "")][0]
check(to_i.get("disable_notification") is True and "Заказчик → подрядчику Lukáš Horváth" in to_i["text"], "Ирине — тихо, кто кому пишет")
settle()
check(not texts(H.CREW, n) and not texts(H.WORKER2, n), "прорабу и технологу этот разговор не приходит")
check(P.access(vK, P.thread(t1["id"])) is None and P.access(vJ, P.thread(t1["id"])) is None, "прораб и технолог его не видят")
n = len(H.CALLS)
code, x = call("/api/portal/chat", H.CREW2, {"thread_id": t1["id"], "text": "Áno, do 28. novembra."})
check(code == 200 and wait(lambda: any("28. novembra" in x for x in texts(H.CLIENT, n))), "мебельщик ответил заказчику")
code, x = call("/api/portal/chat", H.IRINA, {"thread_id": t1["id"], "text": "Кухня — к 28 ноября, монтаж в тот же день."}, lang="ru")
check(code == 200 and P.thread(t1["id"])["studio_joined"], "студия ответила — вступила в разговор")
settle()
n = len(H.CALLS)
call("/api/portal/chat", H.CLIENT, {"thread_id": t1["id"], "text": "Ďakujem."})
check(wait(lambda: any("Ďakujem." in p.get("text", "") and not p.get("disable_notification") for p in sent(to=H.IRINA, since=n))),
      "после ответа студии — Ирине со звуком")

# ---------- Ирина пишет технологу и меняется документами; прораб не видит; заказчик — только согласованное ----------
code, tJ = call("/api/portal/thread", H.IRINA, {"project_id": pid, "kind": "worker", "crew_id": w2}, lang="ru")
check(code == 200 and tJ["kind"] == "worker", "Ирина открыла разговор с технологом")
code, f1 = call(f"/api/portal/upload?thread={tJ['id']}&name=kuhnya-variant-2.pdf", H.IRINA, raw=b"%PDF-1.4 kitchen v2", ctype="application/pdf", lang="ru")
check(code == 200, "Ирина приложила документ")
settle()
n = len(H.CALLS)
code, x = call("/api/portal/chat", H.IRINA, {"thread_id": tJ["id"], "text": "Вариант 2 кухни — посмотрите фасады.", "file_id": f1["id"]}, lang="ru")
check(code == 200 and wait(lambda: any("Вариант 2" in x for x in texts(H.WORKER2, n))), "технологу — сообщение с документом")
check(wait(lambda: any("Вариант 2" in p["caption"] and p["disable_notification"] for p in sent("sendDocument", to=H.CREW2, since=n))),
      "мебельщику — тихая копия переписки с его технологом")
check(any("Štúdio a Jana Kováčová" in x for x in texts(H.CREW2, n)), "мебельщику — пометка «студия и технолог»")
settle()
check(not texts(H.CREW, n) and not texts(H.CLIENT, n), "прорабу и заказчику — ничего")
fl = H.crm.one("SELECT * FROM files WHERE id=?", f1["id"])
check(P.can_see_file(vJ, fl) and P.can_see_file(vL, fl), "документ видят технолог и мебельщик")
check(not P.can_see_file(vK, fl) and not P.can_see_file(vW, fl) and not P.can_see_file(vC, fl), "прораб, его работник и заказчик — нет")
row = H.bot.s.one("SELECT key FROM state WHERE key LIKE ? ORDER BY rowid DESC LIMIT 1", f"chatmap:{H.CREW2}:%")
n = len(H.CALLS)
H.update(H.CREW2, "OK", first="Lukáš", lang="sk", reply_to=int(row["key"].split(":")[2]))
check(any("môžete len čítať" in x for x in texts(H.CREW2, n)), "ответ свайпом в чужой разговор — «только чтение»")
code, x = call("/api/crm/save", H.IRINA, {"entity": "file_vis", "data": {"id": f1["id"], "see_client": 1}}, lang="ru")
check(code == 200, "Ирина: этот документ видит заказчик")
fl = H.crm.one("SELECT * FROM files WHERE id=?", f1["id"])
check(P.can_see_file(vC, fl) and not P.can_see_file(vK, fl), "заказчик видит согласованный вариант, прораб — по-прежнему нет")
check(any(f["id"] == f1["id"] and f["section"] == "shared" for f in P.client_view(pid, H.CLIENT)["files"]), "у заказчика — в «согласованных»")

# ---------- документы подрядчика и работников: кто видит ----------
png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005fe02fea7d6a40000000049454e44ae426082")
ups = {}
n0 = len(H.CALLS)
for uid, vis, name, lang in ((H.CREW2, "client", "kuhnya-smontirovana.png", "sk"), (H.CREW2, "studio", "smeta-fabriki.pdf", "sk"),
                             (H.CREW2, "team", "chertezh-dlya-montazha.pdf", "sk"), (H.WORKER2, "head", "zamery-tehnologa.pdf", "sk"),
                             (H.WORKER, "team", "raskladka-plitki.pdf", "ru"), (H.WORKER, "client", "plitka-gotovo.png", "ru")):
    data = png if name.endswith(".png") else b"%PDF-1.4 x"
    code, f = call(f"/api/portal/upload?project={pid}&name={name}&vis={vis}&title=" + name.split(".")[0], uid, raw=data,
                   ctype="image/png" if name.endswith(".png") else "application/pdf", lang=lang)
    check(code == 200 and f["vis"] == vis, f"документ {name} ({vis})")
    ups[name] = H.crm.one("SELECT * FROM files WHERE id=?", f["id"])
check(wait(lambda: len([x for x in texts(H.IRINA, n0) if "Новый документ" in x]) == 6), "Ирине — о каждом новом документе")
check(wait(lambda: any("zamery-tehnologa" in x for x in texts(H.CREW2, n0))), "мебельщику — документ технолога")
settle()
check(not texts(H.CLIENT, n0), "заказчику — ничего, пока Ирина не одобрит (решено 25.10.2026)")
asks = [p_ for p_ in msgs(H.IRINA, n0) if "Показать заказчику?" in (p_.get("text") or "")]
check(len(asks) == 2 and all("fa:" in json.dumps(p_.get("reply_markup"), ensure_ascii=False) for p_ in asks),
      "Ирине — «Показать заказчику?» с кнопками у двух документов, которые просят показать заказчику")
check(sorted(r["name"] for r in H.crm.q("SELECT name FROM files WHERE review=1")) == ["kuhnya-smontirovana.png", "plitka-gotovo.png"],
      "ждут решения Ирины — эти два")
code, f = call(f"/api/portal/upload?project={pid}&name=x.pdf&vis=head", H.CREW2, raw=b"%PDF", ctype="application/pdf")
check(code == 400, "у подрядчика нет статуса «только руководитель»")
code, f = call(f"/api/portal/upload?project={pid}&name=x.pdf&vis=client", H.CLIENT, raw=b"%PDF", ctype="application/pdf")
check(code == 403, "заказчик документы подрядчиков не загружает")


def see(v):
    return {k for k, f in ups.items() if P.can_see_file(v, f)}


check(see(vC) == set(), f"заказчик: пока Ирина не одобрила — ничего {see(vC)}")
n = len(H.CALLS)
H.update(H.IRINA, data=f"fa:{ups['kuhnya-smontirovana.png']['id']}:1", first="Ирина", lang="ru")
check(wait(lambda: any("Nový dokument" in x for x in texts(H.CLIENT, n))), "Ирина нажала «Показать заказчику» — заказчику сообщение")
check(wait(lambda: any("klientovi" in x or "показала" in x for x in texts(H.CREW2, n))), "мебельщику — Ирина показала ваш документ заказчику")
code, r = call("/api/crm/save", H.IRINA, {"entity": "file_approve", "data": {"id": ups["plitka-gotovo.png"]["id"], "show": True}}, lang="ru")
check(code == 200 and not H.crm.q("SELECT id FROM files WHERE review=1"), "второй — из «Студии»; ждущих решения нет")
ups = {k: H.crm.one("SELECT * FROM files WHERE id=?", f["id"]) for k, f in ups.items()}
check(see(vC) == {"kuhnya-smontirovana.png", "plitka-gotovo.png"}, f"заказчик: только одобренные Ириной {see(vC)}")
check(see(vL) == {"kuhnya-smontirovana.png", "smeta-fabriki.pdf", "chertezh-dlya-montazha.pdf", "zamery-tehnologa.pdf"}, f"мебельщик: свои и технолога {see(vL)}")
check(see(vJ) == {"kuhnya-smontirovana.png", "chertezh-dlya-montazha.pdf", "zamery-tehnologa.pdf"}, f"технолог: для бригады и свои {see(vJ)}")
check(see(vK) == {"raskladka-plitki.pdf", "plitka-gotovo.png"}, f"прораб: только своей бригады {see(vK)}")
check(see(vW) == {"raskladka-plitki.pdf", "plitka-gotovo.png"}, f"плиточник: свои {see(vW)}")
vI = P.viewer(H.IRINA, pid, designer=True)
check(see(vI) == set(ups), "Ирина видит все документы")
check("заказчик" in P.audience(ups["kuhnya-smontirovana.png"]) and "заказчик" not in P.audience(ups["smeta-fabriki.pdf"]), "кто видит — подпись для Ирины")
code, x = call("/api/portal/file", H.CREW2, {"id": ups["smeta-fabriki.pdf"]["id"], "vis": "client"})
fsm = H.crm.one("SELECT * FROM files WHERE id=?", ups["smeta-fabriki.pdf"]["id"])
check(code == 200 and x["file"]["approval"] == "wait" and not P.can_see_file(vC, fsm) and fsm["review"] == 1,
      "подрядчик попросил показать заказчику — ждёт Ирину, заказчик пока не видит")
H.crm.approve_file({"id": fsm["id"], "show": False}, "Ирина")
code, x = call(f"/api/portal/project?id={pid}", H.CREW2)
check(any(f["id"] == fsm["id"] and f["approval"] == "no" for f in x["files"]), "Ирина не показала — подрядчик это видит")
code, x = call("/api/portal/file", H.CREW, {"id": ups["smeta-fabriki.pdf"]["id"], "delete": True}, lang="uk")
check(code == 400, "чужой документ удалить нельзя")
code, x = call("/api/portal/file", H.CREW2, {"id": ups["zamery-tehnologa.pdf"]["id"], "vis": "team"})
check(code == 200, "подрядчик может поменять статус документа своего работника")
code, x = call("/api/portal/file", H.WORKER2, {"id": ups["chertezh-dlya-montazha.pdf"]["id"], "delete": True})
check(code == 400, "работник не удаляет документ руководителя")

# ---------- группа, которую собирает Ирина ----------
settle()
n = len(H.CALLS)
code, x = call("/api/crm/save", H.IRINA, {"entity": "group", "data": {"project_id": pid, "title": "Кухня: технолог",
                                                                       "members": [{"kind": "contractor", "id": env["k2"]["id"]}, {"kind": "crew", "id": w2}]}}, lang="ru")
check(code == 200 and any(t["kind"] == "group" and t["title"] == "Кухня: технолог" for t in x["threads"]), "Ирина собрала группу")
gid = next(t["id"] for t in x["threads"] if t["kind"] == "group")
check(wait(lambda: any("skupinu" in x for x in texts(H.CREW2, n)) and any("skupinu" in x for x in texts(H.WORKER2, n))),
      "участникам — сообщение о группе на их языке")
settle()
check(not texts(H.CREW, n) and not texts(H.CLIENT, n), "прорабу и заказчику — нет")
g = P.thread(gid)
check(P.access(vL, g) == "write" and P.access(vJ, g) == "write" and P.access(vK, g) is None and P.access(vC, g) is None, "кто в группе")
code, x = call("/api/crm/save", H.IRINA, {"entity": "group", "data": {"project_id": pid, "title": "x", "members": [{"kind": "crew", "id": 999}]}}, lang="ru")
check(code == 400, "в группу — только люди этого проекта")
row = H.bot.s.one("SELECT key FROM state WHERE key LIKE ? ORDER BY rowid DESC LIMIT 1", f"chatmap:{H.WORKER2}:%")
n = len(H.CALLS)
H.update(H.WORKER2, "Fasády budú dubové, posielam rozmery.", first="Jana", lang="sk", reply_to=int(row["key"].split(":")[2]))
check(wait(lambda: any("Fasády" in x for x in texts(H.CREW2, n))) and wait(lambda: any("Группа «Кухня: технолог»" in x for x in texts(H.IRINA, n))),
      "технолог ответил в группу свайпом — мебельщику и Ирине")
settle()
check(not texts(H.CREW, n), "прорабу — нет")

# ---------- работник и подрядчик пишут прямо в бот — в свой разговор со студией ----------
n = len(H.CALLS)
H.update(H.WORKER, "Плитка закончилась, нужна ещё одна коробка.", first="Олег", lang="ru")
check(wait(lambda: any("Работник Олег Кравец (плиточник)" in x for x in texts(H.IRINA, n))), "Ирине — сообщение работника с пометкой")
check(wait(lambda: any("Плитка закончилась" in p.get("text", "") and p.get("disable_notification") for p in sent(to=H.CREW, since=n))),
      "прорабу — тихая копия от его работника")
settle()
check(not texts(H.CLIENT, n), "заказчику — нет")
n = len(H.CALLS)
H.update(H.CREW, "Завтра начинаем чистовые.", first="Михайло", lang="uk")
pick = [p for p in sent(to=H.CREW, since=n) if "До якого проєкту" in p.get("text", "")]
check(pick and len(pick[0]["reply_markup"]["inline_keyboard"]) == 2, "у прораба два проекта — бот спрашивает, к какому")
H.update(H.CREW, data=f"pp:{pid}", first="Михайло", lang="uk")
check(wait(lambda: any("Подрядчик Михаил Бондаренко (Прораб)" in x for x in texts(H.IRINA, n))), "прораб пишет в бот — Ирине")
settle()
check(not texts(H.WORKER, n) and not texts(H.CLIENT, n), "работнику и заказчику — нет")

# ---------- наблюдатель «Разработчик ПО» ----------
cid_obs = P.ensure_observer(H.OWNER)
check(cid_obs and P.is_observer(H.OWNER), "создан наблюдатель")
check(P.ensure_observer(H.OWNER) is None, "второй раз не создаётся")
raises(lambda: H.crm.link_contractor({"project_id": pid, "contractor_id": cid_obs}, "Ирина"), "наблюдателя в проект не добавить")
check(OBS not in json.dumps(P.client_view(pid, H.CLIENT), ensure_ascii=False), "заказчик не видит «Разработчик ПО»")
check(OBS not in json.dumps(P.participants(pid), ensure_ascii=False), "в участниках проекта его нет")
code, me = call("/api/portal/me", H.OWNER, lang="ru")
check(code == 200 and me["observer"] and any(p["id"] == pid and "observer" in p["roles"] for p in me["projects"]), "наблюдатель видит все проекты")
code, ov = call(f"/api/portal/project?id={pid}", H.OWNER, lang="ru")
check(code == 200 and ov["role"] == "observer" and ov["readonly"], "кабинет наблюдателя")
check({t["kind"] for t in ov["threads"]} >= {"client", "pc", "org", "worker", "group"}, "наблюдатель видит все разговоры")
check({f["name"] for f in ov["files"]} >= set(ups) | {"kuhnya-variant-2.pdf"}, "и все документы")
code, x = call(f"/api/portal/chat?thread={gid}", H.OWNER, lang="ru")
check(code == 200 and x["readonly"] and any("Fasády" in m["text"] for m in x["messages"]), "наблюдатель читает группу")
code, x = call("/api/portal/chat", H.OWNER, {"thread_id": gid, "text": "тест"}, lang="ru")
check(code == 403, "наблюдатель не пишет")
code, x = call(f"/api/portal/project?id={pid}&preview=worker&crew={w2}", H.OWNER, lang="ru")
check(code == 200 and x["role"] == "worker" and x["preview"], "наблюдатель смотрит глазами работника")
settle()
n = len(H.CALLS)
code, x = call("/api/portal/chat", H.CLIENT, {"thread_id": tC["id"], "text": "Ešte otázka k dverám."})
check(wait(lambda: any(x.startswith("🧪") and "dverám" in x for x in texts(H.OWNER, n))), "наблюдателю — копия 🧪")
check(all(p.get("disable_notification") for p in msgs(H.OWNER, n)), "копии наблюдателю — без звука")

# ---------- суммы подрядчика: вносит подрядчик → заказчик подтверждает ----------
settle()
n = len(H.CALLS)
r = P.contractor_stage(H.CREW, {"project_id": pid, "link_id": env["l1"], "title": "Электрика", "amount": "4200", "currency": "EUR"}, "Михайло")
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
raises(lambda: P.contractor_stage(H.CREW, {"id": st["id"], "project_id": pid, "link_id": env["l1"], "title": "Электрика", "amount": "5000"}, "Михайло"),
       "подтверждённое подрядчик менять не может")
H.crm.save_stage({"id": st["id"], "project_id": pid, "link_id": env["l1"], "title": "Электрика", "amount": 4600, "currency": "EUR",
                  "mode": "pct", "pct": 10}, "Ирина")
check(H.crm.one("SELECT confirmed FROM stages WHERE id=?", st["id"])["confirmed"] is None, "студия изменила сумму — подтверждение снято")
raises(lambda: P.client_stage(H.CREW, st["id"], "confirm", "", "x"), "подрядчик не может подтверждать")
raises(lambda: P.contractor_stage(H.WORKER, {"project_id": pid, "link_id": env["l1"], "title": "x", "amount": "1"}, "Олег"), "работник суммы не вносит")

# ---------- товар, услуга — сообщения заказчику ----------
n = len(H.CALLS)
H.bot.portal_event("order_new", order_id=env["o1"])
check(any("Nový tovar" in x and "3 200 €" in x for x in texts(H.CLIENT, n)), "новый товар — заказчику")
check(not any("2 350" in p.get("text", "") for p in sent(since=n)), "закупка в сообщениях не видна")
check(not texts(H.WORKER, n) and not texts(H.CREW, n), "работнику и подрядчику о товарах — нет")
H.bot.portal_event("order_delivered", order_id=env["o1"])
check(any("Zostáva doplatiť" in x and "1 600 €" in x for x in texts(H.CLIENT, n)), "доставлен — сколько доплатить")

# ---------- напоминания об оплате ----------
due = P.due_reminders(date(2026, 10, 24))
check(any(x["service"]["title"] == "Авторское сопровождение" and x["due"] == "2026-10-15" and x["stage"] == "overdue" for x in due),
      f"просрочен октябрь {due}")
check(not any(x["due"] < "2026-08-15" for x in due), "до внесения услуги — не напоминаем")
n = len(H.CALLS)
check(H.bot.portal_reminders(now=datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc)) >= 1, "напоминание отправлено")
check(any("Platba zatiaľ neprišla" in x for x in texts(H.CLIENT, n)), "заказчику — напоминание по-словацки")
check(any("Не оплачено 7 дней" in x for x in texts(H.IRINA, n)), "Ирине — напоминание")
check(H.bot.portal_reminders(now=datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)) == 0, "второй раз не повторяется")
check(H.bot.portal_reminders(now=datetime(2026, 10, 24, 21, 0, tzinfo=timezone.utc)) == 0, "ночью не напоминает")

# ---------- HTTP: кабинет и «Студия» ----------
code, me = call("/api/portal/me", H.CLIENT)
check(code == 200 and me["lang"] == "sk" and me["projects"][0]["id"] == pid, "кабинет: мои проекты")
code, pv = call(f"/api/portal/project?id={pid}", H.CLIENT)
check(code == 200 and pv["role"] == "client" and "buy" not in json.dumps(pv), "кабинет заказчика по HTTP")
code, x = call(f"/api/portal/project?id={pid}", H.CREW, lang="uk")
check(code == 200 and x["role"] == "contractor" and x["team"][0]["name"] == "Олег Кравец", "кабинет подрядчика: и бригада")
code, x = call(f"/api/portal/chat?thread={tC['id']}", H.CREW, lang="uk")
check(code == 403, "подрядчику разговор заказчика со студией закрыт")
code, x = call(f"/api/portal/chat?thread={tW['id']}", H.CREW, lang="uk")
check(code == 200 and x["readonly"], "подрядчик читает разговор студии со своим работником")
code, x = call("/api/portal/chat", H.CREW, {"thread_id": tW["id"], "text": "x"}, lang="uk")
check(code == 403, "и не пишет в него")
code, x = call(f"/api/portal/project?id={pid}", 999)
check(code == 403, "чужому — нет доступа")
code, chat = call(f"/api/portal/chat?thread={tC['id']}", H.CLIENT)
check(code == 200 and any(m["tr"] and m["tr"].startswith("Preklad") for m in chat["messages"]), "заказчик видит перевод")
check(P.unread(tC["id"], P.viewer(H.CLIENT, pid)) == 0, "прочитано")
code, th = call(f"/api/portal/threads?project={pid}", H.CLIENT)
check(code == 200 and not any(t["kind"] in ("org", "worker", "group") for t in th["threads"]), "заказчику — только его разговоры")
code, x = call(f"/api/portal/project?id={pid}&preview=client", H.IRINA, lang="ru")
check(code == 200 and x.get("preview"), "Ирина: как видит заказчик")
code, x = call(f"/api/portal/project?id={pid}&preview=contractor&link={env['l1']}", H.IRINA, lang="ru")
check(code == 200 and x["role"] == "contractor", "Ирина: как видит подрядчик")
code, x = call(f"/api/portal/project?id={pid}&preview=worker&crew={w1}", H.IRINA, lang="ru")
check(code == 200 and x["role"] == "worker" and "total_eur" not in json.dumps(x), "Ирина: как видит работник")
code, x = call(f"/api/portal/project?id={pid}&preview=client", H.CLIENT)
check(code == 200 and not x.get("preview"), "заказчику превью не даётся (свой кабинет)")
code, x = call("/api/portal/stage", H.CLIENT, {"action": "dispute", "id": st["id"], "note": "Mali sme dohodnutých 4 200 €"})
check(code == 200 and H.crm.one("SELECT disputed FROM stages WHERE id=?", st["id"])["disputed"], "заказчик: не согласен")
code, x = call("/api/portal/ui", H.CLIENT, {"lang": "de", "size": "l"})
check(code == 200 and x["lang"] == "de" and x["size"] == "l", "язык и размер — свои")
code, x = call("/api/crm/invite", H.IRINA, {"kind": "client", "ref_id": env["b"]["id"], "project_id": pid, "lang": "de"}, lang="ru")
check(code == 200 and x["link"].startswith("https://t.me/dumskaya_test_bot?start=pj_") and "Guten Tag" in x["text"], "Ирина: ссылка для заказчика")
k3 = H.crm.save_contractor({"name": "Ján Okno", "trade": "Окна"}, "Ирина")
code, x = call("/api/crm/invite", H.IRINA, {"kind": "contractor", "ref_id": k3["id"], "lang": "sk"}, lang="ru")
check(code == 200 and "Pripojiť sa stačí raz" in x["text"], "Ирина: ссылка подрядчику из карточки, без проекта")
code, x = call("/api/crm/save", H.IRINA, {"entity": "crew", "data": {"contractor_id": env["k1"]["id"], "name": "Игорь", "position": "электрик",
                                                                      "project_id": pid}}, lang="ru")
check(code == 200 and any(w["name"] == "Игорь" and w["assigned"] for c in x["participants"]["contractors"] for w in c["crew"]),
      "Ирина сама добавила работника подрядчику и отметила на объекте")
code, x = call("/api/crm/save", H.IRINA, {"entity": "service", "data": {"project_id": pid, "title": "Доп. визуализации", "kind": "once",
                                                                         "amount": 300, "start": date.today().isoformat(), "notify": True}}, lang="ru")
check(code == 200 and any(s["title"] == "Доп. визуализации" for s in x["services"]) and x["participants"], "Ирина: доп. услуга, проект с участниками")
code, x = call(f"/api/crm/project?id={pid}", H.IRINA, lang="ru")
check(code == 200 and len(x["people"]) == 2 and x["chat"]["count"] >= 10 and x["orders"] and len(x["threads"]) >= 5, "Ирина: проект целиком")
check(any(f["category"] == "work" and f.get("audience") for f in x["files"]), "Ирина: документы подрядчиков с подписью «кто видит»")
check(OBS not in json.dumps(x["participants"], ensure_ascii=False), "наблюдателя нет среди участников и в «Студии»")
code, x = call(f"/api/crm/project?id={pid}", H.CLIENT)
check(code == 403, "заказчику «Студия» закрыта")
# убрать работника из бригады — доступ закрывается
code, r = call("/api/portal/team", H.CREW, {"action": "remove", "crew_id": w1}, lang="uk")
check(code == 200 and not any(w["id"] == w1 for w in r["team"]), "подрядчик убрал работника")
check(wait(lambda: H.bot.user(H.WORKER)["status"] == "removed"), "у работника доступ к боту закрыт")
code, x = call(f"/api/portal/project?id={pid}", H.WORKER, lang="ru")
check(code == 403, "бывший работник проект не видит")
# закрыть кабинет подрядчику
code, x = call("/api/crm/unlink", H.IRINA, {"kind": "contractor", "ref_id": env["k1"]["id"], "project_id": pid}, lang="ru")
check(code == 200, "Ирина закрыла кабинет подрядчику")
check(wait(lambda: H.bot.user(H.CREW)["status"] == "removed"), "подрядчик без кабинета — доступ к боту закрыт")
code, x = call(f"/api/portal/project?id={pid}", H.CREW, lang="uk")
check(code == 403, "подрядчик больше не видит проект")
# удалить наблюдателя
code, x = call("/api/crm/delete", H.IRINA, {"entity": "contractor", "id": cid_obs}, lang="ru")
check(code == 200 and not P.is_observer(H.OWNER), "наблюдатель удалён")
check(P.ensure_observer(H.OWNER) is None, "и не создаётся снова")
code, x = call("/api/portal/me", H.OWNER, lang="ru")
check(code == 403, "разработчику кабинет больше не отдаётся")
check(H.bot.user(H.OWNER)["role"] == "owner" and H.bot.user(H.OWNER)["status"] == "active", "разработчик остался разработчиком")
st0 = H.crm.stats("all")
check(st0["payments"] == 3175 + 2000 + 2000 and st0["margin"] == 850 + 280, f"доход: оплаты без товаров, наценка товаров {st0['payments']} {st0['margin']}")

# ---------- язык кабинета: любой из европейских, человек выбирает сам ----------
import langs  # noqa: E402
FR, PLP = langs.pack("fr"), langs.pack("pl")
check(len(langs.CODES) >= 30 and FR.get("ui") and FR.get("bot"), "языки кабинета: европейские, с готовыми переводами")
inv5 = P.make_invite("client", env["b"]["id"], pid, "fr", "Ирина")
check(inv5["lang"] == "fr", "ссылка заказчику — на французском")
txt = H.bot.invite_text("fr", "client", "Peter", "Appartement", "https://t.me/x?start=pj_x")
check(txt == FR["bot"]["invite_client"].format(name="Peter", project="Appartement", link="https://t.me/x?start=pj_x"), "текст ссылки — французский")
n = len(H.CALLS)
H.update(H.CLIENT2, "/start pj_" + inv5["token"], first="Peter", lang="en")          # Telegram по-английски, ссылка — по-французски
check(H.bot.lang_of(H.CLIENT2) == "fr", "язык кабинета — из ссылки, которую выбрала студия")
menu = [p for m, p in H.CALLS[n:] if m == "setChatMenuButton" and p["chat_id"] == H.CLIENT2]
check(menu and menu[-1]["menu_button"]["text"] == FR["bot"]["menu"], "кнопка меню — по-французски")
check(any(FR["bot"]["welcome_client"].split("{")[0].strip() in x for x in texts(H.CLIENT2, n)), "приветствие — по-французски")
code, me = call("/api/portal/me", H.CLIENT2, lang="en")
check(code == 200 and me["lang"] == "fr" and len(me["langs"]) == len(langs.CODES) and me["langs"][0][0] == "ru", "кабинет: язык и список всех языков")
code, x = call("/api/portal/i18n?lang=fr", H.CLIENT2)
check(code == 200 and x["lang"] == "fr" and len(x["ui"]) >= 200, "тексты кабинета по-французски — с сервера")
code, x = call("/api/portal/i18n?lang=nb", 0)
check(code == 200 and x["lang"] == "no" and x["ui"], "норвежский по коду Telegram nb, без входа (это просто тексты)")
code, x = call("/api/portal/ui", H.CLIENT2, {"lang": "pl"}, lang="en")
check(code == 200 and x["lang"] == "pl" and H.bot.lang_of(H.CLIENT2) == "pl", "заказчик сам выбрал польский")
menu = [p for m, p in H.CALLS if m == "setChatMenuButton" and p["chat_id"] == H.CLIENT2]
check(menu[-1]["menu_button"]["text"] == PLP["bot"]["menu"], "кнопка меню — по-польски")
targets = []
portal_bot.translate_text = lambda text, target: targets.append(target) or (("ru", f"[{target}] " + text) if target != "ru" else None)
n = len(H.CALLS)
code, x = call("/api/portal/chat", H.IRINA, {"thread_id": tC["id"], "text": "Добрый вечер! Шторы повесим в пятницу."}, lang="ru")
check(code == 200 and wait(lambda: any("[pl] Добрый вечер" in x for x in texts(H.CLIENT2, n))), "сообщение Ирины — заказчику на польском")
check(any(PLP["bot"]["auto_tr"] in x for x in texts(H.CLIENT2, n)), "пометка «переведено автоматически» — по-польски")
check("pl" in targets and "de" in targets, "перевод — на язык каждого получателя (Анна выбрала немецкий)")
check(P.label("Прораб", "pl") == PLP["fixed"]["Прораб"] and P.label("Премиум", "fr") == FR["fixed"]["Премиум"], "виды работ и пакеты — по словарю")
code, x = call(f"/api/portal/project?id={pid}", H.CLIENT2, lang="en")
check(code == 200 and x["lang"] == "pl", "кабинет открывается на выбранном языке")
code, x = call(f"/api/portal/project?id={pid}&preview=client&lang=fi", H.IRINA, lang="ru")
check(code == 200 and x["lang"] == "fi", "Ирина: как видит заказчик — на любом языке")
# ---------- сотрудник студии: Ирина добавляет, даёт ссылку, назначает на проекты; без денег и контактов ----------
code, r = call("/api/crm/save", H.IRINA, {"entity": "assistant", "data": {"name": "Мария Петренко", "position": "визуализатор",
                                                                          "phone": "+421 900 000 111"}}, lang="ru")
check(code == 200 and r["saved_id"], "Ирина добавила сотрудника студии")
aid = r["saved_id"]
code, st = call("/api/crm/state", H.IRINA, lang="ru")
check(code == 200 and any(a["id"] == aid and a["position"] == "визуализатор" and a["projects"] == [] for a in st["assistants"]), "сотрудник — в «Студии»")
code, inv = call("/api/crm/invite", H.IRINA, {"kind": "assistant", "ref_id": aid, "lang": "ru"}, lang="ru")
check(code == 200 and "кабинет сотрудника студии" in inv["text"] and "Ирина Думская" in inv["text"], "ссылка сотруднику — от имени Ирины")
n = len(H.CALLS)
H.update(H.ASSIST, "/start " + inv["link"].split("start=")[1], first="Мария", lang="ru")
u = H.bot.user(H.ASSIST)
check(u and u["role"] == "assistant" and u["status"] == "active", "сотрудник подключился: роль «Сотрудник студии»")
check(any("кабинет сотрудника студии" in x for x in texts(H.ASSIST, n)), "сотруднику — приветствие")
check(any("сотрудник студии" in x and "Пока ни на одном проекте" in x for x in texts(H.IRINA, n)), "Ирине — подключился, назначьте на проект")
code, me = call("/api/portal/me", H.ASSIST, lang="ru")
check(code == 200 and me["staff"] and not me["projects"], "кабинет есть, проектов пока нет")
code, x = call(f"/api/portal/project?id={pid}", H.ASSIST, lang="ru")
check(code == 403, "проект без назначения — закрыт")
n = len(H.CALLS)
code, r = call("/api/crm/save", H.IRINA, {"entity": "passist", "data": {"project_id": pid, "assistant_id": aid, "on": True}}, lang="ru")
check(code == 200 and any(a["id"] == aid and a["assigned"] for a in r["assistants"]), "Ирина назначила сотрудника на проект")
check(wait(lambda: any("назначила вас на проект" in x for x in texts(H.ASSIST, n))), "сотруднику — сообщение о назначении")
code, me = call("/api/portal/me", H.ASSIST, lang="ru")
check(code == 200 and [p["roles"] for p in me["projects"] if p["id"] == pid] == [["assistant"]], "проект в кабинете сотрудника")
code, av = call(f"/api/portal/project?id={pid}", H.ASSIST, lang="ru")
dump = json.dumps(av, ensure_ascii=False)
check(code == 200 and av["role"] == "assistant" and not av["readonly"], "кабинет сотрудника студии")
check(not any(w in dump for w in ("+421 905", "+421 911", "+421 944", "+421 948", "@example", "anna@", "lukas@", "@mb_stav", "18000", "21400", "6350", "commission", "total_eur", "buy")),
      "сотруднику — ни денег, ни контактов заказчиков и подрядчиков")
check({c["name"] for c in av["participants"]["contractors"]} >= {"Михаил Бондаренко", "Lukáš Horváth"} and av["participants"]["clients"],
      "участники проекта — по именам")
names = {f["name"] for f in av["files"]}
check("obmernyj-plan.pdf" in names and "oprosnik.pdf" in names and "schet-baxter-zakupka.pdf" not in names, "документация — да, «Другое» — нет")
code, th = call(f"/api/portal/threads?project={pid}", H.ASSIST, lang="ru")
check(code == 200 and {t["kind"] for t in th["threads"]} >= {"client", "pc", "org", "worker", "group"} and all(t["access"] == "write" for t in th["threads"]),
      "все разговоры проекта — и писать в них")
n = len(H.CALLS)
code, x = call("/api/portal/chat", H.ASSIST, {"thread_id": tC["id"], "text": "Добрый день! Визуализации спальни пришлю в пятницу."}, lang="ru")
check(code == 200, "сотрудник пишет заказчикам")
check(wait(lambda: any("Мария Петренко · DUMSKAYA DESIGN" in x for x in texts(H.CLIENT, n))), "заказчику — от имени студии")
settle()
check(any(p.get("disable_notification") and "сотрудник студии" in (p.get("text") or "") for p in msgs(H.IRINA, n)), "Ирине — тихая копия")
m = H.crm.one("SELECT * FROM messages WHERE thread_id=? ORDER BY id DESC LIMIT 1", tC["id"])
check(m["author_kind"] == "assistant" and m["author_name"] == "Мария Петренко", "в разговоре — сотрудник студии")
n = len(H.CALLS)
code, x = call("/api/portal/chat", H.CLIENT, {"thread_id": tC["id"], "text": "Ďakujeme, čakáme."})
check(code == 200 and wait(lambda: any("Разговор:" in x for x in texts(H.ASSIST, n))), "сообщение заказчика — сотруднику, с названием разговора")
settle()
check(any(not p.get("disable_notification") for p in msgs(H.ASSIST, n)), "сотруднику — со звуком")
n = len(H.CALLS)
H.update(H.ASSIST, "Просто текст", first="Мария", lang="ru")
check(wait(lambda: any("Просто текст" in x and "видите только вы двое" in x for x in texts(H.IRINA, n))), "без ответа свайпом — Ирине, в их личный разговор")
settle()
check(not any("Просто текст" in x for u in (H.CLIENT, H.CREW, H.OWNER) for x in texts(u, n)), "больше никому не ушло")
png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005fe02fea7d6a40000000049454e44ae426082")
n = len(H.CALLS)
code, f1 = call(f"/api/portal/upload?project={pid}&cat=visual&vis=studio&name=spalnya-variant-2.png&title=" + urllib.parse.quote("Спальня, вариант 2"), H.ASSIST,
                raw=png, ctype="image/png", lang="ru")
check(code == 200 and f1["mine"] and f1["can_edit"], "сотрудник добавил визуализацию (пока только студии)")
check(wait(lambda: any("Новый файл" in x and "Визуализации" in x and "Видят:" in x and "Показать заказчику?" not in x for x in texts(H.IRINA, n))),
      "Ирине — новый файл (только студии — спрашивать про заказчика не нужно)")
cv = P.client_view(pid, H.CLIENT)
check(not any(f["id"] == f1["id"] for f in cv["files"]), "заказчик его не видит")
code, x = call(f"/api/portal/thumb?id={f1['id']}", H.ASSIST, raw=png, ctype="image/jpeg", lang="ru")
check(code == 200 and H.crm.one("SELECT thumb FROM files WHERE id=?", f1["id"])["thumb"], "превью своей визуализации сотрудник делает сам")
code, x = call(f"/api/portal/thumb?id={f1['id']}", H.CLIENT, raw=png, ctype="image/jpeg")
check(code == 403, "чужому файлу превью не поставить")
code, x = call("/api/portal/file", H.ASSIST, {"id": f1["id"], "vis": "default"}, lang="ru")
check(code == 200 and x["file"]["approval"] == "wait" and not any(f["id"] == f1["id"] for f in P.client_view(pid, H.CLIENT)["files"]),
      "сотрудник открыл — заказчик увидит, когда одобрит Ирина")
H.crm.approve_file({"id": f1["id"], "show": True}, "Ирина")
check(any(f["id"] == f1["id"] for f in P.client_view(pid, H.CLIENT)["files"]), "Ирина одобрила — заказчик видит")
code, x = call(f"/api/portal/upload?project={pid}&cat=other&vis=default&name=schet.pdf", H.ASSIST, raw=b"%PDF", ctype="application/pdf", lang="ru")
check(code == 400, "в «Другое» сотрудник не добавляет")
code, x = call(f"/api/portal/project?id={pid}&preview=assistant&assistant={aid}", H.IRINA, lang="ru")
check(code == 200 and x["role"] == "assistant" and x["readonly"], "Ирина: как видит сотрудник")
code, x = call("/api/crm/state", H.ASSIST, lang="ru")
check(code == 403, "в «Студию» сотруднику нельзя")
code, x = call("/api/portal/stage", H.ASSIST, {"action": "save", "project_id": pid, "link_id": env["l1"], "title": "x", "amount": 1}, lang="ru")
check(code == 400, "суммы подрядчиков сотрудник не вносит")
code, r = call("/api/crm/save", H.IRINA, {"entity": "passist", "data": {"project_id": pid, "assistant_id": aid, "on": False}}, lang="ru")
code, x = call(f"/api/portal/project?id={pid}", H.ASSIST, lang="ru")
check(code == 403 and P.has_cabinet(H.ASSIST), "снят с проекта — проект закрыт, кабинет остаётся")
n = len(H.CALLS)
code, r = call("/api/crm/save", H.IRINA, {"entity": "assistant_remove", "data": {"id": aid}}, lang="ru")
check(code == 200 and wait(lambda: H.bot.user(H.ASSIST)["status"] == "removed"), "сотрудник убран — доступ к боту закрыт")

# ---------- поставщик (плитка): как подрядчик, вместо работ — поставки ----------
code, k3 = call("/api/crm/save", H.IRINA, {"entity": "contractor", "data": {"name": "Keramika Plus", "kind": "supplier", "trade": "Плитка",
                                                                            "phone": "+421 903 777 888"}}, lang="ru")
check(code == 200 and k3["kind"] == "supplier", "поставщик в контактах")
code, r = call("/api/crm/save", H.IRINA, {"entity": "link", "data": {"project_id": pid, "contractor_id": k3["id"], "trade": "Плитка"}}, lang="ru")
l3 = r["saved_id"]
code, inv = call("/api/crm/invite", H.IRINA, {"kind": "contractor", "ref_id": k3["id"], "project_id": pid, "lang": "sk"}, lang="ru")
check(code == 200 and "dodávateľov materiálu" in inv["text"], "ссылка поставщику — текст поставщика")
n = len(H.CALLS)
H.update(H.SUPP, "/start " + inv["link"].split("start=")[1], first="Peter", lang="sk")
check(any("dodávate materiál" in x for x in texts(H.SUPP, n)), "поставщику — его приветствие")
check(any("поставщик" in x for x in texts(H.IRINA, n)), "Ирине — подключился поставщик")
n = len(H.CALLS)
code, x = call("/api/portal/stage", H.SUPP, {"action": "save", "project_id": pid, "link_id": l3, "title": "Obklady kúpeľne", "amount": 2400}, lang="sk")
check(code == 200 and x["mine"][0]["kind"] == "supplier", "поставщик внёс сумму поставки")
check(wait(lambda: any("Potvrďte sumu dodávky" in x for x in texts(H.CLIENT, n)) or any("сумму поставки" in x for x in texts(H.IRINA, n))),
      "заказчику — подтвердить сумму поставки")
settle()
check(any("Поставщик Keramika Plus" in x and "сумму поставки" in x for x in texts(H.IRINA, n)), "Ирине — поставщик внёс сумму поставки")
cv = P.client_view(pid, H.CLIENT)
check(any(c["kind"] == "supplier" and c["trade"] == "Плитка" for c in cv["contractors"]), "заказчик видит поставщика")
check(P.label("Плитка", "sk") == "Obklady a dlažba" and P.label("Напольные покрытия", "de") == "Bodenbeläge", "категории поставщиков — по словарю")
PLB = langs.pack("pl")["bot"]
check(H.bot.invite_text("pl", "supplier", "Jan", "", "L") == PLB["invite_supplier"].format(name="Jan", link="L"), "ссылка поставщику — по-польски")
check(H.bot.invite_text("fr", "assistant", "Marie", "", "L") == FR["bot"]["invite_assistant"].format(name="Marie", head="Irina Dumskaya", link="L"),
      "ссылка сотруднику студии — по-французски, от имени Ирины")
check(P.label("Плитка", "fi") == langs.pack("fi")["fixed"]["Плитка"] and P.label("Сантехника", "el") == langs.pack("el")["fixed"]["Сантехника"],
      "категории поставщиков — на всех языках")
# ---------- завершить проект и вернуть в работу ----------
svc = H.crm.one("SELECT * FROM services WHERE project_id=? AND kind='monthly'", pid)
check(svc and not svc["stopped"], "помесячная услуга идёт")
code, r = call("/api/crm/save", H.IRINA, {"entity": "project_status", "data": {"id": pid, "status": "done", "finished": "2026-10-24",
                                                                               "stop_services": True}}, lang="ru")
check(code == 200 and r["project"]["status"] == "done" and r["project"]["finished"] == "2026-10-24", "Ирина завершила проект")
check(H.crm.one("SELECT stopped FROM services WHERE id=?", svc["id"])["stopped"] == "2026-10-24", "помесячная услуга остановлена датой окончания")
code, me = call("/api/portal/me", H.CLIENT)
check(any(p["id"] == pid and p["status"] == "done" for p in me["projects"]), "заказчик по-прежнему видит проект — «Завершено»")
check(not [x for x in P.due_reminders(date(2026, 12, 20)) if x["project"]["id"] == pid], "по завершённому проекту напоминаний нет")
code, r = call("/api/crm/save", H.IRINA, {"entity": "project_status", "data": {"id": pid, "status": "done", "finished": "2020-01-01"}}, lang="ru")
check(code == 400, "окончание раньше начала — нельзя")
code, r = call("/api/crm/save", H.IRINA, {"entity": "project_status", "data": {"id": pid, "status": "active"}}, lang="ru")
check(code == 200 and r["project"]["status"] == "active" and not r["project"]["finished"], "вернула в работу: окончание стёрто")
h = H.crm.q("SELECT details FROM audit WHERE entity='project' AND entity_id=? ORDER BY id DESC LIMIT 2", pid)
check('"status": "active"' in h[0]["details"] and '"status": "done"' in h[1]["details"], "в истории проекта — и завершение, и возврат")
# ---------- личные разговоры Ирины с сотрудниками: видят только участники ----------
ids = []
for tg_id, name, pos in ((H.ASSIST2, "Ольга Мельник", "визуализатор"), (H.ASSIST3, "Денис Коваль", "комплектатор")):
    code, r = call("/api/crm/save", H.IRINA, {"entity": "assistant", "data": {"name": name, "position": pos}}, lang="ru")
    H.crm.run("UPDATE assistants SET tg_id=?, tg_name=? WHERE id=?", tg_id, name, r["saved_id"])
    H.bot.s.run("INSERT OR REPLACE INTO users(tg_id, name, role, status, created, updated) VALUES(?, ?, 'assistant', 'active', '', '')", tg_id, name)
    H.bot.s.put(f"tg:lang:{tg_id}", "ru")
    ids.append(r["saved_id"])
aA, aB = ids
code, r = call("/api/crm/save", H.IRINA, {"entity": "passist", "data": {"project_id": pid, "assistant_id": aA, "on": True}}, lang="ru")
check(code == 200, "Ирина назначила Ольгу на проект")
code, x = call("/api/portal/thread", H.IRINA, {"project_id": pid, "kind": "staff", "assistant_id": aB}, lang="ru")
check(code == 400, "сотруднику, не назначенному на проект, разговор по проекту не начать")
call("/api/crm/save", H.IRINA, {"entity": "passist", "data": {"project_id": pid, "assistant_id": aB, "on": True}}, lang="ru")
code, tS = call("/api/portal/thread", H.IRINA, {"project_id": pid, "kind": "staff", "assistant_id": aA}, lang="ru")
check(code == 200 and tS["kind"] == "staff" and tS["assistant"]["name"] == "Ольга Мельник", "Ирина начала личный разговор с Ольгой")
thS = P.thread(tS["id"])
vA, vB, vO = P.viewer(H.ASSIST2, pid), P.viewer(H.ASSIST3, pid), P.viewer(H.OWNER, pid)
check(P.access(vA, thS) == "write" and P.access(P.viewer(H.IRINA, pid, designer=True), thS) == "write", "пишут Ирина и Ольга")
check(all(P.access(v, thS) is None for v in (vB, vC, vK, vL, vW, vO)), "Денис, заказчик, подрядчики, работник и наблюдатель его не видят")
check(not any(t["id"] == tS["id"] for v in (vB, vC, vK, vO) for t in P.threads_for(v, pid)), "и в их списках разговоров его нет")
code, x = call(f"/api/portal/chat?thread={tS['id']}", H.CLIENT)
check(code == 403, "заказчик не откроет его и по адресу")
code, x = call("/api/portal/chat", H.ASSIST3, {"thread_id": tS["id"], "text": "Можно мне тоже?"}, lang="ru")
check(code == 403, "Денис в него не пишет")
code, x = call("/api/portal/thread", H.ASSIST3, {"project_id": pid, "kind": "staff", "assistant_id": aA}, lang="ru")
check(code == 400, "сотрудник не начинает разговор Ирины с другим сотрудником")
n = len(H.CALLS)
code, x = call("/api/portal/chat", H.IRINA, {"thread_id": tS["id"], "text": "Оля, визуализации спальни нужны к пятнице."}, lang="ru")
check(code == 200 and wait(lambda: any("визуализации спальни" in x for x in texts(H.ASSIST2, n))), "Ольге — сообщение Ирины")
settle()
check(not any("визуализации спальни" in x for u in (H.ASSIST3, H.CLIENT, H.CREW, H.OWNER, H.WORKER) for x in texts(u, n)),
      "больше никому — ни Денису, ни заказчику, ни подрядчику, ни наблюдателю")
check(not any("Разговор:" in x for x in texts(H.ASSIST2, n)), "свой разговор с Ириной — без подписи «Разговор»")
n = len(H.CALLS)
H.update(H.ASSIST2, "Хорошо, пришлю в четверг.", first="Ольга", lang="ru")
check(wait(lambda: any("пришлю в четверг" in x for x in texts(H.IRINA, n))), "Ольга пишет прямо в бот — Ирине, в их разговор")
settle()
to_i = [p for p in msgs(H.IRINA, n) if "пришлю в четверг" in (p.get("text") or "")][0]
check("видите только вы двое" in to_i["text"] and not to_i.get("disable_notification"), "Ирине — со звуком и пометкой, что видят только они")
check(not any("пришлю в четверг" in x for u in (H.ASSIST3, H.OWNER, H.CLIENT) for x in texts(u, n)), "Денис и наблюдатель не получают")
m = H.crm.one("SELECT * FROM messages WHERE thread_id=? ORDER BY id DESC LIMIT 1", tS["id"])
check(m["author_kind"] == "assistant", "в разговоре — от сотрудника")
fid = H.crm.add_file(pid, "chat", "eskiz.png", __import__("io").BytesIO(png), len(png), "image/png", "Ольга")["id"]
H.crm.run("UPDATE files SET thread_id=?, see_client=1 WHERE id=?", tS["id"], fid)
fr = H.crm.one("SELECT * FROM files WHERE id=?", fid)
check(P.can_see_file(vA, fr) and not P.can_see_file(vC, fr) and not P.can_see_file(vO, fr) and not P.can_see_file(vB, fr),
      "вложение личного разговора — только его участникам, даже если отмечено «заказчику»")
# группа сотрудников
n = len(H.CALLS)
code, r = call("/api/crm/save", H.IRINA, {"entity": "sgroup", "data": {"project_id": pid, "title": "Визуализации и комплектация",
                                                                       "members": [aA, aB, 99999]}}, lang="ru")
check(code == 200 and r["saved_id"], "Ирина собрала группу сотрудников")
tG = P.thread(r["saved_id"])
check(tG["kind"] == "sgroup" and sorted(m["ref_id"] for m in P.members(tG["id"])) == sorted([aA, aB]), "в группе — только назначенные на проект")
check(wait(lambda: all(any("Визуализации и комплектация" in x for x in texts(u, n)) for u in (H.ASSIST2, H.ASSIST3))),
      "обоим пришло сообщение о группе")
check(P.access(vA, tG) == "write" and P.access(vB, tG) == "write" and all(P.access(v, tG) is None for v in (vC, vK, vO, vW)),
      "группу видят только Ирина и сотрудники в ней")
n = len(H.CALLS)
code, x = call("/api/portal/chat", H.ASSIST3, {"thread_id": tG["id"], "text": "Каталог плитки скинул в группу."}, lang="ru")
check(code == 200 and wait(lambda: any("Каталог плитки" in x for x in texts(H.ASSIST2, n))), "сообщение в группе — Ольге")
settle()
check(any("Каталог плитки" in x and "Группа сотрудников" in x for x in texts(H.IRINA, n)), "Ирине — с названием группы")
check(not any("Каталог плитки" in x for u in (H.CLIENT, H.OWNER, H.CREW) for x in texts(u, n)), "заказчику, подрядчику и наблюдателю — нет")
code, r = call("/api/crm/save", H.IRINA, {"entity": "sgroup", "data": {"project_id": pid, "title": "Пусто", "members": [99999]}}, lang="ru")
check(code == 400, "группа без сотрудников проекта — нельзя")
call("/api/crm/save", H.IRINA, {"entity": "passist", "data": {"project_id": pid, "assistant_id": aB, "on": False}}, lang="ru")
check(P.access(P.viewer(H.ASSIST3, pid), tG) is None, "снятый с проекта сотрудник группу больше не видит")

# ---------- исполнитель студии (замерщик): платит студия, пишет только Ирина ----------
code, kH = call("/api/crm/save", H.IRINA, {"entity": "contractor", "data": {"name": "Віктор Литвин", "kind": "hired", "trade": "Замерщик",
                                                                            "phone": "+421 907 000 111"}}, lang="ru")
check(code == 200 and kH["kind"] == "hired", "исполнитель студии в контактах")
check("hired_cats" in H.crm.lists() and "3D-визуализатор" in H.crm.lists()["hired_cats"], "список: замерщик, чертёжник, 3D-визуализатор")
code, r = call("/api/crm/save", H.IRINA, {"entity": "link", "data": {"project_id": pid, "contractor_id": kH["id"], "trade": "Замерщик"}}, lang="ru")
lH = r["saved_id"]
code, inv = call("/api/crm/invite", H.IRINA, {"kind": "contractor", "ref_id": kH["id"], "project_id": pid, "lang": "uk"}, lang="ru")
check(code == 200 and "кабінет виконавця студії" in inv["text"] and "контакти замовника" not in inv["text"], "ссылка — текст исполнителя студии, по-украински")
n = len(H.CALLS)
H.update(H.HIRED, "/start " + inv["link"].split("start=")[1], first="Віктор", lang="uk")
check(any("кабінет виконавця студії" in x for x in texts(H.HIRED, n)), "исполнителю — его приветствие")
check(any("исполнитель студии" in x for x in texts(H.IRINA, n)), "Ирине — подключился исполнитель студии")
hv = P.contractor_view(pid, P.contractor_ids(H.HIRED, pid), H.HIRED)
blob = json.dumps(hv, ensure_ascii=False)
check(hv["clients"] == [] and hv["team"] == [] and hv["mine"][0]["kind"] == "hired" and hv["mine"][0]["stages"] == [], "без контактов заказчика, бригады и сумм")
for bad in ("+421 905 111 222", "anna@example.sk", "Lukáš", "18000", '"expected"', '"commission"', "schet-baxter"):
    check(bad not in blob, f"исполнитель не видит {bad}")
check({"measure", "visual", "docs"} <= {f["category"] for f in hv["files"]} and hv["project"]["address"] == "Ružinovská 12",
      "видит адрес и документацию")
vH = P.viewer(H.HIRED, pid)
check(kinds(vH) == [("org", kH["id"], None, False)], f"разговоры: только с Ириной {kinds(vH)}")
check(not any(t.get("contractor") and t["contractor"]["id"] == kH["id"] for t in P.threads_for(vC, pid)), "заказчику написать ему нельзя — его нет в списке")
check(not any(c["id"] == kH["id"] for c in P.client_view(pid, H.CLIENT)["contractors"]), "заказчик его не видит")
code, x = call("/api/portal/thread", H.CLIENT, {"project_id": pid, "kind": "pc", "contractor_id": kH["id"]})
check(code == 400, "заказчик не начнёт с ним разговор и по адресу")
code, x = call("/api/portal/thread", H.HIRED, {"project_id": pid, "kind": "pc", "contractor_id": kH["id"]}, lang="uk")
check(code == 400, "и он сам — с заказчиком")
tH = P.ensure_thread(pid, "org", contractor_id=kH["id"])
check(P.access(vA, tH) is None and P.access(vK, tH) is None and P.access(vC, tH) is None, "сотрудники, подрядчики и заказчик его разговор не видят")
code, x = call("/api/portal/thread", H.ASSIST2, {"project_id": pid, "kind": "org", "contractor_id": kH["id"]}, lang="ru")
check(code == 400, "сотрудник студии ему не пишет")
code, r = call("/api/crm/save", H.IRINA, {"entity": "group", "data": {"project_id": pid, "title": "Замер", "members": [{"kind": "contractor", "id": kH["id"]}]}}, lang="ru")
check(code == 400, "в группу его не добавить")
code, r = call("/api/crm/save", H.IRINA, {"entity": "stage", "data": {"project_id": pid, "link_id": lH, "title": "Замер", "amount": 150, "mode": "unknown"}}, lang="ru")
check(code == 400, "сумм на подтверждение заказчику у него нет — ему платит студия")
code, x = call("/api/portal/stage", H.HIRED, {"action": "save", "project_id": pid, "link_id": lH, "title": "Замер", "amount": 150}, lang="uk")
check(code == 400, "и сам он их не вносит")
n = len(H.CALLS)
code, x = call("/api/portal/chat", H.IRINA, {"thread_id": tH["id"], "text": "Виктор, замер в четверг в 10:00, ключи у консьержа."}, lang="ru")
check(code == 200 and wait(lambda: any("замер в четверг" in x for x in texts(H.HIRED, n))), "Ирина пишет исполнителю")
settle()
check(not any("замер в четверг" in x for u in (H.ASSIST2, H.CLIENT, H.CREW) for x in texts(u, n)), "сотрудникам, заказчику и подрядчикам — нет")
n = len(H.CALLS)
H.update(H.HIRED, "Добре, буду о 10:00.", first="Віктор", lang="uk")
check(wait(lambda: any("буду о 10:00" in x for x in texts(H.IRINA, n))), "исполнитель пишет в бот — Ирине")
settle()
check(any("Исполнитель студии" in x for x in texts(H.IRINA, n)) and not any("буду о 10:00" in x for x in texts(H.ASSIST2, n)),
      "Ирине — «Исполнитель студии», сотруднику — нет")
code, fH = call(f"/api/portal/upload?project={pid}&cat=measure&vis=studio&name=zamer-kvartira.pdf&title=" + urllib.parse.quote("Замер"), H.HIRED,
                raw=b"%PDF-1.4 zamer", ctype="application/pdf", lang="uk")
fh = H.crm.one("SELECT * FROM files WHERE id=?", fH["id"])
check(code == 200 and fh["category"] == "measure" and fh["review"] == 1, "замер — в «Обмерный план», ждёт решения Ирины")
check(not any(f["id"] == fH["id"] for f in P.client_view(pid, H.CLIENT)["files"]), "заказчик замер пока не видит")
code, x = call("/api/portal/file", H.HIRED, {"id": fH["id"], "vis": "studio", "title": "Замер, 24.10"}, lang="uk")
check(code == 200 and not any(f["id"] == fH["id"] for f in P.client_view(pid, H.CLIENT)["files"]), "открыть заказчику сам не может")
code, x = call("/api/crm/save", H.IRINA, {"entity": "file_approve", "data": {"id": fH["id"], "show": True}}, lang="ru")
check(code == 200 and any(f["id"] == fH["id"] for f in P.client_view(pid, H.CLIENT)["files"]), "Ирина одобрила — заказчик видит")
code, me = call("/api/portal/me", H.HIRED, lang="uk")
check(code == 200 and me["heads"][0]["kind"] == "hired", "в кабинете — вид «исполнитель студии»")
check(P.label("Замерщик", "de") == "Aufmaß-Techniker" and P.label("3D-визуализатор", "fr") == langs.pack("fr")["fixed"]["3D-визуализатор"],
      "виды исполнителей — по словарю на всех языках")
check(H.bot.invite_text("pl", "hired", "Jan", "", "L") == langs.pack("pl")["bot"]["invite_hired"].format(name="Jan", link="L"), "ссылка исполнителю — по-польски")

# ---------- украинский: заказчику и подрядчику на украинском ничего не переводим, Ирине с украинского — тоже ----------
import translate  # noqa: E402
import server_info  # noqa: E402
LLM = []
real_post = translate._post


def fake_post(url, body, headers, timeout=12):
    LLM.append((url, body["messages"][-1]["content"]))
    if "boom" in body["messages"][-1]["content"]:
        raise RuntimeError("ответ 401: invalid key sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    lang = re.search(r"into (\w+)", body["messages"][0]["content"]).group(1)
    return {"model": "gpt-test", "usage": {"prompt_tokens": 120, "completion_tokens": 30},
            "choices": [{"message": {"content": json.dumps({"lang": "sk", "text": f"[{lang}] " + body["messages"][-1]["content"]})}}]}


os.environ["OPENAI_API_KEY"] = "sk-test-not-real-0123456789abcdef"
translate._post = fake_post
usage = server_info.install(H.bot.s)
portal_bot.translate_text = translate.translate_text
check(translate.translate_text("Добрий день, коли приїде диван?", "ru") is None and translate.translate_text("Добрый день, диван приедет в пятницу.", "uk") is None
      and not LLM, "русский и украинский друг для друга не переводятся — без обращения к модели")
check(translate.translate_text("Dobrý deň, kedy príde sedačka?", "uk")[1].startswith("[Ukrainian]") and len(LLM) == 1, "словацкий — на украинский переводится")
LLM.clear()
H.crm.run("UPDATE contractors SET tg_id=? WHERE id=?", H.CREW, env["k1"]["id"])       # Михаилу (кабинет по-украински) кабинет снова открыт
H.bot.s.run("UPDATE users SET status='active' WHERE tg_id=?", H.CREW)
H.bot.s.put(f"tg:lang:{H.CREW}", "uk")
n = len(H.CALLS)
tK = P.ensure_thread(pid, "org", contractor_id=env["k1"]["id"])
code, x = call("/api/portal/chat", H.IRINA, {"thread_id": tK["id"], "text": "Михаил, плитку в ванной кладём в понедельник."}, lang="ru")
check(code == 200 and wait(lambda: any("плитку в ванной" in x for x in texts(H.CREW, n))), "подрядчику (украинский) — сообщение Ирины")
settle()
check(not any("Перекладено автоматично" in x for x in texts(H.CREW, n)) and not LLM, "без перевода и без обращения к модели")
n = len(H.CALLS)
code, x = call("/api/portal/chat", H.CREW, {"thread_id": tK["id"], "text": "Добре, у понеділок зранку почнемо."}, lang="uk")
check(code == 200 and wait(lambda: any("у понеділок зранку" in x for x in texts(H.IRINA, n))), "его ответ по-украински — Ирине")
settle()
check(not any("Перевод на русский" in x for x in texts(H.IRINA, n)) and not LLM, "Ирине — без перевода с украинского")
tPC = P.ensure_thread(pid, "pc", contractor_id=env["k1"]["id"])
n = len(H.CALLS)
code, x = call("/api/portal/chat", H.CLIENT, {"thread_id": tPC["id"], "text": "Dobrý deň, môžeme prísť pozrieť obklady v utorok?"})
check(code == 200 and wait(lambda: any("[Ukrainian]" in x for x in texts(H.CREW, n))), "сообщение заказчицы по-словацки — подрядчику по-украински")
settle()
check(any("[Russian]" in x for x in texts(H.IRINA, n)), "Ирине — по-русски")
day = usage.summary()["periods"]["day"]
check(day["calls"] >= 3 and day["tokens_in"] >= 360 and day["tokens_out"] >= 90, f"расход посчитан: вызовы и токены {day}")
check(any(x["purpose"] == "chat" and x["day"]["calls"] >= 2 for x in usage.summary()["by_purpose"]), "переписка — отдельной строкой")
try:
    with translate.purpose("names"):
        translate.translate_text("boom", "de")
except RuntimeError:
    pass
S2 = usage.summary()
check(S2["periods"]["day"]["errors"] == 1 and S2["last_error"] and "sk-proj" not in S2["last_error"]["error"] and "ответ 401" in S2["last_error"]["error"],
      "ошибка посчитана, ключ в её тексте не показывается")
code, x = call("/api/stats/server", H.OWNER, lang="ru")
dump = json.dumps(x, ensure_ascii=False)
check(code == 200 and x["server"]["disk"]["total"] > 0 and x["llm"]["periods"]["day"]["calls"] >= 3 and x["llm_config"]["provider"] == "openai",
      "разработчику — «Сервер и ИИ»: сервер, расход")
check(x["data"]["crm_db"] > 0 and x["data"]["files"]["count"] >= 7 and x["bot"]["messages"]["day"] >= 1 and x["bot"]["users"]["designer"] == 1,
      "данные: базы, файлы, сообщения, кто в боте")
check("sk-test-not-real" not in dump and "sk-proj" not in dump and any(k["present"] for k in x["llm_config"]["keys"]), "ключей на странице нет — только «ключ есть»")
check(call("/api/stats/server", H.IRINA, lang="ru")[0] == 403 and call("/api/stats/server", H.CLIENT)[0] == 403, "дизайнеру и заказчику — нет")
with urllib.request.urlopen(BASE + "/api/stats/server/app", timeout=10) as r:
    check(r.status == 200 and "Сервер и ИИ" in r.read().decode(), "страница «Сервер и ИИ» открывается")
translate._post = real_post
del os.environ["OPENAI_API_KEY"]
translate.USAGE_HOOK = None
translate.reset_pauses()
# ---------- документы: планировки, варианты и правки, помещения; заказчик только смотрит (решено 25.10.2026) ----------
def up_studio(cat, name, extra=""):
    data = png if name.endswith(".png") else b"%PDF-1.4 x"
    code, f = call(f"/api/crm/upload?project={pid}&cat={cat}&name={urllib.parse.quote(name)}{extra}", H.IRINA, raw=data,
                   ctype="image/png" if name.endswith(".png") else "application/pdf", lang="ru")
    assert code == 200, f
    return H.crm.one("SELECT * FROM files WHERE id=?", f["id"])


pl1 = up_studio("plan", "planirovka-variant-1.pdf")
pl2 = up_studio("plan", "planirovka-variant-2.pdf", "&new=1")
check(pl1["ver"] == 1 and pl2["ver"] == 2, "планировочные решения: вариант 1 и вариант 2")
v1 = up_studio("visual", "gostinaya-1.png", "&room=" + urllib.parse.quote("Гостиная"))
v2 = up_studio("visual", "spalnya-1.png", "&room=" + urllib.parse.quote("Хозяйская спальня"))
r1 = up_studio("visual", "gostinaya-pravka-1.png", "&new=1&room=" + urllib.parse.quote("Гостиная"))
r1b = up_studio("visual", "spalnya-pravka-1.png", "&room=" + urllib.parse.quote("Хозяйская спальня"))
check(v1["ver"] == v2["ver"] == 1 and r1["ver"] == r1b["ver"] == 2 and r1["room"] == "Гостиная", "визуализации: первый вариант, правка 1 — по помещениям")
old_v = H.crm.one("SELECT * FROM files WHERE project_id=? AND category='visual' AND id NOT IN (?, ?, ?, ?) ORDER BY id LIMIT 1", pid, v1["id"], v2["id"], r1["id"], r1b["id"])
check(old_v["ver"] is None, "старые файлы без версии — считаются первым вариантом")
d1 = up_studio("docs", "kuhnya-chertezhi.pdf", "&title=" + urllib.parse.quote("Кухня — чертежи"))
d2 = up_studio("docs", "kuhnya-chertezhi-2.pdf", "&new=1&title=" + urllib.parse.quote("Кухня — чертежи"))
check(d1["ver"] is None and d2["ver"] == 2 and d2["title"] == "Кухня — чертежи", "документ с тем же названием — версия 2")
B_today = date.today().isoformat()
code, r = call("/api/crm/save", H.IRINA, {"entity": "round", "data": {"project_id": pid, "category": "plan", "ver": 2, "agreed": True}}, lang="ru")
check(code == 200 and r["rounds"] == [{"category": "plan", "ver": 2, "agreed": B_today, "agreed_by": "Ирина"}],
      "Ирина отметила: вариант 2 планировки заказчик согласовал")
code, r = call("/api/crm/save", H.IRINA, {"entity": "file_meta", "data": {"id": v2["id"], "room": "Детская"}}, lang="ru")
check(code == 200 and H.crm.one("SELECT room FROM files WHERE id=?", v2["id"])["room"] == "Детская", "Ирина поменяла помещение")
code, x = call(f"/api/portal/project?id={pid}", H.CLIENT, lang="sk")
vis_ = {f["id"]: f for f in x["files"]}
check(code == 200 and {pl1["id"], pl2["id"], v1["id"], r1["id"], d2["id"]} <= set(vis_) and x["rounds"] == [{"category": "plan", "ver": 2, "agreed": B_today}],
      "заказчик видит варианты, правки и отметку «согласовано»")
room_l = P.label("Гостиная", x["lang"])
check(x["lang"] != "ru" and vis_[r1["id"]]["ver"] == 2 and vis_[r1["id"]]["room"] == room_l != "Гостиная" and ["Гостиная", room_l] in x["rooms"] and x["revisions"] == 2,
      f"помещения — на языке заказчика ({x['lang']}); в пакет «Премиум» входят 2 правки")
# заказчик только смотрит: не добавляет, не правит, не удаляет
code, _ = call(f"/api/portal/upload?project={pid}&cat=visual&vis=client&name=x.png", H.CLIENT, raw=png, ctype="image/png")
check(code == 403, "заказчик не добавляет документы")
code, _ = call("/api/portal/file", H.CLIENT, {"id": v1["id"], "delete": True})
check(code in (400, 403) and H.crm.one("SELECT id FROM files WHERE id=?", v1["id"]), "заказчик не удаляет документы")
code, _ = call("/api/portal/file", H.CLIENT, {"id": v1["id"], "title": "x"})
check(code in (400, 403), "и не правит")
code, _ = call(f"/api/portal/thumb?id={v1['id']}", H.CLIENT, raw=png, ctype="image/jpeg")
check(code == 403, "и превью не меняет")
for path in ("/api/crm/save", "/api/crm/delete", "/api/crm/move"):
    code, _ = call(path, H.CLIENT, {"entity": "file", "id": v1["id"], "category": "other"})
    check(code == 403, f"«Студия» ({path}) заказчику закрыта")
# исполнитель-визуализатор: правка 1 по помещению — заказчику только после одобрения Ирины
code, fv = call(f"/api/portal/upload?project={pid}&cat=visual&ver=2&room=" + urllib.parse.quote("Кухня") + "&name=kuhnya-pravka-1.png&title=" + urllib.parse.quote("Kuchyňa"),
                H.HIRED, raw=png, ctype="image/png", lang="uk")
fvr = H.crm.one("SELECT * FROM files WHERE id=?", fv["id"])
check(code == 200 and fvr["category"] == "visual" and fvr["ver"] == 2 and fvr["room"] == "Кухня" and fvr["review"] == 1, "исполнитель добавил правку 1 кухни")
check(not any(f["id"] == fv["id"] for f in P.client_view(pid, H.CLIENT)["files"]), "заказчик её пока не видит")
code, x = call(f"/api/portal/project?id={pid}", H.HIRED, lang="uk")
check(any(f["id"] == fv["id"] and f["approval"] == "wait" for f in x["files"]), "исполнитель видит: ждёт одобрения Ирины")
code, x = call(f"/api/portal/upload?project={pid}&cat=other&vis=client&name=x.pdf", H.HIRED, raw=b"%PDF", ctype="application/pdf", lang="uk")
check(code == 400, "в «Другое» подрядчики не добавляют")
code, pst = call("/api/crm/state", H.IRINA, lang="ru")
check(any(p_["id"] == pid and p_["review"] >= 1 for p_ in pst["projects"]), "в списке проектов «Студии» — сколько ждёт решения Ирины")

# ---------- стадия проекта ----------
n = len(H.CALLS)
code, r = call("/api/crm/save", H.IRINA, {"entity": "project_stage", "data": {"id": pid, "stage": "measure", "day": "2026-07-02"}}, lang="ru")
code, r = call("/api/crm/save", H.IRINA, {"entity": "project_stage", "data": {"id": pid, "stage": "plan_ok"}}, lang="ru")
check(code == 200 and r["project"]["stage"] == "plan_ok" and [x_["stage"] for x_ in r["stages"]][-2:] == ["measure", "plan_ok"], "Ирина поставила стадию")
cl = H.bot.lang_of(H.CLIENT)
st_name = P.label("Согласование планировочных решений", cl)
check(cl != "ru" and st_name != "Согласование планировочных решений" and wait(lambda: any(x_.startswith("📍") and st_name in x_ for x_ in texts(H.CLIENT, n))),
      f"заказчику — новая стадия на его языке ({cl}: {st_name})")
code, x = call(f"/api/portal/project?id={pid}", H.CLIENT, lang="sk")
check(x["stage"] == "plan_ok" and dict(x["stages"])["plan_ok"] == st_name and [y["stage"] for y in x["stage_log"]][-2:] == ["measure", "plan_ok"], "в кабинете — стадия и история")
code, r = call("/api/crm/save", H.IRINA, {"entity": "project_stage", "data": {"id": pid, "stage": "repair", "notify": False}}, lang="ru")
settle()
n = len(H.CALLS)
code, r = call("/api/crm/save", H.IRINA, {"entity": "project_stage", "data": {"id": pid, "stage": "done", "day": "2026-10-24"}}, lang="ru")
check(code == 200 and r["project"]["status"] == "done" and r["project"]["stage"] == "done", "стадия «Завершён» — проект завершён")
code, r = call("/api/crm/save", H.IRINA, {"entity": "project_status", "data": {"id": pid, "status": "active"}}, lang="ru")
check(r["project"]["stage"] == "repair", "вернули в работу — прежняя стадия")
code, r = call("/api/crm/save", H.IRINA, {"entity": "project_stage", "data": {"id": pid, "stage": "furniture_make"}}, lang="ru")
code, r = call("/api/crm/save", H.IRINA, {"entity": "project_status", "data": {"id": pid, "status": "done", "finished": "2026-10-24"}}, lang="ru")
code, r = call("/api/crm/save", H.IRINA, {"entity": "project_stage", "data": {"id": pid, "stage": "furniture_install"}}, lang="ru")
check(r["project"]["status"] == "active" and r["project"]["stage"] == "furniture_install", "заказчик продолжил: рабочая стадия возвращает проект в работу")

# ---------- смена пакета: пересчёт только вверх или прежняя сумма; доход по пакетам ----------
base = H.crm.save_project({"title": "Квартира 80 м², Петржалка", "area": 80, "tariff": "Базовый", "total_eur": 2800, "status": "active",
                           "started": "2026-09-01"}, "Ирина")["project"]
H.crm.save_op({"project_id": base["id"], "kind": "payment", "day": "2026-09-02", "amount": 1400, "currency": "EUR"}, "Ирина")
code, r = call("/api/crm/save", H.IRINA, {"entity": "tariff", "data": {"id": base["id"], "tariff": "Экспресс", "mode": "recalc", "rate": 20}}, lang="ru")
check(code == 400 and "только растёт" in r.get("error", ""), "пересчёт вниз — нельзя")
code, r = call("/api/crm/save", H.IRINA, {"entity": "tariff", "data": {"id": base["id"], "tariff": "Премиум", "mode": "recalc", "rate": 50,
                                                                        "day": "2026-10-01"}}, lang="ru")
check(code == 200 and r["project"]["tariff"] == "Премиум" and r["project"]["total_eur"] == 4000 and r["tariff_changes"][0]["old_total"] == 2800,
      "Базовый → Премиум: 80 м² × 50 € = 4000 €")
H.crm.save_op({"project_id": base["id"], "kind": "payment", "day": "2026-10-02", "amount": 1000, "currency": "EUR"}, "Ирина")
code, r = call("/api/crm/save", H.IRINA, {"entity": "tariff", "data": {"id": base["id"], "tariff": "Премиум+", "mode": "keep", "day": "2026-10-03"}}, lang="ru")
check(code == 200 and r["project"]["total_eur"] == 4000 and r["project"]["tariff"] == "Премиум+", "сменить пакет и оставить прежнюю сумму")
st = H.crm.stats("all")
bt = dict(st["by_tariff"])
check(bt.get("Базовый", 0) >= 1400 and bt.get("Премиум", 0) >= 1000, f"доход до смены — старому пакету, после — новому {bt}")
ups_ = {(u["from"], u["to"]): u for u in st["tariff_ups"]}
check(ups_[("Базовый", "Премиум")]["plus"] == 1200 and ups_[("Премиум", "Премиум+")]["plus"] == 0, f"смены пакета в статистике {st['tariff_ups']}")
code, x = call("/api/crm/save", H.IRINA, {"entity": "lists", "data": {"tariff_info": {"Премиум": {"rate": 55, "revisions": 3}}}}, lang="ru")
check(code == 200 and x["tariff_info"]["Премиум"] == {"rate": 55, "revisions": 3} and x["tariff_info"]["Базовый"]["revisions"] == 1, "пакеты: цена за м² и правки — в настройках")

# ---------- документы не попадают в поиск ----------
req = urllib.request.Request(BASE + f"/api/portal/project?id={pid}", headers={"X-Telegram-Init-Data": H.init_data(H.CLIENT, lang="sk")})
with urllib.request.urlopen(req, timeout=10) as resp:
    check("noindex" in (resp.headers.get("X-Robots-Tag") or ""), "ответы кабинета — noindex")
fu = H.crm.file_view(H.crm.one("SELECT * FROM files WHERE id=?", v1["id"]))["url"]
with urllib.request.urlopen(BASE + fu, timeout=10) as resp:
    check("noindex" in (resp.headers.get("X-Robots-Tag") or "") and resp.headers.get("Cache-Control", "").startswith("private"), "файлы проектов — noindex, private")
srv.shutdown()
print(f"OK: {ok} проверок")
