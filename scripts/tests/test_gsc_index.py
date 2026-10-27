"""Проверка индекса Google (deploy/gsc_index.py): подпись токена (RS256 через openssl), очередь проверок, итоги
по фабрикам каталога, строка утром и одно предложение выкладывать следующую фабрику. Search Console подменён.
Запуск: python3 scripts/tests/test_gsc_index.py"""
import json
import os
import subprocess
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="dd-gsc-")
os.environ["HOME"] = TMP
APP = os.path.join(TMP, "dumskaya")
os.makedirs(os.path.join(APP, "home-catalog"))
for d in ("studio", "home"):
    os.makedirs(os.path.join(TMP, d))
os.environ["SITE_DIR"], os.environ["HOME_SITE_DIR"] = os.path.join(TMP, "studio"), os.path.join(TMP, "home")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "deploy"))
import gsc_index as G  # noqa: E402

FAILS = []


def check(ok, what):
    print(("✓ " if ok else "✗ ") + what)
    if not ok:
        FAILS.append(what)


# сайты на домене, карты сайтов
for f in ("mode", "home-mode"):
    open(os.path.join(APP, f), "w").write("live")
studio = [f"https://dumskaya-design.com/{p}" for p in ("", "sk", "de", "en/contact")]
home = ["https://dumskaya-home.com/", "https://dumskaya-home.com/sofas"] + \
       [f"https://dumskaya-home.com/{l}poliform/sofa-{i}" for i in range(5) for l in ("", "ru/")] + \
       [f"https://dumskaya-home.com/{l}rugiano/bed-{i}" for i in range(5) for l in ("", "ru/")]
for d, urls in (("studio", studio), ("home", home)):
    open(os.path.join(TMP, d, "sitemap.xml"), "w").write("<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>")
frozen = {f"DF-{f}{i}": {"path": {"en": f"/{f}/{k}-{i}", "ru": f"/ru/{f}/{k}-{i}"}} for f, k in (("poliform", "sofa"), ("rugiano", "bed")) for i in range(5)}
json.dump(frozen, open(os.path.join(APP, "home-catalog", "frozen.json"), "w"))
json.dump({"factories": {"poliform": {"since": "2026-10-25"}, "rugiano": {"since": "2026-10-26"}}},
          open(os.path.join(APP, "home-catalog", "publish.json"), "w"))

# ключ служебного аккаунта — настоящий RSA, подпись проверяем открытым ключом
pem = subprocess.run(["openssl", "genrsa", "2048"], capture_output=True, check=True).stdout.decode()
json.dump({"client_email": "reader@x.iam.gserviceaccount.com", "private_key": pem}, open(G.KEY_FILE, "w"))
sent = {}


class Resp:
    def __init__(self, d):
        self.d = json.dumps(d).encode()

    def read(self, *a):
        return self.d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_open(req, timeout=0):
    sent["token"] = req.data.decode()
    return Resp({"access_token": "tok", "expires_in": 3600})


G.urllib.request.urlopen = fake_open
check(G.token() == "tok", "токен по ключу служебного аккаунта")
jwt = dict(x.split("=") for x in sent["token"].split("&"))["assertion"]
h, c, s = jwt.split(".")
import base64  # noqa: E402
pad = lambda x: base64.urlsafe_b64decode(x + "=" * (-len(x) % 4))  # noqa: E731
pub = subprocess.run(["openssl", "rsa", "-pubout"], input=pem.encode(), capture_output=True, check=True).stdout
open(os.path.join(TMP, "pub.pem"), "wb").write(pub)
open(os.path.join(TMP, "sig"), "wb").write(pad(s))
ok = subprocess.run(["openssl", "dgst", "-sha256", "-verify", os.path.join(TMP, "pub.pem"), "-signature", os.path.join(TMP, "sig")],
                    input=f"{h}.{c}".encode(), capture_output=True).returncode == 0
check(ok and json.loads(pad(c))["scope"].endswith("webmasters.readonly"), "подпись RS256 верная, доступ — только чтение")
check(not [f for f in os.listdir(G.STATE_DIR) if f.endswith(".pem")], "закрытый ключ после подписи не остаётся на диске")

# Search Console: в индексе — все страницы Poliform и главная студии, Rugiano — 3 из 10
calls = []


def fake_api(url, body=None):
    if "searchAnalytics" in url:
        dims = body["dimensions"]
        if dims == ["date"]:
            return {"rows": [{"keys": ["2026-10-25"], "clicks": 1, "impressions": 30, "ctr": 0.03, "position": 12.5},
                             {"keys": ["2026-10-26"], "clicks": 2, "impressions": 50, "ctr": 0.04, "position": 9.1}]}
        if dims == ["page"]:
            return {"rows": [{"keys": ["https://dumskaya-home.com/poliform/sofa-1"], "clicks": 2, "impressions": 40, "ctr": 0.05, "position": 8},
                             {"keys": ["https://dumskaya-home.com/sofas"], "clicks": 0, "impressions": 5, "ctr": 0, "position": 30}]}
        if dims == ["country"]:
            return {"rows": [{"keys": ["svk"], "clicks": 2, "impressions": 60, "ctr": 0.03, "position": 10}]}
        if dims == []:
            return {"rows": [{"clicks": 3, "impressions": 80, "ctr": 0.0375, "position": 10.4}]}
        return {"rows": []}
    if url.endswith("/sitemaps"):
        return {"sitemap": [{"path": "https://dumskaya-home.com/sitemap.xml", "lastDownloaded": "2026-10-26T10:00:00Z", "warnings": "0",
                             "errors": "0", "contents": [{"type": "web", "submitted": "3030"}]}]}
    if url == G.SITES_URL:
        return {"siteEntry": [{"siteUrl": "sc-domain:dumskaya-home.com"}, {"siteUrl": "https://dumskaya-design.com/"}]}
    calls.append(body["inspectionUrl"])
    u = body["inspectionUrl"]
    yes = "poliform" in u or u == "https://dumskaya-design.com/" or any(f"bed-{i}" in u and "/ru/" not in u for i in range(3))
    return {"inspectionResult": {"indexStatusResult": {"verdict": "PASS" if yes else "NEUTRAL",
                                                       "coverageState": "Submitted and indexed" if yes else "Discovered - currently not indexed"}}}


G.api = fake_api
notes = []
G.BOT = type("B", (), {"notify": lambda self, t, roles=None: notes.append(t)})()
G.run_all(log=lambda *a: None)
check(len(calls) == len(studio) + len(home), f"проверены все страницы обоих сайтов ({len(calls)})")
g = {n: (y, ch, t) for n, y, ch, t in G.groups("dumskaya-home.com")}
check(g.get("Poliform") == (10, 10, 10) and g.get("Rugiano") == (3, 10, 10) and g.get("разделы магазина") == (0, 2, 2), f"итоги по фабрикам: {g}")
line = G.morning_lines()[0]
check("Сайт студии 1 из 4" in line and "Poliform 10 из 10" in line and "Rugiano 3 из 10" in line, f"строка утром: {line}")
check(not notes, "Rugiano в индексе на 30 % — предлагать рано")
calls.clear()
G.run_all(log=lambda *a: None)
check(not calls, "повторно в тот же день ничего не проверяется (не в индексе — через 2 дня, в индексе — через 2 недели)")
st = G.load("dumskaya-home.com")
for u in st["pages"]:
    if "rugiano" in u:
        st["pages"][u] = dict(st["pages"][u], indexed=True, checked=int(time.time()))
G.save("dumskaya-home.com", st)
G.suggest(log=lambda *a: None)
check(len(notes) == 1 and "Rugiano" in notes[0] and "100%" in notes[0], f"Rugiano в индексе — предложение выкладывать дальше ({notes})")
G.suggest(log=lambda *a: None)
check(len(notes) == 1, "предложение — один раз на фабрику")
w = G.web_data("home")["sites"][0]
sv = w["search"]
check(sv and sv["totals"]["impressions"] == 80 and len(sv["dates"]) == 2 and sv["countries"][0][0] == "Словакия",
      "статистика поиска: итоги, по дням, страны по-русски")
check(dict((n, i) for n, _, i in sv["factories"]) == {"Poliform": 40, "разделы магазина": 5}, f"показы по фабрикам: {sv['factories']}")
check(sv["sitemaps"][0]["urls"] == 3030, "карта сайта: сколько адресов Google принял")
h = w["history"]
check(h and list(h.values())[-1].get("Poliform") == [10, 10, 10], f"снимок дня для прогресса индексации: {h}")
q = G.todo(["a", "b", "c"], {"b": {"indexed": False, "checked": 0}, "c": {"indexed": True, "checked": int(time.time())}}, time.time())
check(q == ["a", "b"], f"очередь: новые, потом давно проверенные не в индексе ({q})")
print("\n" + ("Всё в порядке" if not FAILS else f"Ошибок: {len(FAILS)}"))
sys.exit(1 if FAILS else 0)
