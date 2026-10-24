#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Резервные копии данных студии — на сервере и в Telegram (решено 24.10.2026: на Мак больше не копируем).

Каждую ночь (в первые минуты после полуночи по Братиславе — делает сервис заявок):
  • на сервере — архив ~/dumskaya/backups/dumskaya-data-ГГГГ-ММ-ДД.zip: база «Студии» (crm.db), база бота (bot.db),
    курсы валют (fx.db), заявки (leads.jsonl), статистика сайта (stats/, hits.jsonl, times.jsonl) и настройки сервиса
    (lead.env). Хранятся 7 последних дней, старые удаляются сами;
  • в Telegram разработчику, без звука, — тот же архив, но без lead.env и соли статистики (stats/secret): пароли и ключи
    в Telegram не уходят (при восстановлении их снова вписывает мастер настройки: с Мака npm run leads);
  • в Telegram — новые файлы проектов («Студия», кабинеты, переписка) архивами dumskaya-files-…zip до 45 МБ, каждый файл
    один раз. Файлы, которые лежат только в Telegram (больше 20 МБ), — пересылкой. Больше 50 МБ Telegram от бота
    не принимает — такие есть только на сервере (и в копиях Hetzner), их список — в подписи к архиву.
Файлы проектов на сервере отдельно не копируются: они лежат в ~/dumskaya/crm/files, удалённые — 30 дней в корзине,
а весь сервер каждый день копирует Hetzner (7 копий).

   python3 backups.py --now                       — архив данных сейчас (например, перед рискованной правкой)
   python3 backups.py --restore-data АРХИВ.zip     — вернуть базы и заявки из архива (сервис сначала остановить)
   python3 backups.py --restore-files А.zip Б.zip  — вернуть файлы проектов из архивов dumskaya-files-…zip
Подробно — README, раздел «Резервные копии». Только стандартная библиотека Python 3."""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
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
PART_MAX = 45 * 2**20                   # архив файлов для Telegram — до 45 МБ (бот может отправить до 50 МБ)
TG_MAX = 50 * 2**20
RETRY = 3600                            # не отправилось в Telegram — следующая попытка через час
WARN_AFTER = 3                          # после трёх неудач подряд — сообщение разработчику
FORWARDS_PER_TICK = 5
MIN_FREE = 2 * 1024 ** 3                # сервер общий: архив файлов не собирать, если свободно меньше 2 ГБ
SECRET = {"lead.env", "stats/secret"}   # в Telegram не отправляются
NAME_RE = re.compile(r"^(?:dumskaya-data|crm|bot)-(\d{4}-\d{2}-\d{2})\.(?:zip|db)$")
SERVICE = "dumskaya-lead"

README = """Резервная копия данных студии DUMSKAYA DESIGN за {day}.

crm.db       — учёт «Студии»: проекты, оплаты, заказчики, подрядчики, кабинеты, переписка, список файлов проектов
bot.db       — бот: люди и роли, настройки, состояние
fx.db        — курсы валют центробанков
leads.jsonl  — заявки с сайта
stats/, hits.jsonl, times.jsonl — статистика сайта
{secret}
Сами файлы проектов — в архивах dumskaya-files-….zip (приходят в тот же чат, каждый файл один раз).

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
        (j("lead.env"), "lead.env", "file"),
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
    os.makedirs(backup_dir, exist_ok=True)
    try:
        os.chmod(backup_dir, 0o700)
    except OSError:
        pass
    tmp = os.path.join(backup_dir, f".tmp-{day}")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
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
            secret = "lead.env     — настройки сервиса (токен бота, ключи) — только в копии на сервере" if "lead.env" in have else ""
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


def public_copy(src, dst):
    """Копия архива для Telegram — без паролей и ключей (SECRET)."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            if info.filename not in SECRET:
                zout.writestr(info, zin.read(info.filename))
    return dst


# ---------- файлы проектов ----------
def _safe(s, n=80):
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", str(s or "")).strip(" .")
    return re.sub(r"\s+", " ", s)[:n].strip() or "без названия"


def file_label(crm, f, projects=None):
    """Понятное имя файла в архиве: «12 Квартира в Братиславе/Визуализации/00045-гостиная.jpg»."""
    try:
        from crm import EXTRA_CATS, FILE_CATS
        cats = dict(FILE_CATS + EXTRA_CATS)
    except ImportError:  # pragma: no cover
        cats = {}
    p = (projects or {}).get(f["project_id"])
    if p is None:
        p = crm.one("SELECT id, number, title FROM projects WHERE id=?", f["project_id"]) or {}
    proj = _safe(f"{p.get('number') or p.get('id') or f['project_id']} {p.get('title') or ''}")
    name = _safe(f["name"] or "файл", 120)
    ext = os.path.splitext(f.get("path") or "")[1]
    if ext and not name.lower().endswith(ext.lower()):
        name += ext
    return f"{proj}/{_safe(cats.get(f['category'], f['category']), 40)}/{int(f['id']):05d}-{name}"


def _sent(store):
    try:
        return set(json.loads(store.get("backup:files_sent") or "[]"))
    except ValueError:
        return set()


def _mark(store, ids):
    done = _sent(store) | {int(i) for i in ids}
    store.put("backup:files_sent", json.dumps(sorted(done)))


def pending_files(crm, store, files_dir=None):
    """Файлы проектов, которых ещё нет в Telegram-копии: (на сервере, только в Telegram, слишком большие)."""
    files_dir = files_dir or crm.files_dir
    done = _sent(store)
    local, tg_only, too_big = [], [], []
    for r in crm.q("SELECT * FROM files ORDER BY id"):
        f = dict(r)
        if f["id"] in done:
            continue
        path = os.path.join(files_dir, f["path"]) if f.get("path") else None
        if path and os.path.exists(path):
            size = os.path.getsize(path)
            if size > TG_MAX:
                too_big.append((f, size))
            else:
                local.append((f, path, size))
        elif ":" in (f.get("tg_file_id") or ""):
            tg_only.append(f)
    return local, tg_only, too_big


def pack_part(crm, items, dst, limit=None):
    """Следующий архив файлов: по порядку, пока помещается в limit (по умолчанию PART_MAX)."""
    limit = limit or PART_MAX
    projects = {r["id"]: dict(r) for r in crm.q("SELECT id, number, title FROM projects")}
    taken, total = [], 0
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for f, path, size in items:
            if taken and total + size > limit:
                break
            zf.write(path, file_label(crm, f, projects))
            taken.append(f["id"])
            total += size
    return taken, total


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------- в Telegram ----------
def _fail(bot, why, now, log):
    s = bot.s
    n = int(s.get("backup:fails") or 0) + 1
    s.put("backup:fails", str(n))
    s.put("backup:retry_at", str(now + RETRY))
    log(f"копия в Telegram: не отправилось ({n}) — {why}")
    if n == WARN_AFTER and bot.owner:
        bot.send(bot.owner, f"⚠️ Копия в Telegram не отправляется ({n} попытки подряд): {why}\n\n"
                            "На сервере копии делаются как обычно. Бот попробует снова через час.")


def telegram_tick(bot, crm=None, log=print, now=None, backup_dir=None):
    """Раз в минуту: свежий архив данных — разработчику; затем новые файлы проектов. За один раз — одна отправка
    (или несколько пересылок), чтобы не задерживать другие дела сервиса."""
    if not getattr(bot, "owner", None):
        return None
    now = now if now is not None else time.time()
    s = bot.s
    if float(s.get("backup:retry_at") or 0) > now:
        return None
    backup_dir = backup_dir or BACKUP_DIR
    latest = latest_data_zip(backup_dir)
    if latest:
        day = NAME_RE.match(os.path.basename(latest)).group(1)
        if s.get("backup:sent_day") != day:
            tmp = os.path.join(backup_dir, f".telegram-{os.path.basename(latest)}")
            try:
                public_copy(latest, tmp)
                size = os.path.getsize(tmp)
                if size > TG_MAX:          # не примет никогда — сказать и не пытаться, чтобы не держать очередь
                    bot.send(bot.owner, f"💾 Копия данных за {day} — {human(size)}, больше 50 МБ: Telegram от бота такой "
                                        f"не примет. Она есть на сервере (~/dumskaya/backups, {KEEP_DAYS} дней).",
                             disable_notification=True)
                    ok, why = True, ""
                else:
                    d = datetime.fromisoformat(day).strftime("%d.%m.%Y")
                    cap = (f"💾 <b>Копия данных студии · {d}</b>\n"
                           f"«Студия», бот, заявки, статистика сайта — {human(size)}. Без паролей и ключей.\n"
                           f"На сервере — копии за {KEEP_DAYS} дней.")
                    ok, why, _ = bot.send_file_r(bot.owner, {"name": os.path.basename(latest), "mime": "application/zip"},
                                                 tmp, caption=cap, silent=True)
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            if not ok:
                _fail(bot, why, now, log)
                return False
            s.put("backup:sent_day", day)
            s.drop("backup:fails")
            log(f"копия в Telegram: данные за {day}")
            return "data"
    if crm is None:
        return None
    local, tg_only, too_big = pending_files(crm, s)
    if too_big:                     # больше 50 МБ: в Telegram не уйдут — сказать один раз и больше не пытаться
        lines = "\n".join(f"• {_esc(file_label(crm, f))} — {human(size)}" for f, size in too_big[:15])
        bot.send(bot.owner, "📁 Эти файлы проектов больше 50 МБ — Telegram от бота их не принимает. Они есть на сервере "
                            f"и в копиях Hetzner:\n{lines}", disable_notification=True)
        _mark(s, [f["id"] for f, _ in too_big])
        return "too_big"
    if tg_only:                     # хранятся только в Telegram — переслать ссылкой, без скачивания
        done = []
        for f in tg_only[:FORWARDS_PER_TICK]:
            ok, why, _ = bot.send_file_r(bot.owner, f, None, caption=f"📁 {_esc(file_label(crm, f))}", silent=True)
            if not ok:
                _fail(bot, why, now, log)
                break
            done.append(f["id"])
        if done:
            _mark(s, done)
            s.drop("backup:fails")
            log(f"копия в Telegram: переслано файлов {len(done)}")
        return "forwarded" if done else False
    small = [x for x in local if x[2] <= PART_MAX]
    if small and shutil.disk_usage(backup_dir if os.path.isdir(backup_dir) else APP).free < MIN_FREE + PART_MAX:
        _fail(bot, "на сервере мало свободного места — архив файлов не собирается (сервер общий)", now, log)
        return False
    if small:                       # небольшие — архивом до PART_MAX
        day = today().isoformat()
        n = int(s.get(f"backup:part:{day}") or 0) + 1
        name = f"dumskaya-files-{day}-{n:02d}.zip"
        tmp = os.path.join(backup_dir, "." + name)
        os.makedirs(backup_dir, exist_ok=True)
        try:
            ids, total = pack_part(crm, small, tmp)
            left = len(local) - len(ids)
            cap = (f"📁 <b>Файлы проектов, новые: {len(ids)}</b> — {human(total)}"
                   + (f"\nЕщё {left} — следующими сообщениями" if left else ""))
            ok, why, _ = bot.send_file_r(bot.owner, {"name": name, "mime": "application/zip"}, tmp, caption=cap, silent=True)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        if not ok:
            _fail(bot, why, now, log)
            return False
        _mark(s, ids)
        s.put(f"backup:part:{day}", str(n))
        s.drop("backup:fails")
        log(f"копия в Telegram: {name}, файлов {len(ids)}")
        return "files"
    if local:                       # крупный (до 50 МБ) — сам по себе, без архива, документом
        f, path, size = local[0]
        ok, why, _ = bot.send_file_r(bot.owner, dict(f, mime="application/octet-stream"), path,
                                     caption=f"📁 {_esc(file_label(crm, f))}", silent=True)
        if not ok:
            _fail(bot, why, now, log)
            return False
        _mark(s, [f["id"]])
        s.drop("backup:fails")
        log(f"копия в Telegram: крупный файл {f['id']} ({human(size)})")
        return "file"
    return None


def daily_tick(bot, crm=None, log=print, now=None, backup_dir=None):
    """Хук сервиса (раз в минуту): раз в день — архив данных на сервере и удаление старых; потом — копия в Telegram."""
    backup_dir = backup_dir or BACKUP_DIR
    d = today().isoformat()
    if bot.s.get("backup:zip_day") != d:
        if make_data_zip(d, backup_dir, log=log):
            prune(backup_dir, d, log=log)
        bot.s.put("backup:zip_day", d)          # не получилось — повторим завтра (ошибка уже в журнале)
    return telegram_tick(bot, crm, log=log, now=now, backup_dir=backup_dir)


# ---------- восстановление ----------
def service_active():
    try:
        return subprocess.run(["systemctl", "is-active", "--quiet", SERVICE], timeout=10,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def restore_data(zip_path, app=APP, log=print):
    """Вернуть базы, заявки и статистику из архива данных. Нынешние файлы перед заменой — в ~/dumskaya/restore-ВРЕМЯ/.
    lead.env возвращается, только если его сейчас нет (в копии из Telegram его нет вовсе)."""
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
