#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Кабинет заказчика и подрядчика («Мой проект» в боте студии) и переписка студии с заказчиками.

Дизайнер добавляет в проект заказчиков (обычно до 5 человек) и подрядчиков и даёт каждому одноразовую ссылку
в бот (действует 14 дней): человек открывает её в Telegram и нажимает «Старт» — его Telegram привязывается к записи
заказчика или подрядчика в учёте.

Что видит заказчик (client_view): проект (пакет — тариф, площадь, город), сколько внёс и когда, сколько ещё должен
студии (договор, доп. услуги, товары), доп. услуги (разовые и помесячные — какие месяцы оплачены), товары (цена, авансы,
плановая поставка, статус), файлы проекта — все разделы, кроме «Другое», подрядчиков проекта с контактами и суммами их
работ (подтвердить сумму или «не согласен»), переписку со студией. Бонусы студии, закупочные цены, поставщиков и заметки
студии — не видит: в ответ попадают только перечисленные поля.

Что видит подрядчик (contractor_view): проект (адрес, город, площадь), контакты заказчиков, файлы — обмерный план,
до, визуализации, документация, после — и свой подряд: этапы, сумма заказа, вознаграждение студии (по умолчанию 10 %),
подтвердил ли заказчик, сколько уже отдал. Может сам внести этап (сумму) — заказчик подтверждает. Переписки не видит.

Переписка: заказчики проекта и студия; подрядчики не участвуют. Перевод сообщений — в боте (portal_bot.py).
Только стандартная библиотека Python 3."""
import hashlib
import json
import secrets
from datetime import date, datetime, timedelta, timezone

from crm import CLIENT_CATS, CONTRACTOR_CATS, CrmError, _text, now, today

INVITE_DAYS = 14
MSG_MAX = 4000
REMIND_HOURS = (10, 20)            # напоминания об оплате — днём, по времени Братиславы
REMIND_WINDOW = 60                 # о начислениях старше 60 дней не напоминаем (это уже разговор, а не напоминание)
UI_LANGS = ("ru", "uk", "en", "sk", "de")
STUDIO = {"name": "DUMSKAYA DESIGN", "designer": {"ru": "Ирина Думская", "uk": "Ірина Думська"}, "designer_latin": "Irina Dumskaya",
          "phone": "+421 918 17 77 85", "email": "irina@dumskaya-design.com", "site": "https://dumskaya-design.com"}


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

    # ---------- приглашения и привязка Telegram ----------
    def _record(self, kind, ref_id):
        if kind not in ("client", "contractor"):
            raise CrmError("Неизвестно, кого приглашать")
        rec = self.crm.one(f"SELECT * FROM {'clients' if kind == 'client' else 'contractors'} WHERE id=?", int(ref_id or 0))
        if not rec:
            raise CrmError("Человек не найден")
        return rec

    def make_invite(self, kind, ref_id, project_id, lang, who):
        """Одноразовая ссылка в кабинет. Человек должен быть в проекте; прежняя неиспользованная ссылка этому же
        человеку перестаёт действовать."""
        rec = self._record(kind, ref_id)
        pid = int(project_id or 0)
        if kind == "client" and not any(c["id"] == rec["id"] for c in self.crm.project_people(pid)):
            raise CrmError("Сначала добавьте заказчика в проект")
        if kind == "contractor" and not self.crm.one("SELECT id FROM project_contractors WHERE project_id=? AND contractor_id=?",
                                                     pid, rec["id"]):
            raise CrmError("Сначала добавьте подрядчика в проект")
        self.crm.run("DELETE FROM invites WHERE expires < ?", (datetime.now(timezone.utc) - timedelta(days=30)).isoformat())
        self.crm.run("DELETE FROM invites WHERE kind=? AND ref_id=? AND used_by IS NULL", kind, rec["id"])
        token = secrets.token_urlsafe(12)
        expires = (datetime.now(timezone.utc) + timedelta(days=INVITE_DAYS)).isoformat(timespec="seconds")
        self.crm.run("INSERT INTO invites(token, kind, ref_id, project_id, lang, created_by, created, expires) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                     token, kind, rec["id"], pid, ui_lang(lang), who, now(), expires)
        self.crm.audit(who, "add", "access", rec["id"], {"project_id": pid, "kind": kind, "invite": True})
        return {"token": token, "expires": expires, "name": rec["name"], "kind": kind, "lang": ui_lang(lang)}

    def invite(self, token):
        """Действующее приглашение или None."""
        inv = self.crm.one("SELECT * FROM invites WHERE token=?", str(token or "")[:40])
        if not inv or inv["used_by"] or inv["expires"] < now():
            return None
        return inv

    def use_invite(self, token, tg_id, tg_name):
        """Привязать Telegram к заказчику или подрядчику по ссылке. None — ссылка недействительна.
        Если к записи уже был привязан другой Telegram — он теряет доступ (replaced)."""
        inv = self.invite(token)
        if not inv or not self._count("UPDATE invites SET used_by=?, used=? WHERE token=? AND used_by IS NULL",
                                      int(tg_id), now(), inv["token"]):
            return None
        table = "clients" if inv["kind"] == "client" else "contractors"
        rec = self.crm.one(f"SELECT * FROM {table} WHERE id=?", inv["ref_id"])
        if not rec:
            return None
        self.crm.run(f"UPDATE {table} SET tg_id=?, tg_name=?, tg_since=?, updated=? WHERE id=?",
                     int(tg_id), _text(tg_name, 120), now(), now(), rec["id"])
        self.crm.audit(_text(tg_name, 120) or str(tg_id), "edit", "access", rec["id"],
                       {"project_id": inv["project_id"], "kind": inv["kind"], "joined": True})
        p = self.crm.one("SELECT id, title, number FROM projects WHERE id=?", inv["project_id"]) or {}
        return {"kind": inv["kind"], "ref": dict(rec, tg_id=int(tg_id)), "project": p, "lang": inv["lang"], "by": inv["created_by"],
                "replaced": rec["tg_id"] if rec["tg_id"] and int(rec["tg_id"]) != int(tg_id) else None}

    def unlink(self, kind, ref_id, who):
        """Закрыть кабинет: Telegram отвязывается от записи. Возвращает отвязанный Telegram ID (или None)."""
        rec = self._record(kind, ref_id)
        table = "clients" if kind == "client" else "contractors"
        self.crm.run(f"UPDATE {table} SET tg_id=NULL, tg_name=NULL, tg_since=NULL, updated=? WHERE id=?", now(), rec["id"])
        self.crm.run("DELETE FROM invites WHERE kind=? AND ref_id=? AND used_by IS NULL", kind, rec["id"])
        self.crm.audit(who, "delete", "access", rec["id"], {"kind": kind, "tg_id": rec["tg_id"]})
        return rec["tg_id"]

    def linked(self, tg_id):
        """Записи, к которым привязан этот Telegram: заказчики и подрядчики."""
        t = int(tg_id or 0)
        return {"clients": self.crm.q("SELECT * FROM clients WHERE tg_id=?", t),
                "contractors": self.crm.q("SELECT * FROM contractors WHERE tg_id=?", t)}

    def projects_for(self, tg_id):
        """Проекты в кабинете: где человек заказчик или подрядчик (отменённые — нет)."""
        t = int(tg_id or 0)
        out = {}
        for p in self.crm.q("""SELECT DISTINCT p.id, p.title, p.number, p.city, p.status, p.started FROM projects p
                               WHERE p.status != 'cancelled' AND (p.client_id IN (SELECT id FROM clients WHERE tg_id=?)
                               OR p.id IN (SELECT x.project_id FROM project_clients x JOIN clients c ON c.id=x.client_id WHERE c.tg_id=?))""", t, t):
            out[p["id"]] = dict(p, roles=["client"], unread=self.unread(p["id"], t))
        for p in self.crm.q("""SELECT DISTINCT p.id, p.title, p.number, p.city, p.status, p.started FROM projects p
                               JOIN project_contractors l ON l.project_id=p.id JOIN contractors c ON c.id=l.contractor_id
                               WHERE p.status != 'cancelled' AND c.tg_id=?""", t):
            out.setdefault(p["id"], dict(p, roles=[], unread=0))["roles"].append("contractor")
        return sorted(out.values(), key=lambda p: (p["status"] not in ("active", "paused"), -(p["id"])))

    def client_of(self, tg_id, pid):
        """Запись заказчика этого проекта, к которой привязан Telegram (или None)."""
        t = int(tg_id or 0)
        p = self.crm.one("SELECT status FROM projects WHERE id=?", int(pid or 0))
        if not t or not p or p["status"] == "cancelled":
            return None
        return next((c for c in self.crm.project_people(int(pid)) if c.get("tg_id") == t), None)

    def contractor_ids(self, tg_id, pid):
        """Подрядчики (записи), привязанные к этому Telegram и работающие в проекте."""
        t = int(tg_id or 0)
        if not t:
            return []
        return [r["contractor_id"] for r in self.crm.q(
            """SELECT DISTINCT l.contractor_id FROM project_contractors l JOIN contractors c ON c.id=l.contractor_id
               JOIN projects p ON p.id=l.project_id WHERE l.project_id=? AND c.tg_id=? AND p.status != 'cancelled'""", int(pid or 0), t)]

    # ---------- что видит заказчик ----------
    PROJECT_KEYS = ("id", "number", "title", "city", "country", "address", "area", "tariff", "status", "started", "finished")
    FILE_KEYS = ("id", "category", "name", "url", "thumb_url", "image", "size", "mime", "created")
    STAGE_KEYS = ("id", "title", "day", "amount", "currency", "src", "confirmed", "confirmed_by", "disputed", "disputed_by", "dispute_note")

    def _files(self, P, cats):
        return [_pick(f, self.FILE_KEYS) for f in P["files"] if f["category"] in cats]

    def client_view(self, pid, viewer_tg=None):
        P = self.crm.project(pid)
        p = P["project"]
        if p["status"] == "cancelled":
            raise CrmError("Проект недоступен")
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
        contractors = []
        for k in P["contractors"]:
            contractors.append({"link_id": k["link_id"], "name": k["name"], "trade": k["link_trade"] or k["trade"] or "",
                                "company": k["company"] or "", "phone": k["phone"] or "", "email": k["email"] or "",
                                "messenger": k.get("messenger") or "", "contact_pref": k["contact_pref"] or "",
                                "stages": [_pick(s, self.STAGE_KEYS) for s in k["money"]["stages"]]})
        t = int(viewer_tg or 0)
        return {"role": "client", "project": _pick(p, self.PROJECT_KEYS),
                "money": {"contract": p["total_eur"], "paid": p["paid"], "balance": p["balance"],
                          "services_debt": p["services_debt"], "orders_rest": p["orders_rest"], "total_debt": p["client_debt"]},
                "payments": payments, "services": services, "orders": orders, "files": self._files(P, CLIENT_CATS),
                "cats": list(CLIENT_CATS), "people": [{"name": c["name"], "me": bool(t and c.get("tg_id") == t)} for c in P["people"]],
                "contractors": contractors, "chat": {"unread": self.unread(p["id"], t) if t else 0}, "studio": STUDIO}

    # ---------- что видит подрядчик ----------
    def contractor_view(self, pid, contractor_ids):
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
            mine.append({"link_id": k["link_id"], "name": k["name"], "trade": k["link_trade"] or k["trade"] or "", "stages": stages,
                         "money": _pick(m, ("currency", "order", "expected", "received", "debt", "unknown")),
                         "bonuses": bonuses.get(k["link_id"], [])})
        if not mine:
            raise CrmError("Проект недоступен")
        return {"role": "contractor", "project": _pick(p, self.PROJECT_KEYS),
                "clients": [_pick(c, ("name", "phone", "email", "messenger", "contact_pref")) for c in P["people"]],
                "files": self._files(P, CONTRACTOR_CATS), "cats": list(CONTRACTOR_CATS), "mine": mine,
                "default_pct": self.crm.lists()["default_pct"], "studio": STUDIO}

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
            if not d.get(k):
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
        for k in v.get("contractors", []) + v.get("mine", []):
            tr(k, "trade")
            for s in k["stages"]:
                tr(s, "title")
        return sorted(misses)[:60]

    # ---------- переписка ----------
    def post(self, pid, author_kind, author_tg, author_name, text, file_id=None):
        pid = int(pid or 0)
        if not self.crm.one("SELECT id FROM projects WHERE id=?", pid):
            raise CrmError("Проект не найден")
        text = str(text or "").strip()[:MSG_MAX]
        fid = int(file_id or 0) or None
        if fid and not self.crm.one("SELECT id FROM files WHERE id=? AND project_id=? AND category='chat'", fid, pid):
            fid = None
        if not text and not fid:
            raise CrmError("Пустое сообщение")
        mid = self.crm.run("INSERT INTO messages(project_id, author_kind, author_tg, author_name, text, file_id, created) "
                           "VALUES(?, ?, ?, ?, ?, ?, ?)", pid, author_kind, int(author_tg or 0) or None, _text(author_name, 120),
                           text, fid, now())
        self.mark_read(pid, 0 if author_kind == "studio" else author_tg, mid)
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

    def messages(self, pid, viewer_kind, viewer_tg, lang, after=0, limit=200):
        """Переписка проекта для заказчика или студии: оригинал, перевод на язык читающего (если есть), вложение."""
        rows = self.crm.q("SELECT * FROM messages WHERE project_id=? AND deleted IS NULL AND id>? ORDER BY id DESC LIMIT ?",
                          int(pid), int(after or 0), int(limit))
        out = []
        for m in reversed(rows):
            try:
                tr = json.loads(m["tr"] or "{}") or {}
            except ValueError:
                tr = {}
            f = self.crm.one("SELECT * FROM files WHERE id=?", m["file_id"]) if m["file_id"] else None
            mine = (m["author_kind"] == "studio") if viewer_kind == "studio" else (m["author_tg"] == int(viewer_tg or 0))
            out.append({"id": m["id"], "author_kind": m["author_kind"], "author_name": m["author_name"], "mine": mine,
                        "text": m["text"] or "", "tr": tr.get(lang), "lang": m["lang"], "created": m["created"],
                        "file": _pick(self.crm.file_view(f), self.FILE_KEYS) if f else None})
        return out

    def mark_read(self, pid, key, last_id):
        """Прочитано до сообщения last_id. key — Telegram ID заказчика или 0 (студия)."""
        self.crm.run("""INSERT INTO chat_read(project_id, tg_id, last_id) VALUES(?, ?, ?)
                        ON CONFLICT(project_id, tg_id) DO UPDATE SET last_id=MAX(last_id, excluded.last_id)""",
                     int(pid), int(key or 0), int(last_id or 0))

    def unread(self, pid, tg_id):
        """Непрочитанные у заказчика: от студии и от других заказчиков проекта."""
        r = self.crm.one("SELECT last_id FROM chat_read WHERE project_id=? AND tg_id=?", int(pid), int(tg_id or 0))
        return self.crm.one("""SELECT COUNT(*) AS n FROM messages WHERE project_id=? AND deleted IS NULL AND id>?
                               AND (author_kind='studio' OR COALESCE(author_tg, 0) != ?)""",
                            int(pid), r["last_id"] if r else 0, int(tg_id or 0))["n"]

    def chat_people(self, pid):
        """Кому доставлять переписку: заказчики проекта с привязанным Telegram."""
        return [c for c in self.crm.project_people(pid) if c.get("tg_id")]

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
