"""Заявка на товар фабрики, закреплённой за разработчиком (Calligaris, content/shop/manufacturers.json → "assignee": "owner"):
разработчику — «фабрика закреплена за вами», дизайнеру — как обычно, с пометкой, кому передана; розничная цена фабрики
и прямые ссылки на 2D/3D — в подсказке. Для сравнения — товар партнёра и товар без фабрики.
Запуск: python3 scripts/tests/test_assignee.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402

FAILS = []


def check(ok, what):
    print(("✓ " if ok else "✗ ") + what)
    if not ok:
        FAILS.append(what)


PRODUCTS = {
    "DF-K9001": {"name": "Журнальный столик Twins", "assignee": "owner", "mfr": "Calligaris (Италия)", "mfr_code": "CS5156-C",
                 "retail": {"from": 895, "to": 1290},
                 "models": [{"what": "2D", "formats": ["DWG"], "url": "https://d2q8gr9acofxpc.cloudfront.net/asset/x/dwg", "how": "скачивается сразу"}]},
    "DF-S5001": {"name": "Диван Baxter", "partner": "Александр Замлинский (Италия)", "mfr": "Baxter (Италия)"},
}
H.bot.ensure_partners(PRODUCTS)


def sent_to(uid):
    return [p.get("text") or "" for m, p in H.CALLS if m == "sendMessage" and str(p.get("chat_id")) == str(uid)]


H.CALLS.clear()
lead = {"name": "Max", "contact": "max@example.de", "message": "Lieferung nach: Deutschland\n\nPreis?", "page": "https://dumskaya-home.com/de/calligaris/twins",
        "model": "DF-K9001", "lang": "de", "site": "dumskaya-home.com"}
got = H.bot.route_lead(lead, products=PRODUCTS)
own, iri = sent_to(H.OWNER), sent_to(H.IRINA)
check(len(own) == 1 and "закреплена за вами" in own[0] and "Calligaris" in own[0], "разработчику — «фабрика закреплена за вами»")
check(len(iri) == 1 and "закреплена за разработчиком" in iri[0], "дизайнеру — заявка с пометкой, что передана разработчику")
check("Розница на сайте фабрики:</b> от 895 € (до 1 290 €)" in own[0], "в подсказке — розничная цена фабрики")
check("скачать у фабрики" in own[0] and "DWG" in own[0], "в подсказке — прямая ссылка на DWG")
check(lead["routed"].startswith("фабрика закреплена за разработчиком") and H.OWNER in got and H.IRINA in got, "в учёте: кому передана")

H.CALLS.clear()
lead2 = {"name": "Anna", "contact": "+421 900 000 000", "message": "", "page": "/sofas", "model": "DF-S5001", "lang": "ru"}
H.bot.route_lead(lead2, products=PRODUCTS)
check(not sent_to(H.OWNER) and len(sent_to(H.IRINA)) == 1, "товар партнёра — разработчику не приходит, дизайнеру — да (как было)")

H.CALLS.clear()
H.bot.route_lead({"name": "Ivan", "contact": "ivan@example.com", "message": "", "page": "/", "model": "", "lang": "ru"}, products=PRODUCTS)
check(not sent_to(H.OWNER) and len(sent_to(H.IRINA)) == 1, "обычная заявка — только дизайнеру (как было)")

print("\n" + ("Всё в порядке" if not FAILS else f"Ошибок: {len(FAILS)}"))
sys.exit(1 if FAILS else 0)
