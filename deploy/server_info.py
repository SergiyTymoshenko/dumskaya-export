#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Техданные для разработчика — страница «Сервер и ИИ» (server_app.html, открывается из «Графиков», только разработчику):
  • сервер: нагрузка, память, диск, сколько работает сервер и наш сервис;
  • наши данные: базы, файлы проектов, резервные копии;
  • бот и кабинеты: кто подключён, проекты, заявки, сообщения;
  • языковые модели: сколько вызовов перевода (переписка, названия в кабинетах, заявки), токены, ошибки — за день,
    неделю и месяц, по моделям.
Учёт вызовов — таблица llm_usage в bot.db (по дням; translate.py сообщает о каждом вызове через translate.USAGE_HOOK).
Ключи сервисов сюда не попадают никогда: только «ключ есть» и какая модель. В тексте ошибки всё похожее на ключ
заменяется на «…». Сервер общий с EuroExchange: здесь только чтение — ничего не меняется.
Только стандартная библиотека Python 3."""
import json
import os
import platform
import re
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bratislava")
except Exception:  # noqa: BLE001  pragma: no cover
    TZ = timezone(timedelta(hours=1))

APP = os.path.expanduser("~/dumskaya")
SITE_DIR = os.environ.get("SITE_DIR", "/var/www/dumskaya/site")    # сайт на сервере (выкладка с Мака)
STARTED = time.time()                     # когда запущен сервис (этот процесс)
PURPOSES = [("chat", "Переписка"), ("names", "Названия в кабинетах"), ("lead", "Заявки с сайта"), ("other", "Другое")]
SERVICES = {"sub": "ChatGPT · подписка", "openai": "ChatGPT · платный API", "deepl": "DeepL", "claude": "Claude (Anthropic)"}
KEEP_DAYS = 400                           # учёт вызовов храним чуть больше года
SIZE_CACHE = 600                          # размер папок считаем не чаще раза в 10 минут (файлов может быть много)
SCHEMA = """CREATE TABLE IF NOT EXISTS llm_usage (
  day TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, purpose TEXT NOT NULL,
  calls INTEGER NOT NULL DEFAULT 0, errors INTEGER NOT NULL DEFAULT 0,
  tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0, chars INTEGER NOT NULL DEFAULT 0,
  ms INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(day, provider, model, purpose))"""
SECRETISH = re.compile(r"(?i)(bearer\s+|sk-|key[=:\s]+)?[A-Za-z0-9_\-:.]{24,}")


def today():
    return datetime.now(TZ).date()


def clean_error(text, n=200):
    """Текст ошибки для страницы: без всего, что похоже на ключ или токен, коротко."""
    t = SECRETISH.sub("…", str(text or ""))
    return re.sub(r"\s+", " ", t).strip()[:n]


class Usage:
    """Расход языковых моделей по дням: вызовы, ошибки, токены (у DeepL — знаки), суммарное время ответа."""

    def __init__(self, store):
        self.s = store
        self.s.run(SCHEMA)
        self._pruned = None

    def record(self, ev):
        day = today().isoformat()
        ok = bool(ev.get("ok"))
        self.s.run("""INSERT INTO llm_usage(day, provider, model, purpose, calls, errors, tokens_in, tokens_out, chars, ms)
                      VALUES(?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                      ON CONFLICT(day, provider, model, purpose) DO UPDATE SET calls=calls+1, errors=errors+excluded.errors,
                      tokens_in=tokens_in+excluded.tokens_in, tokens_out=tokens_out+excluded.tokens_out,
                      chars=chars+excluded.chars, ms=ms+excluded.ms""",
                   day, str(ev.get("provider") or "?")[:20], str(ev.get("model") or "?")[:80], str(ev.get("purpose") or "other")[:20],
                   0 if ok else 1, int(ev.get("tokens_in") or 0), int(ev.get("tokens_out") or 0), int(ev.get("chars") or 0),
                   int(ev.get("ms") or 0))
        if not ok:
            self.s.put("llm:last_error", json.dumps({"ts": int(time.time()), "provider": ev.get("provider"), "model": ev.get("model"),
                                                     "purpose": ev.get("purpose"), "error": clean_error(ev.get("error"))}, ensure_ascii=False))
        if self._pruned != day:                    # раз в день — убрать строки старше года
            self._pruned = day
            self.s.run("DELETE FROM llm_usage WHERE day < ?", (today() - timedelta(days=KEEP_DAYS)).isoformat())

    @staticmethod
    def _sum(rows):
        out = {"calls": 0, "errors": 0, "tokens_in": 0, "tokens_out": 0, "chars": 0, "ms": 0}
        for r in rows:
            for k in out:
                out[k] += int(r[k] or 0)
        out["avg_ms"] = round(out["ms"] / out["calls"]) if out["calls"] else 0
        return out

    def summary(self, day=None):
        d = day or today()
        start = (d - timedelta(days=29)).isoformat()
        rows = [dict(r) for r in self.s.all("SELECT * FROM llm_usage WHERE day >= ? AND day <= ? ORDER BY day", start, d.isoformat())]
        since = {"day": d.isoformat(), "week": (d - timedelta(days=6)).isoformat(), "month": start}
        periods = {k: self._sum([r for r in rows if r["day"] >= v]) for k, v in since.items()}
        models = {}
        for r in rows:
            m = models.setdefault((r["provider"], r["model"]), {"provider": r["provider"], "service": SERVICES.get(r["provider"], r["provider"]),
                                                               "model": r["model"], "rows": []})
            m["rows"].append(r)
        by_model = []
        for m in models.values():
            x = {k: v for k, v in m.items() if k != "rows"}
            x.update({k: self._sum([r for r in m["rows"] if r["day"] >= v]) for k, v in since.items()})
            by_model.append(x)
        by_model.sort(key=lambda x: -x["month"]["calls"])
        by_service = []                          # сколько перевела подписка, сколько платные модели (решено 25.10.2026)
        for key in ("sub", "openai", "claude", "deepl"):
            mine = [r for r in rows if r["provider"] == key]
            if mine:
                x = {"provider": key, "service": SERVICES[key]}
                x.update({k: self._sum([r for r in mine if r["day"] >= v]) for k, v in since.items()})
                by_service.append(x)
        by_purpose = []
        for key, name in PURPOSES:
            mine = [r for r in rows if r["purpose"] == key]
            if mine:
                x = {"purpose": key, "name": name}
                x.update({k: self._sum([r for r in mine if r["day"] >= v]) for k, v in since.items()})
                by_purpose.append(x)
        series = []
        for i in range(29, -1, -1):
            day_s = (d - timedelta(days=i)).isoformat()
            s = self._sum([r for r in rows if r["day"] == day_s])
            series.append({"day": day_s, "calls": s["calls"], "errors": s["errors"], "tokens": s["tokens_in"] + s["tokens_out"], "chars": s["chars"]})
        try:
            last = json.loads(self.s.get("llm:last_error") or "null")
        except ValueError:
            last = None
        total = self.s.one("SELECT MIN(day) AS since, SUM(calls) AS calls FROM llm_usage")
        return {"periods": periods, "by_model": by_model, "by_service": by_service, "by_purpose": by_purpose, "series": series, "last_error": last,
                "since": total["since"] if total else None, "all_calls": int((total["calls"] if total else 0) or 0)}


USAGE = None
_sizes, _sizes_at, _sizes_lock = {}, 0.0, threading.Lock()


def install(store):
    """Включить учёт: таблица в bot.db и функция для translate.py."""
    global USAGE
    USAGE = Usage(store)
    try:
        import translate
        translate.USAGE_HOOK = USAGE.record
    except ImportError:  # pragma: no cover
        pass
    return USAGE


def llm_config():
    """Что настроено для перевода — без ключей: сервисы по порядку (подписка ChatGPT → платный ChatGPT → Claude → DeepL),
    модель, адрес шлюза (только имя хоста), «ключ есть», пропускается ли сейчас после ошибки."""
    try:
        import translate
    except ImportError:  # pragma: no cover
        return {"provider": None, "chain": []}
    now = time.time()
    chain = []
    for p in translate.ORDER:
        x = {"provider": p, "service": SERVICES.get(p, p), "configured": translate.configured(p)}
        if p in ("sub", "openai"):
            base, key, model = translate.openai_cfg(p)
            host = re.sub(r"^https?://", "", base).split("/")[0].split("@")[-1]
            x.update({"model": model if x["configured"] else "", "via": "" if host == "api.openai.com" or not x["configured"] else host,
                      "key": bool(key)})
        elif p == "claude":
            x.update({"model": (os.environ.get("TRANSLATE_MODEL", "").strip() or translate.CLAUDE_DEFAULT_MODEL) if x["configured"] else "",
                      "key": x["configured"]})
        else:
            x.update({"model": "DeepL API" if x["configured"] else "", "key": x["configured"]})
        pause = translate.paused(p, now)
        if pause and x["configured"]:
            x["paused_until"], x["paused_why"] = int(pause[0]), pause[1]
        chain.append(x)
    active = [x for x in chain if x["configured"]]
    first = active[0] if active else {}
    return {"provider": first.get("provider"), "service": first.get("service", ""), "model": first.get("model", ""), "via": first.get("via", ""),
            "chain": chain, "keys": [{"service": x["service"], "present": x["key"]} for x in chain]}


def _meminfo():
    out = {}
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                k, _, v = line.partition(":")
                if k in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                    out[k] = int(v.split()[0]) * 1024
    except OSError:
        pass
    return out


def _proc_status():
    out = {}
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                k, _, v = line.partition(":")
                if k in ("VmRSS", "Threads"):
                    out[k] = int(v.split()[0]) * (1024 if k == "VmRSS" else 1)
    except OSError:
        pass
    return out


def server():
    """Сервер целиком (он общий с EuroExchange) и наш сервис."""
    try:
        load = [round(x, 2) for x in os.getloadavg()]
    except OSError:
        load = None
    m = _meminfo()
    try:
        with open("/proc/uptime", encoding="ascii") as f:
            up = int(float(f.read().split()[0]))
    except (OSError, ValueError):
        up = None
    root = APP if os.path.isdir(APP) else "/"
    du = shutil.disk_usage(root)
    ps = _proc_status()
    return {"load": load, "cpus": os.cpu_count() or 1, "uptime": up,
            "mem": {"total": m.get("MemTotal"), "available": m.get("MemAvailable"),
                    "used": (m["MemTotal"] - m["MemAvailable"]) if "MemTotal" in m and "MemAvailable" in m else None},
            "swap": {"total": m.get("SwapTotal"), "used": (m["SwapTotal"] - m["SwapFree"]) if "SwapTotal" in m and "SwapFree" in m else None},
            "disk": {"total": du.total, "used": du.used, "free": du.free, "min_free": 2 * 1024 ** 3},
            "service": {"started": int(STARTED), "uptime": int(time.time() - STARTED), "rss": ps.get("VmRSS"),
                        "threads": ps.get("Threads") or threading.active_count(), "python": platform.python_version()}}


def _file_size(path):
    total = 0
    for p in (path, path + "-wal"):
        try:
            total += os.path.getsize(p)
        except OSError:
            pass
    return total


def _dir_size(path):
    total = n = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
                n += 1
            except OSError:
                pass
    return total, n


def _site_size(path):
    """Сайт на сервере: всего (размер, файлов), страниц, фото (папка img)."""
    out = {"size": 0, "count": 0, "pages": 0, "img_size": 0, "img_count": 0}
    for root, _dirs, files in os.walk(path):
        top = os.path.relpath(root, path).split(os.sep)[0]
        for f in files:
            try:
                n = os.path.getsize(os.path.join(root, f))
            except OSError:
                continue
            out["size"] += n
            out["count"] += 1
            out["pages"] += f.endswith(".html") and f != "404.html"
            if top == "img":
                out["img_size"] += n
                out["img_count"] += 1
    return out


def _tg_only(db_path):
    """Файлы проектов, которые лежат только в Telegram (больше 20 МБ — бот их не скачивает): (сколько, размер)."""
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
        try:
            r = con.execute("SELECT COUNT(*), COALESCE(SUM(size), 0) FROM files WHERE (path IS NULL OR path = '') "
                            "AND tg_file_id LIKE '%:%'").fetchone()
        finally:
            con.close()
        return int(r[0] or 0), int(r[1] or 0)
    except sqlite3.Error:
        return 0, 0


def data(store=None):
    """Наши данные на диске: сайт, файлы проектов (и корзина), базы, статистика сайта, резервные копии — и всего."""
    global _sizes, _sizes_at
    import backups
    import crm
    with _sizes_lock:
        if time.time() - _sizes_at > SIZE_CACHE or not _sizes:
            files = _dir_size(crm.FILES_DIR) if os.path.isdir(crm.FILES_DIR) else (0, 0)
            trash_dir = os.path.join(os.path.dirname(os.path.abspath(crm.FILES_DIR)), "trash")
            stats_dir = os.path.join(APP, "stats")
            stats = (_dir_size(stats_dir)[0] if os.path.isdir(stats_dir) else 0) + sum(
                _file_size(os.environ.get(k, os.path.join(APP, n))) for k, n in (("HITS_FILE", "hits.jsonl"), ("TIMES_FILE", "times.jsonl")))
            _sizes = {"files": files, "trash": _dir_size(trash_dir)[0] if os.path.isdir(trash_dir) else 0, "stats": stats,
                      "site": _site_size(SITE_DIR) if os.path.isdir(SITE_DIR) else None, "tg_only": _tg_only(crm.CRM_DB)}
            _sizes_at = time.time()
        sizes = dict(_sizes)
    bdir = backups.BACKUP_DIR
    zips = sorted(f for f in os.listdir(bdir) if backups.NAME_RE.match(f)) if os.path.isdir(bdir) else []
    data_zips = [f for f in zips if f.startswith("dumskaya-data-")]
    last = data_zips[-1] if data_zips else None
    bsize = sum(os.path.getsize(os.path.join(bdir, f)) for f in zips)
    dbs = {"crm_db": _file_size(crm.CRM_DB), "bot_db": _file_size(crm.BOT_DB),
           "other_db": _file_size(os.environ.get("FX_DB", os.path.join(APP, "fx.db"))) + _file_size(os.environ.get("LEADS_FILE", os.path.join(APP, "leads.jsonl")))}
    site = sizes["site"]
    total = sum(dbs.values()) + sizes["files"][0] + sizes["trash"] + sizes["stats"] + bsize + (site["size"] if site else 0)
    return dict(dbs, **{"files": {"size": sizes["files"][0], "count": sizes["files"][1], "trash": sizes["trash"],
                                  "tg_only": sizes["tg_only"][0], "tg_only_size": sizes["tg_only"][1]},
                        "site": site, "stats": sizes["stats"], "total": total,
                        "backups": {"count": len(data_zips), "size": bsize,
                                    "last": backups.NAME_RE.match(last).group(1) if last else None,
                                    "last_size": os.path.getsize(os.path.join(bdir, last)) if last else 0, "keep_days": backups.KEEP_DAYS},
                        "counted": int(_sizes_at)})


def bot_stats(bot):
    """Кто подключён к боту, проекты, заявки и сообщения за день, неделю и месяц."""
    out = {"users": {}, "pending": 0}
    for r in bot.s.all("SELECT role, status, COUNT(*) AS n FROM users GROUP BY role, status"):
        if r["status"] == "active":
            out["users"][r["role"] or "?"] = r["n"]
        elif r["status"] == "pending":
            out["pending"] += r["n"]
    crm = getattr(bot, "crm", None)
    if not crm:
        return out
    now = datetime.now(timezone.utc)
    since = {k: (now - timedelta(days=d)).isoformat(timespec="seconds") for k, d in (("day", 1), ("week", 7), ("month", 30))}
    out["projects"] = {r["status"]: r["n"] for r in crm.q("SELECT status, COUNT(*) AS n FROM projects GROUP BY status")}
    out["leads"] = {k: crm.one("SELECT COUNT(*) AS n FROM leads WHERE ts >= ? AND deleted IS NULL", v)["n"] for k, v in since.items()}
    out["messages"] = {k: crm.one("SELECT COUNT(*) AS n FROM messages WHERE created >= ? AND deleted IS NULL", v)["n"] for k, v in since.items()}
    out["cabinets"] = {
        "clients": crm.one("SELECT COUNT(*) AS n FROM clients WHERE tg_id IS NOT NULL")["n"],
        "contractors": crm.one("SELECT COUNT(*) AS n FROM contractors WHERE tg_id IS NOT NULL AND observer IS NULL")["n"],
        "crew": crm.one("SELECT COUNT(*) AS n FROM crew WHERE tg_id IS NOT NULL AND removed IS NULL")["n"],
        "assistants": crm.one("SELECT COUNT(*) AS n FROM assistants WHERE tg_id IS NOT NULL AND removed IS NULL")["n"]}
    return out


def snapshot(bot):
    """Всё для страницы «Сервер и ИИ» одним ответом."""
    out = {"ts": int(time.time()), "server": server(), "llm_config": llm_config(), "llm": USAGE.summary() if USAGE else None}
    try:
        out["data"] = data(getattr(bot, "s", None))
    except Exception as e:  # noqa: BLE001
        out["data"] = {"error": clean_error(f"{type(e).__name__}: {e}")}
    try:
        out["bot"] = bot_stats(bot) if bot else None
    except Exception as e:  # noqa: BLE001
        out["bot"] = {"error": clean_error(f"{type(e).__name__}: {e}")}
    return out
