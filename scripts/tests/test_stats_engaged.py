"""Посетители как в Google Analytics и программы за VPN (deploy/site_stats.py, deploy/geo.py; решено 27.10.2026).

  • вовлечённый посетитель — больше 10 с на сайте, 2+ страницы, нажатие на контакт или заявка; «все заходы» — рядом;
  • адрес дата-центра (там же серверы VPN) сам по себе не робот: человек за VPN листает, касается, двигает мышь;
    робот — если страница прислала флажок «действий не было» (или браузер под управлением программы — navigator.webdriver);
  • то же для устаревшего браузера и многих браузеров с одного адреса;
  • старые страницы (без флажка действий) по этому правилу не отсеиваются.
База провайдеров в тесте — подменённая (hosting), сеть не нужна.
Запуск: python3 scripts/tests/test_stats_engaged.py"""
import json
import os
import sys
import tempfile
import time

LOGS = tempfile.mkdtemp(prefix="dd-eng-")
os.environ["SITE_LOG_GLOB"] = os.path.join(LOGS, "dumskaya*.log*")
os.environ["HOME_LOG_GLOB"] = os.path.join(LOGS, "dumskaya-home*.log*")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402,F401  (временные папки и сервис)
import site_stats as S  # noqa: E402
import geo  # noqa: E402

FAILS = []


def check(ok, what):
    print(("✓ " if ok else "✗ ") + what)
    if not ok:
        FAILS.append(what)


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36"
NOW = time.time()
CUR = 130 + int((NOW - S._REL["Chrome"][1]) // (28 * 86400))
NEW, OLD = UA.format(v=CUR), UA.format(v=CUR - 30)
DC = {"20.0.0.1": "Microsoft Corporation", "20.0.0.2": "Microsoft Corporation", "20.0.0.3": "Proton AG", "20.0.0.4": "Hetzner Online GmbH"}
geo.hosting = lambda ip: DC.get(ip)                     # база провайдеров — подменённая
BASE = max(S.day_bounds(S.today())[0] + 5, NOW - 1500)


def entry(ts, uri, ip, ua=NEW, nav=True):
    h = {"User-Agent": [ua], "Accept-Language": ["en-US,en;q=0.9"]}
    if nav:
        h["Sec-Fetch-Mode"] = ["navigate"]
    return json.dumps({"ts": ts, "request": {"client_ip": ip, "method": "GET", "host": "dumskaya-design.com", "uri": uri, "headers": h},
                       "status": 200})


lines, t = [], BASE
people = {
    "1.0.0.1": (NEW, ["/", "/en/contact"], [(5, 1), (30, 1)]),      # две страницы — вовлечён
    "1.0.0.2": (NEW, ["/"], [(25, 1)]),                             # одна страница, 25 с — вовлечён
    "1.0.0.3": (NEW, ["/"], [(2, 0)]),                              # одна страница, 2 с, дом. интернет — посетитель, не вовлечён
    "20.0.0.1": (NEW, ["/"], [(40, 1)]),                            # VPN (дата-центр) с действиями — посетитель, вовлечён
    "20.0.0.2": (NEW, ["/"], [(1, 0)]),                             # дата-центр, ни одного действия — робот
    "20.0.0.3": (NEW, ["/"], [(1, None)]),                          # дата-центр, старая страница без флажка — не отсеиваем
    "1.0.0.5": (OLD, ["/"], [(1, 0)]),                              # браузер старше года, без действий — робот
    "1.0.0.6": (NEW, ["/"], [(15, 1, "wd")]),                       # браузер под управлением программы — робот
}
for i, (ip, (ua, pages, _)) in enumerate(people.items()):
    for j, p in enumerate(pages):
        lines.append(entry(t + i * 10 + j * 3, p, ip, ua))
    lines.append(entry(t + i * 10 + 1, "/_astro/site.css", ip, ua, nav=False))
with open(os.path.join(LOGS, "dumskaya.log"), "w") as fh:
    fh.write("\n".join(sorted(lines, key=lambda x: json.loads(x)["ts"])) + "\n")
open(os.path.join(LOGS, "dumskaya-home.log"), "w").close()
for ip, (ua, pages, beacons) in people.items():
    for p, b in zip(pages, beacons):
        S.record_time(p, b[0], ip, ua, None if b[1] is None else bool(b[1]), len(b) > 2)

d = S.web("7")["total"]
check(d["visitors"] == 5, f"все заходы: 5 (люди, VPN с действиями и старая страница без флажка), есть {d['visitors']}")
check(d["engaged"] == 3, f"вовлечённые: 3 — две страницы, 25 с, VPN 40 с (есть {d['engaged']})")
lv = S.web("1h")
sm = lv["summary"]
check(sm["visitors"] == 5 and sm["engaged"] == 3, f"«1 час»: 5 заходов, 3 вовлечённых (есть {sm['visitors']}, {sm['engaged']})")
vpn = [s for s in lv["sessions"] if s["suspect"] and "Microsoft" in s["suspect"]]
check(len(vpn) == 1 and vpn[0]["acted"] is True and vpn[0]["engaged"], "VPN с действиями — в «1 час» с пометкой и как посетитель")
short = [s for s in lv["sessions"] if not s["engaged"]]
check(len(short) == 2, f"не вовлечённые — помечены ({len(short)})")
check(S.old_browser(OLD) and not S.old_browser(NEW) and not S.old_browser(UA.format(v=CUR) + " Edg/120.0"), "устаревший браузер — по версии Chrome")
f0 = {"i": False, "w": False, "known": True, "c": False}
check(S.program_robot("20.0.0.4", NEW, f0) and not S.program_robot("1.0.0.9", NEW, f0), "дата-центр без действий — робот, домашний — нет")
check(not S.program_robot("20.0.0.4", NEW, dict(f0, c=True)), "дата-центр, но нажал на контакт — посетитель")
check(S.program_robot("1.0.0.9", NEW, f0, uas_on_ip=6) and not S.program_robot("1.0.0.9", NEW, f0, uas_on_ip=2),
      "много браузеров с одного адреса без действий — робот")
check(S.engaged(1, 11) and S.engaged(2, 0) and S.engaged(1, 0, {"c": True}) and S.engaged(1, 3, None, True) and not S.engaged(1, 10),
      "правило вовлечённости: больше 10 с, 2+ страницы, контакт, заявка")
print("\n" + ("Всё в порядке" if not FAILS else f"Ошибок: {len(FAILS)}"))
sys.exit(1 if FAILS else 0)
