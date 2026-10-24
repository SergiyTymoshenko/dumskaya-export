"""Проверка кабинетов: заказчик, подрядчик, работник подрядчика, наблюдатель «Разработчик ПО» — приглашения, права
(деньги, документы, разговоры), разговоры с переводом и уведомлениями, группы, бригада, подтверждение сумм, напоминания
об оплате, адреса /api/portal и /api/crm. Временные базы, Telegram подменён.

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
check(wait(lambda: any("Nový dokument" in x and "kuhnya-smontirovana" in x for x in texts(H.CLIENT, n0))), "заказчику — документ, открытый ему")
check(wait(lambda: any("zamery-tehnologa" in x for x in texts(H.CREW2, n0))), "мебельщику — документ технолога")
settle()
check(not any("smeta-fabriki" in x for x in texts(H.CLIENT, n0)), "заказчику о закрытом документе — нет")
code, f = call(f"/api/portal/upload?project={pid}&name=x.pdf&vis=head", H.CREW2, raw=b"%PDF", ctype="application/pdf")
check(code == 400, "у подрядчика нет статуса «только руководитель»")
code, f = call(f"/api/portal/upload?project={pid}&name=x.pdf&vis=client", H.CLIENT, raw=b"%PDF", ctype="application/pdf")
check(code == 403, "заказчик документы подрядчиков не загружает")


def see(v):
    return {k for k, f in ups.items() if P.can_see_file(v, f)}


check(see(vC) == {"kuhnya-smontirovana.png", "plitka-gotovo.png"}, f"заказчик: только открытые ему {see(vC)}")
check(see(vL) == {"kuhnya-smontirovana.png", "smeta-fabriki.pdf", "chertezh-dlya-montazha.pdf", "zamery-tehnologa.pdf"}, f"мебельщик: свои и технолога {see(vL)}")
check(see(vJ) == {"kuhnya-smontirovana.png", "chertezh-dlya-montazha.pdf", "zamery-tehnologa.pdf"}, f"технолог: для бригады и свои {see(vJ)}")
check(see(vK) == {"raskladka-plitki.pdf", "plitka-gotovo.png"}, f"прораб: только своей бригады {see(vK)}")
check(see(vW) == {"raskladka-plitki.pdf", "plitka-gotovo.png"}, f"плиточник: свои {see(vW)}")
vI = P.viewer(H.IRINA, pid, designer=True)
check(see(vI) == set(ups), "Ирина видит все документы")
check("заказчик" in P.audience(ups["kuhnya-smontirovana.png"]) and "заказчик" not in P.audience(ups["smeta-fabriki.pdf"]), "кто видит — подпись для Ирины")
code, x = call("/api/portal/file", H.CREW2, {"id": ups["smeta-fabriki.pdf"]["id"], "vis": "client"})
check(code == 200 and P.can_see_file(vC, H.crm.one("SELECT * FROM files WHERE id=?", ups["smeta-fabriki.pdf"]["id"])), "подрядчик открыл документ заказчику")
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
srv.shutdown()
print(f"OK: {ok} проверок")
