#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Кабинеты в боте студии («Мой проект»): заказчик, подрядчик, работник подрядчика, наблюдатель — и разговоры
и документы проекта с правами доступа (решено 24.10.2026).

Кто как попадает в бот (у каждого — личная ссылка t.me/<бот>?start=pj_…, на 14 дней, одноразовая):
  • заказчик — ссылку даёт Ирина из проекта;
  • подрядчик (руководитель: хозяин мебельной фабрики, прораб…) — ссылку Ирина даёт ОДИН раз (из карточки подрядчика
    или из проекта); дальше он видит все проекты, в которые его добавили;
  • работник подрядчика (технолог, установщик…) — ссылку даёт сам подрядчик из кабинета («Бригада»); на каждый проект
    подрядчик сам отмечает, кто из бригады там работает (подключённый работник не попадает во все проекты сразу);
  • наблюдатель «Разработчик ПО» — подрядчик-заглушка для тестирования: видит все проекты, все разговоры и документы
    (только чтение); заказчики и подрядчики его не видят; удалить — как обычного подрядчика в «Студии» (Контакты).

Что кто видит:
  • заказчик — оплаты, долг, доп. услуги, товары (без закупки), документы студии (кроме «Другое»), документы подрядчиков,
    открытые для заказчика, и согласованные студией вложения разговоров; подрядчиков (руководителей) с контактами
    и суммами работ; разговоры: со студией и с каждым подрядчиком (студия видит, но не вмешивается, пока не напишет);
  • подрядчик — свой подряд (суммы, 10 % студии), контакты заказчиков, документацию студии, документы своей бригады;
    разговоры: со студией, с заказчиками, группы, где он есть, и переписку студии со своими работниками (только чтение);
  • работник — проект без денег (ни суммы проекта, ни вознаграждения студии), контакты руководителя и студии,
    документацию, документы бригады, открытые для неё; разговоры — свой со студией и группы, куда его добавили.
    Заказчику писать не может (и заказчик ему — только руководителю).
  • Ирина (студия) — всё; пишет любому участнику, собирает группы, решает, видит ли заказчик документ.
Документы подрядчика: «заказчик, студия и бригада», «только студия», «только бригада»; работника — «руководитель и
студия», «вся бригада», «заказчик тоже». Ирина видит всё и может открыть любой документ заказчику.
Только стандартная библиотека Python 3."""
import hashlib
import json
import secrets
from datetime import date, datetime, timedelta, timezone

from crm import CLIENT_CATS, CONTRACTOR_CATS, FILE_CATS, CrmError, _text, now, today

INVITE_DAYS = 14
MSG_MAX = 4000
REMIND_WINDOW = 60                 # о начислениях старше 60 дней не напоминаем (это уже разговор, а не напоминание)
UI_LANGS = ("ru", "uk", "en", "sk", "de")
STUDIO = {"name": "DUMSKAYA DESIGN", "designer": {"ru": "Ирина Думская", "uk": "Ірина Думська"}, "designer_latin": "Irina Dumskaya",
          "phone": "+421 918 17 77 85", "email": "irina@dumskaya-design.com", "site": "https://dumskaya-design.com"}
OBSERVER_NAME = "Разработчик ПО"
THREAD_KINDS = ("client", "pc", "org", "worker", "group")
VIS_HEAD = ("client", "studio", "team")        # документ подрядчика: заказчик, студия и бригада / только студия / бригада
VIS_CREW = ("head", "team", "client")          # документ работника: руководитель и студия / вся бригада / заказчик тоже

# виды работ и пакеты из справочников «Студии» — в кабинете на языке человека (пакеты — как на сайте);
# остальные названия (услуги, товары, этапы) переводятся сервисом перевода и запоминаются
FIXED = {
    "Прораб": ("Виконроб", "Site manager", "Stavbyvedúci", "Bauleiter"),
    "Мебельщик": ("Меблевик", "Furniture maker", "Stolár", "Tischler"),
    "Шторница": ("Штори", "Curtains", "Záclony a závesy", "Vorhänge"),
    "Кондиционерщик": ("Кондиціонери", "Air conditioning", "Klimatizácia", "Klimaanlage"),
    "Двери": ("Двері", "Doors", "Dvere", "Türen"),
    "Окна": ("Вікна", "Windows", "Okná", "Fenster"),
    "Электрик": ("Електрик", "Electrician", "Elektrikár", "Elektriker"),
    "Сантехник": ("Сантехнік", "Plumber", "Inštalatér", "Installateur"),
    "Плиточник": ("Плиточник", "Tiler", "Obkladač", "Fliesenleger"),
    "Маляр": ("Маляр", "Painter", "Maliar", "Maler"),
    "Полы": ("Підлога", "Flooring", "Podlahy", "Böden"),
    "Свет": ("Світло", "Lighting", "Svetlo", "Licht"),
    "Камень и столешницы": ("Камінь і стільниці", "Stone and worktops", "Kameň a pracovné dosky", "Stein und Arbeitsplatten"),
    "Стекло и зеркала": ("Скло і дзеркала", "Glass and mirrors", "Sklo a zrkadlá", "Glas und Spiegel"),
    "Другое": ("Інше", "Other", "Iné", "Sonstiges"),
    "Экспресс": ("Експрес", "Express", "Express", "Express"),
    "Мебель": ("Меблі", "Furniture", "Nábytok", "Möbel"),
    "Базовый": ("Базовий", "Basic", "Základný", "Basis"),
    "Премиум": ("Преміум", "Premium", "Premium", "Premium"),
    "Премиум+": ("Преміум+", "Premium+", "Premium+", "Premium+"),
    "Авторское сопровождение": ("Авторський нагляд", "Design supervision", "Autorský dozor", "Künstlerische Oberleitung"),
    "Индивидуальный": ("Індивідуальний", "Custom", "Individuálny", "Individuell"),
}
FIXED_LANGS = ("uk", "en", "sk", "de")


def ui_lang(code):
    """Язык кабинета по коду Telegram: ru, uk, en, sk, de; чешский — словацкий, белорусский — русский, остальное — английский."""
    c = (code or "").lower().split("-")[0]
    return c if c in UI_LANGS else {"cs": "sk", "be": "ru"}.get(c, "en")


def _pick(row, keys):
    return {k: row.get(k) for k in keys}


class Portal:
    def __init__(self, crm):
        self.crm = crm

    def _count(self, sql, *args):
        with self.crm.lock:
            return self.crm.db.execute(sql, args).rowcount

    # ---------- кто есть кто ----------
    def is_observer(self, tg_id):
        return bool(tg_id) and bool(self.crm.one("SELECT id FROM contractors WHERE observer=1 AND tg_id=?", int(tg_id)))

    def observers(self):
        return self.crm.q("SELECT * FROM contractors WHERE observer=1 AND tg_id IS NOT NULL")

    def ensure_observer(self, owner_tg):
        """Подрядчик «Разработчик ПО» для тестирования — привязан к Telegram разработчика, видит всё (только чтение).
        Создаётся один раз: удалили в «Студии» — больше не появится."""
        if not owner_tg or self.crm.setting("observer_created"):
            return None
        cid = self.crm.run("INSERT INTO contractors(name, trade, note, observer, tg_id, tg_name, tg_since, created, updated) "
                           "VALUES(?, 'Другое', ?, 1, ?, 'Разработчик', ?, ?, ?)", OBSERVER_NAME,
                           "Наблюдатель для тестирования: видит все проекты, разговоры и документы в кабинетах (только чтение). "
                           "Заказчики и подрядчики его не видят. Удалить, когда тестирование закончится.", int(owner_tg), now(), now(), now())
        self.crm.setting("observer_created", now())
        self.crm.audit("система", "add", "contractor", cid, {"observer": True})
        return cid

    def client_of(self, tg_id, pid):
        """Запись заказчика этого проекта, к которой привязан Telegram (или None)."""
        t = int(tg_id or 0)
        p = self.crm.one("SELECT status FROM projects WHERE id=?", int(pid or 0))
        if not t or not p or p["status"] == "cancelled":
            return None
        return next((c for c in self.crm.project_people(int(pid)) if c.get("tg_id") == t), None)

    def contractor_ids(self, tg_id, pid):
        """Подрядчики (руководители), привязанные к этому Telegram и работающие в проекте (наблюдатель — нет)."""
        t = int(tg_id or 0)
        if not t:
            return []
        return [r["contractor_id"] for r in self.crm.q(
            """SELECT DISTINCT l.contractor_id FROM project_contractors l JOIN contractors c ON c.id=l.contractor_id
               JOIN projects p ON p.id=l.project_id WHERE l.project_id=? AND c.tg_id=? AND c.observer IS NULL
               AND p.status != 'cancelled'""", int(pid or 0), t)]

    def crew_ids(self, tg_id, pid):
        """Работники (записи бригад) с этим Telegram, которых их подрядчик отметил на этом объекте."""
        t = int(tg_id or 0)
        if not t:
            return []
        return [r["id"] for r in self.crm.q(
            """SELECT DISTINCT w.id FROM crew w JOIN project_crew x ON x.crew_id=w.id
               JOIN project_contractors l ON l.project_id=x.project_id AND l.contractor_id=w.contractor_id
               JOIN projects p ON p.id=x.project_id WHERE x.project_id=? AND w.tg_id=? AND w.removed IS NULL
               AND p.status != 'cancelled'""", int(pid or 0), t)]

    def viewer(self, tg_id, pid, designer=False):
        """Кто смотрит этот проект: студия, наблюдатель, заказчик, руководитель подрядчика, работник (может быть несколько ролей)."""
        t = int(tg_id or 0)
        if designer:
            return {"tg": t, "studio": True, "observer": False, "client": None, "heads": set(), "crew": set()}
        return {"tg": t, "studio": False, "observer": self.is_observer(t), "client": self.client_of(t, pid),
                "heads": set(self.contractor_ids(t, pid)), "crew": set(self.crew_ids(t, pid))}

    def has_cabinet(self, tg_id):
        """Есть ли у Telegram кабинет: заказчик проекта (не отменённого), подключённый подрядчик, работник бригады
        или наблюдатель. Подрядчик и работник без текущих проектов кабинет не теряют — их подключают один раз."""
        t = int(tg_id or 0)
        if not t:
            return False
        if self.crm.one("SELECT id FROM contractors WHERE tg_id=?", t) or self.crm.one("SELECT id FROM crew WHERE tg_id=? AND removed IS NULL", t):
            return True
        return any("client" in p["roles"] for p in self.projects_for(t))

    def crews_of(self, tg_id):
        """Записи бригад, к которым привязан этот Telegram (с именем подрядчика)."""
        return self.crm.q("""SELECT w.*, c.name AS head_name FROM crew w JOIN contractors c ON c.id=w.contractor_id
                             WHERE w.tg_id=? AND w.removed IS NULL ORDER BY w.id""", int(tg_id or 0))

    def default_threads(self, tg_id):
        """Куда идёт сообщение, написанное прямо в чат бота (без ответа свайпом): заказчику — разговор со студией,
        подрядчику — его разговор со студией, работнику — его разговор со студией. [(проект, разговор)]"""
        t = int(tg_id or 0)
        out = []
        for p in self.projects_for(t):
            v = self.viewer(t, p["id"])
            th = None
            if v["client"]:
                th = self.ensure_thread(p["id"], "client")
            elif v["heads"]:
                th = self.ensure_thread(p["id"], "org", contractor_id=sorted(v["heads"])[0])
            elif v["crew"]:
                th = self.ensure_thread(p["id"], "worker", crew_id=sorted(v["crew"])[0])
            if th:
                out.append((p, th))
        return out

    def author(self, v, t):
        """Кто пишет в этот разговор: (вид автора, имя) — по записи в учёте (как его знает студия)."""
        k = t["kind"]
        if v["studio"]:
            return "studio", STUDIO["designer"]["ru"]
        if v["client"] and (k == "client" or (k == "pc" and t["contractor_id"] not in v["heads"])):
            return "client", v["client"].get("name") or ""
        head = None
        if k in ("org", "pc") and t["contractor_id"] in v["heads"]:
            head = t["contractor_id"]
        elif k == "group":
            mem = self.members(t["id"])
            head = next((m["ref_id"] for m in mem if m["kind"] == "contractor" and m["ref_id"] in v["heads"]), None)
            if head is None:
                wid = next((m["ref_id"] for m in mem if m["kind"] == "crew" and m["ref_id"] in v["crew"]), None)
                if wid:
                    w = self.crm.one("SELECT name FROM crew WHERE id=?", wid) or {}
                    return "crew", w.get("name") or ""
        if head:
            c = self.crm.one("SELECT name FROM contractors WHERE id=?", head) or {}
            return "contractor", c.get("name") or ""
        if k == "worker" and t["crew_id"] in v["crew"]:
            w = self.crm.one("SELECT name FROM crew WHERE id=?", t["crew_id"]) or {}
            return "crew", w.get("name") or ""
        raise CrmError("Нет доступа")

    def projects_for(self, tg_id):
        """Проекты в кабинете и роли в них: client, contractor, worker, observer (отменённые проекты — нет)."""
        t = int(tg_id or 0)
        out = {}
        cols = "p.id, p.title, p.number, p.city, p.status, p.started"

        def add(rows, role):
            for p in rows:
                x = out.setdefault(p["id"], dict(p, roles=[]))
                if role not in x["roles"]:
                    x["roles"].append(role)
        add(self.crm.q(f"""SELECT DISTINCT {cols} FROM projects p WHERE p.status != 'cancelled' AND
                           (p.client_id IN (SELECT id FROM clients WHERE tg_id=?) OR p.id IN (SELECT x.project_id FROM project_clients x
                            JOIN clients c ON c.id=x.client_id WHERE c.tg_id=?))""", t, t), "client")
        add(self.crm.q(f"""SELECT DISTINCT {cols} FROM projects p JOIN project_contractors l ON l.project_id=p.id
                           JOIN contractors c ON c.id=l.contractor_id WHERE p.status != 'cancelled' AND c.tg_id=? AND c.observer IS NULL""", t),
            "contractor")
        add(self.crm.q(f"""SELECT DISTINCT {cols} FROM projects p JOIN project_crew x ON x.project_id=p.id JOIN crew w ON w.id=x.crew_id
                           JOIN project_contractors l ON l.project_id=p.id AND l.contractor_id=w.contractor_id
                           WHERE p.status != 'cancelled' AND w.tg_id=? AND w.removed IS NULL""", t), "worker")
        if self.is_observer(t):
            add(self.crm.q(f"SELECT {cols} FROM projects p WHERE p.status != 'cancelled'"), "observer")
        for p in out.values():
            v = self.viewer(t, p["id"])
            p["unread"] = 0 if p["roles"] == ["observer"] else sum(x["unread"] for x in self.threads_for(v, p["id"]) if x.get("id"))
        return sorted(out.values(), key=lambda p: (p["status"] not in ("active", "paused"), -(p["id"])))

    # ---------- приглашения и привязка Telegram ----------
    TABLES = {"client": "clients", "contractor": "contractors", "crew": "crew"}

    def _record(self, kind, ref_id):
        if kind not in self.TABLES:
            raise CrmError("Неизвестно, кого приглашать")
        rec = self.crm.one(f"SELECT * FROM {self.TABLES[kind]} WHERE id=?", int(ref_id or 0))
        if not rec or (kind == "crew" and rec["removed"]):
            raise CrmError("Человек не найден")
        if kind == "contractor" and rec["observer"]:
            raise CrmError("Наблюдателю ссылка не нужна — он уже подключён")
        return rec

    def make_invite(self, kind, ref_id, project_id, lang, who):
        """Одноразовая ссылка в бот. Заказчик должен быть в проекте; подрядчику ссылка нужна один раз — проект не обязателен;
        работнику ссылку даёт его подрядчик. Прежняя неиспользованная ссылка этому же человеку перестаёт действовать."""
        rec = self._record(kind, ref_id)
        pid = int(project_id or 0) or None
        if kind == "client" and not any(c["id"] == rec["id"] for c in self.crm.project_people(pid or 0)):
            raise CrmError("Сначала добавьте заказчика в проект")
        if kind == "contractor" and pid and not self.crm.one("SELECT id FROM project_contractors WHERE project_id=? AND contractor_id=?",
                                                             pid, rec["id"]):
            pid = None
        self.crm.run("DELETE FROM invites WHERE expires < ?", (datetime.now(timezone.utc) - timedelta(days=30)).isoformat())
        self.crm.run("DELETE FROM invites WHERE kind=? AND ref_id=? AND used_by IS NULL", kind, rec["id"])
        token = secrets.token_urlsafe(12)
        expires = (datetime.now(timezone.utc) + timedelta(days=INVITE_DAYS)).isoformat(timespec="seconds")
        self.crm.run("INSERT INTO invites(token, kind, ref_id, project_id, lang, created_by, created, expires) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                     token, kind, rec["id"], pid, ui_lang(lang), who, now(), expires)
        self.crm.audit(who, "add", "access", rec["id"], {"project_id": pid, "kind": kind, "invite": True})
        return {"token": token, "expires": expires, "name": rec["name"], "kind": kind, "lang": ui_lang(lang), "project_id": pid}

    def invite(self, token):
        """Действующее приглашение или None."""
        inv = self.crm.one("SELECT * FROM invites WHERE token=?", str(token or "")[:40])
        if not inv or inv["used_by"] or inv["expires"] < now():
            return None
        return inv

    def use_invite(self, token, tg_id, tg_name):
        """Привязать Telegram по ссылке. None — ссылка недействительна. Если к записи уже был привязан другой Telegram —
        он теряет доступ (replaced)."""
        inv = self.invite(token)
        if not inv or not self._count("UPDATE invites SET used_by=?, used=? WHERE token=? AND used_by IS NULL",
                                      int(tg_id), now(), inv["token"]):
            return None
        table = self.TABLES.get(inv["kind"])
        rec = self.crm.one(f"SELECT * FROM {table} WHERE id=?", inv["ref_id"]) if table else None
        if not rec or (inv["kind"] == "crew" and rec["removed"]):
            return None
        self.crm.run(f"UPDATE {table} SET tg_id=?, tg_name=?, tg_since=?, updated=? WHERE id=?",
                     int(tg_id), _text(tg_name, 120), now(), now(), rec["id"])
        self.crm.audit(_text(tg_name, 120) or str(tg_id), "edit", "access", rec["id"],
                       {"project_id": inv["project_id"], "kind": inv["kind"], "joined": True})
        p = self.crm.one("SELECT id, title, number FROM projects WHERE id=?", inv["project_id"] or 0) or {}
        head = self.crm.one("SELECT * FROM contractors WHERE id=?", rec["contractor_id"]) if inv["kind"] == "crew" else None
        return {"kind": inv["kind"], "ref": dict(rec, tg_id=int(tg_id)), "project": p, "lang": inv["lang"], "by": inv["created_by"],
                "head": head, "replaced": rec["tg_id"] if rec["tg_id"] and int(rec["tg_id"]) != int(tg_id) else None}

    def unlink(self, kind, ref_id, who):
        """Закрыть кабинет: Telegram отвязывается от записи. Возвращает отвязанный Telegram ID (или None)."""
        if kind not in self.TABLES:
            raise CrmError("Неизвестно, кому закрыть кабинет")
        rec = self.crm.one(f"SELECT * FROM {self.TABLES[kind]} WHERE id=?", int(ref_id or 0))
        if not rec:
            raise CrmError("Человек не найден")
        self.crm.run(f"UPDATE {self.TABLES[kind]} SET tg_id=NULL, tg_name=NULL, tg_since=NULL, updated=? WHERE id=?", now(), rec["id"])
        self.crm.run("DELETE FROM invites WHERE kind=? AND ref_id=? AND used_by IS NULL", kind, rec["id"])
        self.crm.audit(who, "delete", "access", rec["id"], {"kind": kind, "tg_id": rec["tg_id"]})
        return rec["tg_id"]

    # ---------- бригада подрядчика ----------
    def head_check(self, tg_id, contractor_id):
        c = self.crm.one("SELECT * FROM contractors WHERE id=? AND tg_id=? AND observer IS NULL", int(contractor_id or 0), int(tg_id or 0))
        if not c:
            raise CrmError("Нет доступа")
        return c

    def my_contractors(self, tg_id):
        return self.crm.q("SELECT * FROM contractors WHERE tg_id=? AND observer IS NULL ORDER BY id", int(tg_id or 0))

    def team(self, contractor_id, pid=None):
        """Работники подрядчика: кто подключён к боту, на каких объектах; assigned — на этом объекте."""
        rows = self.crm.q("SELECT * FROM crew WHERE contractor_id=? AND removed IS NULL ORDER BY name COLLATE NOCASE", int(contractor_id))
        on = {}
        for x in self.crm.q("""SELECT x.crew_id, p.id, p.title FROM project_crew x JOIN projects p ON p.id=x.project_id
                               WHERE p.status != 'cancelled' AND x.crew_id IN (SELECT id FROM crew WHERE contractor_id=?)""", int(contractor_id)):
            on.setdefault(x["crew_id"], []).append({"id": x["id"], "title": x["title"]})
        out = []
        for w in rows:
            inv = self.crm.one("SELECT expires FROM invites WHERE kind='crew' AND ref_id=? AND used_by IS NULL AND expires > ?", w["id"], now())
            out.append({"id": w["id"], "name": w["name"], "position": w["position"] or "", "phone": w["phone"] or "",
                        "tg": bool(w["tg_id"]), "tg_name": w["tg_name"] or "", "since": w["tg_since"],
                        "invite_until": inv["expires"] if inv else None, "projects": on.get(w["id"], []),
                        "assigned": bool(pid) and any(p["id"] == int(pid) for p in on.get(w["id"], []))})
        return out

    def crew_add(self, contractor_id, d, who):
        name = _text(d.get("name"), 120)
        if not name:
            raise CrmError("Напишите имя работника")
        cid = self.crm.run("INSERT INTO crew(contractor_id, name, position, phone, created_by, created, updated) VALUES(?, ?, ?, ?, ?, ?, ?)",
                           int(contractor_id), name, _text(d.get("position"), 80), _text(d.get("phone"), 60), who, now(), now())
        self.crm.audit(who, "add", "crew", cid, {"contractor_id": int(contractor_id), "name": name})
        return cid

    def crew_edit(self, crew_id, d, who):
        w = self.crew_get(crew_id)
        name = _text(d.get("name", w["name"]), 120)
        if not name:
            raise CrmError("Напишите имя работника")
        self.crm.run("UPDATE crew SET name=?, position=?, phone=?, updated=? WHERE id=?", name, _text(d.get("position", w["position"]), 80),
                     _text(d.get("phone", w["phone"]), 60), now(), w["id"])
        self.crm.audit(who, "edit", "crew", w["id"], {"contractor_id": w["contractor_id"], "name": name})
        return w["id"]

    def crew_get(self, crew_id, contractor_id=None):
        w = self.crm.one("SELECT * FROM crew WHERE id=? AND removed IS NULL", int(crew_id or 0))
        if not w or (contractor_id is not None and w["contractor_id"] != int(contractor_id)):
            raise CrmError("Работник не найден")
        return w

    def crew_remove(self, crew_id, who):
        """Убрать из бригады: доступ к боту закрывается, со всех объектов снимается. Возвращает его Telegram ID."""
        w = self.crew_get(crew_id)
        self.crm.run("UPDATE crew SET removed=?, tg_id=NULL, updated=? WHERE id=?", now(), now(), w["id"])
        self.crm.run("DELETE FROM project_crew WHERE crew_id=?", w["id"])
        self.crm.run("DELETE FROM invites WHERE kind='crew' AND ref_id=? AND used_by IS NULL", w["id"])
        self.crm.audit(who, "delete", "crew", w["id"], {"contractor_id": w["contractor_id"]})
        return w["tg_id"]

    def crew_assign(self, pid, crew_id, on, who):
        """Работник на этом объекте (или нет). Подрядчик работника должен быть в проекте."""
        w = self.crew_get(crew_id)
        pid = int(pid or 0)
        if not self.crm.one("SELECT id FROM project_contractors WHERE project_id=? AND contractor_id=?", pid, w["contractor_id"]):
            raise CrmError("Подрядчика этого работника нет в проекте")
        was = bool(self.crm.one("SELECT 1 FROM project_crew WHERE project_id=? AND crew_id=?", pid, w["id"]))
        if on and not was:
            self.crm.run("INSERT INTO project_crew(project_id, crew_id, created_by, created) VALUES(?, ?, ?, ?)", pid, w["id"], who, now())
        elif not on and was:
            self.crm.run("DELETE FROM project_crew WHERE project_id=? AND crew_id=?", pid, w["id"])
        if bool(on) != was:
            self.crm.audit(who, "add" if on else "delete", "pcrew", w["id"], {"project_id": pid, "crew_id": w["id"]})
        return {"changed": bool(on) != was, "crew": w}

    def participants(self, pid):
        """Все подключённые к проекту (для Ирины и наблюдателя): заказчики, подрядчики (без наблюдателя) и их бригада."""
        pid = int(pid)
        clients = [{"id": c["id"], "name": c["name"], "tg": bool(c.get("tg_id")), "tg_name": c.get("tg_name") or "", "main": c.get("main")}
                   for c in self.crm.project_people(pid)]
        out = []
        for k in self.crm.q("""SELECT l.id AS link_id, l.trade AS link_trade, c.* FROM project_contractors l JOIN contractors c ON c.id=l.contractor_id
                              WHERE l.project_id=? AND c.observer IS NULL ORDER BY l.id""", pid):
            if any(x["id"] == k["id"] for x in out):
                continue
            out.append({"id": k["id"], "link_id": k["link_id"], "name": k["name"], "trade": k["link_trade"] or k["trade"] or "",
                        "company": k["company"] or "", "tg": bool(k["tg_id"]), "tg_name": k["tg_name"] or "",
                        "crew": [dict(w, projects=None) for w in self.team(k["id"], pid)]})
        return {"clients": clients, "contractors": out}

    # ---------- разговоры ----------
    def thread(self, tid):
        return self.crm.one("SELECT * FROM threads WHERE id=?", int(tid or 0))

    def members(self, tid):
        return self.crm.q("SELECT kind, ref_id FROM thread_members WHERE thread_id=? ORDER BY kind, ref_id", int(tid))

    def _linked(self, pid, contractor_id):
        c = self.crm.one("""SELECT c.* FROM project_contractors l JOIN contractors c ON c.id=l.contractor_id
                            WHERE l.project_id=? AND c.id=? AND c.observer IS NULL""", int(pid), int(contractor_id or 0))
        if not c:
            raise CrmError("Этого подрядчика нет в проекте")
        return c

    def ensure_thread(self, pid, kind, contractor_id=None, crew_id=None, who=""):
        """Разговор проекта (создаётся при первом обращении): client, pc и org — с подрядчиком, worker — с работником."""
        pid = int(pid or 0)
        if kind not in ("client", "pc", "org", "worker"):
            raise CrmError("Неизвестный разговор")
        if not self.crm.one("SELECT id FROM projects WHERE id=?", pid):
            raise CrmError("Проект не найден")
        cid = wid = None
        if kind in ("pc", "org"):
            cid = self._linked(pid, contractor_id)["id"]
        if kind == "worker":
            w = self.crew_get(crew_id)
            self._linked(pid, w["contractor_id"])
            wid = w["id"]
        t = self.crm.one("SELECT * FROM threads WHERE project_id=? AND kind=? AND COALESCE(contractor_id, 0)=? AND COALESCE(crew_id, 0)=?",
                         pid, kind, cid or 0, wid or 0)
        if t:
            return t
        tid = self.crm.run("INSERT INTO threads(project_id, kind, contractor_id, crew_id, created_by, created, updated) VALUES(?, ?, ?, ?, ?, ?, ?)",
                           pid, kind, cid, wid, _text(who, 120), now(), now())
        return self.thread(tid)

    def save_group(self, pid, d, who):
        """Группа, которую собирает Ирина: название и участники — подрядчики (руководители) и работники их бригад.
        Работник, которого ещё не отметили на этом объекте, отмечается сам."""
        pid = int(pid or 0)
        title = _text(d.get("title"), 120)
        if not title:
            raise CrmError("Назовите группу, например «Кухня: технолог»")
        mem = set()
        for m in d.get("members") or []:
            kind, ref = (m.get("kind"), m.get("id")) if isinstance(m, dict) else m
            if kind == "contractor":
                mem.add(("contractor", self._linked(pid, ref)["id"]))
            elif kind == "crew":
                w = self.crew_get(ref)
                self._linked(pid, w["contractor_id"])
                self.crew_assign(pid, w["id"], True, who)
                mem.add(("crew", w["id"]))
        if not mem:
            raise CrmError("Добавьте в группу хотя бы одного человека")
        tid = int(d.get("id") or 0)
        if tid:
            t = self.thread(tid)
            if not t or t["project_id"] != pid or t["kind"] != "group":
                raise CrmError("Группа не найдена")
            self.crm.run("UPDATE threads SET title=?, updated=? WHERE id=?", title, now(), tid)
            self.crm.run("DELETE FROM thread_members WHERE thread_id=?", tid)
        else:
            tid = self.crm.run("INSERT INTO threads(project_id, kind, title, created_by, created, updated) VALUES(?, 'group', ?, ?, ?, ?)",
                               pid, title, _text(who, 120), now(), now())
        for kind, ref in sorted(mem):
            self.crm.run("INSERT INTO thread_members(thread_id, kind, ref_id) VALUES(?, ?, ?)", tid, kind, ref)
        self.crm.audit(who, "edit" if d.get("id") else "add", "thread", tid, {"project_id": pid, "title": title, "members": sorted(mem)})
        return self.thread(tid)

    def access(self, v, t):
        """Что этот человек может с разговором: write — читать и писать, read — только читать, None — не видит."""
        if not t:
            return None
        if v["studio"]:
            return "write"
        best = "read" if v["observer"] else None
        k = t["kind"]
        if v["client"] and k in ("client", "pc"):
            return "write"
        heads, crew = v["heads"], v["crew"]
        if k in ("org", "pc") and t["contractor_id"] in heads:
            return "write"
        if k == "worker":
            if t["crew_id"] in crew:
                return "write"
            w = self.crm.one("SELECT contractor_id FROM crew WHERE id=?", t["crew_id"])
            if w and w["contractor_id"] in heads:
                best = "read"                    # подрядчик видит переписку студии со своим работником
        if k == "group":
            mem = self.members(t["id"])
            if any(m["kind"] == "contractor" and m["ref_id"] in heads for m in mem) or \
                    any(m["kind"] == "crew" and m["ref_id"] in crew for m in mem):
                return "write"
            if heads:
                mine = {w["id"] for w in self.crm.q(f"SELECT id FROM crew WHERE contractor_id IN ({','.join('?' * len(heads))})", *heads)}
                if any(m["kind"] == "crew" and m["ref_id"] in mine for m in mem):
                    best = "read"
        return best

    def thread_info(self, t, v, acc=None, lang=None):
        """Разговор для списка: кто в нём, последнее сообщение (с переводом на язык lang, если есть), непрочитанные."""
        acc = acc or self.access(v, t)
        out = {"id": t["id"], "kind": t["kind"], "title": t["title"] or "", "access": acc, "studio_joined": bool(t["studio_joined"]),
               "contractor": None, "crew": None, "members": []}
        if t["contractor_id"]:
            c = self.crm.one("SELECT id, name, trade, company FROM contractors WHERE id=?", t["contractor_id"]) or {}
            link = self.crm.one("SELECT trade FROM project_contractors WHERE project_id=? AND contractor_id=?", t["project_id"], t["contractor_id"]) or {}
            out["contractor"] = {"id": c.get("id"), "name": c.get("name") or "", "trade": link.get("trade") or c.get("trade") or "",
                                 "company": c.get("company") or ""}
        if t["crew_id"]:
            w = self.crm.one("SELECT w.id, w.name, w.position, c.name AS head FROM crew w JOIN contractors c ON c.id=w.contractor_id WHERE w.id=?",
                             t["crew_id"]) or {}
            out["crew"] = {"id": w.get("id"), "name": w.get("name") or "", "position": w.get("position") or "", "head": w.get("head") or ""}
        if t["kind"] == "group":
            for m in self.members(t["id"]):
                if m["kind"] == "contractor":
                    c = self.crm.one("SELECT name, trade FROM contractors WHERE id=?", m["ref_id"]) or {}
                    out["members"].append({"kind": "contractor", "id": m["ref_id"], "name": c.get("name") or "", "role": c.get("trade") or ""})
                else:
                    w = self.crm.one("SELECT w.name, w.position, c.name AS head FROM crew w JOIN contractors c ON c.id=w.contractor_id WHERE w.id=?",
                                     m["ref_id"]) or {}
                    out["members"].append({"kind": "crew", "id": m["ref_id"], "name": w.get("name") or "",
                                           "role": " · ".join(x for x in (w.get("position"), w.get("head")) if x)})
        last = self.crm.one("SELECT * FROM messages WHERE thread_id=? AND deleted IS NULL ORDER BY id DESC LIMIT 1", t["id"])
        out["count"] = self.crm.one("SELECT COUNT(*) AS n FROM messages WHERE thread_id=? AND deleted IS NULL", t["id"])["n"]
        tr = {}
        if last and lang:
            try:
                tr = json.loads(last["tr"] or "{}") or {}
            except ValueError:
                tr = {}
        out["last"] = {"author_kind": last["author_kind"], "author_name": last["author_name"], "created": last["created"],
                       "text": tr.get(lang) or last["text"] or "", "file": bool(last["file_id"])} if last else None
        if lang and lang != "ru":                    # вид работ — на языке человека
            for k in ("contractor",):
                if out[k] and out[k].get("trade"):
                    out[k]["trade"] = self.label(out[k]["trade"], lang) or out[k]["trade"]
            for m in out["members"]:
                if m["kind"] == "contractor" and m["role"]:
                    m["role"] = self.label(m["role"], lang) or m["role"]
        out["updated"] = last["created"] if last else t["created"]
        out["unread"] = 0 if (v["observer"] and not v["studio"]) or v.get("preview") else self.unread(t["id"], v)
        return out

    def threads_for(self, v, pid, lang=None):
        """Разговоры проекта, которые человек видит. Свои разговоры по умолчанию создаются сами: заказчику — со студией,
        подрядчику — со студией, работнику — со студией. Заказчику — ещё «написать подрядчику» (start)."""
        pid = int(pid)
        if v["client"]:
            self.ensure_thread(pid, "client")
        for h in v["heads"]:
            self.ensure_thread(pid, "org", contractor_id=h)
        for w in v["crew"]:
            self.ensure_thread(pid, "worker", crew_id=w)
        out = []
        for t in self.crm.q("SELECT * FROM threads WHERE project_id=? ORDER BY id", pid):
            acc = self.access(v, t)
            if acc:
                out.append(self.thread_info(t, v, acc, lang))
        if v["client"]:                       # заказчик может написать любому подрядчику (руководителю), не работникам
            have = {x["contractor"]["id"] for x in out if x["kind"] == "pc" and x["contractor"]}
            for k in self.crm.q("""SELECT DISTINCT c.id, c.name, c.trade, c.company, l.trade AS link_trade FROM project_contractors l
                                   JOIN contractors c ON c.id=l.contractor_id WHERE l.project_id=? AND c.observer IS NULL
                                   AND c.tg_id IS NOT NULL""", pid):
                if k["id"] not in have:
                    trade = k["link_trade"] or k["trade"] or ""
                    out.append({"id": None, "kind": "pc", "start": True, "access": "write", "unread": 0, "count": 0, "last": None,
                                "contractor": {"id": k["id"], "name": k["name"], "trade": (self.label(trade, lang) or trade) if lang else trade,
                                               "company": k["company"] or ""}, "crew": None, "members": [], "updated": ""})
        def own(x):                                   # свой разговор со студией — первым
            return (x["kind"] == "client" and v["client"]) or (x["kind"] == "org" and (x["contractor"] or {}).get("id") in v["heads"]) or \
                (x["kind"] == "worker" and (x["crew"] or {}).get("id") in v["crew"])
        # дальше — свежие сверху; «только чтение» и «написать подрядчику» — в конце
        out.sort(key=lambda x: x.get("updated") or "", reverse=True)
        out.sort(key=lambda x: (not own(x), x.get("start", False), x["access"] == "read" and not v["studio"] and not v["observer"]))
        return out

    def post(self, tid, author_kind, author_tg, author_name, text, file_id=None):
        t = self.thread(tid)
        if not t:
            raise CrmError("Разговор не найден")
        text = str(text or "").strip()[:MSG_MAX]
        fid = int(file_id or 0) or None
        if fid and not self.crm.one("SELECT id FROM files WHERE id=? AND project_id=? AND category='chat'", fid, t["project_id"]):
            fid = None
        if not text and not fid:
            raise CrmError("Пустое сообщение")
        mid = self.crm.run("INSERT INTO messages(project_id, thread_id, author_kind, author_tg, author_name, text, file_id, created) "
                           "VALUES(?, ?, ?, ?, ?, ?, ?, ?)", t["project_id"], t["id"], author_kind, int(author_tg or 0) or None,
                           _text(author_name, 120), text, fid, now())
        if fid:
            self.crm.run("UPDATE files SET thread_id=? WHERE id=?", t["id"], fid)
        if author_kind == "studio" and t["kind"] == "pc" and not t["studio_joined"]:
            self.crm.run("UPDATE threads SET studio_joined=? WHERE id=?", now(), t["id"])   # студия вступила в разговор
        self.crm.run("UPDATE threads SET updated=? WHERE id=?", now(), t["id"])
        self.mark_read(t["id"], 0 if author_kind == "studio" else author_tg, mid)
        return self.message(mid)

    def message(self, mid):
        return self.crm.one("SELECT * FROM messages WHERE id=?", int(mid or 0))

    def set_translation(self, mid, lang, text, src_lang=None):
        with self.crm.lock:
            m = self.message(mid)
            if not m:
                return
            try:
                tr = json.loads(m["tr"] or "{}") or {}
            except ValueError:
                tr = {}
            tr[lang] = text
            self.crm.run("UPDATE messages SET tr=?, lang=COALESCE(?, lang) WHERE id=?", json.dumps(tr, ensure_ascii=False), src_lang, m["id"])

    def messages(self, tid, v, lang, after=0, limit=200):
        """Сообщения разговора: оригинал, перевод на язык читающего (если есть), вложение."""
        rows = self.crm.q("SELECT * FROM messages WHERE thread_id=? AND deleted IS NULL AND id>? ORDER BY id DESC LIMIT ?",
                          int(tid), int(after or 0), int(limit))
        out = []
        for m in reversed(rows):
            try:
                tr = json.loads(m["tr"] or "{}") or {}
            except ValueError:
                tr = {}
            f = self.crm.one("SELECT * FROM files WHERE id=?", m["file_id"]) if m["file_id"] else None
            mine = (m["author_kind"] == "studio") if v["studio"] else (bool(v["tg"]) and m["author_tg"] == v["tg"])
            out.append({"id": m["id"], "author_kind": m["author_kind"], "author_name": m["author_name"], "mine": mine,
                        "text": m["text"] or "", "tr": tr.get(lang), "lang": m["lang"], "created": m["created"],
                        "file": self._file_out(f, v) if f else None})
        return out

    def mark_read(self, tid, key, last_id):
        """Прочитано до сообщения last_id. key — Telegram ID или 0 (студия)."""
        self.crm.run("""INSERT INTO thread_read(thread_id, tg_id, last_id) VALUES(?, ?, ?)
                        ON CONFLICT(thread_id, tg_id) DO UPDATE SET last_id=MAX(last_id, excluded.last_id)""",
                     int(tid), int(key or 0), int(last_id or 0))

    def unread(self, tid, v):
        key = 0 if v["studio"] else v["tg"]
        r = self.crm.one("SELECT last_id FROM thread_read WHERE thread_id=? AND tg_id=?", int(tid), int(key))
        if v["studio"]:
            cond, args = "author_kind != 'studio'", ()
        else:
            cond, args = "(author_kind='studio' OR COALESCE(author_tg, 0) != ?)", (int(key),)
        return self.crm.one(f"SELECT COUNT(*) AS n FROM messages WHERE thread_id=? AND deleted IS NULL AND id>? AND {cond}",
                            int(tid), r["last_id"] if r else 0, *args)["n"]

    def recipients(self, tid, author_tg=None, author_kind=None):
        """Кому доставить новое сообщение в Telegram. studio — дизайнерам (громко или тихо: разговор заказчика с подрядчиком,
        пока студия в нём не писала, — тихо); people — [{tg, who, name, loud}] без автора; наблюдатель — тихая копия."""
        t = self.thread(tid)
        res = {}
        a = int(author_tg or 0)

        def add(tg, who, name, loud):
            if not tg or int(tg) == a:
                return
            p = res.get(int(tg))
            if not p or (loud and not p["loud"]):
                res[int(tg)] = {"tg": int(tg), "who": who, "name": name or "", "loud": loud}
        k = t["kind"]
        if k in ("client", "pc"):
            for c in self.crm.project_people(t["project_id"]):
                add(c.get("tg_id"), "client", c["name"], True)
        if k in ("org", "pc") and t["contractor_id"]:
            c = self.crm.one("SELECT tg_id, name FROM contractors WHERE id=?", t["contractor_id"]) or {}
            add(c.get("tg_id"), "contractor", c.get("name"), True)
        if k == "worker":
            w = self.crm.one("SELECT tg_id, name, contractor_id FROM crew WHERE id=? AND removed IS NULL", t["crew_id"]) or {}
            add(w.get("tg_id"), "crew", w.get("name"), True)
            h = self.crm.one("SELECT tg_id, name FROM contractors WHERE id=?", w.get("contractor_id") or 0) or {}
            add(h.get("tg_id"), "contractor", h.get("name"), False)
        if k == "group":
            heads_of_crew = set()
            for m in self.members(t["id"]):
                if m["kind"] == "contractor":
                    c = self.crm.one("SELECT tg_id, name FROM contractors WHERE id=?", m["ref_id"]) or {}
                    add(c.get("tg_id"), "contractor", c.get("name"), True)
                else:
                    w = self.crm.one("SELECT tg_id, name, contractor_id FROM crew WHERE id=? AND removed IS NULL", m["ref_id"]) or {}
                    add(w.get("tg_id"), "crew", w.get("name"), True)
                    heads_of_crew.add(w.get("contractor_id"))
            for cid in heads_of_crew:
                c = self.crm.one("SELECT tg_id, name FROM contractors WHERE id=?", cid or 0) or {}
                add(c.get("tg_id"), "contractor", c.get("name"), False)
        for o in self.observers():
            add(o["tg_id"], "observer", o["name"], False)
        studio = None
        if author_kind != "studio":
            studio = {"loud": not (k == "pc" and not t["studio_joined"])}
        return {"thread": t, "studio": studio, "people": list(res.values())}

    # ---------- документы ----------
    PROJECT_KEYS = ("id", "number", "title", "city", "country", "address", "area", "tariff", "status", "started", "finished")
    FILE_KEYS = ("id", "category", "name", "url", "thumb_url", "image", "size", "mime", "created", "title", "vis", "owner_kind", "thread_id")
    STAGE_KEYS = ("id", "title", "day", "amount", "currency", "src", "confirmed", "confirmed_by", "disputed", "disputed_by", "dispute_note")

    def can_see_file(self, v, f):
        if v["studio"] or v["observer"]:
            return True
        cat = f["category"]
        if cat == "goods":
            return False
        if f.get("thread_id"):                       # вложение разговора — участникам; заказчику — если студия открыла
            if self.access(v, self.thread(f["thread_id"])):
                return True
            return bool(v["client"]) and f.get("see_client") == 1
        if cat == "work":                            # документ подрядчика или его работника
            org = f.get("owner_contractor")
            if org in v["heads"]:
                return True
            if v["crew"]:
                if f.get("owner_crew") in v["crew"]:
                    return True
                orgs = {w["contractor_id"] for w in self.crm.q(f"SELECT contractor_id FROM crew WHERE id IN ({','.join('?' * len(v['crew']))})",
                                                                *v["crew"])}
                if org in orgs and f.get("vis") in ("team", "client"):
                    return True
            if v["client"]:
                sc = f.get("see_client")
                return sc == 1 or (sc is None and f.get("vis") == "client")
            return False
        if cat not in dict(FILE_CATS):
            return False
        if v["client"]:                              # документ студии — по разделу или как решила Ирина
            sc = f.get("see_client")
            if sc == 1 or (sc is None and cat in CLIENT_CATS):
                return True
        if v["heads"] or v["crew"]:
            sc = f.get("see_crew")
            if sc == 1 or (sc is None and cat in CONTRACTOR_CATS):
                return True
        return False

    def audience(self, f):
        """Кто видит документ — по-русски, для Ирины и наблюдателя."""
        who = ["студия"]
        if f.get("thread_id"):
            t = self.thread(f["thread_id"])
            who.append("участники разговора" + (f" «{t['title']}»" if t and t["title"] else ""))
            if f.get("see_client") == 1 and (not t or t["kind"] not in ("client", "pc")):
                who.append("заказчик")
            return ", ".join(who)
        if f["category"] == "work":
            org = self.crm.one("SELECT name FROM contractors WHERE id=?", f.get("owner_contractor") or 0) or {}
            vis = f.get("vis")
            who.append(org.get("name") or "подрядчик")
            if vis in ("team", "client"):
                who.append("его бригада")
            sc = f.get("see_client")
            if sc == 1 or (sc is None and vis == "client"):
                who.append("заказчик")
            return ", ".join(who)
        sc, sw = f.get("see_client"), f.get("see_crew")
        if sc == 1 or (sc is None and f["category"] in CLIENT_CATS):
            who.append("заказчик")
        if sw == 1 or (sw is None and f["category"] in CONTRACTOR_CATS):
            who.append("подрядчики и их бригады")
        return ", ".join(who)

    def _file_out(self, f, v):
        x = _pick(self.crm.file_view(f), self.FILE_KEYS)
        x["see_client"] = f.get("see_client")
        x["owner_contractor"] = f.get("owner_contractor")
        x["owner_name"] = ""
        if f.get("owner_crew"):
            w = self.crm.one("SELECT name, position FROM crew WHERE id=?", f["owner_crew"]) or {}
            x["owner_name"] = w.get("name") or ""
            x["owner_role"] = w.get("position") or ""
        elif f.get("owner_contractor"):
            c = self.crm.one("SELECT name, trade FROM contractors WHERE id=?", f["owner_contractor"]) or {}
            x["owner_name"] = c.get("name") or ""
            x["owner_role"] = c.get("trade") or ""
        x["mine"] = bool(f.get("owner_crew") in v["crew"] or (f.get("owner_kind") == "contractor" and f.get("owner_contractor") in v["heads"]))
        x["can_edit"] = bool(x["mine"] or (f["category"] == "work" and f.get("owner_contractor") in v["heads"]))
        if v["studio"] or v["observer"]:
            x["audience"] = self.audience(f)
        return x

    def files_for(self, v, pid):
        rows = self.crm.q("SELECT * FROM files WHERE project_id=? AND category != 'goods' ORDER BY id DESC", int(pid))
        out = []
        for f in rows:
            if self.can_see_file(v, f):
                x = self._file_out(f, v)
                x["section"] = "shared" if f.get("thread_id") else f["category"]
                out.append(x)
        return out

    def upload(self, v, pid, name, stream, size, mime, vis, title, who):
        """Документ от подрядчика или работника (фото выполненных работ, техническая документация) — раздел «От подрядчиков»."""
        if v["heads"]:
            org = sorted(v["heads"])[0]
            if vis not in VIS_HEAD:
                raise CrmError("Выберите, кто видит документ")
            owner = ("contractor", org, None)
        elif v["crew"]:
            wid = sorted(v["crew"])[0]
            w = self.crew_get(wid)
            if vis not in VIS_CREW:
                raise CrmError("Выберите, кто видит документ")
            owner = ("crew", w["contractor_id"], wid)
        else:
            raise CrmError("Нет доступа")
        f = self.crm.add_file(pid, "work", name, stream, size, mime, who)
        self.crm.run("UPDATE files SET owner_kind=?, owner_contractor=?, owner_crew=?, vis=?, title=? WHERE id=?",
                     owner[0], owner[1], owner[2], vis, _text(title, 200), f["id"])
        return self._file_out(self.crm.one("SELECT * FROM files WHERE id=?", f["id"]), v)

    def edit_file(self, v, d, who):
        """Свой документ (или документ своей бригады — у подрядчика): кто видит, подпись, удалить."""
        f = self.crm.one("SELECT * FROM files WHERE id=? AND category='work'", int(d.get("id") or 0))
        if not f:
            raise CrmError("Файл не найден")
        x = self._file_out(f, v)
        if not x["can_edit"]:
            raise CrmError("Нет доступа")
        if d.get("delete"):
            self.crm.delete("file", f["id"], who)
            return None
        vis = d.get("vis", f["vis"])
        if vis not in (VIS_HEAD if f["owner_kind"] == "contractor" else VIS_CREW):
            raise CrmError("Выберите, кто видит документ")
        self.crm.run("UPDATE files SET vis=?, title=? WHERE id=?", vis, _text(d.get("title", f["title"]), 200), f["id"])
        return self._file_out(self.crm.one("SELECT * FROM files WHERE id=?", f["id"]), v)

    # ---------- что видит заказчик ----------
    def _money_view(self, P):
        p = P["project"]
        titles = {("s", s["id"]): s["title"] for s in P["services"]}
        titles.update({("o", o["id"]): o["title"] for o in P["orders"]})
        payments = []
        for o in P["ops"]:
            if o["kind"] != "payment":
                continue
            what = "order" if o["order_id"] else "service" if o["service_id"] else "contract"
            payments.append({"id": o["id"], "day": o["day"], "amount": o["amount"], "currency": o["currency"], "amount_eur": o["amount_eur"],
                             "method": o["method"] or "", "for": what,
                             "title": titles.get(("o", o["order_id"])) or titles.get(("s", o["service_id"])) or ""})
        services = []
        for s in P["services"]:
            if s["cancelled"]:
                continue
            m = s["money"]
            services.append(dict(_pick(s, ("id", "title", "kind", "amount", "start", "months", "stopped")),
                                 **_pick(m, ("charges", "charged", "paid", "debt", "prepaid", "next", "status", "overdue"))))
        orders = []
        for o in P["orders"]:
            m = o["money"]
            if m["status"] == "cancelled" and not m["paid"]:
                continue
            orders.append(dict(_pick(o, ("id", "title", "code", "qty", "url", "photo", "day", "price", "currency", "price_eur",
                                         "planned", "delivered", "note_client")),
                               **_pick(m, ("paid", "rest", "rest_eur", "status")),
                               payments=[_pick(x, ("day", "amount", "currency")) for x in o["payments"]]))
        return {"money": {"contract": p["total_eur"], "paid": p["paid"], "balance": p["balance"], "services_debt": p["services_debt"],
                          "orders_rest": p["orders_rest"], "total_debt": p["client_debt"]},
                "payments": payments, "services": services, "orders": orders}

    def client_view(self, pid, viewer_tg=None):
        P = self.crm.project(pid)
        p = P["project"]
        if p["status"] == "cancelled":
            raise CrmError("Проект недоступен")
        t = int(viewer_tg or 0)
        v = self.viewer(t, pid) if t else {"tg": 0, "studio": False, "observer": False, "client": {"id": 0}, "heads": set(), "crew": set()}
        v = dict(v, client=v["client"] or {"id": 0}, heads=set(), crew=set(), observer=False)   # смотрит именно как заказчик
        contractors = []
        for k in P["contractors"]:
            if k.get("observer") or any(c["id"] == k["id"] for c in contractors):
                continue
            stages = [_pick(s, self.STAGE_KEYS) for x in P["contractors"] if x["id"] == k["id"] for s in x["money"]["stages"]]
            contractors.append({"id": k["id"], "link_id": k["link_id"], "name": k["name"], "trade": k["link_trade"] or k["trade"] or "",
                                "company": k["company"] or "", "phone": k["phone"] or "", "email": k["email"] or "",
                                "messenger": k.get("messenger") or "", "contact_pref": k["contact_pref"] or "",
                                "can_write": bool(k.get("tg_id")), "stages": stages})
        files = self.files_for(v, p["id"])
        return dict({"role": "client", "project": _pick(p, self.PROJECT_KEYS), "files": files,
                     "people": [{"name": c["name"], "me": bool(t and c.get("tg_id") == t)} for c in P["people"]],
                     "contractors": contractors, "studio": STUDIO,
                     "chat": {"unread": sum(x["unread"] for x in self.threads_for(self.viewer(t, pid), pid) if x.get("id")) if t else 0}},
                    **self._money_view(P))

    # ---------- что видит подрядчик (руководитель) ----------
    def contractor_view(self, pid, contractor_ids, viewer_tg=None):
        P = self.crm.project(pid)
        p = P["project"]
        if p["status"] == "cancelled":
            raise CrmError("Проект недоступен")
        ids = {int(x) for x in contractor_ids}
        bonuses = {}
        for o in P["ops"]:
            if o["kind"] == "commission" and o["link_id"]:
                bonuses.setdefault(o["link_id"], []).append(_pick(o, ("day", "amount", "currency", "stage_id")))
        mine = []
        for k in P["contractors"]:
            if k["id"] not in ids:
                continue
            m = k["money"]
            stages = []
            for s in m["stages"]:
                x = _pick(s, self.STAGE_KEYS + ("pct", "commission", "received"))
                x["note"] = s["note"] if s.get("src") == "contractor" else ""      # заметки студии подрядчику не показываем
                x["mine"] = s.get("src") == "contractor"
                stages.append(x)
            mine.append({"id": k["id"], "link_id": k["link_id"], "name": k["name"], "trade": k["link_trade"] or k["trade"] or "",
                         "stages": stages, "money": _pick(m, ("currency", "order", "expected", "received", "debt", "unknown")),
                         "bonuses": bonuses.get(k["link_id"], [])})
        if not mine:
            raise CrmError("Проект недоступен")
        v = {"tg": int(viewer_tg or 0), "studio": False, "observer": False, "client": None, "heads": ids, "crew": set()}
        team = []
        for cid in sorted(ids):
            for w in self.team(cid, pid):
                team.append(dict(w, contractor_id=cid))
        return {"role": "contractor", "project": _pick(p, self.PROJECT_KEYS),
                "clients": [_pick(c, ("name", "phone", "email", "messenger", "contact_pref")) for c in P["people"]],
                "files": self.files_for(v, p["id"]), "mine": mine, "team": team,
                "default_pct": self.crm.lists()["default_pct"], "studio": STUDIO}

    # ---------- что видит работник подрядчика ----------
    def worker_view(self, pid, crew_ids, viewer_tg=None):
        """Проект без денег: ни суммы проекта, ни вознаграждения студии. Контакты руководителя и студии, документы."""
        p = self.crm.one("SELECT * FROM projects WHERE id=?", int(pid))
        if not p or p["status"] == "cancelled" or not crew_ids:
            raise CrmError("Проект недоступен")
        me, heads = [], []
        for wid in sorted(crew_ids):
            w = self.crew_get(wid)
            c = self.crm.one("SELECT * FROM contractors WHERE id=?", w["contractor_id"]) or {}
            link = self.crm.one("SELECT trade FROM project_contractors WHERE project_id=? AND contractor_id=?", p["id"], c.get("id") or 0) or {}
            me.append({"id": w["id"], "name": w["name"], "position": w["position"] or "", "head": c.get("name") or ""})
            if not any(h["name"] == c.get("name") for h in heads):
                heads.append({"name": c.get("name") or "", "trade": link.get("trade") or c.get("trade") or "", "company": c.get("company") or "",
                              "phone": c.get("phone") or "", "email": c.get("email") or "", "messenger": c.get("messenger") or "",
                              "contact_pref": c.get("contact_pref") or ""})
        v = {"tg": int(viewer_tg or 0), "studio": False, "observer": False, "client": None, "heads": set(), "crew": set(int(x) for x in crew_ids)}
        return {"role": "worker", "project": _pick(p, ("id", "number", "title", "city", "country", "address", "area", "status", "started")),
                "me": me, "heads": heads, "files": self.files_for(v, p["id"]), "studio": STUDIO}

    # ---------- наблюдатель («Разработчик ПО»): всё, только чтение ----------
    def observer_view(self, pid, viewer_tg):
        p = self.crm.one("SELECT * FROM projects WHERE id=?", int(pid))
        if not p or p["status"] == "cancelled":
            raise CrmError("Проект недоступен")
        v = {"tg": int(viewer_tg or 0), "studio": False, "observer": True, "client": None, "heads": set(), "crew": set()}
        return {"role": "observer", "project": _pick(p, self.PROJECT_KEYS), "participants": self.participants(pid),
                "files": self.files_for(v, pid), "threads": self.threads_for(v, pid), "studio": STUDIO}

    # ---------- этапы: подрядчик вносит сумму, заказчик подтверждает ----------
    def contractor_stage(self, tg_id, d, who):
        """Подрядчик вносит или правит свой этап (пока заказчик его не подтвердил). Бонус студии — процент по умолчанию,
        или как настроила студия у этого этапа."""
        pid, lid = int(d.get("project_id") or 0), int(d.get("link_id") or 0)
        link = self.crm.one("SELECT * FROM project_contractors WHERE id=? AND project_id=?", lid, pid)
        if not link or link["contractor_id"] not in self.contractor_ids(tg_id, pid):
            raise CrmError("Нет доступа")
        old = None
        if d.get("id"):
            old = self.crm.one("SELECT * FROM stages WHERE id=? AND link_id=?", int(d["id"]), lid)
            if not old:
                raise CrmError("Этап не найден")
            if old["src"] != "contractor":
                raise CrmError("Этот этап внесла студия — изменить его может только студия")
            if old["confirmed"]:
                raise CrmError("Заказчик уже подтвердил эту сумму — изменить её может только студия")
        if not _text(d.get("title"), 120):
            raise CrmError("Напишите, что за работа")
        cur = str(d.get("currency") or "EUR").upper()
        if old and old["commission"] is None:
            mode, pct, commission = "unknown", None, None
        elif old and old["pct"] is None:
            mode, pct, commission = "sum", None, old["commission"]
        else:
            mode, pct, commission = "pct", old["pct"] if old else self.crm.lists()["default_pct"], None
        r = self.crm.save_stage({"id": old["id"] if old else None, "project_id": pid, "link_id": lid, "title": d.get("title"),
                                 "day": d.get("day") or today().isoformat(), "amount": d.get("amount"), "currency": cur,
                                 "mode": mode, "pct": pct, "commission": commission, "note": d.get("note")}, who, origin="contractor")
        return {"stage_id": r["saved_id"], "was": old, "project_id": pid, "link_id": lid}

    def contractor_delete_stage(self, tg_id, d, who):
        sid = int(d.get("id") or 0)
        st = self.crm.one("SELECT * FROM stages WHERE id=?", sid)
        if not st:
            raise CrmError("Этап не найден")
        link = self.crm.one("SELECT * FROM project_contractors WHERE id=?", st["link_id"])
        if not link or link["contractor_id"] not in self.contractor_ids(tg_id, st["project_id"]):
            raise CrmError("Нет доступа")
        if st["src"] != "contractor" or st["confirmed"]:
            raise CrmError("Удалить можно только свой этап, пока заказчик его не подтвердил")
        if self.crm.one("SELECT id FROM ops WHERE stage_id=? LIMIT 1", sid):
            raise CrmError("По этому этапу уже есть расчёты со студией — удалить может только студия")
        self.crm.delete("stage", sid, who)
        return {"project_id": st["project_id"], "stage": st}

    def client_stage(self, tg_id, stage_id, action, note, who):
        """Заказчик подтверждает сумму работ подрядчика или отмечает «не согласен» (с комментарием)."""
        st = self.crm.one("SELECT * FROM stages WHERE id=?", int(stage_id or 0))
        if not st or not self.client_of(tg_id, st["project_id"]):
            raise CrmError("Нет доступа")
        if action == "confirm":
            self.crm.run("UPDATE stages SET confirmed=?, confirmed_by=?, disputed=NULL, disputed_by=NULL, dispute_note=NULL, updated=? WHERE id=?",
                         now(), _text(who, 120), now(), st["id"])
        elif action == "dispute":
            self.crm.run("UPDATE stages SET disputed=?, disputed_by=?, dispute_note=?, confirmed=NULL, confirmed_by=NULL, updated=? WHERE id=?",
                         now(), _text(who, 120), _text(note, 500), now(), st["id"])
        else:
            raise CrmError("Неизвестное действие")
        self.crm.audit(_text(who, 120), "edit", "stage", st["id"], {"project_id": st["project_id"], action: True})
        self.crm.touch(st["project_id"])
        return dict(self.crm.one("SELECT * FROM stages WHERE id=?", st["id"]), action=action)

    # ---------- названия на языке человека ----------
    @staticmethod
    def _tr_key(text, lang):
        return "tr:" + lang + ":" + hashlib.sha1(text.strip().encode()).hexdigest()[:20]

    def label(self, text, lang):
        """Название на языке кабинета: вид работ и пакет — из словаря, остальное — сохранённый перевод.
        None — перевода ещё нет (его можно заказать в фоне). Русским и украинским названия оставляем как есть."""
        t = str(text or "").strip()
        if not t or lang == "ru":
            return t
        f = FIXED.get(t)
        if f:
            return f[FIXED_LANGS.index(lang)] if lang in FIXED_LANGS else t
        if lang == "uk":
            return t
        return self.crm.setting(self._tr_key(t, lang))

    def remember_label(self, text, lang, out):
        self.crm.setting(self._tr_key(str(text).strip(), lang), out or str(text).strip())

    def localize(self, v, lang):
        """Подставить в кабинет названия на языке человека. Возвращает названия без перевода (перевести в фоне)."""
        misses = set()

        def tr(d, k):
            if not d or not d.get(k):
                return
            x = self.label(d[k], lang)
            if x is None:
                misses.add(d[k].strip())
            else:
                d[k] = x
        for k in ("title", "tariff", "city", "country"):
            tr(v["project"], k)
        for s in v.get("services", []):
            tr(s, "title")
        for o in v.get("orders", []):
            tr(o, "title")
            tr(o, "note_client")
        for p in v.get("payments", []):
            tr(p, "title")
        for f in v.get("files", []):                  # кто прислал документ и подпись к нему
            tr(f, "owner_role")
            tr(f, "title")
        for k in v.get("contractors", []) + v.get("mine", []) + v.get("heads", []):
            tr(k, "trade")
            for s in k.get("stages", []):
                tr(s, "title")
        return sorted(misses)[:60]

    # ---------- напоминания об оплате доп. услуг ----------
    def due_reminders(self, on=None):
        """Начисления доп. услуг, о которых пора напомнить (заказчику и студии): в день оплаты и ещё раз, если через 7 дней
        не оплачено. Не напоминаем о месяцах, которые уже прошли, когда услугу внесли в учёт (их оплаты могли не внести),
        и о первом платеже в день внесения услуги (заказчику и так пришло сообщение о новой услуге)."""
        on = on or today()
        out = []
        projects = {p["id"]: p for p in self.crm.q("SELECT id, title, number, status FROM projects WHERE status IN ('active', 'paused')")}
        for pid, e in self.crm.extras().items():
            if pid not in projects:
                continue
            for s in e["services"]:
                created = (s["created"] or "")[:10]
                for ch in s["money"]["charges"]:
                    if ch["status"] not in ("due", "overdue"):
                        continue
                    days = (on - date.fromisoformat(ch["due"])).days
                    if days > REMIND_WINDOW or ch["due"] < created:
                        continue
                    stage = "overdue" if ch["status"] == "overdue" else "due"
                    if stage == "due" and ch["due"] <= created:
                        continue
                    key = f"remind:{s['id']}:{ch['due']}:{stage}"
                    if self.crm.setting(key):
                        continue
                    out.append({"key": key, "stage": stage, "project": projects[pid], "service": _pick(s, ("id", "title", "kind", "amount")),
                                "due": ch["due"], "amount": ch["amount"], "paid": ch["paid"], "rest": round(ch["amount"] - ch["paid"], 2),
                                "debt": s["money"]["debt"]})
        return out

    def reminded(self, key):
        self.crm.setting(key, now())
        if key.endswith(":overdue"):                     # просрочено — «в день оплаты» уже не нужно
            self.crm.setting(key[:-len("overdue")] + "due", now())

    def chat_people(self, pid):
        """Заказчики проекта с привязанным Telegram."""
        return [c for c in self.crm.project_people(pid) if c.get("tg_id")]
