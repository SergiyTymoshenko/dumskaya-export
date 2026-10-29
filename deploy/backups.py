#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Резервные копии данных студии — только на сервере (решено 25.10.2026: в Telegram больше не отправляем,
24.10.2026 — на Мак больше не копируем).

Каждую ночь (в первые минуты после полуночи по Братиславе — делает сервис заявок) на сервере — архив
~/dumskaya/backups/dumskaya-data-ГГГГ-ММ-ДД.zip: база «Студии» (crm.db), база бота (bot.db), курсы валют (fx.db),
заявки (leads.jsonl), статистика сайта (stats/, hits.jsonl, times.jsonl) и настройки сервиса (lead.env). Хранятся
7 последних дней, старые удаляются сами. Не записался архив — разработчику сообщение в бот (только об ошибке).
Файлы проектов отдельно не копируются: они лежат в ~/dumskaya/crm/files, удалённые — 30 дней в корзине,
а весь сервер каждый день копирует Hetzner (7 копий) — это и есть защита на случай потери сервера.

   python3 backups.py --now                       — архив данных сейчас (например, перед рискованной правкой)
   python3 backups.py --restore-data АРХИВ.zip     — вернуть базы и заявки из архива (сервис сначала остановить)
   python3 backups.py --restore-files А.zip Б.zip  — вернуть файлы проектов из архивов dumskaya-files-…zip
                                                    (их бот присылал в Telegram до 25.10.2026)
Подробно — README, раздел «Резервные копии». Только стандартная библиотека Python 3."""
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bratislava")
except Exception:  # noqa: BLE001
    TZ = timezone(timedelta(hours=1))

APP = os.path.expanduser("~/dumskaya")
BACKUP_DIR = os.environ.get("BACKUP_DIR", os.path.join(APP, "backups"))
FILES_DIR = os.environ.get("CRM_FILES", os.path.join(APP, "crm", "files"))
KEEP_DAYS = 7                           # на сервере — копии за 7 последних дней (решено 24.10.2026)
NAME_RE = re.compile(r"^(?:dumskaya-data|crm|bot)-(\d{4}-\d{2}-\d{2})\.(?:zip|db)$")
SERVICE = "dumskaya-lead"

README = """Резервная копия данных студии DUMSKAYA DESIGN за {day}.

crm.db       — учёт «Студии»: проекты, оплаты, заказчики, подрядчики, кабинеты, переписка, список файлов проектов
bot.db       — бот: люди и роли, настройки, состояние
fx.db        — курсы валют центробанков
leads.jsonl  — заявки с сайта
stats/, hits.jsonl, times.jsonl — статистика сайта; stats-home/, hits-home.jsonl, times-home.jsonl — каталога dumskaya-home.com
{secret}
Сами файлы проектов в архив не входят: они на сервере в ~/dumskaya/crm/files, весь сервер копирует Hetzner.

Как вернуть — README репозитория сайта, раздел «Резервные копии»: на сервере
  sudo systemctl stop dumskaya-lead
  python3 ~/dumskaya/deploy/backups.py --restore-data ЭТОТ-АРХИВ.zip
  sudo systemctl start dumskaya-lead
"""


def today():
    return datetime.now(TZ).date()


def sources(app=APP):
    """Что входит в архив данных: (путь на сервере, имя в архиве, вид)."""
    e = os.environ.get
    j = lambda n: os.path.join(app, n)  # noqa: E731
    return [
        (e("CRM_DB", j("crm.db")), "crm.db", "db"),
        (e("BOT_DB", j("bot.db")), "bot.db", "db"),
        (e("FX_DB", j("fx.db")), "fx.db", "db"),
        (e("LEADS_FILE", j("leads.jsonl")), "leads.jsonl", "file"),
        (e("HITS_FILE", j("hits.jsonl")), "hits.jsonl", "file"),
        (e("TIMES_FILE", j("times.jsonl")), "times.jsonl", "file"),
        (e("STATS_DIR", j("stats")), "stats", "dir"),
        (e("HOME_HITS_FILE", j("hits-home.jsonl")), "hits-home.jsonl", "file"),     # статистика каталога dumskaya-home.com
        (e("HOME_TIMES_FILE", j("times-home.jsonl")), "times-home.jsonl", "file"),
        (e("HOME_STATS_DIR", j("stats-home")), "stats-home", "dir"),
        (j("lead.env"), "lead.env", "file"),
        (j("blocked.json"), "blocked.json", "file"),             # заблокированные отправители заявок
    ]


def human(n):
    n = float(n or 0)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024 or unit == "ГБ":
            return f"{n:.0f} {unit}" if unit in ("Б", "КБ") else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return ""


# ---------- архив данных ----------
def make_data_zip(day=None, backup_dir=None, srcs=None, log=print):
    """Архив данных за день: dumskaya-data-ДЕНЬ.zip в папке копий (права 600). Базы SQLite копируются стандартным
    способом SQLite — целостно и во время работы сервиса. Возвращает путь к архиву или None."""
    day = str(day or today())
    backup_dir = backup_dir or BACKUP_DIR
    srcs = srcs if srcs is not None else sources()
    tmp = os.path.join(backup_dir, f".tmp-{day}")
    try:
        os.makedirs(backup_dir, exist_ok=True)
        try:
            os.chmod(backup_dir, 0o700)
        except OSError:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp)
    except OSError as e:                      # папки копий нет и не создаётся (место, права) — сказать, не падать
        log(f"копия: архив не записался — папка копий {backup_dir}: {e}")
        return None
    dst = os.path.join(backup_dir, f"dumskaya-data-{day}.zip")
    have = []
    try:
        with zipfile.ZipFile(dst + ".part", "w", zipfile.ZIP_DEFLATED) as zf:
            for path, arc, kind in srcs:
                if not os.path.exists(path):
                    continue
                try:
                    if kind == "db":
                        copy = os.path.join(tmp, arc)
                        s, t = sqlite3.connect(path), sqlite3.connect(copy)
                        with t:
                            s.backup(t)
                        s.close()
                        t.close()
                        zf.write(copy, arc)
                    elif kind == "dir":
                        for root, _, names in os.walk(path):
                            for n in sorted(names):
                                full = os.path.join(root, n)
                                zf.write(full, arc + "/" + os.path.relpath(full, path).replace(os.sep, "/"))
                    else:
                        zf.write(path, arc)
                    have.append(arc)
                except (sqlite3.Error, OSError) as e:
                    log(f"копия: {arc} — ошибка {e}")
            secret = "lead.env     — настройки сервиса (токен бота, ключи)" if "lead.env" in have else ""
            zf.writestr("ПРОЧТИ-МЕНЯ.txt", README.format(day=day, secret=secret))
        os.replace(dst + ".part", dst)
        os.chmod(dst, 0o600)
    except OSError as e:
        log(f"копия: архив не записался — {e}")
        try:
            os.remove(dst + ".part")
        except OSError:
            pass
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    log(f"копия: {os.path.basename(dst)} ({human(os.path.getsize(dst))}: {', '.join(have) or 'данных пока нет'})")
    return dst


def prune(backup_dir=None, day=None, keep=KEEP_DAYS, log=print):
    """Удалить копии старше keep дней (и прежние копии баз crm-ДЕНЬ.db / bot-ДЕНЬ.db)."""
    backup_dir = backup_dir or BACKUP_DIR
    cutoff = (datetime.fromisoformat(str(day or today())).date() - timedelta(days=keep - 1)).isoformat()
    gone = []
    for f in sorted(os.listdir(backup_dir)) if os.path.isdir(backup_dir) else []:
        m = NAME_RE.match(f)
        if m and m.group(1) < cutoff:
            try:
                os.remove(os.path.join(backup_dir, f))
                gone.append(f)
            except OSError:
                pass
    if gone:
        log(f"копия: удалены старые — {len(gone)}")
    return gone


def latest_data_zip(backup_dir=None):
    backup_dir = backup_dir or BACKUP_DIR
    zips = sorted(f for f in os.listdir(backup_dir) if f.startswith("dumskaya-data-") and f.endswith(".zip")) \
        if os.path.isdir(backup_dir) else []
    return os.path.join(backup_dir, zips[-1]) if zips else None


def on_start(bot):
    """Сервис запущен: убрать отметки прежней копии в Telegram (решено 25.10.2026: копии только на сервере)."""
    try:
        for k in ("backup:sent_day", "backup:fails", "backup:retry_at", "backup:files_sent"):
            bot.s.drop(k)
        bot.s.run("DELETE FROM state WHERE key LIKE 'backup:part:%'")
    except Exception:  # noqa: BLE001
        pass


def daily_tick(bot, crm=None, log=print, now=None, backup_dir=None):
    """Хук сервиса (раз в минуту): раз в день — архив данных на сервере и удаление старых. Архив не записался —
    разработчику одно сообщение (повтор — завтра; причина — в журнале сервиса)."""
    backup_dir = backup_dir or BACKUP_DIR
    d = today().isoformat()
    if bot.s.get("backup:zip_day") == d:
        return None
    errors = []
    path = make_data_zip(d, backup_dir, log=lambda t: (errors.append(t), log(t)))
    if path:
        prune(backup_dir, d, log=log)
    bot.s.put("backup:zip_day", d)
    if not path and getattr(bot, "owner", None):
        why = next((e for e in reversed(errors) if "ошибка" in e or "не записался" in e), "") or "причина — в журнале сервиса"
        why = re.sub(r"^копия: (архив не записался — )?", "", why)
        bot.send(bot.owner, f"⚠️ Резервная копия данных за {d} на сервере не записалась: {_esc(why)}\n\n"
                            f"Прежние копии на месте (~/dumskaya/backups, {KEEP_DAYS} дней). Бот попробует снова завтра; "
                            "сейчас вручную — на сервере: python3 ~/dumskaya/deploy/backups.py --now")
    return "data" if path else False


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------- восстановление ----------
def service_active():
    try:
        return subprocess.run(["systemctl", "is-active", "--quiet", SERVICE], timeout=10,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def restore_data(zip_path, app=APP, log=print):
    """Вернуть базы, заявки и статистику из архива данных. Нынешние файлы перед заменой — в ~/dumskaya/restore-ВРЕМЯ/.
    lead.env возвращается, только если его сейчас нет (в прежних копиях из Telegram его нет вовсе)."""
    stamp = datetime.now(TZ).strftime("%Y-%m-%d-%H%M%S")
    keep = os.path.join(app, f"restore-{stamp}")
    paths = {arc: path for path, arc, _ in sources(app)}
    done = []
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/") and n != "ПРОЧТИ-МЕНЯ.txt"]
        for n in names:
            top = n.split("/", 1)[0]
            if top not in paths or ".." in n.split("/"):
                continue
            target = paths[top] if top == n else os.path.join(paths[top], n.split("/", 1)[1])
            if n == "lead.env" and os.path.exists(target):
                continue
            if os.path.exists(target):
                rel = os.path.relpath(target, app) if target.startswith(app) else os.path.basename(target)
                os.makedirs(os.path.dirname(os.path.join(keep, rel)), exist_ok=True)
                shutil.copy2(target, os.path.join(keep, rel))
            if top.endswith(".db"):
                for x in ("-wal", "-shm"):      # журнал старой базы к новой не применять
                    if os.path.exists(target + x):
                        os.makedirs(keep, exist_ok=True)
                        shutil.move(target + x, os.path.join(keep, os.path.basename(target) + x))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(n) as src, open(target + ".restore", "wb") as out:
                shutil.copyfileobj(src, out)
            os.replace(target + ".restore", target)
            if top.endswith(".db") or n == "lead.env":
                os.chmod(target, 0o600)
            done.append(n)
    log(f"возвращено: {len(done)} — {', '.join(sorted({d.split('/')[0] for d in done}))}")
    if os.path.isdir(keep):
        log(f"прежние файлы сохранены в {keep}")
    return done


def restore_files(zip_paths, crm, log=print):
    """Вернуть файлы проектов из архивов dumskaya-files-…zip: файл узнаётся по номеру в начале имени (00045-…);
    кладётся на своё место, если его там нет. Миниатюры, которых нет, сбрасываются (сделаются заново)."""
    back, have, unknown = 0, 0, 0
    for zp in zip_paths:
        with zipfile.ZipFile(zp) as zf:
            for n in zf.namelist():
                m = re.match(r"(\d+)-", os.path.basename(n))
                if not m:
                    continue
                f = crm.one("SELECT * FROM files WHERE id=?", int(m.group(1)))
                if not f or not f["path"]:
                    unknown += 1
                    continue
                target = os.path.join(crm.files_dir, f["path"])
                if os.path.exists(target):
                    have += 1
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(n) as src, open(target + ".restore", "wb") as out:
                    shutil.copyfileobj(src, out)
                os.replace(target + ".restore", target)
                back += 1
    for f in crm.q("SELECT id, thumb FROM files WHERE thumb IS NOT NULL"):
        if not os.path.exists(os.path.join(crm.files_dir, f["thumb"])):
            crm.run("UPDATE files SET thumb=NULL WHERE id=?", f["id"])
    log(f"файлы проектов: возвращено {back}, уже были {have}, нет в базе {unknown}")
    return back, have, unknown


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--now"]:
        p = make_data_zip()
        if p:
            prune(day=today())
        sys.exit(0 if p else 1)
    if args[:1] == ["--restore-data"] and len(args) == 2:
        if service_active():
            sys.exit(f"Сначала остановите сервис: sudo systemctl stop {SERVICE}")
        restore_data(args[1])
        print(f"Готово. Запустите сервис: sudo systemctl start {SERVICE}")
        sys.exit(0)
    if args[:1] == ["--restore-files"] and len(args) >= 2:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from crm import Crm
        restore_files(args[1:], Crm())
        sys.exit(0)
    print(__doc__)
