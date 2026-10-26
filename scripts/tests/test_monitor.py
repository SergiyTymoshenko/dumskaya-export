"""Сторож сайтов (deploy/site_monitor.py): студия и магазин — отдельно, со своими режимами, состоянием и названием
в сообщениях. Сеть не нужна: проверка, сертификат и время подменены.

   python3 scripts/tests/test_monitor.py      — в конце «OK: N проверок»"""
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "deploy"))
import site_monitor as M  # noqa: E402

ok, problems = 0, []


def check(cond, what):
    global ok
    if cond:
        ok += 1
    else:
        problems.append(what)


class Store:
    def __init__(self):
        self.d = {}

    def get(self, k, default=None):
        return self.d.get(k, default)

    def put(self, k, v):
        self.d[k] = v

    def drop(self, k):
        self.d.pop(k, None)


class Bot:
    def __init__(self):
        self.s, self.sent = Store(), []

    def notify(self, text, roles=()):
        self.sent.append(text)
        return [1]


app = tempfile.mkdtemp()
M.APP = app
open(os.path.join(app, "mode"), "w").write("live")
open(os.path.join(app, "home-mode"), "w").write("preview")
bot, now = Bot(), [1_000_000.0]
state = {"studio": (True, "", 12), "home": (False, "ответ 502", 30)}
mk = lambda **kw: M.SiteMonitor(bot, clock=lambda: now[0], retry_wait=0, cert_fn=lambda u: 70, diag_fn=lambda: "• диагноз", **kw)  # noqa: E731
studio = mk(check_fn=lambda u: state["studio"])
home = mk(url=M.HOME_URL, name="Магазин", key="monh", mode_file="home-mode", site_dir=M.HOME_SITE_DIR, check_fn=lambda u: state["home"])

for _ in range(4):
    studio.tick(); home.tick(); now[0] += 60
check(not bot.sent and home.status_data()["live"] is False, "магазин в режиме просмотра — не проверяется и не пишет")
check(studio.status_data()["ok"] is True and studio.status_data()["ms"] == 12, "студия: работает, 12 мс")

open(os.path.join(app, "home-mode"), "w").write("live")
for _ in range(3):
    studio.tick(); home.tick(); now[0] += 60
check(len(bot.sent) == 1 and "🔴 <b>Магазин не отвечает</b>" in bot.sent[0] and "dumskaya-home.com" in bot.sent[0] and "502" in bot.sent[0],
      "магазин не отвечает 3 раза подряд — одно сообщение «Магазин не отвечает»")
check(bot.s.get("monh:down_since") and not bot.s.get("mon:down_since"), "состояние у магазина своё (monh:), у студии не тронуто")
d = home.status_data()
check(d["live"] and d["ok"] is False and d["why"] == "ответ 502" and d["down_since"], "«Графики»: магазин — не отвечает, причина")
state["home"] = (True, "", 40)
home.tick()
check(len(bot.sent) == 2 and "🟢 <b>Магазин снова работает</b>" in bot.sent[1], "магазин снова работает — сообщение")
check(not bot.s.get("monh:down_since"), "состояние магазина сброшено")
state["studio"] = (False, "не ответил за 20 секунд", 20000)
for _ in range(3):
    studio.tick(); now[0] += 60
check(len(bot.sent) == 3 and "🔴 <b>Сайт не отвечает</b>" in bot.sent[2] and "dumskaya-design.com" in bot.sent[2], "студия — по-прежнему «Сайт не отвечает»")
os.makedirs(os.path.join(app, "home"))
M.HOME_SITE_DIR = os.path.join(app, "home", "site")
tips = M.diagnose(M.HOME_SITE_DIR)
check("deploy:home" in tips, "нет файлов магазина — подсказка выложить магазин (npm run deploy:home)")

print("\n".join("✗ " + p for p in problems))
print(f"{'ОШИБКИ: ' + str(len(problems)) if problems else 'OK'}: {ok} проверок")
sys.exit(1 if problems else 0)
