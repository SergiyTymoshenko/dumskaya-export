#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Адреса /api/portal/* сервиса заявок — кабинет заказчика и подрядчика («Мой проект», страница portal_app.html)
и переписка студии с заказчиками.

Кто есть кто — по подписи Telegram (заголовок X-Telegram-Init-Data), как в «Студии»:
  • заказчик и подрядчик видят только свои проекты и только то, что отдаёт crm_portal.py (без бонусов и закупок);
  • дизайнер студии может посмотреть кабинет глазами заказчика или подрядчика (?preview=…) и пишет в переписку;
  • разработчику кабинеты не отдаются (заявки и проекты студии ему не нужны — решено 24.10.2026).
Уведомления в Telegram (новое сообщение, сумма на подтверждение…) отправляет бот в фоне — ответ не ждёт Telegram."""
import json
import threading
import time
import urllib.parse
from collections import defaultdict, deque

from crm import CrmError
from crm_portal import STUDIO, ui_lang

CRM = None            # ставит lead_service.py
PORTAL = None
BOT = None
CHECK = None          # check_init_data из site_stats (подпись Telegram)
TOKEN = ""
CHAT_FILE_MAX = 20 * 1024 * 1024       # вложение в переписке — до 20 МБ
CHAT_RATE = defaultdict(deque)          # Telegram ID → время последних сообщений
CHAT_MAX, CHAT_WINDOW = 30, 600         # не больше 30 сообщений за 10 минут
SIZES = ("m", "l", "xl")
_lock = threading.Lock()


class Denied(Exception):
    """Нет доступа к этому проекту — ответ 403 без подробностей."""


def bg(fn, *args, **kw):
    """Уведомления в Telegram — в фоне, чтобы ответ кабинету не ждал Telegram и перевод."""
    def run():
        try:
            fn(*args, **kw)
        except Exception as e:  # noqa: BLE001
            if BOT:
                BOT.log(f"кабинет: уведомление не отправлено: {type(e).__name__}: {e}")
    threading.Thread(target=run, daemon=True).start()


def init_user(h):
    """(Telegram ID, данные пользователя из initData) — по подписи Telegram; иначе (None, {})."""
    raw = h.headers.get("X-Telegram-Init-Data", "")
    uid = CHECK(raw, TOKEN) if CHECK else None
    if not uid:
        return None, {}
    try:
        user = json.loads(dict(urllib.parse.parse_qsl(raw)).get("user") or "{}")
    except ValueError:
        user = {}
    return uid, user if isinstance(user, dict) else {}


def who(h):
    """Кто открыл кабинет: {"tg", "name", "lang", "size", "designer", "user"} или None (нет подписи, нет в боте)."""
    uid, tu = init_user(h)
    u = BOT.user(uid) if uid and BOT else None
    if not u or u["status"] != "active":
        return None
    if tu.get("language_code"):                      # язык Telegram — запоминаем (если человек не выбрал сам)
        code = str(tu["language_code"])[:8]
        if BOT.s.get(f"tg:lang:{uid}") != code:
            BOT.s.put(f"tg:lang:{uid}", code)
    name = " ".join(x for x in (tu.get("first_name"), tu.get("last_name")) if x) or u["name"] or str(uid)
    return {"tg": uid, "name": name, "lang": BOT.lang_of(uid), "size": BOT.s.get(f"ui:size:{uid}") or
            ("l" if u["role"] == "designer" else "m"), "designer": u["role"] == "designer", "user": u}


def _deny(h, code=403, msg="Нет доступа"):
    h.reply(code, {"ok": False, "error": msg})
    return True


def _body(h, limit=20000):
    n = int(h.headers.get("Content-Length") or 0)
    if n <= 0 or n > limit:
        raise CrmError("Слишком большой запрос")
    d = json.loads(h.rfile.read(n).decode("utf-8", "replace") or "{}")
    if not isinstance(d, dict):
        raise CrmError("Неверный запрос")
    return d


def chat_allowed(w, pid):
    """Переписка проекта: дизайнер студии или заказчик этого проекта. Подрядчики — нет."""
    if w["designer"]:
        return "studio"
    return "client" if PORTAL.client_of(w["tg"], pid) else None


def project_view(w, q):
    pid = int(q.get("id") or 0)
    if w["designer"] and q.get("preview"):           # дизайнер смотрит кабинет глазами заказчика или подрядчика
        if q["preview"] == "contractor":
            link = CRM.one("SELECT contractor_id FROM project_contractors WHERE id=? AND project_id=?", int(q.get("link") or 0), pid)
            if not link:
                raise CrmError("Подрядчик в этом проекте не найден")
            return dict(PORTAL.contractor_view(pid, [link["contractor_id"]]), preview=True)
        return dict(PORTAL.client_view(pid), preview=True)
    want = q.get("as")
    is_client = PORTAL.client_of(w["tg"], pid) is not None
    ids = PORTAL.contractor_ids(w["tg"], pid)
    if is_client and (want != "contractor" or not ids):
        v = PORTAL.client_view(pid, w["tg"])
    elif ids:
        v = PORTAL.contractor_view(pid, ids)
    else:
        raise Denied()
    v["both"] = bool(is_client and ids)
    return v


def handle_get(h, path, query):
    if not path.startswith("/api/portal/"):
        return False
    if path == "/api/portal/app":
        import crm_api
        h.reply(200, None, html_page=crm_api.page("portal_app.html"), telegram_frame=True)
        return True
    if not (CRM and PORTAL and BOT):
        return _deny(h, 503, "Кабинет сейчас недоступен")
    w = who(h)
    if not w:
        return _deny(h)
    q = dict(urllib.parse.parse_qsl(query))
    try:
        if path == "/api/portal/me":
            projects = PORTAL.projects_for(w["tg"])
            if not projects and not w["designer"]:
                return _deny(h, 403, "no_projects")
            return h.reply(200, {"name": w["name"], "lang": w["lang"], "size": w["size"], "designer": w["designer"],
                                 "projects": projects, "studio": STUDIO, "translate": BOT.can_translate()}) or True
        if path == "/api/portal/project":
            v = project_view(w, q)
            # дизайнер в просмотре может выбрать язык, как у заказчика
            lang = ui_lang(q["lang"]) if v.get("preview") and q.get("lang") else w["lang"]
            misses = PORTAL.localize(v, lang)             # названия услуг, товаров, этапов — на языке человека
            if misses and BOT.can_translate():
                bg(BOT.fill_labels, misses, lang)         # переводы появятся при следующем открытии
            v["lang"] = lang
            return h.reply(200, v) or True
        if path == "/api/portal/chat":
            pid = int(q.get("project") or 0)
            kind = chat_allowed(w, pid)
            if not kind:
                return _deny(h)
            rows = PORTAL.messages(pid, kind, w["tg"], "ru" if kind == "studio" else w["lang"], q.get("after") or 0)
            if rows and not q.get("preview"):
                PORTAL.mark_read(pid, 0 if kind == "studio" else w["tg"], rows[-1]["id"])
            return h.reply(200, {"messages": rows, "lang": "ru" if kind == "studio" else w["lang"],
                                 "people": [c["name"] for c in PORTAL.chat_people(pid)]}) or True
    except Denied:
        return _deny(h)
    except CrmError as e:
        return h.reply(400, {"ok": False, "error": str(e)}) or True
    except (ValueError, TypeError):
        return h.reply(400, {"ok": False, "error": "Неверные данные"}) or True
    h.reply(404, {"ok": False})
    return True


def _rate_ok(uid):
    now = time.time()
    with _lock:
        q = CHAT_RATE[uid]
        while q and now - q[0] > CHAT_WINDOW:
            q.popleft()
        if len(q) >= CHAT_MAX:
            return False
        q.append(now)
        return True


def handle_post(h, path, query):
    if not path.startswith("/api/portal/"):
        return False
    if not (CRM and PORTAL and BOT):
        return _deny(h, 503, "Кабинет сейчас недоступен")
    w = who(h)
    if not w:
        return _deny(h)
    q = dict(urllib.parse.parse_qsl(query))
    try:
        if path == "/api/portal/upload":                 # вложение в переписку (фото, PDF…) — потом сообщение с ним
            pid = int(q.get("project") or 0)
            if not chat_allowed(w, pid):
                return _deny(h)
            n = int(h.headers.get("Content-Length") or 0)
            if n > CHAT_FILE_MAX:
                h.close_connection = True
                return h.reply(413, {"ok": False, "error": "file_too_big"}) or True
            f = CRM.add_file(pid, "chat", q.get("name") or "file", h.rfile, n,
                             h.headers.get("Content-Type", "application/octet-stream"), w["name"])
            return h.reply(200, {"id": f["id"], "name": f["name"], "url": f["url"], "image": f["image"]}) or True
        d = _body(h)
        if path == "/api/portal/chat":
            pid = int(d.get("project_id") or 0)
            kind = chat_allowed(w, pid)
            if not kind:
                return _deny(h)
            if not _rate_ok(w["tg"]):
                return h.reply(429, {"ok": False, "error": "rate"}) or True
            m = PORTAL.post(pid, kind, w["tg"], STUDIO["designer"]["ru"] if kind == "studio" else w["name"],
                            d.get("text"), d.get("file_id"))
            bg(BOT.chat_fanout, m["id"])
            return h.reply(200, {"ok": True, "id": m["id"]}) or True
        if path == "/api/portal/read":
            pid = int(d.get("project_id") or 0)
            kind = chat_allowed(w, pid)
            if kind:
                PORTAL.mark_read(pid, 0 if kind == "studio" else w["tg"], d.get("last_id") or 0)
            return h.reply(200, {"ok": True}) or True
        if path == "/api/portal/stage":
            act = d.get("action")
            if act in ("confirm", "dispute"):
                st = PORTAL.client_stage(w["tg"], d.get("id"), act, d.get("note"), w["name"])
                bg(BOT.portal_event, "stage_" + act, stage_id=st["id"], by=w["name"])
                return h.reply(200, PORTAL.client_view(st["project_id"], w["tg"])) or True
            if act == "save":
                r = PORTAL.contractor_stage(w["tg"], d, w["name"] + " (подрядчик)")
                bg(BOT.portal_event, "stage_saved", stage_id=r["stage_id"], was=r["was"], by=w["name"], by_contractor=True)
                return h.reply(200, PORTAL.contractor_view(r["project_id"], PORTAL.contractor_ids(w["tg"], r["project_id"]))) or True
            if act == "delete":
                r = PORTAL.contractor_delete_stage(w["tg"], d, w["name"] + " (подрядчик)")
                return h.reply(200, PORTAL.contractor_view(r["project_id"], PORTAL.contractor_ids(w["tg"], r["project_id"]))) or True
            raise CrmError("Неизвестное действие")
        if path == "/api/portal/ui":                     # язык и размер текста — свои у каждого
            if d.get("lang"):
                BOT.s.put(f"ui:lang:{w['tg']}", ui_lang(d["lang"]))
                BOT.sync_portal_menu(w["tg"])
            if d.get("size") in SIZES:
                BOT.s.put(f"ui:size:{w['tg']}", d["size"])
            return h.reply(200, {"lang": BOT.lang_of(w["tg"]), "size": BOT.s.get(f"ui:size:{w['tg']}") or w["size"]}) or True
    except CrmError as e:
        return h.reply(400, {"ok": False, "error": str(e)}) or True
    except (ValueError, TypeError):
        return h.reply(400, {"ok": False, "error": "Неверные данные"}) or True
    h.reply(404, {"ok": False})
    return True
