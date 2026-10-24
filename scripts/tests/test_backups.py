"""Проверка резервных копий (deploy/backups.py): архив данных на сервере, 7 дней хранения, копия в Telegram без паролей
и ключей, новые файлы проектов архивами (каждый один раз), большие файлы, повтор при сбое, восстановление баз и файлов.
Временные базы и папки, Telegram подменён.

   python3 scripts/tests/test_backups.py      — в конце «OK: N проверок»"""
import json
import os
import shutil
import sqlite3
import sys
import time
import zipfile
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402
import backups as B  # noqa: E402

ok = 0


def check(cond, what):
    global ok
    if not cond:
        raise AssertionError(what)
    ok += 1


APP = os.path.join(H.TMP, "dumskaya")
BK = os.environ["BACKUP_DIR"]
GOT = os.path.join(H.TMP, "telegram")      # что «ушло» в Telegram: архивы копируются сюда
os.makedirs(GOT, exist_ok=True)
SENT = []
FAIL = {"on": False}


def fake_send_file_r(self, chat_id, f, path, caption=None, rows=None, silent=False):
    if FAIL["on"]:
        return False, "Telegram не ответил", None
    if f.get("tg_file_id") == "video:BROKEN":         # ссылка на файл в Telegram, которую Telegram больше не принимает
        return False, "Bad Request: wrong file identifier/HTTP URL specified", None
    rec = {"chat": chat_id, "name": f.get("name"), "caption": caption, "silent": silent, "ref": f.get("tg_file_id")}
    if path:
        rec["copy"] = os.path.join(GOT, f"{len(SENT):03d}-{f['name']}")
        shutil.copy(path, rec["copy"])
    SENT.append(rec)
    return True, "", 5000 + len(SENT)


H.Bot.send_file_r = fake_send_file_r
B.PART_MAX = 300 * 1024                     # архив файлов «до 45 МБ» — в проверке 300 КБ
B.TG_MAX = 400 * 1024                       # «больше 50 МБ» — в проверке больше 400 КБ
bot, crm = H.bot, H.crm


def msgs(since=0):
    return [p for m, p in H.CALLS[since:] if m == "sendMessage"]


# ---------- данные ----------
with open(os.path.join(APP, "lead.env"), "w") as fh:
    fh.write("TELEGRAM_BOT_TOKEN=123:SECRET\n")
with open(os.environ["LEADS_FILE"], "w") as fh:
    fh.write(json.dumps({"name": "Anna", "contact": "+43 1", "message": "Kitchen"}) + "\n")
with open(os.path.join(APP, "stats", "secret"), "w") as fh:
    fh.write("salt")
with open(os.path.join(APP, "stats", "2026-10-20.json"), "w") as fh:
    fh.write('{"visitors": 12}')
pid = crm.run("INSERT INTO projects(number, title, total_eur, created) VALUES('12', 'Квартира в Братиславе: 127 м²', 9000, '2026-10-01')")
os.makedirs(os.path.join(crm.files_dir, str(pid)), exist_ok=True)


def add_file(name, cat, size, tg=None, on_disk=True):
    fid = crm.run("INSERT INTO files(project_id, category, name, mime, size, tg_file_id, created) VALUES(?, ?, ?, 'image/jpeg', ?, ?, '2026-10-02')",
                  pid, cat, name, size, tg)
    rel = f"{pid}/{fid}{os.path.splitext(name)[1]}"
    if on_disk:
        with open(os.path.join(crm.files_dir, rel), "wb") as fh:
            fh.write(os.urandom(size))
        crm.run("UPDATE files SET path=? WHERE id=?", rel, fid)
    return fid


f1 = add_file("гостиная.jpg", "visual", 120 * 1024)
f2 = add_file("спальня.jpg", "visual", 120 * 1024)
f3 = add_file("план.pdf", "measure", 200 * 1024)
f4 = add_file("видео обхода.mp4", "after", 30 * 1024 * 1024, tg="video:AAA", on_disk=False)   # только в Telegram
f5 = add_file("огромный.pdf", "docs", 500 * 1024)                                             # больше «50 МБ»
thumb = f"{pid}/{f1}-thumb.jpg"
with open(os.path.join(crm.files_dir, thumb), "wb") as fh:
    fh.write(b"thumb")
crm.run("UPDATE files SET thumb=? WHERE id=?", thumb, f1)

# ---------- 1. ночью: архив на сервере и копия в Telegram ----------
n0 = len(H.CALLS)
r = B.daily_tick(bot, crm, log=lambda *a: None)
day = B.today().isoformat()
server_zip = os.path.join(BK, f"dumskaya-data-{day}.zip")
check(r == "data" and os.path.exists(server_zip), "архив данных за сегодня на сервере и отправлен")
check(oct(os.stat(server_zip).st_mode & 0o777) == "0o600", "архив на сервере — только для владельца (600)")
with zipfile.ZipFile(server_zip) as z:
    names = set(z.namelist())
check({"crm.db", "bot.db", "leads.jsonl", "lead.env", "stats/secret", "stats/2026-10-20.json", "ПРОЧТИ-МЕНЯ.txt"} <= names,
      f"на сервере — всё, включая lead.env: {sorted(names)}")
tg = SENT[-1]
check(tg["chat"] == bot.owner and tg["silent"] and tg["name"] == f"dumskaya-data-{day}.zip", "разработчику, без звука, понятное имя")
with zipfile.ZipFile(tg["copy"]) as z:
    tnames = set(z.namelist())
    db = os.path.join(H.TMP, "check.db")
    with open(db, "wb") as fh:
        fh.write(z.read("crm.db"))
    readme = z.read("ПРОЧТИ-МЕНЯ.txt").decode()
check("lead.env" not in tnames and "stats/secret" not in tnames and "crm.db" in tnames, "в Telegram — без паролей и соли статистики")
check(b"SECRET" not in open(tg["copy"], "rb").read(), "токена нет нигде в архиве для Telegram")
con = sqlite3.connect(db)
check(con.execute("SELECT title FROM projects WHERE id=?", (pid,)).fetchone()[0].startswith("Квартира"), "база в архиве целая и читается")
con.close()
check("--restore-data" in readme and "только в копии на сервере" not in readme.split("crm.db")[0], "в архиве — как восстановить")
check(not [f for f in os.listdir(BK) if f.startswith(".")], "временных файлов не осталось")
check(B.daily_tick(bot, None, log=lambda *a: None) is None, "второй раз за день — ни архива, ни отправки")

# ---------- 2. файлы проектов ----------
n1 = len(H.CALLS)
r = B.daily_tick(bot, crm, log=lambda *a: None)
big = msgs(n1)
check(r == "too_big" and big and "огромный.pdf" in big[0]["text"] and big[0].get("disable_notification"), "файл больше лимита — сказано один раз, без звука")
r = B.daily_tick(bot, crm, log=lambda *a: None)
check(r == "forwarded" and SENT[-1]["ref"] == "video:AAA" and "видео обхода" in SENT[-1]["caption"], "файл только в Telegram — переслан ссылкой")
parts = []
while True:
    r = B.daily_tick(bot, crm, log=lambda *a: None)
    if r != "files":
        break
    parts.append(SENT[-1])
check(r is None and len(parts) == 2, f"файлы ушли двумя архивами по лимиту: {len(parts)} r={r} last={SENT[-1]} fails={bot.s.get('backup:fails')}")
check(parts[0]["name"] == f"dumskaya-files-{day}-01.zip" and parts[1]["name"] == f"dumskaya-files-{day}-02.zip", "архивы пронумерованы")
check("Ещё 1" in parts[0]["caption"], "в подписи — сколько осталось")
inside = []
for p in parts:
    with zipfile.ZipFile(p["copy"]) as z:
        inside += z.namelist()
check(sorted(inside) == sorted([f"12 Квартира в Братиславе 127 м²/Визуализации/{f1:05d}-гостиная.jpg",
                                f"12 Квартира в Братиславе 127 м²/Визуализации/{f2:05d}-спальня.jpg",
                                f"12 Квартира в Братиславе 127 м²/Обмерный план/{f3:05d}-план.pdf"]), f"понятные имена: {inside}")
check(B.daily_tick(bot, crm, log=lambda *a: None) is None, "каждый файл — один раз")
f6 = add_file("после ремонта.jpg", "after", 50 * 1024)
r = B.daily_tick(bot, crm, log=lambda *a: None)
check(r == "files" and SENT[-1]["name"].endswith("-03.zip"), "новый файл — следующим архивом")
f7 = add_file("документация.pdf", "docs", 350 * 1024)          # больше архива, но в лимите Telegram
r = B.daily_tick(bot, crm, log=lambda *a: None)
check(r == "file" and SENT[-1]["name"] == "документация.pdf" and f"{f7:05d}-документация.pdf" in SENT[-1]["caption"],
      "крупный файл — сам по себе, с понятной подписью")
check(B.daily_tick(bot, crm, log=lambda *a: None) is None, "очередь пуста")

# ---------- 3. сбой Telegram ----------
bot.s.put("backup:zip_day", "")
bot.s.put("backup:sent_day", "")
FAIL["on"] = True
n2 = len(H.CALLS)
t = 1_000_000.0
check(B.daily_tick(bot, crm, log=lambda *a: None, now=t) is False, "не отправилось")
check(B.daily_tick(bot, crm, log=lambda *a: None, now=t + 60) is None, "следующая попытка — не раньше чем через час")
B.daily_tick(bot, crm, log=lambda *a: None, now=t + 3601)
B.daily_tick(bot, crm, log=lambda *a: None, now=t + 7202)
warn = [m for m in msgs(n2) if "не отправляется" in m["text"]]
check(len(warn) == 1 and warn[0]["chat_id"] == bot.owner, "после трёх неудач — одно сообщение разработчику")
FAIL["on"] = False
bot.s.put("backup:sent_day", "")
check(B.daily_tick(bot, crm, log=lambda *a: None, now=t + 10900) == "data" and not bot.s.get("backup:fails"), "связь вернулась — отправилось")
bot.s.put("backup:retry_at", str(time.time() + 3600))
B.on_start(bot)
check(not bot.s.get("backup:retry_at"), "после перезапуска сервиса (выкладки) — пробует сразу, без часа ожидания")

# ---------- 3а. файл только в Telegram, которого Telegram больше не отдаёт, не держит очередь ----------
fz = crm.add_tg_only(pid, "visual", "старое видео.mp4", 30 * 2**20, "video/mp4", "Ирина", "video:BROKEN")["id"]
fg = crm.add_tg_only(pid, "visual", "новое видео.mp4", 30 * 2**20, "video/mp4", "Ирина", "video:GOOD")["id"]
n3 = len(H.CALLS)
r = B.daily_tick(bot, crm, log=lambda *a: None)
lost = [m for m in msgs(n3) if "больше не отдаёт" in m["text"]]
check(r == "forwarded" and SENT[-1]["ref"] == "video:GOOD", "соседний файл переслан")
check(len(lost) == 1 and "старое видео.mp4" in lost[0]["text"] and lost[0].get("disable_notification"), "о потерянном — одно тихое сообщение")
check(not bot.s.get("backup:fails") and not bot.s.get("backup:retry_at"), "это не сбой — очередь не встала")
check(B.daily_tick(bot, crm, log=lambda *a: None) is None, "второй раз не пытается")

# ---------- 3б. отправка файла в Telegram: имя файла — так, как его понимает Telegram ----------
import crm_bot  # noqa: E402
import email.parser  # noqa: E402
from email import policy  # noqa: E402
CAP = {}


class FakeResp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b'{"ok": true, "result": {"message_id": 7}}'


def fake_urlopen(req, timeout=0):
    CAP["req"] = req
    return FakeResp()


real_urlopen = crm_bot.urllib.request.urlopen
crm_bot.urllib.request.urlopen = fake_urlopen
try:
    for name, mime, raw in (("dumskaya-data-2026-10-25.zip", "application/zip", b"PK\x03\x04 data"),
                            ("Смета кухни «вариант 2».pdf", "application/pdf", b"%PDF-1.4 x"),
                            ('a"b.jpg', "image/jpeg", b"\xff\xd8\xff jpeg")):
        tmpf = os.path.join(H.TMP, "upload.bin")
        with open(tmpf, "wb") as fh:
            fh.write(raw)
        ok_, why, mid = crm_bot.CrmBotMixin.send_file_r(bot, bot.owner, {"name": name, "mime": mime}, tmpf, caption="<b>x</b>", silent=True)
        req = CAP["req"]
        body = req.data
        msg = email.parser.BytesParser(policy=policy.HTTP).parsebytes(b"Content-Type: " + req.get_header("Content-type").encode() + b"\r\n\r\n" + body)
        got = {p.get_param("name", header="content-disposition"): p for p in msg.iter_parts()}
        field = "photo" if mime == "image/jpeg" else "document"
        f_part = got.get(field)
        check(ok_ and mid == 7 and f_part is not None and f_part.get_filename() and f_part.get_payload(decode=True) == raw,
              f"{name}: файл — с именем файла, содержимое на месте")
        check(b"filename*" not in body and ('filename="' + name.replace('"', "%22") + '"').encode() in body, f"{name}: filename=\"…\" (UTF-8), без filename*")
        check(got["chat_id"].get_payload() == str(bot.owner) and got["disable_notification"].get_payload() == "true"
              and got["parse_mode"].get_payload() == "HTML", f"{name}: остальные поля на месте")
finally:
    crm_bot.urllib.request.urlopen = real_urlopen

# ---------- 4. хранение 7 дней ----------
d0 = B.today()
for k in (1, 6, 7, 8, 20):
    open(os.path.join(BK, f"dumskaya-data-{(d0 - timedelta(days=k)).isoformat()}.zip"), "w").close()
open(os.path.join(BK, f"crm-{(d0 - timedelta(days=25)).isoformat()}.db"), "w").close()
open(os.path.join(BK, f"bot-{(d0 - timedelta(days=2)).isoformat()}.db"), "w").close()
gone = B.prune(BK, d0, log=lambda *a: None)
left = sorted(f for f in os.listdir(BK) if B.NAME_RE.match(f))
check(len([f for f in left if f.startswith("dumskaya-data")]) == 3 and len(gone) == 4,
      f"на сервере — только последние 7 дней (сегодня, −1, −6): {left}")

# ---------- 5. восстановление баз ----------
crm.run("DELETE FROM projects WHERE id=?", pid)
crm.db.commit() if hasattr(crm.db, "commit") else None
with open(os.path.join(APP, "lead.env"), "w") as fh:
    fh.write("TELEGRAM_BOT_TOKEN=NEW\n")
done = B.restore_data(server_zip, app=APP, log=lambda *a: None)
con = sqlite3.connect(os.environ["CRM_DB"])
check(con.execute("SELECT COUNT(*) FROM projects WHERE id=?", (pid,)).fetchone()[0] == 1, "проект вернулся из копии")
con.close()
check(open(os.path.join(APP, "lead.env")).read() == "TELEGRAM_BOT_TOKEN=NEW\n", "нынешний lead.env не перезаписан")
keep = [d for d in os.listdir(APP) if d.startswith("restore-")]
check(keep and os.path.exists(os.path.join(APP, keep[0], "crm.db")), "прежние базы сохранены в restore-…")
check("stats/2026-10-20.json" in done and not os.path.exists(os.environ["CRM_DB"] + "-wal"), "статистика возвращена, журнал старой базы убран")

# ---------- 6. восстановление файлов ----------
from crm import Crm  # noqa: E402
crm2 = Crm(path=os.environ["CRM_DB"], rates=H.FakeRates(), files_dir=crm.files_dir, backup_dir=BK)
orig = open(os.path.join(crm.files_dir, f"{pid}/{f1}.jpg"), "rb").read()
os.remove(os.path.join(crm.files_dir, f"{pid}/{f1}.jpg"))
os.remove(os.path.join(crm.files_dir, thumb))
back, have, unknown = B.restore_files([p["copy"] for p in parts], crm2, log=lambda *a: None)
check(back == 1 and have == 2 and unknown == 0, f"возвращён удалённый файл, остальные на месте: {back} {have} {unknown}")
check(open(os.path.join(crm.files_dir, f"{pid}/{f1}.jpg"), "rb").read() == orig, "файл тот же байт в байт")
check(crm2.one("SELECT thumb FROM files WHERE id=?", f1)["thumb"] is None, "пропавшая миниатюра сброшена")

print(f"OK: {ok} проверок")
