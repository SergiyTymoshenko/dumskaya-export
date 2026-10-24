#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram-бот студии DUMSKAYA DESIGN — внутренний инструмент. Работает внутри сервиса заявок
(lead_service.py), только стандартная библиотека Python 3.

Пользователи и роли:
  1) разработчик (BOT_OWNER_ID в lead.env) — получает все уведомления, принимает пользователей;
  2) дизайнер студии — получает заявки с сайта и уведомления о заявках партнёрам, принимает пользователей;
     назначить дизайнера может только разработчик. За одним из студии закреплены товары магазина студии
     (товары без партнёра): заявки на них идут ему, разработчику — копия. Если дизайнер один — за ним
     автоматически; сменить — кнопка в карточке человека (/users), только у разработчика;
  3) партнёры: поставщик, изготовитель мебели, прораб, независимый подрядчик — привязаны к компании
     (частное лицо — компания с его именем). Людям компании приходят заявки с сайта на её товары;
  4) сотрудники поставщиков — их добавляет сам поставщик: /invite даёт одноразовую ссылку,
     сотрудник открывает её и нажимает «Старт», поставщик подтверждает. Сотрудникам приходят заявки
     на товары компании, как и поставщику. Студия видит их в /users и может закрыть доступ.

Попасть в бот можно только по одобрению: человек нажимает «Старт», разработчику и дизайнерам приходит
запрос с кнопками ролей (или, по ссылке-приглашению, — поставщику). Данные — в SQLite (BOT_DB, по умолчанию
~/dumskaya/bot.db). Сообщения получаем long polling'ом (getUpdates) — входящих подключений к серверу не нужно.
"""
import html
import json
import os
import secrets
import sqlite3
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

try:                                   # перевод сообщений заказчиков (translate.py рядом)
    from translate import lang_from
except ImportError:                    # pragma: no cover
    def lang_from(code):
        return ""

SITE = "https://dumskaya-design.com"
ROLES = {
    "owner": "Разработчик",
    "designer": "Дизайнер студии",
    "supplier": "Поставщик",
    "staff": "Сотрудник поставщика",
    "maker": "Изготовитель мебели",
    "foreman": "Прораб",
    "contractor": "Независимый подрядчик",
}
ROLE_ORDER = list(ROLES)
ADMIN_ROLES = ("owner", "designer")
PARTNER_ROLES = ("supplier", "maker", "foreman", "contractor")   # партнёры студии
COMPANY_ROLES = PARTNER_ROLES + ("staff",)                         # привязаны к компании-партнёру
INVITE_DAYS = 7

ADMIN_COMMANDS = [{"command": "users", "description": "Пользователи и запросы"},
                  {"command": "partners", "description": "Партнёры и их товары"},
                  {"command": "site", "description": "Работает ли сайт"},
                  {"command": "stats", "description": "Посетители сайта"},
                  {"command": "help", "description": "Что умеет бот"},
                  {"command": "cancel", "description": "Отменить ввод"}]
# кнопки под полем ввода у разработчика и дизайнера (нажатие = команда); «Графики» — кнопка меню слева от поля
BTN_STATS, BTN_SITE, BTN_USERS, BTN_PARTNERS = "📊 Статистика", "🌐 Сайт", "👥 Пользователи", "🤝 Партнёры"
ADMIN_BUTTONS = {BTN_STATS: "/stats", BTN_SITE: "/site", BTN_USERS: "/users", BTN_PARTNERS: "/partners"}
ADMIN_KEYBOARD = {"keyboard": [[{"text": BTN_STATS}, {"text": BTN_SITE}], [{"text": BTN_USERS}, {"text": BTN_PARTNERS}]],
                  "resize_keyboard": True, "is_persistent": True}
KEYBOARD_VERSION = "1"               # сменить — и кнопки придут всем заново (если поменялся набор)
SUPPLIER_COMMANDS = [{"command": "team", "description": "Мои сотрудники"},
                     {"command": "invite", "description": "Пригласить сотрудника"},
                     {"command": "help", "description": "Что умеет бот"}]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  tg_id INTEGER PRIMARY KEY,
  name TEXT, username TEXT,
  role TEXT,                    -- owner, designer, supplier, staff, maker, foreman, contractor
  status TEXT NOT NULL,         -- pending, active, rejected, removed
  partner_id INTEGER,           -- компания-партнёр (для партнёров и сотрудников поставщиков)
  added_by INTEGER, created TEXT, updated TEXT
);
CREATE TABLE IF NOT EXISTS partners (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  created TEXT
);
CREATE TABLE IF NOT EXISTS invites (  -- одноразовые ссылки поставщиков для сотрудников
  token TEXT PRIMARY KEY,
  partner_id INTEGER NOT NULL,
  created_by INTEGER NOT NULL,
  created TEXT, expires TEXT,
  used_by INTEGER, used TEXT
);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
"""


def now(days=0):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")


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

    def count(self, sql, *a):
        """Выполнить изменение и вернуть число затронутых строк."""
        with self.lock:
            return self.db.execute(sql, a).rowcount

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
        self.monitor = None                  # сторож сайта (site_monitor.py), ставит lead_service.py
        if self.owner:
            u = self.user(self.owner)
            if not u:
                self.s.run("INSERT INTO users(tg_id, name, role, status, created, updated) VALUES(?, ?, 'owner', 'active', ?, ?)",
                           self.owner, "Разработчик", now(), now())
            elif u["role"] != "owner" or u["status"] != "active":
                self.s.run("UPDATE users SET role='owner', status='active', partner_id=NULL, updated=? WHERE tg_id=?",
                           now(), self.owner)

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
        """Кнопки: (текст, callback_data) или (текст, {"web_app": {...}} / {"url": ...})."""
        return {"inline_keyboard": [[{"text": t, **d} if isinstance(d, dict) else {"text": t, "callback_data": d}
                                     for t, d in row] for row in rows if row]}

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

    def is_supplier(self, u):
        return bool(u) and u["status"] == "active" and u["role"] == "supplier" and bool(u["partner_id"])

    def partner(self, pid):
        return self.s.one("SELECT * FROM partners WHERE id=?", pid) if pid else None

    def company(self, u):
        p = self.partner(u["partner_id"]) if u else None
        return p["name"] if p else "—"

    def label(self, u):
        if not u:
            return "—"
        tag = f" (@{u['username']})" if u["username"] else ""
        return f"{u['name'] or u['tg_id']}{tag}"

    def role_line(self, u):
        role = ROLES.get(u["role"], "—")
        p = self.partner(u["partner_id"])
        return role + (f" «{p['name']}»" if p else "")

    def notify(self, text, roles=ADMIN_ROLES, skip=(), rows=None):
        """Сообщение всем активным пользователям с этими ролями (по умолчанию — разработчику и дизайнерам)."""
        sent = []
        for u in self.active(roles):
            if u["tg_id"] in skip:
                continue
            if self.send(u["tg_id"], text, rows):
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
        self.ensure_shop_manager()
        self.ensure_partners()
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
        for u in self.active(ADMIN_ROLES + ("supplier",)):
            self.set_commands(u)

    def set_commands(self, u):
        """Меню команд конкретного человека: у студии — /users, /partners; у поставщика — /team, /invite."""
        scope = {"type": "chat", "chat_id": u["tg_id"]}
        cmds = ADMIN_COMMANDS if self.is_admin(u) else SUPPLIER_COMMANDS if self.is_supplier(u) else None
        if cmds:
            self.api("setMyCommands", scope=scope, commands=cmds)
        else:
            self.api("deleteMyCommands", scope=scope)
        self.sync_buttons(u)

    # ---------- кнопки студии ----------
    def stats_app_url(self):
        """Адрес мини-приложения с графиками — только когда сайт на домене (иначе открывать нечего)."""
        st = getattr(self, "stats", None)
        if not st or not st.live_fn():
            return None
        try:
            from site_stats import APP_URL
            return APP_URL
        except ImportError:
            return None

    def keyboard_extra(self, u):
        """Для отправки сообщения разработчику или дизайнеру — с кнопками студии под полем ввода."""
        if not self.is_admin(u):
            return {}
        self.s.put(f"kbd:{u['tg_id']}", KEYBOARD_VERSION)
        return {"reply_markup": ADMIN_KEYBOARD}

    def sync_buttons(self, u):
        """Кнопки под полем ввода и кнопка «Графики» слева — у разработчика и дизайнера; у остальных — убрать."""
        uid, flag = u["tg_id"], f"kbd:{u['tg_id']}"
        if self.is_admin(u):
            url = self.stats_app_url()
            self.api("setChatMenuButton", chat_id=uid, menu_button=(
                {"type": "web_app", "text": "Графики", "web_app": {"url": url}} if url else {"type": "commands"}))
            if self.s.get(flag) != KEYBOARD_VERSION:
                self.send(uid, "Кнопки студии — внизу экрана: статистика, сайт, пользователи и партнёры."
                          + (" Слева от поля ввода — «Графики» посетителей сайта." if url else ""),
                          **self.keyboard_extra(u))
        elif self.s.get(flag):
            self.s.drop(flag)
            self.send(uid, "Кнопки студии убраны.", reply_markup={"remove_keyboard": True})
            self.api("setChatMenuButton", chat_id=uid, menu_button={"type": "commands"})

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
        arg = text.split(maxsplit=1)[1].strip() if cmd and len(text.split(maxsplit=1)) > 1 else ""

        if cmd == "/start" and arg.startswith("inv_"):     # ссылка-приглашение от поставщика
            return self.join_invite(uid, name, f.get("username"), u, arg[4:])
        if not u or u["status"] != "active":
            return self.stranger(uid, name, f.get("username"), u)
        if text in ADMIN_BUTTONS and self.is_admin(u):     # кнопка под полем ввода = команда
            self.s.drop(f"await:{uid}")
            cmd, arg = ADMIN_BUTTONS[text], ""
        if cmd == "/cancel":
            self.s.drop(f"await:{uid}")
            return self.send(uid, "Отменено.")
        if self.is_admin(u) and not cmd and self.s.get(f"await:{uid}"):
            return self.admin_input(u, text)
        if cmd in ("/start", "/help"):
            return self.send(uid, self.welcome(u), **self.keyboard_extra(u))
        if cmd == "/users" and self.is_admin(u):
            return self.users_list(uid)
        if cmd == "/partners" and self.is_admin(u):
            return self.partners_list(uid)
        if cmd == "/site" and self.is_admin(u):
            mon = getattr(self, "monitor", None)
            return self.send(uid, mon.status() if mon else "Сторож сайта не запущен.")
        if cmd == "/stats" and self.is_admin(u):
            st = getattr(self, "stats", None)
            if not st:
                return self.send(uid, "Статистика посетителей не запущена.")
            return self.send(uid, st.command(), st.button())
        if cmd == "/team" and self.is_supplier(u):
            return self.team_list(u)
        if cmd == "/invite" and self.is_supplier(u):
            return self.make_invite(u)
        self.send(uid, "Команды — в меню слева от поля ввода или /help.")

    def stranger(self, uid, name, username, u):
        if u and u["status"] == "pending":
            return self.send(uid, "Запрос на доступ уже отправлен. Как только его одобрят, бот напишет вам.")
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
        rows.append([(ROLES["supplier"], f"ro:{mode}:{uid}:supplier"), (ROLES["staff"], f"ro:{mode}:{uid}:staff")])
        rows.append([(ROLES["maker"], f"ro:{mode}:{uid}:maker"), (ROLES["foreman"], f"ro:{mode}:{uid}:foreman")])
        rows.append([(ROLES["contractor"], f"ro:{mode}:{uid}:contractor")])
        rows.append([("Отклонить", f"x:{uid}")] if mode == "a" else [("← Назад", f"u:{uid}")])
        return rows

    def welcome(self, u):
        role = u["role"]
        head = f"<b>DUMSKAYA DESIGN</b> — внутренний бот студии.\nВаша роль: {esc(self.role_line(u))}.\n\n"
        if role == "owner":
            return head + ("Сюда приходят все уведомления: заявки с сайта, заявки партнёрам, запросы доступа и ошибки, "
                           "а если сайт перестанет отвечать — «🔴 Сайт не отвечает» (и «🟢 снова работает»).\n\n"
                           "Каждый день в 9:00 — отчёт о посетителях сайта за вчера, по понедельникам — и за неделю.\n\n"
                           "Кнопки внизу экрана: 📊 Статистика, 🌐 Сайт, 👥 Пользователи, 🤝 Партнёры; "
                           "слева от поля ввода — «Графики» посетителей.")
        if role == "designer":
            mgr = self.shop_manager()
            shop = ("Товары магазина студии закреплены за вами — заявки на них тоже приходят сюда.\n\n"
                    if mgr and mgr["tg_id"] == u["tg_id"] else "")
            return head + ("Сюда приходят заявки с сайта, уведомления о заявках партнёрам и запросы на доступ к боту.\n"
                           + shop + "\nКнопки внизу экрана: 📊 Статистика (посетители сайта), 🌐 Сайт (работает ли), "
                           "👥 Пользователи, 🤝 Партнёры; слева от поля ввода — «Графики» посетителей.")
        if role == "supplier":
            return head + ("Сюда будут приходить заявки с сайта dumskaya-design.com на ваши товары — вам "
                           "и вашим сотрудникам в боте.\n\n/team — ваши сотрудники в боте\n/invite — пригласить сотрудника")
        if role == "staff":
            return head + "Сюда будут приходить заявки с сайта dumskaya-design.com на товары вашей компании."
        return head + "Уведомления для вашей роли появятся позже — студия сообщит об этом."

    # ---------- кнопки ----------
    def on_button(self, cq):
        self.api("answerCallbackQuery", callback_query_id=cq["id"])
        who = self.user(cq["from"]["id"])
        msg = cq.get("message")
        if not who or who["status"] != "active" or not msg:
            return
        parts = (cq.get("data") or "").split(":")
        try:
            if self.is_admin(who):
                return self.admin_button(who, msg, parts)
            if self.is_supplier(who):
                return self.supplier_button(who, msg, parts)
        except (IndexError, ValueError):
            return

    def admin_button(self, admin, msg, parts):
        act = parts[0]
        if act == "ro":                            # ro:режим:uid:роль — выбрана роль
            mode, uid, role = parts[1], int(parts[2]), parts[3]
            return self.pick_role(admin, msg, mode, uid, role)
        if act == "pt":                            # pt:режим:uid:роль:партнёр — выбрана компания
            mode, uid, role, pid = parts[1], int(parts[2]), parts[3], int(parts[4])
            if role not in COMPANY_ROLES or not self.partner(pid) or not self.check_target(admin, msg, mode, uid):
                return
            return self.approve(admin, uid, role, pid, msg)
        if act == "pp":                            # pp:режим:uid:роль — частное лицо (компания с его именем)
            mode, uid, role = parts[1], int(parts[2]), parts[3]
            if role not in PARTNER_ROLES or not self.check_target(admin, msg, mode, uid):
                return
            return self.approve(admin, uid, role, self.partner_by_name(self.user(uid)["name"]), msg)
        if act == "np":                            # np:режим:uid:роль — новая компания
            mode, uid, role = parts[1], int(parts[2]), parts[3]
            if role not in PARTNER_ROLES or not self.check_target(admin, msg, mode, uid):
                return
            self.s.put(f"await:{admin['tg_id']}", json.dumps({"uid": uid, "role": role, "mode": mode}))
            return self.send(admin["tg_id"], f"Напишите название компании для {esc(self.label(self.user(uid)))}. "
                                             f"/cancel — отменить.",
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
        if act == "sm":                            # закрепить товары магазина студии (только разработчик)
            u = self.user(int(parts[1]))
            if admin["role"] != "owner" or not u or u["status"] != "active" or u["role"] not in ADMIN_ROLES:
                return self.edit(msg, "Закрепить товары магазина может только разработчик — за собой или дизайнером студии.")
            self.set_shop_manager(u, by=admin)
            return self.user_card(admin, u["tg_id"], msg)

    def check_target(self, admin, msg, mode, uid):
        u = self.user(uid)
        if not u:
            self.edit(msg, "Пользователь не найден.")
            return False
        if mode == "a" and u["status"] != "pending":
            self.edit(msg, f"Запрос уже обработан: {esc(self.label(u))} — "
                           f"{esc(self.role_line(u)) if u['status'] == 'active' else 'не принят'}.")
            return False
        if mode == "c" and not self.can_manage(admin, u):
            self.edit(msg, "Этого пользователя может изменить только разработчик.")
            return False
        return True

    def can_manage(self, admin, u):
        if not u or u["role"] == "owner":
            return False
        return admin["role"] == "owner" or u["role"] not in ADMIN_ROLES

    def find_partner(self, ref):
        """Партнёр товара: номер из бота (/partners) или название компании (для фабрик из content/shop/manufacturers.json)."""
        if ref is None or str(ref).strip() == "":
            return None
        if str(ref).isdigit():
            return self.partner(int(ref))
        return self.s.one("SELECT * FROM partners WHERE name=?", str(ref).strip())

    def ensure_partners(self, products=None):
        """Компании партнёров, указанные у товаров по названию, заводятся в боте заранее — при приёме человека
        их остаётся выбрать из списка («Из какой компании?»)."""
        products = products if products is not None else load_products()
        for name in sorted({str(it.get("partner")).strip() for it in products.values()
                            if it.get("partner") and not str(it.get("partner")).isdigit()}):
            if not self.s.one("SELECT 1 FROM partners WHERE name=?", name):
                self.s.run("INSERT INTO partners(name, created) VALUES(?, ?)", name, now())

    def partner_by_name(self, name):
        p = self.s.one("SELECT * FROM partners WHERE name=?", name)
        return p["id"] if p else self.s.run("INSERT INTO partners(name, created) VALUES(?, ?)", name, now())

    def pick_role(self, admin, msg, mode, uid, role):
        if role not in ROLES or role == "owner" or not self.check_target(admin, msg, mode, uid):
            return
        if role == "designer":
            if admin["role"] != "owner":
                return self.edit(msg, "Назначить дизайнера студии может только разработчик.")
            return self.approve(admin, uid, role, None, msg)
        u = self.user(uid)
        if role == "staff":                         # сотрудник — только в компанию, где есть поставщик
            partners = self.s.all("SELECT DISTINCT p.* FROM partners p JOIN users s ON s.partner_id=p.id "
                                  "AND s.role='supplier' AND s.status='active' ORDER BY p.name LIMIT 30")
            rows = [[(p["name"], f"pt:{mode}:{uid}:{role}:{p['id']}")] for p in partners]
            rows.append([("← Назад", f"u:{uid}")])
            if not partners:
                return self.edit(msg, "Сотрудника можно добавить только в компанию поставщика, а поставщиков в боте "
                                      "пока нет. Сначала примите поставщика.", rows)
            return self.edit(msg, f"{esc(self.label(u))} — {esc(ROLES[role])}.\nЧей сотрудник?", rows)
        partners = self.s.all("SELECT * FROM partners ORDER BY name LIMIT 30")
        rows = [[(p["name"], f"pt:{mode}:{uid}:{role}:{p['id']}")] for p in partners if p["name"] != u["name"]]
        rows.append([(f"👤 Без компании — {u['name']}", f"pp:{mode}:{uid}:{role}")])
        rows.append([("➕ Новая компания", f"np:{mode}:{uid}:{role}")])
        rows.append([("← Назад", f"u:{uid}")])
        self.edit(msg, f"{esc(self.label(u))} — {esc(ROLES[role])}.\nИз какой компании?", rows)

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
        pid = self.partner_by_name(name)
        self.s.drop(f"await:{admin['tg_id']}")
        self.approve(admin, uid, role, pid, None)

    def approve(self, admin, uid, role, pid, msg):
        was = self.user(uid)
        self.s.run("UPDATE users SET role=?, status='active', partner_id=?, added_by=?, updated=? WHERE tg_id=?",
                   role, pid if role in COMPANY_ROLES else None, admin["tg_id"], now(), uid)
        u = self.user(uid)
        result = f"✅ {esc(self.label(u))} — {esc(self.role_line(u))}"
        if msg:
            self.edit(msg, result, [[("Пользователи", "users")]])
        else:
            self.send(admin["tg_id"], result)
        changed = was and was["status"] == "active"
        self.send(uid, ("Ваша роль в боте изменена.\n\n" if changed else "Доступ к боту открыт.\n\n") + self.welcome(u),
                  **self.keyboard_extra(u))
        self.set_commands(u)
        verb = "изменил(а) роль" if changed else "принял(а)"
        self.notify(f"{esc(self.label(admin))} {verb}: {esc(self.label(u))} — {esc(self.role_line(u))}", skip=(admin["tg_id"],))
        self.ensure_shop_manager()

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
        self.set_commands(self.user(uid))
        self.edit(msg, f"Доступ закрыт: {esc(self.label(u))}", [[("Пользователи", "users")]])
        self.send(uid, "Доступ к боту студии DUMSKAYA DESIGN закрыт.")
        self.notify(f"{esc(self.label(admin))} закрыл(а) доступ: {esc(self.label(u))}", skip=(admin["tg_id"],))
        self.ensure_shop_manager()

    # ---------- товары магазина студии ----------
    def shop_manager(self):
        """Кто отвечает за товары магазина студии (товары без партнёра): ему приходят заявки на них."""
        v = self.s.get("shop_manager")
        u = self.user(int(v)) if v and v.isdigit() else None
        return u if u and u["status"] == "active" and u["role"] in ADMIN_ROLES else None

    def set_shop_manager(self, u, by=None):
        self.s.put("shop_manager", str(u["tg_id"]))
        self.send(u["tg_id"], "🛒 За вами закреплены товары магазина студии на сайте dumskaya-design.com. "
                              "Заявки на них будут приходить сюда.")
        self.notify(f"🛒 Товары магазина студии закреплены за: {esc(self.label(u))}", roles=("owner",), skip=(u["tg_id"],))

    def ensure_shop_manager(self):
        """Если ответственного нет (или он больше не в студии), а дизайнер студии один — закрепить за ним."""
        if self.shop_manager():
            return
        designers = self.active(("designer",))
        if len(designers) == 1:
            self.set_shop_manager(designers[0])
        else:
            self.s.drop("shop_manager")

    # ---------- сотрудники поставщика ----------
    def make_invite(self, sup):
        if not self.username:
            return self.send(sup["tg_id"], "Не получилось создать ссылку — попробуйте через минуту.")
        self.s.run("DELETE FROM invites WHERE expires < ?", now(-30))
        token = secrets.token_urlsafe(12)
        self.s.run("INSERT INTO invites(token, partner_id, created_by, created, expires) VALUES(?, ?, ?, ?, ?)",
                   token, sup["partner_id"], sup["tg_id"], now(), now(INVITE_DAYS))
        company = esc(self.company(sup))
        self.send(sup["tg_id"], f"Ссылка для сотрудника «{company}» — в следующем сообщении. Перешлите его сотруднику.\n\n"
                                f"Он откроет ссылку и нажмёт «Старт» — вам придёт запрос, нажмите «Принять».\n"
                                f"Ссылка одноразовая (один сотрудник), действует {INVITE_DAYS} дней.")
        self.send(sup["tg_id"], f"Приглашение в бот студии DUMSKAYA DESIGN для сотрудников «{company}»:\n"
                                f"https://t.me/{self.username}?start=inv_{token}")

    def join_invite(self, uid, name, username, u, token):
        if u and u["status"] == "active":
            return self.send(uid, f"Вы уже подключены к боту: {esc(self.role_line(u))}.\n\n/help — что умеет бот")
        if u and u["status"] == "rejected":
            return self.send(uid, "Доступ к боту не предоставлен. Если это ошибка — свяжитесь со студией DUMSKAYA DESIGN.")
        if u and u["status"] == "pending" and u["role"] == "staff":
            return self.send(uid, "Запрос уже отправлен поставщику. Как только он подтвердит, бот напишет вам.")
        inv = self.s.one("SELECT * FROM invites WHERE token=?", token)
        sup = self.user(inv["created_by"]) if inv else None
        if (not inv or inv["used_by"] or inv["expires"] < now() or not self.is_supplier(sup)
                or sup["partner_id"] != inv["partner_id"]
                or not self.s.count("UPDATE invites SET used_by=?, used=? WHERE token=? AND used_by IS NULL", uid, now(), token)):
            return self.send(uid, "Ссылка-приглашение недействительна: она уже использована или устарела. "
                                  "Попросите у поставщика новую.")
        if u:
            self.s.run("UPDATE users SET status='pending', role='staff', partner_id=?, added_by=?, updated=? WHERE tg_id=?",
                       inv["partner_id"], sup["tg_id"], now(), uid)
        else:
            self.s.run("INSERT INTO users(tg_id, name, username, role, status, partner_id, added_by, created, updated) "
                       "VALUES(?, ?, ?, 'staff', 'pending', ?, ?, ?, ?)",
                       uid, name, username, inv["partner_id"], sup["tg_id"], now(), now())
        u = self.user(uid)
        company = esc(self.company(sup))
        self.send(uid, f"Здравствуйте! Это внутренний бот студии DUMSKAYA DESIGN.\n\n"
                       f"Запрос отправлен: {esc(self.label(sup))} («{company}»). Как только он подтвердит, бот напишет вам.")
        self.send(sup["tg_id"], f"<b>Сотрудник по вашему приглашению</b>\n{esc(self.label(u))}\nTelegram ID: <code>{uid}</code>"
                                f"\n\nПринять сотрудником «{company}»? Ему будут приходить заявки на товары компании.",
                  [[("Принять", f"sa:{uid}"), ("Отклонить", f"sx:{uid}")]])

    def own_staff(self, sup, u, statuses=("active", "pending")):
        return bool(u) and u["role"] == "staff" and u["partner_id"] == sup["partner_id"] and u["status"] in statuses

    def supplier_button(self, sup, msg, parts):
        act = parts[0]
        if act == "team":
            return self.team_list(sup, msg)
        if act == "inv":
            return self.make_invite(sup)
        if act not in ("sa", "sx", "su", "srm", "srm2"):
            return
        uid = int(parts[1])
        u = self.user(uid)
        back = [[("← Мои сотрудники", "team")]]
        if act in ("sa", "sx") and not self.own_staff(sup, u, ("pending",)):
            return self.edit(msg, "Запрос уже обработан.", back)
        if act in ("su", "srm", "srm2") and not self.own_staff(sup, u):
            return self.edit(msg, "Этого человека уже нет среди ваших сотрудников в боте.", back)
        company = esc(self.company(sup))
        who = esc(self.label(u))
        if act == "sa":
            self.s.run("UPDATE users SET status='active', added_by=?, updated=? WHERE tg_id=?", sup["tg_id"], now(), uid)
            u = self.user(uid)
            self.edit(msg, f"✅ {who} — ваш сотрудник в боте.", back)
            self.send(uid, "Доступ к боту открыт.\n\n" + self.welcome(u))
            return self.notify(f"{esc(self.label(sup))} («{company}») добавил(а) сотрудника: {who}")
        if act == "sx":
            self.s.run("UPDATE users SET status='removed', role=NULL, partner_id=NULL, updated=? WHERE tg_id=?", now(), uid)
            self.edit(msg, f"Отклонено: {who}", back)
            return self.send(uid, "Поставщик не подтвердил ваш доступ к боту.")
        if act == "su":
            if u["status"] == "pending":
                return self.edit(msg, f"<b>Запрос по приглашению</b>\n{who}\nTelegram ID: <code>{uid}</code>\n\n"
                                      f"Принять сотрудником «{company}»?",
                                 [[("Принять", f"sa:{uid}"), ("Отклонить", f"sx:{uid}")]] + back)
            return self.edit(msg, f"<b>{who}</b>\nСотрудник «{company}»\nTelegram ID: <code>{uid}</code>",
                             [[("Закрыть доступ", f"srm:{uid}")]] + back)
        if act == "srm":
            return self.edit(msg, f"Закрыть доступ к боту для {who}?",
                             [[("Да, закрыть доступ", f"srm2:{uid}"), ("Отмена", f"su:{uid}")]])
        if act == "srm2":
            self.s.run("UPDATE users SET status='removed', updated=? WHERE tg_id=?", now(), uid)
            self.edit(msg, f"Доступ закрыт: {who}", back)
            self.send(uid, "Доступ к боту студии DUMSKAYA DESIGN закрыт.")
            return self.notify(f"{esc(self.label(sup))} («{company}») закрыл(а) доступ сотруднику: {who}")

    def team_list(self, sup, msg=None):
        staff = self.s.all("SELECT * FROM users WHERE role='staff' AND partner_id=? AND status IN ('active','pending') "
                           "ORDER BY status='pending' DESC, name", sup["partner_id"])
        lines, rows = [f"<b>Сотрудники «{esc(self.company(sup))}» в боте</b>"], []
        for u in staff:
            if u["status"] == "pending":
                lines.append(f"⏳ {esc(self.label(u))} — ждёт подтверждения")
                rows.append([(f"⏳ {self.label(u)}", f"su:{u['tg_id']}")])
            else:
                lines.append(f"• {esc(self.label(u))}")
                rows.append([(self.label(u), f"su:{u['tg_id']}")])
        if not staff:
            lines.append("Пока никого.")
        lines.append("\nСотрудникам приходят заявки с сайта на товары компании. Нажмите на человека, чтобы закрыть доступ.")
        rows.append([("➕ Пригласить сотрудника", "inv")])
        text = "\n".join(lines)
        return self.edit(msg, text, rows) if msg else self.send(sup["tg_id"], text, rows)

    # ---------- списки ----------
    def users_list(self, chat_id, msg=None):
        users = self.s.all("SELECT u.*, p.name AS company FROM users u LEFT JOIN partners p ON p.id=u.partner_id "
                           "WHERE u.status IN ('active','pending')")
        users = sorted(users, key=lambda u: (u["status"] != "pending", u["role"] not in ADMIN_ROLES, (u["company"] or "").lower(),
                                             ROLE_ORDER.index(u["role"]) if u["role"] in ROLE_ORDER else 99, u["name"] or ""))
        lines, rows = ["<b>Пользователи бота</b>"], []
        for u in users:
            if u["status"] == "pending":
                by = f" (по приглашению поставщика, {esc(self.role_line(u))})" if u["role"] == "staff" else ""
                lines.append(f"⏳ {esc(self.label(u))} — ждёт одобрения{by}")
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
            note = (f"\nЖдёт подтверждения поставщика: {esc(self.label(self.user(u['added_by'])))} "
                    f"({esc(self.role_line(u))})" if u["role"] == "staff" else "")
            return self.edit(msg, f"<b>Запрос доступа</b>\n{esc(self.label(u))}\nTelegram ID: <code>{uid}</code>{note}"
                                  f"\n\nКем принять?", self.role_rows("a", uid, admin))
        text = (f"<b>{esc(self.label(u))}</b>\nРоль: {esc(self.role_line(u))}\nTelegram ID: <code>{uid}</code>"
                + (f"\nПринял(а): {esc(self.label(self.user(u['added_by'])))}" if u["added_by"] else ""))
        mgr = self.shop_manager()
        if mgr and mgr["tg_id"] == uid:
            text += "\n🛒 За ней/ним закреплены товары магазина студии"
        if self.can_manage(admin, u):
            rows = [[("Изменить роль", f"cr:{uid}")], [("Закрыть доступ", f"rm:{uid}")], [("← Все пользователи", "users")]]
        else:
            rows = [[("← Все пользователи", "users")]]
        if admin["role"] == "owner" and u["role"] in ADMIN_ROLES and not (mgr and mgr["tg_id"] == uid):
            rows.insert(0, [("🛒 Закрепить товары магазина", f"sm:{uid}")])
        self.edit(msg, text, rows)

    def partners_list(self, chat_id, products=None):
        products = products if products is not None else load_products()
        lines = ["<b>Партнёры</b>"]
        for p in self.s.all("SELECT * FROM partners ORDER BY name"):
            people = sorted(self.s.all("SELECT * FROM users WHERE partner_id=? AND status='active'", p["id"]),
                            key=lambda u: (ROLE_ORDER.index(u["role"]) if u["role"] in ROLE_ORDER else 99, u["name"] or ""))
            people = [f"{self.label(u)} ({ROLES.get(u['role'], '—').lower()})" for u in people]
            goods = sorted(code for code, it in products.items()
                           if str(it.get("partner") or "") in (str(p["id"]), p["name"]))
            if len(goods) > 12:
                goods = goods[:12] + [f"… всего {len(goods)}"]
            lines.append(f"\n<b>№{p['id']} {esc(p['name'])}</b>\n"
                         f"Люди: {esc(', '.join(people)) if people else 'никого — заявки придут вам'}\n"
                         f"Товары на сайте: {esc(', '.join(goods)) if goods else 'нет'}")
        if len(lines) == 1:
            lines.append("Пока нет. Партнёр появляется, когда вы принимаете человека в роли поставщика, "
                         "изготовителя, прораба или подрядчика и указываете его компанию.")
        own = sorted(code for code, it in products.items() if not it.get("partner"))
        if own:
            m = self.shop_manager()
            lines.append(f"\n<b>Товары студии</b>: {esc(', '.join(own))}\n"
                         f"Ответственный: {esc(self.label(m)) if m else 'не назначен — заявки приходят разработчику и дизайнерам'}")
        lines.append("\nНомер партнёра (№) нужен, чтобы привязать к нему товар в магазине на сайте.")
        self.send(chat_id, "\n".join(lines))

    # ---------- заявки с сайта ----------
    def route_lead(self, lead, products=None):
        """Заявку — разработчику и дизайнерам; если это товар партнёра — ещё и людям этого партнёра
        (поставщику и его сотрудникам). Возвращает список Telegram ID, кому доставлено."""
        products = products if products is not None else load_products()
        model = (lead.get("model") or "").strip()
        prod = products.get(model.upper()) if model else None
        body = format_lead(lead, model, prod)
        pid = prod.get("partner") if prod else None
        delivered = []
        if pid:
            p = self.find_partner(pid)
            people = self.s.all("SELECT * FROM users WHERE partner_id=? AND status='active'", p["id"]) if p else []
            for u in people:
                if self.send(u["tg_id"], "<b>Заявка с сайта DUMSKAYA DESIGN на ваш товар</b>\n\n" + body):
                    delivered.append(u["tg_id"])
            who = ", ".join(self.label(u) for u in people if u["tg_id"] in delivered)
            if not p:
                head = (f"⚠️ <b>Заявка на товар партнёра {esc(pid if not str(pid).isdigit() else '№' + str(pid))}</b> — "
                        f"такого партнёра нет в боте, передайте заявку вручную")
            elif who:
                head = f"<b>Заявка на товар партнёра «{esc(p['name'])}»</b> — передана: {esc(who)}"
            else:
                head = f"⚠️ <b>Заявка на товар партнёра «{esc(p['name'])}»</b> — партнёр не подключён к боту, передайте заявку вручную"
            delivered += self.notify(head + "\n\n" + body)
        elif prod:                                   # товар магазина студии — ответственному, разработчику копия
            m = self.shop_manager()
            if m and self.send(m["tg_id"], "<b>🛒 Заявка на товар магазина</b> — закреплён за вами\n\n" + body):
                delivered.append(m["tg_id"])
                delivered += self.notify(f"<b>🛒 Заявка на товар магазина</b> — передана: {esc(self.label(m))}\n\n" + body,
                                         roles=("owner",), skip=(m["tg_id"],))
            else:
                delivered += self.notify("<b>🛒 Заявка на товар магазина</b>\n\n" + body)
        else:
            delivered += self.notify("<b>Заявка с сайта</b>\n\n" + body)
        return delivered


def format_lead(lead, model, prod):
    lines = [f"<b>Имя:</b> {esc(lead.get('name'))}", f"<b>Контакт:</b> {esc(lead.get('contact'))}"]
    if model:
        lines.append(f"<b>Интересует:</b> {esc(model)}" + (f" — {esc(prod.get('name'))}" if prod and prod.get("name") else ""))
    if prod and prod.get("mfr"):                     # подсказка для студии и партнёра; клиент этого не видит
        hint = f"<b>Изготовитель:</b> {esc(prod['mfr'])}"
        if prod.get("mfr_code"):
            hint += f", артикул изготовителя <code>{esc(prod['mfr_code'])}</code>"
        if prod.get("collection"):
            hint += f", коллекция {esc(prod['collection'])}"
        if str(prod.get("mfr_url") or "").startswith("http"):
            hint += f', <a href="{esc(prod["mfr_url"])}">страница у фабрики</a>'
        lines.append(hint)
        ref = prod.get("catalog")                    # где товар в каталоге (техкарте) фабрики; номер — ссылка на страницу PDF
        if isinstance(ref, dict) and ref.get("pages"):
            def pg(p):
                n, label, what = (list(p) + [None, None, None])[:3]
                txt = esc(label or n)
                if ref.get("url") and str(n).isdigit():
                    txt = f'<a href="{esc(ref["url"])}#page={int(n)}">{txt}</a>'
                return txt + (f" ({esc(what)})" if what else "")
            lines.append(f"<b>{esc(ref.get('label') or 'Каталог')}:</b> {esc(ref.get('catalog', ''))}, стр. "
                         + ", ".join(pg(p) for p in ref["pages"]))
    msg, ru = lead.get("message") or "", lead.get("message_ru") or ""
    if msg:
        if ru and len(msg) + len(ru) > 3300:          # Telegram берёт до 4096 знаков; полностью — в письме и файле заявок
            cut = lambda s: s if len(s) <= 1600 else s[:1600].rstrip() + " … (дальше — в письме)"  # noqa: E731
            msg, ru = cut(msg), cut(ru)
        lines.append(f"<b>Сообщение:</b>\n{esc(msg)}")
        if ru:
            src = lang_from(lead.get("message_lang"))
            lines.append(f"<b>Перевод на русский{(' ' + esc(src)) if src else ''}:</b>\n{esc(ru)}")
        elif lead.get("translate_error"):
            lines.append("<i>Перевести не получилось — сервис перевода не ответил.</i>")
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
