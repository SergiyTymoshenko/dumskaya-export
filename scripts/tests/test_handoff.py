"""Заявка на товар партнёра (Александр Замлинский и др., решено 28.10.2026): сама партнёру не уходит — студии
приходит с кнопками «➡️ Отдаём «…»» и «🏠 Оставляем себе» (они же — в «Студии», в заявке). «Отдаём» пересылает
заявку людям партнёра в боте (один раз); партнёр не в боте — отметка «переслать вручную». «Оставляем себе» —
партнёру ничего. Решение видно в «Студии» и в списке заявок.
Запуск: python3 scripts/tests/test_handoff.py"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402

FAILS = []


def check(ok, what):
    print(("✓ " if ok else "✗ ") + what)
    if not ok:
        FAILS.append(what)


PARTNER = "Александр Замлинский (Италия)"
PRODUCTS = {"DF-S5001": {"name": "Диван Baxter", "partner": PARTNER, "mfr": "Baxter (Италия)"},
            "DF-L7001": {"name": "Светильник IDL", "partner": "Нет такого партнёра"}}
H.bot.ensure_partners(PRODUCTS)
sys.modules[type(H.bot).__module__].load_products = lambda: PRODUCTS   # кнопки в боте читают товары сайта — здесь тестовые
H.bot.crm = H.crm
ZAM = 500
pid = H.bot.partner_by_name(PARTNER)
H.bot.s.run("INSERT INTO users(tg_id, name, role, status, partner_id, created, updated) VALUES(?, 'Александр', 'supplier', 'active', ?, '', '')", ZAM, pid)


def sent_to(uid):
    return [(p.get("text") or "", p.get("reply_markup")) for m, p in H.CALLS if m == "sendMessage" and str(p.get("chat_id")) == str(uid)]


def new_lead(name):
    lead = {"name": name, "contact": name.lower() + "@example.it", "message": "Prezzo?", "page": "https://dumskaya-home.com/baxter/sofa",
            "model": "DF-S5001", "lang": "it", "site": "dumskaya-home.com", "time": "2026-10-28T10:00:0" + str(len(name) % 10) + "+00:00"}
    lead["crm_id"] = H.crm.add_lead(lead)
    return lead


# 1. пришла заявка: партнёру — ничего, Ирине — с кнопками
H.CALLS.clear()
lead = new_lead("Marco")
H.bot.route_lead(lead, products=PRODUCTS)
H.crm.lead_routed(lead["crm_id"], lead["routed"])
iri = sent_to(H.IRINA)
kb = json.dumps(iri[0][1], ensure_ascii=False) if iri else ""
check(not sent_to(ZAM), "партнёру заявка сама не уходит")
check(len(iri) == 1 and "ему пока не отправлена" in iri[0][0] and f"ho:{lead['crm_id']}:p" in kb and f"ho:{lead['crm_id']}:s" in kb
      and "Отдаём «" + PARTNER in kb and "Оставляем себе" in kb, "Ирине — заявка с кнопками «Отдаём «…»» / «Оставляем себе»")
r = H.crm.lead(lead["crm_id"])
check(r["partner_id"] == pid and r["partner"] == PARTNER and not r["handoff"], "в «Студии»: товар партнёра, решения пока нет")
row = [x for x in H.crm.leads_list()["leads"] if x["id"] == lead["crm_id"]][0]
check(row["partner"] == PARTNER and row["handoff"] is None, "в списке заявок — тоже")

# 2. «Отдаём» кнопкой в боте — пересылка партнёру, кнопка отмечена
H.CALLS.clear()
H.update(H.IRINA, data=f"ho:{lead['crm_id']}:p", first="Ирина")
z = sent_to(ZAM)
check(len(z) == 1 and "на ваш товар" in z[0][0] and "Marco" in z[0][0] and "Baxter" in z[0][0], "«Отдаём» — заявка ушла партнёру")
edits = [p for m, p in H.CALLS if m == "editMessageReplyMarkup"]
check(edits and "✓ Отдали «" in json.dumps(edits[-1], ensure_ascii=False), "кнопка в сообщении — «✓ Отдали «…»»")
check(any("Заявка отдана" in t for t, _ in sent_to(H.IRINA)), "Ирине — «Заявка отдана …»")
r = H.crm.lead(lead["crm_id"])
check(r["handoff"] == "partner" and "отдана партнёру" in r["routed"] and r["handoff_by"], "в «Студии»: отдана, кем и когда")
H.CALLS.clear()
H.update(H.IRINA, data=f"ho:{lead['crm_id']}:p", first="Ирина")
check(not sent_to(ZAM), "второй раз партнёру не пересылается")

# 3. «Оставляем себе» из «Студии» — партнёру ничего
lead2 = new_lead("Giulia")
H.CALLS.clear()
H.bot.route_lead(lead2, products=PRODUCTS)
H.serve(18799)
req = urllib.request.Request("http://127.0.0.1:18799/api/crm/handoff", data=json.dumps({"id": lead2["crm_id"], "mode": "s"}).encode(),
                             headers={"X-Telegram-Init-Data": H.init_data(H.IRINA), "Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=10) as resp:
    x = json.loads(resp.read())
check(x["handoff"] == "self" and "оставили себе" in x["routed"] and not sent_to(ZAM), "«Оставляем себе» в «Студии» — партнёру ничего")
req = urllib.request.Request("http://127.0.0.1:18799/api/crm/handoff", data=json.dumps({"id": lead2["crm_id"], "mode": "p"}).encode(),
                             headers={"X-Telegram-Init-Data": H.init_data(H.OWNER), "Content-Type": "application/json"})
try:
    urllib.request.urlopen(req, timeout=10); code = 200
except urllib.error.HTTPError as e:
    code = e.code
check(code == 403 and not sent_to(ZAM), "разработчик в «Студии» решение не меняет (только просмотр)")

# 4. партнёр не в боте — отметка «переслать вручную»
H.bot.s.run("UPDATE users SET status='removed' WHERE tg_id=?", ZAM)
lead3 = new_lead("Luca")
H.bot.route_lead(lead3, products=PRODUCTS)
ok, text = H.bot.lead_handoff(lead3["crm_id"], "p", H.bot.user(H.IRINA))
check(ok and "не подключён к боту" in text and H.crm.lead(lead3["crm_id"])["handoff"] == "partner", "партнёр не в боте — «перешлите сами», отмечено «отдаём»")

# 5. обычная заявка — без кнопок партнёра
H.CALLS.clear()
plain = {"name": "Ivan", "contact": "ivan@example.com", "message": "", "page": "/", "model": "", "lang": "ru", "time": "2026-10-28T11:00:00+00:00"}
plain["crm_id"] = H.crm.add_lead(plain)
H.bot.route_lead(plain, products=PRODUCTS)
check(sent_to(H.IRINA) and "ho:" not in json.dumps(sent_to(H.IRINA)[0][1]), "обычная заявка — без кнопок «Отдаём»")

print("\n" + ("Всё в порядке" if not FAILS else f"Ошибок: {len(FAILS)}"))
sys.exit(1 if FAILS else 0)
