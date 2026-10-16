#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram-бот студии DUMSKAYA DESIGN — внутренний инструмент. Работает внутри сервиса заявок
(lead_service.py), только стандартная библиотека Python 3.

Пользователи и роли:
  • разработчик (BOT_OWNER_ID в lead.env) — получает все уведомления, принимает пользователей;
  • дизайнер студии — получает заявки с сайта и уведомления о заявках партнёрам, принимает пользователей;
    назначить дизайнера может только разработчик;
  • партнёры: поставщик, изготовитель мебели, прораб — привязаны к компании (партнёру).
    Поставщику (и любому пользователю компании) приходят заявки с сайта на товары этой компании.

Попасть в бот можно только по одобрению: человек нажимает «Старт», разработчику и дизайнерам приходит
запрос с кнопками ролей. Данные — в SQLite (BOT_DB, по умолчанию ~/dumskaya/bot.db).
Сообщения получаем long polling'ом (getUpdates) — входящих подключений к серверу не нужно.
"""
import html
import json
import os
import sqlite3
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone

SITE = "https://dumskaya-design.com"
ROLES = {
    "owner": "Разработчик",
    "designer": "Дизайнер студии",
    "supplier": "Поставщик",
    "maker": "Изготовитель мебели",
    "foreman": "Прораб",
}
ADMIN_ROLES = ("owner", "designer")
PARTNER_ROLES = ("supplier", "maker", "foreman")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  tg_id INTEGER PRIMARY KEY,
  name TEXT, username TEXT,
  role TEXT,                    -- owner, designer, supplier, maker, foreman
  status TEXT NOT NULL,         -- pending, active, rejected, removed
  partner_id INTEGER,           -- компания-партнёр (для партнёрских ролей)
  added_by INTEGER, created TEXT, updated TEXT
);
CREATE TABLE IF NOT EXISTS partners (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  created TEXT
);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def esc(s):
    return html.escape(str(s or ""), quote=False)


class Store:
    def __init__(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript(SCHEMA)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def all(self, sql, *a):
        with self.lock:
            return self.db.execute(sql, a).fetchall()

    def one(self, sql, *a):
        r = self.all(sql, *a)
        return r[0] if r else None

    def run(self, sql, *a):
        with self.lock:
            return self.db.execute(sql, a).lastrowid

    def get(self, key, default=None):
        r = self.one("SELECT value FROM state WHERE key=?", key)
        return r["value"] if r else default

    def put(self, key, value):
        self.run("INSERT INTO state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", key, value)

    def drop(self, key):
        self.run("DELETE FROM state WHERE key=?", key)


class Bot:
    def __init__(self, token, owner_id, db_path, log=print):
        self.token = token
        self.owner = int(owner_id) if str(owner_id or "").strip().isdigit() else None
        self.log = log
        self.s = Store(db_path)
        self.stop = threading.Event()
        self.username = ""
        if self.owner:
            u = self.user(self.owner)
            if not u:
                self.s.run("INSERT INTO users(tg_id, name, role, status, created, updated) VALUES(?, ?, 'owner', 'active', ?, ?)",
                           self.owner, "Разработчик", now(), now())
            elif u["role"] != "owner" or u["status"] != "active":
                self.s.run("UPDATE users SET role='owner', status='active', updated=? WHERE tg_id=?", now(), self.owner)

    # ---------- Telegram API ----------
    def api(self, method, **params):
        req = urllib.request.Request(f"https://api.telegram.org/bot{self.token}/{method}",
                                     data=json.dumps(params).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=int(params.get("timeout") or 0) + 20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read())
            except Exception:  # noqa: BLE001
                return {"ok": False, "error_code": e.code, "description": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error_code": 0, "description": f"{type(e).__name__}: {e}"}

    @staticmethod
    def kb(rows):
        return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows if row]}

    def send(self, chat_id, text, rows=None, **extra):
        p = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}, **extra}
        if rows:
            p["reply_markup"] = self.kb(rows)
        r = self.api("sendMessage", **p)
        if not r.get("ok"):
            self.log(f"telegram: не отправлено {chat_id}: {r.get('description')}")
        return r.get("ok", False)

    def edit(self, msg, text, rows=None):
        p = {"chat_id": msg["chat"]["id"], "message_id": msg["message_id"], "text": text, "parse_mode": "HTML",
             "link_preview_options": {"is_disabled": True}, "reply_markup": self.kb(rows or [])}
        self.api("editMessageText", **p)

    # ---------- пользователи ----------
    def user(self, tg_id):
        return self.s.one("SELECT * FROM users WHERE tg_id=?", int(tg_id))

    def active(self, roles=None):
        rows = self.s.all("SELECT * FROM users WHERE status='active' ORDER BY role, name")
        return [u for u in rows if roles is None or u["role"] in roles]

    def is_admin(self, u):
        return bool(u) and u["status"] == "active" and u["role"] in ADMIN_ROLES

    def partner(self, pid):
        return self.s.one("SELECT * FROM partners WHERE id=?", pid) if pid else None

    def label(self, u):
        if not u:
            return "—"
        tag = f" (@{u['username']})" if u["username"] else ""
        return f"{u['name'] or u['tg_id']}{tag}"

    def role_line(self, u):
        role = ROLES.get(u["role"], "—")
        p = self.partner(u["partner_id"])
        return role + (f" «{p['name']}»" if p else "")

    def notify(self, text, roles=ADMIN_ROLES, skip=()):
        """Сообщение всем активным пользователям с этими ролями (по умолчанию — разработчику и дизайнерам)."""
        sent = []
        for u in self.active(roles):
            if u["tg_id"] in skip:
                continue
            if self.send(u["tg_id"], text):
                sent.append(u["tg_id"])
        return sent

    def notify_owner(self, text):
        if self.owner:
            self.send(self.owner, text)

    # ---------- приём сообщений ----------
    def run(self):
        me = self.api("getMe")
        self.username = (me.get("result") or {}).get("username", "")
        self.setup_profile()
        offset = int(self.s.get("offset", "0") or 0)
        pause = 1
        self.log(f"бот @{self.username or '?'} слушает Telegram")
        while not self.stop.is_set():
            r = self.api("getUpdates", offset=offset, timeout=50, allowed_updates=["message", "callback_query"])
            if not r.get("ok"):
                code = r.get("error_code")
                if code == 409:
                    self.log("telegram: этот бот уже читает другая программа (409) — жду")
                    wait = 30
                elif code == 401:
                    self.log("telegram: токен не принят (401)")
                    wait = 300
                else:
                    wait = pause
                    pause = min(pause * 2, 60)
                self.stop.wait(wait)
                continue
            pause = 1
            for upd in r.get("result", []):
                offset = upd["update_id"] + 1
                self.s.put("offset", str(offset))     # до обработки: сбойное сообщение не зациклит бота
                try:
                    self.handle(upd)
                except Exception as e:  # noqa: BLE001
                    self.log(f"бот: ошибка {type(e).__name__}: {e}")
                    self.notify_owner(f"⚠️ Ошибка бота: <code>{esc(type(e).__name__)}: {esc(e)}</code>")

    def start(self):
        t = threading.Thread(target=self._loop, name="telegram-bot", daemon=True)
        t.start()
        return t

    def _loop(self):
        while not self.stop.is_set():
            try:
                self.run()
            except Exception as e:  # noqa: BLE001
                self.log(f"бот остановился: {type(e).__name__}: {e} — перезапуск через 10 с")
                self.stop.wait(10)

    def setup_profile(self):
        self.api("setMyDescription", description="Внутренний бот студии DUMSKAYA DESIGN. Доступ — только по приглашению студии.")
        self.api("setMyShortDescription", short_description="Внутренний бот студии DUMSKAYA DESIGN")
        self.api("setMyCommands", commands=[{"command": "start", "description": "Начать"},
                                            {"command": "help", "description": "Что умеет бот"}])
        for u in self.active(ADMIN_ROLES):
            self.admin_commands(u["tg_id"])

    def admin_commands(self, tg_id, on=True):
        scope = {"type": "chat", "chat_id": tg_id}
        if not on:
            self.api("deleteMyCommands", scope=scope)
            return
        self.api("setMyCommands", scope=scope, commands=[
            {"command": "users", "description": "Пользователи и запросы"},
            {"command": "partners", "description": "Партнёры и их товары"},
            {"command": "help", "description": "Что умеет бот"},
            {"command": "cancel", "description": "Отменить ввод"}])

    def handle(self, upd):
        if "callback_query" in upd:
            return self.on_button(upd["callback_query"])
        m = upd.get("message")
        if not m or (m.get("chat") or {}).get("type") != "private" or not m.get("from"):
            return                                   # группы и каналы бот не обслуживает
        f = m["from"]
        if f.get("is_bot"):
            return
        uid = f["id"]
        name = " ".join(x for x in (f.get("first_name"), f.get("last_name")) if x) or str(uid)
        u = self.user(uid)
        if u:
            self.s.run("UPDATE users SET name=?, username=? WHERE tg_id=?", name, f.get("username"), uid)
            u = self.user(uid)
        text = (m.get("text") or "").strip()
        cmd = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""

        if not u or u["status"] != "active":
            return self.stranger(uid, name, f.get("username"), u)
        if cmd == "/cancel":
            self.s.drop(f"await:{uid}")
            return self.send(uid, "Отменено.")
        if self.is_admin(u) and not cmd and self.s.get(f"await:{uid}"):
            return self.admin_input(u, text)
        if cmd in ("/start", "/help"):
            return self.send(uid, self.welcome(u))
        if cmd == "/users" and self.is_admin(u):
            return self.users_list(uid)
        if cmd == "/partners" and self.is_admin(u):
            return self.partners_list(uid)
        self.send(uid, "Команды — в меню слева от поля ввода или /help.")

    def stranger(self, uid, name, username, u):
        if u and u["status"] == "pending":
            return self.send(uid, "Запрос на доступ уже отправлен. Как только студия его одобрит, бот напишет вам.")
        if u and u["status"] == "rejected":
            return self.send(uid, "Доступ к боту не предоставлен. Если это ошибка — свяжитесь со студией DUMSKAYA DESIGN.")
        if u:
            self.s.run("UPDATE users SET status='pending', role=NULL, partner_id=NULL, updated=? WHERE tg_id=?", now(), uid)
        else:
            self.s.run("INSERT INTO users(tg_id, name, username, status, created, updated) VALUES(?, ?, ?, 'pending', ?, ?)",
                       uid, name, username, now(), now())
        self.send(uid, "Здравствуйте! Это внутренний бот студии DUMSKAYA DESIGN.\n\n"
                       "Запрос на доступ отправлен студии. Как только его одобрят, бот напишет вам.")
        u = self.user(uid)
        text = (f"<b>Запрос доступа к боту</b>\n{esc(self.label(u))}\nTelegram ID: <code>{uid}</code>\n\nКем принять?")
        for a in self.active(ADMIN_ROLES):
            self.send(a["tg_id"], text, self.role_rows("a", uid, a))

    def role_rows(self, mode, uid, admin):
        rows = []
        if admin["role"] == "owner":
            rows.append([(ROLES["designer"], f"ro:{mode}:{uid}:designer")])
        rows.append([(ROLES["supplier"], f"ro:{mode}:{uid}:supplier"), (ROLES["maker"], f"ro:{mode}:{uid}:maker")])
        rows.append([(ROLES["foreman"], f"ro:{mode}:{uid}:foreman")])
        rows.append([("Отклонить", f"x:{uid}")] if mode == "a" else [("← Назад", f"u:{uid}")])
        return rows

    def welcome(self, u):
        role = u["role"]
        head = f"<b>DUMSKAYA DESIGN</b> — внутренний бот студии.\nВаша роль: {esc(self.role_line(u))}.\n\n"
        if role == "owner":
            return head + ("Сюда приходят все уведомления: заявки с сайта, заявки партнёрам, запросы доступа и ошибки.\n\n"
                           "/users — пользователи и запросы\n/partners — партнёры и их товары")
        if role == "designer":
            return head + ("Сюда приходят заявки с сайта, уведомления о заявках партнёрам и запросы на доступ к боту.\n\n"
                           "/users — пользователи и запросы\n/partners — партнёры и их товары")
        if role == "supplier":
            return head + "Сюда будут приходить заявки с сайта dumskaya-design.com на ваши товары."
        return head + "Уведомления для вашей роли появятся позже — студия сообщит об этом."

    # ---------- кнопки ----------
    def on_button(self, cq):
        self.api("answerCallbackQuery", callback_query_id=cq["id"])
        admin = self.user(cq["from"]["id"])
        msg = cq.get("message")
        if not self.is_admin(admin) or not msg:
            return
        parts = (cq.get("data") or "").split(":")
        act = parts[0]
        try:
            if act == "ro":                            # ro:режим:uid:роль — выбрана роль
                mode, uid, role = parts[1], int(parts[2]), parts[3]
                return self.pick_role(admin, msg, mode, uid, role)
            if act == "pt":                            # pt:режим:uid:роль:партнёр — выбрана компания
                mode, uid, role, pid = parts[1], int(parts[2]), parts[3], int(parts[4])
                if not self.check_target(admin, msg, mode, uid):
                    return
                return self.approve(admin, uid, role, pid, msg)
            if act == "np":                            # np:режим:uid:роль — новая компания
                mode, uid, role = parts[1], int(parts[2]), parts[3]
                if not self.check_target(admin, msg, mode, uid):
                    return
                self.s.put(f"await:{admin['tg_id']}", json.dumps({"uid": uid, "role": role, "mode": mode}))
                return self.send(admin["tg_id"], f"Напишите название компании для {esc(self.label(self.user(uid)))} "
                                                 f"(или имя, если это частный мастер). /cancel — отменить.",
                                 reply_markup={"force_reply": True, "input_field_placeholder": "Название компании"})
            if act == "x":                             # отклонить запрос
                return self.reject(admin, int(parts[1]), msg)
            if act == "u":                             # карточка пользователя
                return self.user_card(admin, int(parts[1]), msg)
            if act == "cr":                            # сменить роль — выбор новой роли
                uid = int(parts[1])
                if not self.check_target(admin, msg, "c", uid):
                    return
                return self.edit(msg, f"{esc(self.label(self.user(uid)))} — новая роль:", self.role_rows("c", uid, admin))
            if act == "rm":                            # удалить — подтверждение
                uid = int(parts[1])
                if not self.can_manage(admin, self.user(uid)):
                    return self.edit(msg, "Этого пользователя может изменить только разработчик.")
                return self.edit(msg, f"Закрыть доступ к боту для {esc(self.label(self.user(uid)))}?",
                                 [[("Да, закрыть доступ", f"rm2:{uid}"), ("Отмена", f"u:{uid}")]])
            if act == "rm2":
                return self.remove(admin, int(parts[1]), msg)
            if act == "users":
                return self.users_list(admin["tg_id"], msg)
        except (IndexError, ValueError):
            return

    def check_target(self, admin, msg, mode, uid):
        u = self.user(uid)
        if not u:
            self.edit(msg, "Пользователь не найден.")
            return False
        if mode == "a" and u["status"] != "pending":
            self.edit(msg, f"Запрос уже обработан: {esc(self.label(u))} — "
                           f"{esc(self.role_line(u)) if u['status'] == 'active' else 'отклонён'}.")
            return False
        if mode == "c" and not self.can_manage(admin, u):
            self.edit(msg, "Этого пользователя может изменить только разработчик.")
            return False
        return True

    def can_manage(self, admin, u):
        if not u or u["role"] == "owner":
            return False
        return admin["role"] == "owner" or u["role"] not in ADMIN_ROLES

    def pick_role(self, admin, msg, mode, uid, role):
        if role not in ROLES or role == "owner" or not self.check_target(admin, msg, mode, uid):
            return
        if role == "designer":
            if admin["role"] != "owner":
                return self.edit(msg, "Назначить дизайнера студии может только разработчик.")
            return self.approve(admin, uid, role, None, msg)
        partners = self.s.all("SELECT * FROM partners ORDER BY name LIMIT 30")
        rows = [[(p["name"], f"pt:{mode}:{uid}:{role}:{p['id']}")] for p in partners]
        rows.append([("➕ Новая компания", f"np:{mode}:{uid}:{role}")])
        rows.append([("← Назад", f"u:{uid}")])
        self.edit(msg, f"{esc(self.label(self.user(uid)))} — {esc(ROLES[role])}.\nИз какой компании?", rows)

    def admin_input(self, admin, text):
        st = json.loads(self.s.get(f"await:{admin['tg_id']}") or "{}")
        name = " ".join(text.split())
        if not (2 <= len(name) <= 80):
            return self.send(admin["tg_id"], "Название — от 2 до 80 символов. Напишите ещё раз или /cancel.")
        uid, role, mode = st.get("uid"), st.get("role"), st.get("mode", "a")
        u = self.user(uid) if uid else None
        if not u or role not in PARTNER_ROLES or (mode == "a" and u["status"] != "pending"):
            self.s.drop(f"await:{admin['tg_id']}")
            return self.send(admin["tg_id"], "Запрос уже обработан.")
        p = self.s.one("SELECT * FROM partners WHERE name=?", name)
        pid = p["id"] if p else self.s.run("INSERT INTO partners(name, created) VALUES(?, ?)", name, now())
        self.s.drop(f"await:{admin['tg_id']}")
        self.approve(admin, uid, role, pid, None)

    def approve(self, admin, uid, role, pid, msg):
        was = self.user(uid)
        self.s.run("UPDATE users SET role=?, status='active', partner_id=?, added_by=?, updated=? WHERE tg_id=?",
                   role, pid if role in PARTNER_ROLES else None, admin["tg_id"], now(), uid)
        u = self.user(uid)
        result = f"✅ {esc(self.label(u))} — {esc(self.role_line(u))}"
        if msg:
            self.edit(msg, result, [[("Пользователи", "users")]])
        else:
            self.send(admin["tg_id"], result)
        changed = was and was["status"] == "active"
        self.send(uid, ("Ваша роль в боте изменена.\n\n" if changed else "Доступ к боту открыт.\n\n") + self.welcome(u))
        self.admin_commands(uid, role in ADMIN_ROLES)
        verb = "изменил(а) роль" if changed else "принял(а)"
        self.notify(f"{esc(self.label(admin))} {verb}: {esc(self.label(u))} — {esc(self.role_line(u))}", skip=(admin["tg_id"],))

    def reject(self, admin, uid, msg):
        u = self.user(uid)
        if not u or u["status"] != "pending":
            return self.edit(msg, "Запрос уже обработан.")
        self.s.run("UPDATE users SET status='rejected', added_by=?, updated=? WHERE tg_id=?", admin["tg_id"], now(), uid)
        self.edit(msg, f"Отклонён запрос: {esc(self.label(u))}")
        self.notify(f"{esc(self.label(admin))} отклонил(а) запрос: {esc(self.label(u))}", skip=(admin["tg_id"],))

    def remove(self, admin, uid, msg):
        u = self.user(uid)
        if not self.can_manage(admin, u):
            return self.edit(msg, "Этого пользователя может изменить только разработчик.")
        self.s.run("UPDATE users SET status='removed', updated=? WHERE tg_id=?", now(), uid)
        self.admin_commands(uid, False)
        self.edit(msg, f"Доступ закрыт: {esc(self.label(u))}", [[("Пользователи", "users")]])
        self.send(uid, "Доступ к боту студии DUMSKAYA DESIGN закрыт.")
        self.notify(f"{esc(self.label(admin))} закрыл(а) доступ: {esc(self.label(u))}", skip=(admin["tg_id"],))

    # ---------- списки ----------
    def users_list(self, chat_id, msg=None):
        users = self.s.all("SELECT * FROM users WHERE status IN ('active','pending') "
                           "ORDER BY status='pending' DESC, role, name")
        lines, rows = ["<b>Пользователи бота</b>"], []
        for u in users:
            if u["status"] == "pending":
                lines.append(f"⏳ {esc(self.label(u))} — ждёт одобрения")
                rows.append([(f"⏳ {self.label(u)}", f"u:{u['tg_id']}")])
            else:
                lines.append(f"• {esc(self.label(u))} — {esc(self.role_line(u))}")
                if u["role"] != "owner":
                    rows.append([(f"{self.label(u)} — {ROLES.get(u['role'], '')}", f"u:{u['tg_id']}")])
        lines.append("\nНажмите на человека, чтобы изменить роль или закрыть доступ.")
        text = "\n".join(lines)
        return self.edit(msg, text, rows) if msg else self.send(chat_id, text, rows)

    def user_card(self, admin, uid, msg):
        u = self.user(uid)
        if not u:
            return self.edit(msg, "Пользователь не найден.")
        if u["status"] == "pending":
            return self.edit(msg, f"<b>Запрос доступа</b>\n{esc(self.label(u))}\nTelegram ID: <code>{uid}</code>\n\nКем принять?",
                             self.role_rows("a", uid, admin))
        text = (f"<b>{esc(self.label(u))}</b>\nРоль: {esc(self.role_line(u))}\nTelegram ID: <code>{uid}</code>"
                + (f"\nПринял(а): {esc(self.label(self.user(u['added_by'])))}" if u["added_by"] else ""))
        if self.can_manage(admin, u):
            rows = [[("Изменить роль", f"cr:{uid}")], [("Закрыть доступ", f"rm:{uid}")], [("← Все пользователи", "users")]]
        else:
            rows = [[("← Все пользователи", "users")]]
        self.edit(msg, text, rows)

    def partners_list(self, chat_id, products=None):
        products = products if products is not None else load_products()
        lines = ["<b>Партнёры</b>"]
        for p in self.s.all("SELECT * FROM partners ORDER BY name"):
            people = [self.label(u) for u in self.s.all("SELECT * FROM users WHERE partner_id=? AND status='active'", p["id"])]
            goods = sorted(code for code, it in products.items() if str(it.get("partner") or "") == str(p["id"]))
            lines.append(f"\n<b>№{p['id']} {esc(p['name'])}</b>\n"
                         f"Люди: {esc(', '.join(people)) if people else 'никого — заявки придут вам'}\n"
                         f"Товары на сайте: {esc(', '.join(goods)) if goods else 'нет'}")
        if len(lines) == 1:
            lines.append("Пока нет. Партнёр появляется, когда вы принимаете человека в роли поставщика, "
                         "изготовителя или прораба и указываете его компанию.")
        lines.append("\nНомер партнёра (№) нужен, чтобы привязать к нему товар в магазине на сайте.")
        self.send(chat_id, "\n".join(lines))

    # ---------- заявки с сайта ----------
    def route_lead(self, lead, products=None):
        """Заявку — разработчику и дизайнерам; если это товар партнёра — ещё и людям этого партнёра.
        Возвращает список Telegram ID, кому доставлено."""
        products = products if products is not None else load_products()
        model = (lead.get("model") or "").strip()
        prod = products.get(model.upper()) if model else None
        body = format_lead(lead, model, prod)
        pid = prod.get("partner") if prod else None
        delivered = []
        if pid:
            p = self.partner(int(pid)) if str(pid).isdigit() else None
            people = self.s.all("SELECT * FROM users WHERE partner_id=? AND status='active'", int(pid)) if p else []
            for u in people:
                if self.send(u["tg_id"], "<b>Заявка с сайта DUMSKAYA DESIGN на ваш товар</b>\n\n" + body):
                    delivered.append(u["tg_id"])
            who = ", ".join(self.label(u) for u in people if u["tg_id"] in delivered)
            if not p:
                head = f"⚠️ <b>Заявка на товар партнёра №{esc(pid)}</b> — такого партнёра нет в боте, передайте заявку вручную"
            elif who:
                head = f"<b>Заявка на товар партнёра «{esc(p['name'])}»</b> — передана: {esc(who)}"
            else:
                head = f"⚠️ <b>Заявка на товар партнёра «{esc(p['name'])}»</b> — партнёр не подключён к боту, передайте заявку вручную"
            delivered += self.notify(head + "\n\n" + body)
        else:
            delivered += self.notify("<b>Заявка с сайта</b>\n\n" + body)
        return delivered


def format_lead(lead, model, prod):
    lines = [f"<b>Имя:</b> {esc(lead.get('name'))}", f"<b>Контакт:</b> {esc(lead.get('contact'))}"]
    if model:
        lines.append(f"<b>Интересует:</b> {esc(model)}" + (f" — {esc(prod.get('name'))}" if prod and prod.get("name") else ""))
    if lead.get("message"):
        lines.append(f"<b>Сообщение:</b>\n{esc(lead.get('message'))}")
    page = lead.get("page") or ""
    lines.append(f"<i>{esc(lead.get('lang', ''))} · {esc(SITE + page)}</i>")
    return "\n".join(lines)


PRODUCTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shop-products.json")


def load_products(path=PRODUCTS_FILE):
    """Товары магазина: артикул → название, страница, партнёр (номер) — собирается из сайта при выкладке."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {str(k).upper(): v for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}

