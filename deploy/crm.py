#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Учёт проектов студии — для разработчика и дизайнера (кнопка «Студия» в боте, страница crm_app.html).

Проект: номер по внутреннему учёту, название, заказчик, город, площадь, тариф, сумма договора (в евро), статус.
Операции проекта (вся история):
  • оплата заказчика — сумма, валюта, дата, способ;
  • бонус от поставщика («откат») — за мебель, шторы, свет и т. п.;
  • перепродажа — студия посредник: закупка и продажа, доход — разница.
Суммы в любой валюте; в евро — по курсу центробанка на дату операции (fx.py) или по курсу, введённому вручную.
Баланс проекта: договор − оплаты заказчика. Доход студии: оплаты + бонусы + наценка на перепродаже.
Ещё: заказчики (телефон, почта, как удобнее связаться), подрядчики по видам работ, файлы проекта
(до, после, визуализации, документация) — в ~/dumskaya/crm/files, ссылки на них подписаны и действуют 12 часов.

Данные — ~/dumskaya/crm.db (SQLite). Каждый день — копия базы студии и базы бота в ~/dumskaya/backups (30 дней);
при выкладке с Мака копии и файлы скачиваются на Мак. Только стандартная библиотека Python 3.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bratislava")
except Exception:  # noqa: BLE001
    TZ = timezone(timedelta(hours=1))

APP = os.path.expanduser("~/dumskaya")
CRM_DB = os.environ.get("CRM_DB", os.path.join(APP, "crm.db"))
FILES_DIR = os.environ.get("CRM_FILES", os.path.join(APP, "crm", "files"))
BACKUP_DIR = os.environ.get("BACKUP_DIR", os.path.join(APP, "backups"))
BACKUP_KEEP = 30
FILE_MAX = 60 * 1024 * 1024            # один файл — до 60 МБ
MIN_FREE = 2 * 1024 ** 3               # оставлять на диске сервера хотя бы 2 ГБ (сервер общий)
LINK_HOURS = 12

STATUSES = [("active", "В работе"), ("paused", "На паузе"), ("done", "Завершён"), ("cancelled", "Отменён")]
KINDS = {"payment": "Оплата заказчика", "commission": "Бонус от поставщика", "resale": "Перепродажа"}
FILE_CATS = [("before", "До"), ("after", "После"), ("visual", "Визуализации"), ("docs", "Документация")]
CONTACT_PREFS = ["Звонок", "WhatsApp", "Telegram", "Viber", "E-mail", "SMS"]
PAY_METHODS = ["Банковский перевод", "Наличные", "Карта", "Другое"]
DEFAULTS = {
    "tariffs": ["Экспресс", "Мебель", "Базовый", "Премиум", "Премиум+", "Авторское сопровождение", "Индивидуальный"],
    "trades": ["Прораб", "Мебельщик", "Шторница", "Кондиционерщик", "Двери", "Окна", "Электрик", "Сантехник",
               "Плиточник", "Маляр", "Полы", "Свет", "Камень и столешницы", "Стекло и зеркала", "Другое"],
    "commission_cats": ["Мебель", "Шторы", "Свет", "Кухня", "Сантехника", "Двери", "Окна", "Отделочные материалы",
                        "Техника", "Декор", "Другое"],
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT, email TEXT, messenger TEXT,
  contact_pref TEXT, city TEXT, note TEXT, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, title TEXT NOT NULL, client_id INTEGER, city TEXT, country TEXT,
  address TEXT, area REAL, tariff TEXT, total_eur REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'active',
  started TEXT, finished TEXT, note TEXT, created_by TEXT, created TEXT, updated TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS projects_number ON projects(number) WHERE number IS NOT NULL AND number != '';
CREATE TABLE IF NOT EXISTS ops (            -- операции проекта; у перепродажи amount — продажа, buy — закупка
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, kind TEXT NOT NULL, day TEXT NOT NULL,
  title TEXT, category TEXT, method TEXT, counterparty TEXT,
  amount REAL NOT NULL, currency TEXT NOT NULL, rate REAL NOT NULL, rate_src TEXT, amount_eur REAL NOT NULL,
  buy REAL, buy_currency TEXT, buy_rate REAL, buy_rate_src TEXT, buy_eur REAL,
  note TEXT, created_by TEXT, created TEXT, updated TEXT);
CREATE INDEX IF NOT EXISTS ops_project ON ops(project_id);
CREATE INDEX IF NOT EXISTS ops_day ON ops(day);
CREATE TABLE IF NOT EXISTS contractors (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, trade TEXT, company TEXT, phone TEXT, email TEXT,
  contact_pref TEXT, city TEXT, note TEXT, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS project_contractors (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, contractor_id INTEGER NOT NULL, trade TEXT,
  note TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, category TEXT NOT NULL, name TEXT, path TEXT,
  thumb TEXT, mime TEXT, size INTEGER, tg_file_id TEXT, note TEXT, created_by TEXT, created TEXT);
CREATE INDEX IF NOT EXISTS files_project ON files(project_id);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, who TEXT, action TEXT, entity TEXT, entity_id INTEGER, details TEXT);
"""


class CrmError(Exception):
    """Ошибка, которую можно показать человеку как есть."""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today():
    return datetime.now(TZ).date()


def _text(v, n=500):
    v = str(v if v is not None else "").strip()
    return v[:n]


def _money(v, field="Сумма", allow_zero=False):
    s = str(v if v is not None else "").replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        x = round(float(s), 2)
    except ValueError:
        raise CrmError(f"{field}: введите число") from None
    if x < 0 or (x == 0 and not allow_zero):
        raise CrmError(f"{field}: должна быть больше нуля")
    if x > 1e9:
        raise CrmError(f"{field}: слишком большое число")
    return x


def _day(v, field="Дата", required=True):
    v = _text(v, 10)
    if not v and not required:
        return None
    try:
        return date.fromisoformat(v).isoformat()
    except ValueError:
        raise CrmError(f"{field}: укажите дату") from None


def _row(r):
    return dict(r) if r is not None else None


class Crm:
    def __init__(self, path=CRM_DB, rates=None, files_dir=FILES_DIR, backup_dir=BACKUP_DIR, extra_backups=()):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path, self.files_dir, self.backup_dir = path, files_dir, backup_dir
        self.extra_backups = list(extra_backups)       # другие базы SQLite для ежедневной копии (база бота)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.rates = rates
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.executescript(SCHEMA)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        self.secret = self.setting("link_secret") or self._new_secret()

    # ---------- база ----------
    def q(self, sql, *args):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def one(self, sql, *args):
        with self.lock:
            return _row(self.db.execute(sql, args).fetchone())

    def run(self, sql, *args):
        with self.lock:
            return self.db.execute(sql, args).lastrowid

    def setting(self, key, value=None):
        if value is None:
            r = self.one("SELECT value FROM settings WHERE key=?", key)
            return r["value"] if r else None
        self.run("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", key, value)
        return value

    def _new_secret(self):
        return self.setting("link_secret", secrets.token_hex(24))

    def lists(self):
        """Справочники: тарифы, виды работ, категории бонусов (меняются в настройках) и постоянные списки."""
        out = {}
        for k, v in DEFAULTS.items():
            try:
                out[k] = json.loads(self.setting(k) or "null") or v
            except ValueError:
                out[k] = v
        try:
            from fx import CURRENCIES
        except ImportError:  # pragma: no cover
            CURRENCIES = [("EUR", "€", "евро")]
        out.update(statuses=STATUSES, kinds=KINDS, file_cats=FILE_CATS, contact_prefs=CONTACT_PREFS, pay_methods=PAY_METHODS,
                   currencies=CURRENCIES)
        return out

    def save_lists(self, data, who):
        for k in DEFAULTS:
            if k in data:
                items = [_text(x, 60) for x in (data[k] or []) if _text(x, 60)]
                if not items:
                    raise CrmError("Список не может быть пустым")
                self.setting(k, json.dumps(list(dict.fromkeys(items)), ensure_ascii=False))
        self.audit(who, "edit", "settings", 0, data)
        return self.lists()

    def audit(self, who, action, entity, entity_id, details=None):
        self.run("INSERT INTO audit(ts, who, action, entity, entity_id, details) VALUES(?, ?, ?, ?, ?, ?)",
                 now(), who, action, entity, entity_id, json.dumps(details or {}, ensure_ascii=False, default=str)[:4000])

    # ---------- курсы ----------
    def _convert(self, amount, currency, day, manual_rate=None):
        """(курс к евро, откуда курс, сумма в евро). Курс — сколько единиц валюты в одном евро."""
        currency = (currency or "EUR").upper()
        if currency == "EUR":
            return 1.0, "", amount
        if manual_rate not in (None, "", 0, "0"):
            rate = _money(manual_rate, "Курс")
            return rate, "вручную", round(amount / rate, 2)
        if not self.rates:
            raise CrmError("Курсы валют недоступны — укажите курс вручную")
        try:
            rate, used, src = self.rates.rate(currency, day)
        except Exception as e:  # noqa: BLE001
            raise CrmError(f"Не удалось получить курс {currency} ({e}) — укажите курс вручную") from None
        return rate, f"{src} {used}".strip(), round(amount / rate, 2)

    def rate(self, currency, day):
        rate, src, _ = self._convert(1.0, currency, _day(day))
        return {"currency": currency, "rate": rate, "src": src}

    # ---------- проекты ----------
    def project_rows(self):
        """Все проекты с итогами: оплачено, доп. доход, остаток к оплате."""
        rows = self.q("""
            SELECT p.*, c.name AS client_name, c.phone AS client_phone,
              COALESCE((SELECT SUM(amount_eur) FROM ops o WHERE o.project_id=p.id AND o.kind='payment'), 0) AS paid,
              COALESCE((SELECT SUM(amount_eur) FROM ops o WHERE o.project_id=p.id AND o.kind='commission'), 0) AS bonus,
              COALESCE((SELECT SUM(amount_eur - buy_eur) FROM ops o WHERE o.project_id=p.id AND o.kind='resale'), 0) AS margin,
              (SELECT MAX(day) FROM ops o WHERE o.project_id=p.id) AS last_op,
              (SELECT COUNT(*) FROM files f WHERE f.project_id=p.id) AS files
            FROM projects p LEFT JOIN clients c ON c.id=p.client_id ORDER BY p.updated DESC""")
        for r in rows:
            for k in ("paid", "bonus", "margin"):
                r[k] = round(r[k], 2)
            r["extra"] = round(r["bonus"] + r["margin"], 2)
            r["balance"] = round((r["total_eur"] or 0) - r["paid"], 2)
            r["income"] = round(r["paid"] + r["extra"], 2)
        return rows

    def project(self, pid):
        p = next((r for r in self.project_rows() if r["id"] == int(pid)), None)
        if not p:
            raise CrmError("Проект не найден")
        ops = self.q("SELECT * FROM ops WHERE project_id=? ORDER BY day DESC, id DESC", p["id"])
        for o in ops:
            o["income"] = round(o["amount_eur"] - (o["buy_eur"] or 0) if o["kind"] == "resale" else o["amount_eur"], 2)
        links = self.q("""SELECT l.id AS link_id, l.trade AS link_trade, l.note AS link_note, c.*
                          FROM project_contractors l JOIN contractors c ON c.id=l.contractor_id
                          WHERE l.project_id=? ORDER BY l.id""", p["id"])
        files = [self.file_view(f) for f in self.q("SELECT * FROM files WHERE project_id=? ORDER BY id DESC", p["id"])]
        client = self.one("SELECT * FROM clients WHERE id=?", p["client_id"]) if p["client_id"] else None
        history = self.q("SELECT ts, who, action, entity, entity_id FROM audit WHERE (entity='project' AND entity_id=?) OR "
                         "(entity IN ('op', 'file', 'link') AND (details LIKE ? OR details LIKE ?)) ORDER BY id DESC LIMIT 50",
                         p["id"], f'%"project_id": {p["id"]},%', f'%"project_id": {p["id"]}}}%')
        return {"project": p, "ops": ops, "contractors": links, "files": files, "client": client, "history": history}

    def save_project(self, d, who):
        pid = int(d.get("id") or 0)
        title = _text(d.get("title"), 200)
        if not title:
            raise CrmError("Укажите название проекта")
        number = _text(d.get("number"), 40)
        if number and self.one("SELECT id FROM projects WHERE number=? AND id!=?", number, pid):
            raise CrmError(f"Номер {number} уже есть у другого проекта")
        status = d.get("status") or "active"
        if status not in dict(STATUSES):
            raise CrmError("Неизвестный статус")
        client_id = int(d.get("client_id") or 0) or None
        if client_id and not self.one("SELECT id FROM clients WHERE id=?", client_id):
            raise CrmError("Заказчик не найден")
        area = _text(d.get("area"), 20)
        fields = dict(number=number or None, title=title, client_id=client_id, city=_text(d.get("city"), 80),
                      country=_text(d.get("country"), 80), address=_text(d.get("address"), 200),
                      area=_money(area, "Площадь") if area else None, tariff=_text(d.get("tariff"), 60),
                      total_eur=_money(d.get("total_eur") or 0, "Сумма договора", allow_zero=True), status=status,
                      started=_day(d.get("started"), "Начало", False), finished=_day(d.get("finished"), "Окончание", False),
                      note=_text(d.get("note"), 3000))
        if pid:
            if not self.one("SELECT id FROM projects WHERE id=?", pid):
                raise CrmError("Проект не найден")
            sets = ", ".join(f"{k}=?" for k in fields)
            self.run(f"UPDATE projects SET {sets}, updated=? WHERE id=?", *fields.values(), now(), pid)
            self.audit(who, "edit", "project", pid, fields)
        else:
            cols = ", ".join(fields)
            pid = self.run(f"INSERT INTO projects({cols}, created_by, created, updated) VALUES({', '.join('?' * len(fields))}, ?, ?, ?)",
                           *fields.values(), who, now(), now())
            self.audit(who, "add", "project", pid, fields)
        return self.project(pid)

    def touch(self, pid):
        self.run("UPDATE projects SET updated=? WHERE id=?", now(), pid)

    # ---------- операции ----------
    def save_op(self, d, who):
        oid = int(d.get("id") or 0)
        pid = int(d.get("project_id") or 0)
        if not self.one("SELECT id FROM projects WHERE id=?", pid):
            raise CrmError("Проект не найден")
        kind = d.get("kind")
        if kind not in KINDS:
            raise CrmError("Неизвестный вид операции")
        day = _day(d.get("day"))
        cur = (d.get("currency") or "EUR").upper()
        amount = _money(d.get("amount"), "Цена продажи" if kind == "resale" else "Сумма")
        rate, src, eur = self._convert(amount, cur, day, d.get("rate") if d.get("manual_rate") else None)
        f = dict(project_id=pid, kind=kind, day=day, title=_text(d.get("title"), 200), category=_text(d.get("category"), 60),
                 method=_text(d.get("method"), 60), counterparty=_text(d.get("counterparty"), 120),
                 amount=amount, currency=cur, rate=rate, rate_src=src, amount_eur=eur,
                 buy=None, buy_currency=None, buy_rate=None, buy_rate_src=None, buy_eur=None, note=_text(d.get("note"), 2000))
        if kind == "resale":
            if not f["title"]:
                raise CrmError("Укажите, что перепродано")
            bcur = (d.get("buy_currency") or cur).upper()
            buy = _money(d.get("buy"), "Цена закупки")
            brate, bsrc, beur = self._convert(buy, bcur, day, d.get("buy_rate") if d.get("manual_buy_rate") else None)
            f.update(buy=buy, buy_currency=bcur, buy_rate=brate, buy_rate_src=bsrc, buy_eur=beur)
        if oid:
            if not self.one("SELECT id FROM ops WHERE id=? AND project_id=?", oid, pid):
                raise CrmError("Операция не найдена")
            sets = ", ".join(f"{k}=?" for k in f)
            self.run(f"UPDATE ops SET {sets}, updated=? WHERE id=?", *f.values(), now(), oid)
            self.audit(who, "edit", "op", oid, f)
        else:
            oid = self.run(f"INSERT INTO ops({', '.join(f)}, created_by, created, updated) VALUES({', '.join('?' * len(f))}, ?, ?, ?)",
                           *f.values(), who, now(), now())
            self.audit(who, "add", "op", oid, f)
        self.touch(pid)
        return self.project(pid)

    # ---------- заказчики и подрядчики ----------
    def save_client(self, d, who):
        cid = int(d.get("id") or 0)
        name = _text(d.get("name"), 120)
        if not name:
            raise CrmError("Укажите имя заказчика")
        pref = _text(d.get("contact_pref"), 30)
        f = dict(name=name, phone=_text(d.get("phone"), 60), email=_text(d.get("email"), 120),
                 messenger=_text(d.get("messenger"), 120), contact_pref=pref if pref in CONTACT_PREFS else "",
                 city=_text(d.get("city"), 80), note=_text(d.get("note"), 2000))
        if f["email"] and not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+$", f["email"]):
            raise CrmError("E-mail записан с ошибкой")
        return self._save("clients", "client", cid, f, who)

    def save_contractor(self, d, who):
        cid = int(d.get("id") or 0)
        name = _text(d.get("name"), 120)
        if not name:
            raise CrmError("Укажите имя подрядчика")
        pref = _text(d.get("contact_pref"), 30)
        f = dict(name=name, trade=_text(d.get("trade"), 60), company=_text(d.get("company"), 120),
                 phone=_text(d.get("phone"), 60), email=_text(d.get("email"), 120),
                 contact_pref=pref if pref in CONTACT_PREFS else "", city=_text(d.get("city"), 80), note=_text(d.get("note"), 2000))
        return self._save("contractors", "contractor", cid, f, who)

    def _save(self, table, entity, rid, f, who):
        if rid:
            if not self.one(f"SELECT id FROM {table} WHERE id=?", rid):
                raise CrmError("Запись не найдена")
            self.run(f"UPDATE {table} SET {', '.join(f'{k}=?' for k in f)}, updated=? WHERE id=?", *f.values(), now(), rid)
            self.audit(who, "edit", entity, rid, f)
        else:
            rid = self.run(f"INSERT INTO {table}({', '.join(f)}, created, updated) VALUES({', '.join('?' * len(f))}, ?, ?)",
                           *f.values(), now(), now())
            self.audit(who, "add", entity, rid, f)
        return self.one(f"SELECT * FROM {table} WHERE id=?", rid)

    def link_contractor(self, d, who):
        pid, cid = int(d.get("project_id") or 0), int(d.get("contractor_id") or 0)
        if not self.one("SELECT id FROM projects WHERE id=?", pid) or not self.one("SELECT id FROM contractors WHERE id=?", cid):
            raise CrmError("Проект или подрядчик не найден")
        trade, note = _text(d.get("trade"), 60), _text(d.get("note"), 500)
        lid = int(d.get("id") or 0)
        if lid:
            self.run("UPDATE project_contractors SET trade=?, note=? WHERE id=? AND project_id=?", trade, note, lid, pid)
        else:
            lid = self.run("INSERT INTO project_contractors(project_id, contractor_id, trade, note, created) VALUES(?, ?, ?, ?, ?)",
                           pid, cid, trade, note, now())
        self.audit(who, "edit" if d.get("id") else "add", "link", lid, {"project_id": pid, "contractor_id": cid, "trade": trade})
        self.touch(pid)
        return self.project(pid)

    # ---------- удаление ----------
    def delete(self, entity, rid, who):
        rid = int(rid or 0)
        if entity == "op":
            o = self.one("SELECT * FROM ops WHERE id=?", rid)
            if not o:
                raise CrmError("Операция не найдена")
            self.run("DELETE FROM ops WHERE id=?", rid)
            self.audit(who, "delete", "op", rid, o)
            self.touch(o["project_id"])
            return self.project(o["project_id"])
        if entity == "link":
            link = self.one("SELECT * FROM project_contractors WHERE id=?", rid)
            if not link:
                raise CrmError("Не найдено")
            self.run("DELETE FROM project_contractors WHERE id=?", rid)
            self.audit(who, "delete", "link", rid, link)
            return self.project(link["project_id"])
        if entity == "file":
            f = self.one("SELECT * FROM files WHERE id=?", rid)
            if not f:
                raise CrmError("Файл не найден")
            for p in (f["path"], f["thumb"]):
                if p:
                    try:
                        os.remove(os.path.join(self.files_dir, p))
                    except OSError:
                        pass
            self.run("DELETE FROM files WHERE id=?", rid)
            self.audit(who, "delete", "file", rid, f)
            return self.project(f["project_id"])
        if entity == "project":
            p = self.one("SELECT * FROM projects WHERE id=?", rid)
            if not p:
                raise CrmError("Проект не найден")
            if self.one("SELECT id FROM ops WHERE project_id=? LIMIT 1", rid) or self.one("SELECT id FROM files WHERE project_id=? LIMIT 1", rid):
                raise CrmError("В проекте есть операции или файлы — удалить нельзя. Поставьте статус «Отменён».")
            self.run("DELETE FROM project_contractors WHERE project_id=?", rid)
            self.run("DELETE FROM projects WHERE id=?", rid)
            self.audit(who, "delete", "project", rid, p)
            return {}
        if entity == "client":
            c = self.one("SELECT * FROM clients WHERE id=?", rid)
            if not c:
                raise CrmError("Заказчик не найден")
            if self.one("SELECT id FROM projects WHERE client_id=? LIMIT 1", rid):
                raise CrmError("У заказчика есть проекты — сначала уберите его из проектов")
            self.run("DELETE FROM clients WHERE id=?", rid)
            self.audit(who, "delete", "client", rid, c)
            return {}
        if entity == "contractor":
            c = self.one("SELECT * FROM contractors WHERE id=?", rid)
            if not c:
                raise CrmError("Подрядчик не найден")
            if self.one("SELECT id FROM project_contractors WHERE contractor_id=? LIMIT 1", rid):
                raise CrmError("Подрядчик указан в проектах — сначала уберите его оттуда")
            self.run("DELETE FROM contractors WHERE id=?", rid)
            self.audit(who, "delete", "contractor", rid, c)
            return {}
        raise CrmError("Неизвестно, что удалять")

    # ---------- файлы ----------
    def disk(self):
        used = 0
        for root, _, names in os.walk(self.files_dir):
            for n in names:
                try:
                    used += os.path.getsize(os.path.join(root, n))
                except OSError:
                    pass
        try:
            free = shutil.disk_usage(self.files_dir if os.path.isdir(self.files_dir) else APP).free
        except OSError:
            free = None
        return {"used": used, "free": free}

    def add_file(self, pid, category, name, stream, size, mime, who, tg_file_id=None, note=""):
        """Сохранить файл проекта. stream — объект с read(); size — сколько байт читать."""
        pid = int(pid or 0)
        if not self.one("SELECT id FROM projects WHERE id=?", pid):
            raise CrmError("Проект не найден")
        if category not in dict(FILE_CATS):
            raise CrmError("Неизвестный раздел файлов")
        if size <= 0:
            raise CrmError("Пустой файл")
        if size > FILE_MAX:
            raise CrmError(f"Файл больше {FILE_MAX // 2**20} МБ — пришлите его в бот как документ или разделите")
        os.makedirs(os.path.join(self.files_dir, str(pid)), exist_ok=True)
        if shutil.disk_usage(self.files_dir).free - size < MIN_FREE:
            raise CrmError("На сервере заканчивается место — файл не сохранён. Напишите разработчику.")
        name = _text(os.path.basename(name or "файл"), 150) or "файл"
        fid = self.run("INSERT INTO files(project_id, category, name, mime, size, tg_file_id, note, created_by, created) "
                       "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)", pid, category, name, _text(mime, 100), 0, tg_file_id, _text(note, 500), who, now())
        ext = os.path.splitext(name)[1].lower()
        ext = ext if re.fullmatch(r"\.[a-z0-9]{1,8}", ext) else ""
        rel = f"{pid}/{fid}{ext}"
        full = os.path.join(self.files_dir, rel)
        got = 0
        try:
            with open(full + ".part", "wb") as out:
                while got < size:
                    chunk = stream.read(min(1024 * 1024, size - got))
                    if not chunk:
                        break
                    out.write(chunk)
                    got += len(chunk)
            if got != size:
                raise CrmError("Файл пришёл не полностью — попробуйте ещё раз")
            os.replace(full + ".part", full)
        except BaseException:
            self.run("DELETE FROM files WHERE id=?", fid)
            try:
                os.remove(full + ".part")
            except OSError:
                pass
            raise
        self.run("UPDATE files SET path=?, size=? WHERE id=?", rel, got, fid)
        self.audit(who, "add", "file", fid, {"project_id": pid, "category": category, "name": name, "size": got})
        self.touch(pid)
        return self.file_view(self.one("SELECT * FROM files WHERE id=?", fid))

    def add_tg_only(self, pid, category, name, size, mime, who, tg_file_id):
        """Файл больше 20 МБ, присланный в бот: Telegram не отдаёт такие боту на скачивание — храним ссылку на него
        в Telegram; в «Студии» его можно прислать себе в чат."""
        pid = int(pid or 0)
        if not self.one("SELECT id FROM projects WHERE id=?", pid) or category not in dict(FILE_CATS):
            raise CrmError("Проект или раздел не найден")
        fid = self.run("INSERT INTO files(project_id, category, name, mime, size, tg_file_id, created_by, created) "
                       "VALUES(?, ?, ?, ?, ?, ?, ?, ?)", pid, category, _text(name, 150) or "файл", _text(mime, 100), int(size or 0),
                       tg_file_id, who, now())
        self.audit(who, "add", "file", fid, {"project_id": pid, "category": category, "name": name, "telegram": True})
        self.touch(pid)
        return self.file_view(self.one("SELECT * FROM files WHERE id=?", fid))

    def set_thumb(self, fid, data):
        f = self.one("SELECT * FROM files WHERE id=?", int(fid))
        if not f:
            raise CrmError("Файл не найден")
        if not data or len(data) > 2 * 1024 * 1024:
            raise CrmError("Неподходящее превью")
        rel = f"{f['project_id']}/{f['id']}-thumb.jpg"
        with open(os.path.join(self.files_dir, rel), "wb") as out:
            out.write(data)
        self.run("UPDATE files SET thumb=? WHERE id=?", rel, f["id"])
        return self.file_view(self.one("SELECT * FROM files WHERE id=?", f["id"]))

    def move_file(self, fid, category, who):
        if category not in dict(FILE_CATS):
            raise CrmError("Неизвестный раздел файлов")
        f = self.one("SELECT * FROM files WHERE id=?", int(fid))
        if not f:
            raise CrmError("Файл не найден")
        self.run("UPDATE files SET category=? WHERE id=?", category, f["id"])
        self.audit(who, "edit", "file", f["id"], {"project_id": f["project_id"], "category": category})
        return self.project(f["project_id"])

    def sign(self, fid, variant, exp=None):
        exp = exp or int(time.time()) + LINK_HOURS * 3600
        mac = hmac.new(self.secret.encode(), f"{fid}:{variant}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        return f"/api/crm/file?id={fid}&v={variant}&e={exp}&s={mac}"

    def check_sig(self, fid, variant, exp, sig):
        try:
            if int(exp) < time.time():
                return False
        except ValueError:
            return False
        good = hmac.new(self.secret.encode(), f"{fid}:{variant}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        return hmac.compare_digest(good, sig or "")

    def file_view(self, f):
        v = dict(f)
        image = (f.get("mime") or "").startswith("image/")
        v["url"] = self.sign(f["id"], "o") if f.get("path") else None
        v["thumb_url"] = self.sign(f["id"], "t") if f.get("thumb") else (v["url"] if image and (f.get("size") or 0) < 1.5 * 2**20 else None)
        v["image"] = image
        v.pop("path", None)
        v.pop("thumb", None)
        return v

    def file_path(self, fid, variant):
        f = self.one("SELECT * FROM files WHERE id=?", int(fid))
        if not f:
            return None, None
        rel = f["thumb"] if variant == "t" else f["path"]
        return (os.path.join(self.files_dir, rel) if rel else None), f      # без пути — файл хранится в Telegram

    # ---------- деньги ----------
    @staticmethod
    def period_bounds(period, d=None):
        d = d or today()
        if period == "month":
            a = d.replace(day=1)
        elif period == "quarter":
            a = d.replace(month=(d.month - 1) // 3 * 3 + 1, day=1)
        elif period == "year":
            a = d.replace(month=1, day=1)
        else:
            return None, None
        return a.isoformat(), d.isoformat()

    def stats(self, period="month"):
        """Доход за период (по дате операции): оплаты заказчиков, бонусы, наценка; по месяцам, городам, тарифам;
        сколько заказчики ещё должны по проектам в работе."""
        a, b = self.period_bounds(period)
        where, args = ("WHERE o.day>=? AND o.day<=?", (a, b)) if a else ("", ())
        rows = self.q(f"""SELECT o.*, p.city, p.tariff, p.title AS project_title, p.number AS project_number
                          FROM ops o JOIN projects p ON p.id=o.project_id {where}""", *args)

        def income(o):
            return o["amount_eur"] - (o["buy_eur"] or 0) if o["kind"] == "resale" else o["amount_eur"]
        tot = {"payment": 0.0, "commission": 0.0, "resale": 0.0}
        cities, tariffs, projects = {}, {}, {}
        for o in rows:
            x = income(o)
            tot[o["kind"]] += x
            cities[o["city"] or "—"] = cities.get(o["city"] or "—", 0) + x
            tariffs[o["tariff"] or "—"] = tariffs.get(o["tariff"] or "—", 0) + x
            projects[o["project_id"]] = projects.get(o["project_id"], 0) + x
        # по месяцам: последние 12 месяцев, за «всё время» — с первой операции
        first = self.one("SELECT MIN(day) AS d FROM ops")["d"]
        t = today()
        y, mo = divmod(t.year * 12 + t.month - 1 - 11, 12)          # первое число месяца 11 месяцев назад
        start = date.fromisoformat(first).replace(day=1) if period == "all" and first else date(y, mo + 1, 1)
        months, m = [], start
        while m <= t:
            months.append(m.strftime("%Y-%m"))
            m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        by_month = {k: {"month": k, "payment": 0.0, "commission": 0.0, "resale": 0.0} for k in months}
        for o in self.q("SELECT * FROM ops WHERE day>=?", start.isoformat()):
            k = o["day"][:7]
            if k in by_month:
                by_month[k][o["kind"]] += income(o)
        months_out = []
        for k in months:
            r = by_month[k]
            months_out.append({kk: round(v, 2) if isinstance(v, float) else v for kk, v in r.items()}
                              | {"total": round(r["payment"] + r["commission"] + r["resale"], 2)})
        owing = [p for p in self.project_rows() if p["status"] in ("active", "paused") and p["balance"] > 0.005]
        names = {p["id"]: p for p in self.project_rows()}
        top = sorted(projects.items(), key=lambda kv: -kv[1])[:8]
        new = self.q("SELECT COUNT(*) AS n, COALESCE(SUM(total_eur), 0) AS s FROM projects WHERE " +
                     ("COALESCE(started, substr(created, 1, 10))>=? AND COALESCE(started, substr(created, 1, 10))<=?" if a else "1"), *args)[0]
        return {
            "period": period, "from": a, "to": b,
            "income": round(sum(tot.values()), 2), "payments": round(tot["payment"], 2),
            "bonuses": round(tot["commission"], 2), "margin": round(tot["resale"], 2), "ops": len(rows),
            "projects_with_income": len(projects), "new_projects": new["n"], "new_contracts": round(new["s"], 2),
            "months": months_out,
            "by_city": [[k, round(v, 2)] for k, v in sorted(cities.items(), key=lambda kv: -kv[1]) if abs(v) > 0.005],
            "by_tariff": [[k, round(v, 2)] for k, v in sorted(tariffs.items(), key=lambda kv: -kv[1]) if abs(v) > 0.005],
            "top_projects": [[names[k]["number"] or "", names[k]["title"], round(v, 2), k] for k, v in top if k in names],
            "owing": round(sum(p["balance"] for p in owing), 2),
            "owing_projects": [[p["number"] or "", p["title"], p["balance"], p["id"]] for p in sorted(owing, key=lambda p: -p["balance"])[:10]],
        }

    # ---------- всё для приложения ----------
    def state(self):
        projects = self.project_rows()
        clients = self.q("SELECT * FROM clients ORDER BY name COLLATE NOCASE")
        by_client = {}
        for p in projects:
            if p["client_id"]:
                by_client.setdefault(p["client_id"], []).append(p["id"])
        for c in clients:
            c["projects"] = by_client.get(c["id"], [])
        contractors = self.q("""SELECT c.*, (SELECT COUNT(*) FROM project_contractors l WHERE l.contractor_id=c.id) AS projects
                                FROM contractors c ORDER BY c.trade, c.name COLLATE NOCASE""")
        cities = sorted({x for x in [p["city"] for p in projects] + [c["city"] for c in clients] + [c["city"] for c in contractors] if x})
        return {"projects": projects, "clients": clients, "contractors": contractors, "cities": cities, "lists": self.lists(),
                "disk": self.disk()}

    # ---------- копии ----------
    def backup_if_due(self, log=print):
        """Раз в день — копия базы студии (и базы бота) в ~/dumskaya/backups; старше 30 дней — удаляются."""
        d = today().isoformat()
        if self.setting("backup_day") == d:
            return False
        os.makedirs(self.backup_dir, exist_ok=True)
        for src, name in [(self.path, "crm")] + [(p, os.path.splitext(os.path.basename(p))[0]) for p in self.extra_backups]:
            if not os.path.exists(src):
                continue
            dst = os.path.join(self.backup_dir, f"{name}-{d}.db")
            try:
                s = sqlite3.connect(src)
                t = sqlite3.connect(dst + ".tmp")
                with t:
                    s.backup(t)
                s.close()
                t.close()
                os.replace(dst + ".tmp", dst)
                os.chmod(dst, 0o600)
            except (sqlite3.Error, OSError) as e:
                log(f"копия {name}: ошибка {e}")
        cutoff = (today() - timedelta(days=BACKUP_KEEP)).isoformat()
        for f in os.listdir(self.backup_dir):
            m = re.search(r"-(\d{4}-\d{2}-\d{2})\.db$", f)
            if m and m.group(1) < cutoff:
                try:
                    os.remove(os.path.join(self.backup_dir, f))
                except OSError:
                    pass
        self.setting("backup_day", d)
        return True
