"""Проверка резервных копий (deploy/backups.py): архив данных на сервере, 7 дней хранения, в Telegram ничего не уходит
(решено 25.10.2026), сообщение разработчику, если архив не записался, восстановление баз и файлов.
Временные базы и папки, Telegram подменён.

   python3 scripts/tests/test_backups.py      — в конце «OK: N проверок»"""
import json
import os
import sqlite3
import sys
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
SENT = []


def fake_send_file_r(self, chat_id, f, path, caption=None, rows=None, silent=False):
    SENT.append({"chat": chat_id, "name": f.get("name")})
    return True, "", 5000 + len(SENT)


H.Bot.send_file_r = fake_send_file_r
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
thumb = f"{pid}/{f1}-thumb.jpg"
with open(os.path.join(crm.files_dir, thumb), "wb") as fh:
    fh.write(b"thumb")
crm.run("UPDATE files SET thumb=? WHERE id=?", thumb, f1)

# ---------- 1. ночью: архив на сервере; в Telegram — ничего ----------
n0 = len(H.CALLS)
r = B.daily_tick(bot, crm, log=lambda *a: None)
day = B.today().isoformat()
server_zip = os.path.join(BK, f"dumskaya-data-{day}.zip")
check(r == "data" and os.path.exists(server_zip), "архив данных за сегодня на сервере")
check(oct(os.stat(server_zip).st_mode & 0o777) == "0o600", "архив на сервере — только для владельца (600)")
with zipfile.ZipFile(server_zip) as z:
    names = set(z.namelist())
    db = os.path.join(H.TMP, "check.db")
    with open(db, "wb") as fh:
        fh.write(z.read("crm.db"))
    readme = z.read("ПРОЧТИ-МЕНЯ.txt").decode()
check({"crm.db", "bot.db", "leads.jsonl", "lead.env", "stats/secret", "stats/2026-10-20.json", "ПРОЧТИ-МЕНЯ.txt"} <= names,
      f"на сервере — всё, включая lead.env: {sorted(names)}")
con = sqlite3.connect(db)
check(con.execute("SELECT title FROM projects WHERE id=?", (pid,)).fetchone()[0].startswith("Квартира"), "база в архиве целая и читается")
con.close()
check("--restore-data" in readme and "Telegram" not in readme, "в архиве — как восстановить, про Telegram — ни слова")
check(not [f for f in os.listdir(BK) if f.startswith(".")], "временных файлов не осталось")
check(not SENT and not [m for m, p in H.CALLS[n0:] if m in ("sendDocument", "sendMessage", "sendVideo", "sendPhoto", "copyMessage")],
      "в Telegram не ушло ничего — ни архив, ни файлы проектов, ни сообщения")
check(B.daily_tick(bot, crm, log=lambda *a: None) is None, "второй раз за день — ничего")
for _ in range(3):
    B.daily_tick(bot, crm, log=lambda *a: None)
check(not SENT and len(H.CALLS) == n0, "и через минуту, и потом — тоже ничего (файлы проектов в Telegram не копируются)")

# ---------- 2. архив не записался — одно сообщение разработчику ----------
bad_dir = os.path.join(H.TMP, "not-a-dir")
with open(bad_dir, "w") as fh:
    fh.write("x")
bot.s.put("backup:zip_day", "")
n2 = len(H.CALLS)
r = B.daily_tick(bot, crm, log=lambda *a: None, backup_dir=bad_dir)
warn = msgs(n2)
check(r is False and len(warn) == 1 and warn[0]["chat_id"] == bot.owner and "не записалась" in warn[0]["text"]
      and "backups.py --now" in warn[0]["text"], "архив не записался — разработчику одно сообщение с подсказкой")
check(B.daily_tick(bot, crm, log=lambda *a: None, backup_dir=bad_dir) is None and len(msgs(n2)) == 1, "в тот же день — не повторяет")
check(not SENT, "и в этом случае файлов в Telegram нет")

# ---------- 3. после выкладки — отметки прежней копии в Telegram убираются ----------
for k, v in (("backup:sent_day", day), ("backup:fails", "2"), ("backup:retry_at", "1"), ("backup:files_sent", "[1, 2]"),
             (f"backup:part:{day}", "3")):
    bot.s.put(k, v)
B.on_start(bot)
check(not any(bot.s.get(k) for k in ("backup:sent_day", "backup:fails", "backup:retry_at", "backup:files_sent", f"backup:part:{day}")),
      "старые отметки копии в Telegram убраны")
check(bot.s.get("backup:zip_day") == day, "отметка архива на сервере осталась")

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

# ---------- 6. восстановление файлов из прежних архивов dumskaya-files-…zip (бот присылал их до 25.10.2026) ----------
from crm import Crm  # noqa: E402
crm2 = Crm(path=os.environ["CRM_DB"], rates=H.FakeRates(), files_dir=crm.files_dir, backup_dir=BK)
old_zip = os.path.join(H.TMP, f"dumskaya-files-{day}-01.zip")
with zipfile.ZipFile(old_zip, "w") as z:
    for fid, rel, cat in ((f1, f"{pid}/{f1}.jpg", "Визуализации"), (f2, f"{pid}/{f2}.jpg", "Визуализации"), (f3, f"{pid}/{f3}.pdf", "Обмерный план")):
        z.write(os.path.join(crm.files_dir, rel), f"12 Квартира в Братиславе 127 м²/{cat}/{fid:05d}-x{os.path.splitext(rel)[1]}")
orig = open(os.path.join(crm.files_dir, f"{pid}/{f1}.jpg"), "rb").read()
os.remove(os.path.join(crm.files_dir, f"{pid}/{f1}.jpg"))
os.remove(os.path.join(crm.files_dir, thumb))
back, have, unknown = B.restore_files([old_zip], crm2, log=lambda *a: None)
check(back == 1 and have == 2 and unknown == 0, f"возвращён удалённый файл, остальные на месте: {back} {have} {unknown}")
check(open(os.path.join(crm.files_dir, f"{pid}/{f1}.jpg"), "rb").read() == orig, "файл тот же байт в байт")
check(crm2.one("SELECT thumb FROM files WHERE id=?", f1)["thumb"] is None, "пропавшая миниатюра сброшена")

print(f"OK: {ok} проверок")
