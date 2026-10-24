#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Учёт проектов студии — для разработчика и дизайнера (кнопка «Студия» в боте, страница crm_app.html).

Проект: номер по внутреннему учёту, название, заказчик, город, площадь, тариф, сумма договора (в евро), статус.
Операции проекта (вся история):
  • оплата заказчика — сумма, валюта, дата, способ;
  • бонус («откат») — от подрядчика (с привязкой к нему и этапу) или от поставщика, фабрики;
  • перепродажа — студия посредник: закупка и продажа, доход — разница.
Подрядчики в проекте — с этапами работ: сумма заказа и бонус студии с неё (процент, по умолчанию 10 %, сумма или
«пока неизвестно»). Долг подрядчика = ожидаемые бонусы − полученные бонусы от него в этом проекте.
Суммы в евро, гривне, долларе, злотом; в евро — по курсу центробанка на дату (fx.py) или по курсу, введённому вручную.
Баланс проекта: договор − оплаты заказчика. Доход студии: оплаты + полученные бонусы + наценка на перепродаже.
Ещё: заказчики (телефон, почта, как удобнее связаться), файлы проекта (обмерный план, опросник, до, визуализации,
документация, после, другое) — в ~/dumskaya/crm/files, ссылки на них подписаны и действуют 12 часов; удалённые
файлы 30 дней лежат в ~/dumskaya/crm/trash.

Данные — ~/dumskaya/crm.db (SQLite). Каждый день — копия базы студии и базы бота в ~/dumskaya/backups (30 дней);
с Мака `npm run backup` (и каждая выкладка) делает свежую копию и скачивает копии и файлы на Мак.
Только стандартная библиотека Python 3.

   python3 crm.py --backup-now     — свежая копия баз сейчас (её делает npm run backup с Мака)
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone

try:
    from fx import CODES, CURRENCIES
except ImportError:  # pragma: no cover
    CURRENCIES, CODES = [("EUR", "€", "евро")], ["EUR"]

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bratislava")
except Exception:  # noqa: BLE001
    TZ = timezone(timedelta(hours=1))

APP = os.path.expanduser("~/dumskaya")
CRM_DB = os.environ.get("CRM_DB", os.path.join(APP, "crm.db"))
FILES_DIR = os.environ.get("CRM_FILES", os.path.join(APP, "crm", "files"))
BACKUP_DIR = os.environ.get("BACKUP_DIR", os.path.join(APP, "backups"))
BOT_DB = os.environ.get("BOT_DB", os.path.join(APP, "bot.db"))
BACKUP_KEEP = 30
TRASH_KEEP = 30                         # удалённые файлы проектов лежат в корзине 30 дней
DEFAULT_PCT = 10                        # бонус студии с заказа подрядчика по умолчанию, %
FILE_MAX = 60 * 1024 * 1024            # один файл — до 60 МБ
MIN_FREE = 2 * 1024 ** 3               # оставлять на диске сервера хотя бы 2 ГБ (сервер общий)
LINK_HOURS = 12

STATUSES = [("active", "В работе"), ("paused", "На паузе"), ("done", "Завершён"), ("cancelled", "Отменён")]
KINDS = {"payment": "Оплата заказчика", "commission": "Бонус", "resale": "Перепродажа"}
FILE_CATS = [("measure", "Обмерный план"), ("brief", "Опросник"), ("before", "До"), ("visual", "Визуализации"),
             ("docs", "Документация"), ("after", "После"), ("other", "Другое")]
PHOTO_CATS = ("before", "visual", "after")
CONTACT_PREFS = ["Звонок", "WhatsApp", "Telegram", "Viber", "E-mail", "SMS"]
# заявки: при получении — что это (заявка, реклама или предложение сотрудничества, спам, игнорировать), дальше у настоящих —
# в работе, стала проектом, закрыта (решено 24.10.2026)
LEAD_STATUSES = [("new", "Новая"), ("lead", "Заявка"), ("work", "В работе"), ("project", "Стала проектом"), ("closed", "Закрыта"),
                 ("ad", "Реклама, сотрудничество"), ("spam", "Спам"), ("ignore", "Игнорировать")]
LEAD_TRIAGE = ["lead", "ad", "spam", "ignore"]          # «что это» — при получении, и кнопками в сообщении бота
LEAD_FLOW = ["work", "project", "closed"]               # «как идёт» — у настоящих заявок
LEAD_HIDDEN = ["ad", "spam", "ignore"]                  # не заявки: во «Все» не попадают, у каждого своя кнопка
TEST_CONTACTS = ("заявка отправлена с сервера", "test@example.com")   # пробные заявки мастера настройки и проверки
LEADS_ARCHIVE_DAYS = 30             # заявки, пришедшие до «Студии»: за 30 дней — «В работе», старше — «Закрыта»
LEADS_TRASH_DAYS = 30               # удалённая заявка 30 дней в «Удалённых» (можно вернуть), потом имя, контакт и текст стираются
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
  note TEXT, created_by TEXT, created TEXT, updated TEXT,
  link_id INTEGER, stage_id INTEGER);         -- бонус от подрядчика проекта (project_contractors) и за какой этап
CREATE INDEX IF NOT EXISTS ops_project ON ops(project_id);
CREATE INDEX IF NOT EXISTS ops_day ON ops(day);
CREATE TABLE IF NOT EXISTS contractors (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, trade TEXT, company TEXT, phone TEXT, email TEXT,
  contact_pref TEXT, city TEXT, note TEXT, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS project_contractors (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, contractor_id INTEGER NOT NULL, trade TEXT,
  note TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS stages (         -- этапы работ подрядчика в проекте: сумма заказа и бонус студии с неё
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, link_id INTEGER NOT NULL, title TEXT, day TEXT,
  amount REAL NOT NULL DEFAULT 0, currency TEXT NOT NULL, rate REAL NOT NULL, rate_src TEXT, amount_eur REAL NOT NULL DEFAULT 0,
  pct REAL, commission REAL, commission_eur REAL,   -- commission NULL — бонус пока неизвестен
  note TEXT, created_by TEXT, created TEXT, updated TEXT);
CREATE INDEX IF NOT EXISTS stages_link ON stages(link_id);
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, category TEXT NOT NULL, name TEXT, path TEXT,
  thumb TEXT, mime TEXT, size INTEGER, tg_file_id TEXT, note TEXT, created_by TEXT, created TEXT);
CREATE INDEX IF NOT EXISTS files_project ON files(project_id);
CREATE TABLE IF NOT EXISTS leads (            -- заявки с сайта (в файле leads.jsonl — они же, без статусов)
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, name TEXT, contact TEXT, message TEXT, message_ru TEXT,
  message_lang TEXT, page TEXT, model TEXT, model_name TEXT, lang TEXT, routed TEXT,
  status TEXT NOT NULL DEFAULT 'new', note TEXT, project_id INTEGER, updated TEXT, updated_by TEXT,
  src TEXT UNIQUE, deleted TEXT);            -- src: время + имя + контакт — одна заявка не попадёт дважды (и удалённая не вернётся)
CREATE INDEX IF NOT EXISTS leads_ts ON leads(ts);
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


def _cur(v):
    c = str(v or "EUR").upper()
    if c not in CODES:
        raise CrmError("Валюта: выберите из списка (" + ", ".join(CODES) + ")")
    return c


def _row(r):
    return dict(r) if r is not None else None


def _debt(stages, ops):
    """Бонусы подрядчика в проекте. stages — его этапы, ops — полученные от него бонусы.
    Считается в валюте его этапов (если все в одной), иначе в евро: так оплата в той же валюте закрывает долг ровно,
    без хвостов от разницы курсов. Возвращает ожидаемое, полученное, долг — в этой валюте и в евро."""
    known = [s for s in stages if s["commission"] is not None]
    curs = {s["currency"] for s in (known or stages)} or {o["currency"] for o in ops}
    cur = next(iter(curs)) if len(curs) == 1 else "EUR"
    k = 1.0                                             # сколько единиц валюты долга в одном евро
    if cur != "EUR":
        for pairs in ([(s["commission"], s["commission_eur"]) for s in known if s["currency"] == cur],
                      [(s["amount"], s["amount_eur"]) for s in stages if s["currency"] == cur],
                      [(o["amount"], o["amount_eur"]) for o in ops if o["currency"] == cur]):
            a, e = sum(x for x, _ in pairs), sum(y or 0 for _, y in pairs)
            if a > 0 and e > 0:
                k = a / e
                break

    def in_cur(amount, currency, amount_eur):
        return amount if currency == cur else (amount_eur or 0) * k
    expected = sum(in_cur(s["commission"], s["currency"], s["commission_eur"]) for s in known)
    received = sum(in_cur(o["amount"], o["currency"], o["amount_eur"]) for o in ops)
    debt = expected - received if expected - received > 0.005 else 0.0
    out_stages = []
    for s in stages:
        got = sum(in_cur(o["amount"], o["currency"], o["amount_eur"]) for o in ops if o.get("stage_id") == s["id"])
        out_stages.append(dict(s, received=round(got, 2)))
    return {"currency": cur, "rate": round(k, 6), "expected": round(expected, 2), "received": round(received, 2),
            "debt": round(debt, 2), "expected_eur": round(expected / k, 2), "received_eur": round(sum(o["amount_eur"] for o in ops), 2),
            "debt_eur": round(debt / k, 2), "unknown": len(stages) - len(known),
            "order": round(sum(in_cur(s["amount"], s["currency"], s["amount_eur"]) for s in stages), 2),
            "order_eur": round(sum(s["amount_eur"] for s in stages), 2), "stages": out_stages, "ops": len(ops)}


def backup_dbs(sources, backup_dir, day, log=print):
    """Копии баз SQLite (стандартным способом SQLite — целостные и во время работы сервиса): name-день.db."""
    os.makedirs(backup_dir, exist_ok=True)
    made = []
    for src, name in sources:
        if not os.path.exists(src):
            continue
        dst = os.path.join(backup_dir, f"{name}-{day}.db")
        try:
            s = sqlite3.connect(src)
            t = sqlite3.connect(dst + ".tmp")
            with t:
                s.backup(t)
            s.close()
            t.close()
            os.replace(dst + ".tmp", dst)
            os.chmod(dst, 0o600)
            made.append(dst)
        except (sqlite3.Error, OSError) as e:
            log(f"копия {name}: ошибка {e}")
    return made


class Crm:
    def __init__(self, path=CRM_DB, rates=None, files_dir=FILES_DIR, backup_dir=BACKUP_DIR, extra_backups=()):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path, self.files_dir, self.backup_dir = path, files_dir, backup_dir
        self.trash_dir = os.path.join(os.path.dirname(os.path.abspath(files_dir)), "trash")
        self.extra_backups = list(extra_backups)       # другие базы SQLite для ежедневной копии (база бота)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.rates = rates
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.executescript(SCHEMA)
            cols = {r[1] for r in self.db.execute("PRAGMA table_info(ops)")}
            for c in ("link_id", "stage_id"):                  # базы, созданные до этапов подрядчиков
                if c not in cols:
                    self.db.execute(f"ALTER TABLE ops ADD COLUMN {c} INTEGER")
            if "deleted" not in {r[1] for r in self.db.execute("PRAGMA table_info(leads)")}:   # до удаления заявок
                self.db.execute("ALTER TABLE leads ADD COLUMN deleted TEXT")
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
            pct = float(self.setting("default_pct") or DEFAULT_PCT)
        except ValueError:
            pct = DEFAULT_PCT
        out.update(statuses=STATUSES, lead_statuses=LEAD_STATUSES, lead_triage=LEAD_TRIAGE, lead_flow=LEAD_FLOW, lead_hidden=LEAD_HIDDEN, kinds=KINDS, file_cats=FILE_CATS, photo_cats=PHOTO_CATS, contact_prefs=CONTACT_PREFS,
                   pay_methods=PAY_METHODS, currencies=CURRENCIES, default_pct=pct)
        return out

    def save_lists(self, data, who):
        for k in DEFAULTS:
            if k in data:
                items = [_text(x, 60) for x in (data[k] or []) if _text(x, 60)]
                if not items:
                    raise CrmError("Список не может быть пустым")
                self.setting(k, json.dumps(list(dict.fromkeys(items)), ensure_ascii=False))
        if "default_pct" in data:
            pct = _money(data["default_pct"], "Бонус по умолчанию")
            if pct > 100:
                raise CrmError("Бонус по умолчанию: не больше 100 %")
            self.setting("default_pct", str(pct))
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
        debts = {}
        for m in self.link_money().values():
            d = debts.setdefault(m["project_id"], [0.0, 0.0])
            d[0] += m["debt_eur"]
            d[1] += m["expected_eur"]
        for r in rows:
            for k in ("paid", "bonus", "margin"):
                r[k] = round(r[k], 2)
            r["extra"] = round(r["bonus"] + r["margin"], 2)
            r["balance"] = round((r["total_eur"] or 0) - r["paid"], 2)
            r["income"] = round(r["paid"] + r["extra"], 2)
            r["contractor_debt"], r["bonus_expected"] = (round(x, 2) for x in debts.get(r["id"], (0, 0)))
        return rows

    def link_money(self, project_id=None):
        """{link_id: бонусы подрядчика в проекте (_debt) + project_id, contractor_id, trade}."""
        flt, args = ("WHERE project_id=?", (int(project_id),)) if project_id else ("", ())
        links = self.q(f"SELECT * FROM project_contractors {flt}", *args)
        stages = self.q(f"SELECT * FROM stages {flt} ORDER BY day, id", *args)
        ops = self.q(f"SELECT * FROM ops {flt + ' AND' if flt else 'WHERE'} kind='commission' AND link_id IS NOT NULL ORDER BY day, id", *args)
        out = {}
        for link in links:
            m = _debt([x for x in stages if x["link_id"] == link["id"]], [o for o in ops if o["link_id"] == link["id"]])
            m.update(link_id=link["id"], project_id=link["project_id"], contractor_id=link["contractor_id"], trade=link["trade"])
            out[link["id"]] = m
        return out

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
        money = self.link_money(p["id"])
        for link in links:
            link["money"] = money.get(link["link_id"]) or _debt([], [])
        files = [self.file_view(f) for f in self.q("SELECT * FROM files WHERE project_id=? ORDER BY id DESC", p["id"])]
        client = self.one("SELECT * FROM clients WHERE id=?", p["client_id"]) if p["client_id"] else None
        history = self.q("SELECT ts, who, action, entity, entity_id FROM audit WHERE (entity='project' AND entity_id=?) OR "
                         "(entity IN ('op', 'file', 'link', 'stage') AND (details LIKE ? OR details LIKE ?)) ORDER BY id DESC LIMIT 50",
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
        cur = _cur(d.get("currency"))
        amount = _money(d.get("amount"), "Цена продажи" if kind == "resale" else "Сумма")
        link_id = stage_id = None
        counterparty = _text(d.get("counterparty"), 120)
        if kind == "commission" and d.get("link_id"):
            link = self.one("""SELECT l.id, c.name FROM project_contractors l JOIN contractors c ON c.id=l.contractor_id
                               WHERE l.id=? AND l.project_id=?""", int(d["link_id"]), pid)
            if not link:
                raise CrmError("Подрядчик в этом проекте не найден")
            link_id, counterparty = link["id"], link["name"]
            if d.get("stage_id"):
                if not self.one("SELECT id FROM stages WHERE id=? AND link_id=?", int(d["stage_id"]), link_id):
                    raise CrmError("Этап не найден")
                stage_id = int(d["stage_id"])
        rate, src, eur = self._convert(amount, cur, day, d.get("rate") if d.get("manual_rate") else None)
        f = dict(project_id=pid, kind=kind, day=day, title=_text(d.get("title"), 200), category=_text(d.get("category"), 60),
                 method=_text(d.get("method"), 60), counterparty=counterparty,
                 amount=amount, currency=cur, rate=rate, rate_src=src, amount_eur=eur,
                 buy=None, buy_currency=None, buy_rate=None, buy_rate_src=None, buy_eur=None, note=_text(d.get("note"), 2000),
                 link_id=link_id, stage_id=stage_id)
        if kind == "resale":
            if not f["title"]:
                raise CrmError("Укажите, что перепродано")
            bcur = _cur(d.get("buy_currency") or cur)
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

    # ---------- заявки с сайта ----------
    @staticmethod
    def lead_src(lead):
        return hashlib.sha1(f"{lead.get('time')}|{lead.get('name')}|{lead.get('contact')}".encode()).hexdigest()[:20]

    def add_lead(self, lead, status=None, note=""):
        """Заявка с сайта → в учёт (если её там ещё нет). Возвращает номер заявки."""
        src = self.lead_src(lead)
        if (lead.get("contact") or "").strip().lower() in TEST_CONTACTS:
            status, note = "test", "Пробная заявка при настройке сервиса"
        self.run("""INSERT OR IGNORE INTO leads(ts, name, contact, message, message_ru, message_lang, page, model, model_name, lang,
                    routed, status, note, src, updated) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                 _text(lead.get("time"), 40) or now(), _text(lead.get("name"), 120), _text(lead.get("contact"), 160),
                 _text(lead.get("message"), 4000), _text(lead.get("message_ru"), 6000), _text(lead.get("message_lang"), 10),
                 _text(lead.get("page"), 300), _text(lead.get("model"), 40), _text(lead.get("model_name"), 200),
                 _text(lead.get("lang"), 5), _text(lead.get("routed"), 300), status or "new", _text(note, 500), src, now())
        return self.one("SELECT id FROM leads WHERE src=?", src)["id"]

    def lead_routed(self, lid, routed, model_name=""):
        self.run("UPDATE leads SET routed=?, model_name=COALESCE(NULLIF(?, ''), model_name) WHERE id=?",
                 _text(routed, 300), _text(model_name, 200), int(lid))

    def import_leads(self, path, log=print):
        """Заявки из файла leads.jsonl, которых ещё нет в учёте (пришли до «Студии» или пока учёт не работал).
        Пришедшие до «Студии»: последние 30 дней — «В работе», старше — «Закрыта»; новые — «Новая»."""
        if not os.path.exists(path):
            return 0
        first_run = not self.one("SELECT id FROM leads LIMIT 1")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=LEADS_ARCHIVE_DAYS)).isoformat()
        added = 0
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    lead = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(lead, dict) or self.one("SELECT id FROM leads WHERE src=?", self.lead_src(lead)):
                    continue
                if first_run:
                    old = str(lead.get("time") or "") < cutoff
                    self.add_lead(lead, "closed" if old else "work", "Пришла до запуска «Студии» — статус поставлен автоматически")
                else:
                    self.add_lead(lead)
                added += 1
        if added:
            log(f"учёт: заявок из файла добавлено {added}")
        return added

    def leads_list(self):
        rows = self.q("""SELECT l.id, l.ts, l.name, l.contact, substr(COALESCE(NULLIF(l.message_ru, ''), l.message), 1, 160) AS snippet,
                                l.model, l.model_name, l.lang, l.status, l.project_id, l.routed, p.title AS project_title, l.deleted
                         FROM leads l LEFT JOIN projects p ON p.id=l.project_id
                         WHERE l.status != 'test' AND (l.deleted IS NULL OR l.deleted >= ?) ORDER BY l.ts DESC, l.id DESC""",
                      self._trash_cutoff())
        return {"leads": rows, "statuses": LEAD_STATUSES, "trash_days": LEADS_TRASH_DAYS}

    @staticmethod
    def _trash_cutoff():
        return (datetime.now(timezone.utc) - timedelta(days=LEADS_TRASH_DAYS)).isoformat(timespec="seconds")

    def _live_lead(self, lid):
        """Заявка, которую можно менять: есть и не удалена."""
        r = self.one("SELECT id, name, status, note, project_id, deleted FROM leads WHERE id=? AND status != 'test'", int(lid or 0))
        if not r:
            raise CrmError("Заявка не найдена")
        if r["deleted"]:
            raise CrmError("Заявка удалена — сначала верните её")
        return r

    def delete_leads(self, ids, who):
        """Удалить заявки: 30 дней лежат в «Удалённых» (можно вернуть), потом имя, контакт и текст стираются.
        Сама строка остаётся отметкой, чтобы заявка не вернулась из файла leads.jsonl. Проект из заявки остаётся."""
        if not isinstance(ids, (list, tuple)):
            ids = [ids]
        done = 0
        for lid in ids[:1000]:
            try:
                r = self._live_lead(int(lid))
            except (CrmError, TypeError, ValueError):
                continue
            self.run("UPDATE leads SET deleted=?, updated=?, updated_by=? WHERE id=?", now(), now(), who, r["id"])
            self.audit(who, "delete", "lead", r["id"], {"status": r["status"]})
            done += 1
        if not done:
            raise CrmError("Заявка не найдена")
        return {"deleted": done}

    def restore_lead(self, d, who):
        lid = int(d.get("id") or 0)
        r = self.one("SELECT id FROM leads WHERE id=? AND deleted IS NOT NULL AND deleted >= ?", lid, self._trash_cutoff())
        if not r:
            raise CrmError("Заявки нет среди удалённых")
        self.run("UPDATE leads SET deleted=NULL, updated=?, updated_by=? WHERE id=?", now(), who, lid)
        self.audit(who, "restore", "lead", lid, {})
        return self.lead(lid)

    def purge_leads(self):
        """Удалённые больше 30 дней назад: имя, контакт, текст и заметки стираются (и в истории изменений)."""
        old = [r["id"] for r in self.q("""SELECT id FROM leads WHERE deleted IS NOT NULL AND deleted < ?
                                          AND (name IS NOT NULL OR contact IS NOT NULL OR message IS NOT NULL)""",
                                       self._trash_cutoff())]
        for lid in old:
            self.run("""UPDATE leads SET name=NULL, contact=NULL, message=NULL, message_ru=NULL, note=NULL, page=NULL,
                        routed=NULL, model_name=NULL WHERE id=?""", lid)
            self.run("UPDATE audit SET details=NULL WHERE entity='lead' AND entity_id=?", lid)
        return len(old)

    def lead(self, lid):
        r = self.one("""SELECT l.*, p.title AS project_title, p.number AS project_number FROM leads l
                        LEFT JOIN projects p ON p.id=l.project_id WHERE l.id=? AND (l.deleted IS NULL OR l.deleted >= ?)""",
                     int(lid or 0), self._trash_cutoff())
        if not r:
            raise CrmError("Заявка не найдена")
        r.pop("src", None)
        r["history"] = self.q("SELECT ts, who, action, details FROM audit WHERE entity='lead' AND entity_id=? ORDER BY id DESC LIMIT 20", r["id"])
        return r

    def save_lead(self, d, who):
        lid = int(d.get("id") or 0)
        row = self._live_lead(lid)
        status = d.get("status")
        if status not in dict(LEAD_STATUSES):
            raise CrmError("Неизвестный статус заявки")
        if row["project_id"] and status in LEAD_HIDDEN:
            raise CrmError("Из этой заявки уже сделан проект")
        f = dict(status=status, note=_text(d.get("note"), 2000))
        self.run("UPDATE leads SET status=?, note=?, updated=?, updated_by=? WHERE id=?", f["status"], f["note"], now(), who, lid)
        self.audit(who, "edit", "lead", lid, f)
        return self.lead(lid)

    def set_lead_status(self, lid, status, who):
        """Статус заявки кнопкой в сообщении бота; заметка остаётся."""
        cur = self._live_lead(lid)
        return self.save_lead({"id": lid, "status": status, "note": cur["note"] or ""}, who)

    def lead_to_project(self, d, who):
        """Из заявки — заказчик (новый или выбранный) и проект; заявка → «Стала проектом»."""
        lid = self._live_lead(d.get("lead_id"))["id"]
        c, pd = d.get("client") or {}, d.get("project") or {}
        if not _text(pd.get("title"), 200):                       # проверить до того, как создавать заказчика
            raise CrmError("Укажите название проекта")
        number = _text(pd.get("number"), 40)
        if number and self.one("SELECT id FROM projects WHERE number=?", number):
            raise CrmError(f"Номер {number} уже есть у другого проекта")
        cid = int(c.get("id") or 0)
        if cid and not self.one("SELECT id FROM clients WHERE id=?", cid):
            raise CrmError("Заказчик не найден")
        if not cid:
            cid = self.save_client(c, who)["id"]
        pr = self.save_project(dict(pd, client_id=cid), who)
        pid = pr["project"]["id"]
        self.run("UPDATE leads SET status='project', project_id=?, updated=?, updated_by=? WHERE id=?", pid, now(), who, lid)
        self.audit(who, "edit", "lead", lid, {"status": "project", "project_id": pid})
        return pr

    # ---------- этапы работ подрядчика ----------
    def save_stage(self, d, who):
        sid, pid, lid = int(d.get("id") or 0), int(d.get("project_id") or 0), int(d.get("link_id") or 0)
        if not self.one("SELECT id FROM project_contractors WHERE id=? AND project_id=?", lid, pid):
            raise CrmError("Подрядчик в этом проекте не найден")
        day = _day(d.get("day") or today().isoformat())
        cur = _cur(d.get("currency"))
        amount = _money(d.get("amount") or 0, "Сумма заказа", allow_zero=True)
        mode = d.get("mode")
        pct = commission = None
        if mode == "pct":
            pct = _money(d.get("pct"), "Процент")
            if pct > 100:
                raise CrmError("Процент: не больше 100")
            if amount <= 0:
                raise CrmError("Чтобы посчитать бонус в процентах, укажите сумму заказа")
            commission = round(amount * pct / 100, 2)
        elif mode == "sum":
            commission = _money(d.get("commission"), "Бонус студии")
        elif mode != "unknown":
            raise CrmError("Выберите, как считать бонус студии")
        if amount <= 0 and commission is None:
            raise CrmError("Укажите сумму заказа или бонус студии")
        rate, src, amount_eur = self._convert(amount, cur, day, d.get("rate") if d.get("manual_rate") else None)
        f = dict(project_id=pid, link_id=lid, title=_text(d.get("title"), 120), day=day, amount=amount, currency=cur,
                 rate=rate, rate_src=src, amount_eur=amount_eur, pct=pct, commission=commission,
                 commission_eur=round(commission / rate, 2) if commission is not None else None, note=_text(d.get("note"), 1000))
        if sid:
            if not self.one("SELECT id FROM stages WHERE id=? AND project_id=?", sid, pid):
                raise CrmError("Этап не найден")
            self.run(f"UPDATE stages SET {', '.join(f'{k}=?' for k in f)}, updated=? WHERE id=?", *f.values(), now(), sid)
            self.audit(who, "edit", "stage", sid, f)
        else:
            sid = self.run(f"INSERT INTO stages({', '.join(f)}, created_by, created, updated) VALUES({', '.join('?' * len(f))}, ?, ?, ?)",
                           *f.values(), who, now(), now())
            self.audit(who, "add", "stage", sid, f)
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
            if self.one("SELECT id FROM stages WHERE link_id=? LIMIT 1", rid) or self.one("SELECT id FROM ops WHERE link_id=? LIMIT 1", rid):
                raise CrmError("У подрядчика в этом проекте есть этапы или полученные бонусы — сначала удалите их")
            self.run("DELETE FROM project_contractors WHERE id=?", rid)
            self.audit(who, "delete", "link", rid, link)
            return self.project(link["project_id"])
        if entity == "stage":
            st = self.one("SELECT * FROM stages WHERE id=?", rid)
            if not st:
                raise CrmError("Этап не найден")
            self.run("UPDATE ops SET stage_id=NULL WHERE stage_id=?", rid)      # полученные бонусы остаются за подрядчиком
            self.run("DELETE FROM stages WHERE id=?", rid)
            self.audit(who, "delete", "stage", rid, st)
            self.touch(st["project_id"])
            return self.project(st["project_id"])
        if entity == "file":
            f = self.one("SELECT * FROM files WHERE id=?", rid)
            if not f:
                raise CrmError("Файл не найден")
            trash = os.path.join(self.trash_dir, today().isoformat())   # 30 дней в корзине, потом удаляется
            for p in (f["path"], f["thumb"]):
                if p:
                    try:
                        os.makedirs(trash, exist_ok=True)
                        os.replace(os.path.join(self.files_dir, p), os.path.join(trash, f"{f['project_id']}-{os.path.basename(p)}"))
                    except OSError:
                        pass
            self.run("DELETE FROM files WHERE id=?", rid)
            self.audit(who, "delete", "file", rid, f)
            return self.project(f["project_id"])
        if entity == "lead":
            return self.delete_leads([rid], who)
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
        all_rows = self.project_rows()
        owing = [p for p in all_rows if p["status"] in ("active", "paused") and p["balance"] > 0.005]
        names = {p["id"]: p for p in all_rows}
        # подрядчики должны бонусы: по всем проектам, кроме отменённых; по подрядчику и его проектам
        people = {c["id"]: c for c in self.q("SELECT id, name, trade FROM contractors")}
        owe = {}
        for m in self.link_money().values():
            pr = names.get(m["project_id"])
            if m["debt"] <= 0 or not pr or pr["status"] == "cancelled":
                continue
            c = owe.setdefault(m["contractor_id"], {"id": m["contractor_id"], "name": (people.get(m["contractor_id"]) or {}).get("name", "—"),
                                                     "trade": m["trade"] or (people.get(m["contractor_id"]) or {}).get("trade") or "",
                                                     "debt_eur": 0.0, "projects": []})
            c["debt_eur"] += m["debt_eur"]
            c["projects"].append({"id": pr["id"], "number": pr["number"] or "", "title": pr["title"], "debt": m["debt"],
                                  "currency": m["currency"], "debt_eur": m["debt_eur"]})
        owe_list = sorted(owe.values(), key=lambda c: -c["debt_eur"])
        # бонусы за период — от кого
        sources = {}
        for o in rows:
            if o["kind"] == "commission":
                k = o["counterparty"] or "Не указано"
                sources[k] = sources.get(k, 0) + o["amount_eur"]
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
            "contractors_owe": round(sum(c["debt_eur"] for c in owe_list), 2),
            "owe_contractors": [dict(c, debt_eur=round(c["debt_eur"], 2)) for c in owe_list[:15]],
            "bonus_sources": [[k, round(v, 2)] for k, v in sorted(sources.items(), key=lambda kv: -kv[1])[:8] if abs(v) > 0.005],
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
        status = {p["id"]: p["status"] for p in projects}
        links = []
        for m in self.link_money().values():
            links.append({k: m[k] for k in ("link_id", "project_id", "contractor_id", "trade", "currency", "expected", "received",
                                            "debt", "expected_eur", "received_eur", "debt_eur", "unknown", "order", "order_eur")}
                         | {"stages": len(m["stages"])})
        for c in contractors:
            mine = [x for x in links if x["contractor_id"] == c["id"] and status.get(x["project_id"]) != "cancelled"]
            c["debt_eur"] = round(sum(x["debt_eur"] for x in mine), 2)
            c["received_eur"] = round(sum(x["received_eur"] for x in mine), 2)
        cities = sorted({x for x in [p["city"] for p in projects] + [c["city"] for c in clients] + [c["city"] for c in contractors] if x})
        leads_new = self.one("SELECT COUNT(*) AS n FROM leads WHERE status='new' AND deleted IS NULL")["n"]
        return {"projects": projects, "clients": clients, "contractors": contractors, "links": links, "cities": cities,
                "lists": self.lists(), "disk": self.disk(), "leads_new": leads_new}

    # ---------- копии ----------
    def backup_if_due(self, log=print):
        """Раз в день — копия базы студии (и базы бота) в ~/dumskaya/backups; старше 30 дней — удаляются.
        Заодно из корзины удаляются файлы, удалённые больше 30 дней назад."""
        d = today().isoformat()
        if self.setting("backup_day") == d:
            return False
        backup_dbs([(self.path, "crm")] + [(p, os.path.splitext(os.path.basename(p))[0]) for p in self.extra_backups],
                   self.backup_dir, d, log)
        cutoff = (today() - timedelta(days=BACKUP_KEEP)).isoformat()
        for f in os.listdir(self.backup_dir):
            m = re.search(r"-(\d{4}-\d{2}-\d{2})\.db$", f)
            if m and m.group(1) < cutoff:
                try:
                    os.remove(os.path.join(self.backup_dir, f))
                except OSError:
                    pass
        if os.path.isdir(self.trash_dir):
            old = (today() - timedelta(days=TRASH_KEEP)).isoformat()
            for day_dir in os.listdir(self.trash_dir):
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day_dir) and day_dir < old:
                    shutil.rmtree(os.path.join(self.trash_dir, day_dir), ignore_errors=True)
        self.purge_leads()
        self.setting("backup_day", d)
        return True


if __name__ == "__main__":
    if "--backup-now" in sys.argv:          # npm run backup на Маке: свежая копия перед скачиванием
        made = backup_dbs([(CRM_DB, "crm"), (BOT_DB, "bot")], BACKUP_DIR, today().isoformat())
        print("копии: " + (", ".join(os.path.basename(x) for x in made) or "баз пока нет"))
    else:
        print(__doc__)
