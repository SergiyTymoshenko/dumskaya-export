#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Адреса /api/crm/* сервиса заявок — учёт проектов студии (crm.py) для страницы «Студия» (crm_app.html).

Всё, кроме самой страницы и файлов, — только разработчику и дизайнеру: по подписи Telegram (заголовок
X-Telegram-Init-Data), как у графиков. Файлы отдаются по подписанным ссылкам (действуют 12 часов): так их можно
открыть в браузере и скачать. Опасные для сайта типы (HTML, SVG…) отдаются только как вложение и в «песочнице».
"""
import json
import os
import urllib.parse

from crm import FILE_MAX, CrmError

CRM = None            # ставит lead_service.py
BOT = None
INLINE_OK = ("image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf", "video/mp4", "text/plain")


def app_page():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "crm_app.html"), encoding="utf-8") as fh:
        return fh.read()


def _json_body(h, limit=300_000):
    n = int(h.headers.get("Content-Length") or 0)
    if n <= 0 or n > limit:
        raise CrmError("Слишком большой запрос")
    data = json.loads(h.rfile.read(n).decode("utf-8", "replace") or "{}")
    if not isinstance(data, dict):
        raise CrmError("Неверный запрос")
    return data


def _who(u):
    return u["name"] or str(u["tg_id"])


def handle_get(h, path, query):
    """True — запрос обработан."""
    if not path.startswith("/api/crm/"):
        return False
    q = dict(urllib.parse.parse_qsl(query))
    if path == "/api/crm/app":
        h.reply(200, None, html_page=app_page(), telegram_frame=True)
        return True
    if path == "/api/crm/file":
        serve_file(h, q)
        return True
    if not CRM:
        h.reply(503, {"ok": False, "error": "Учёт не запущен"})
        return True
    u = h.stats_admin()
    if not u:
        h.reply(403, {"ok": False, "error": "Нет доступа: учёт открыт разработчику и дизайнеру студии."})
        return True
    try:
        if path == "/api/crm/state":
            out = CRM.state()
            out["me"] = {"name": u["name"], "role": u["role"]}
            return h.reply(200, out) or True
        if path == "/api/crm/project":
            return h.reply(200, CRM.project(q.get("id"))) or True
        if path == "/api/crm/stats":
            p = q.get("p", "month")
            return h.reply(200, CRM.stats(p if p in ("month", "quarter", "year", "all") else "month")) or True
        if path == "/api/crm/rate":
            return h.reply(200, CRM.rate(q.get("cur", "EUR").upper(), q.get("day", ""))) or True
    except CrmError as e:
        return h.reply(400, {"ok": False, "error": str(e)}) or True
    h.reply(404, {"ok": False})
    return True


def handle_post(h, path, query):
    if not path.startswith("/api/crm/"):
        return False
    if not CRM:
        h.reply(503, {"ok": False, "error": "Учёт не запущен"})
        return True
    u = h.stats_admin()
    if not u:
        h.reply(403, {"ok": False, "error": "Нет доступа"})
        return True
    q = dict(urllib.parse.parse_qsl(query))
    who = _who(u)
    try:
        if path == "/api/crm/upload":
            n = int(h.headers.get("Content-Length") or 0)
            if n > FILE_MAX:
                h.close_connection = True
                return h.reply(413, {"ok": False, "error": f"Файл больше {FILE_MAX // 2**20} МБ"}) or True
            f = CRM.add_file(q.get("project"), q.get("cat"), q.get("name") or "файл", h.rfile, n,
                             h.headers.get("Content-Type", "application/octet-stream"), who)
            return h.reply(200, f) or True
        if path == "/api/crm/thumb":
            n = int(h.headers.get("Content-Length") or 0)
            if n <= 0 or n > 2 * 1024 * 1024:
                return h.reply(400, {"ok": False, "error": "Неподходящее превью"}) or True
            return h.reply(200, CRM.set_thumb(q.get("id"), h.rfile.read(n))) or True
        data = _json_body(h)
        if path == "/api/crm/save":
            entity, d = data.get("entity"), data.get("data") or {}
            fn = {"project": CRM.save_project, "op": CRM.save_op, "client": CRM.save_client,
                  "contractor": CRM.save_contractor, "link": CRM.link_contractor, "stage": CRM.save_stage,
                  "lists": CRM.save_lists}.get(entity)
            if not fn:
                raise CrmError("Неизвестно, что сохранять")
            return h.reply(200, fn(d, who)) or True
        if path == "/api/crm/delete":
            return h.reply(200, CRM.delete(data.get("entity"), data.get("id"), who)) or True
        if path == "/api/crm/move":
            return h.reply(200, CRM.move_file(data.get("id"), data.get("category"), who)) or True
        if path == "/api/crm/send":                      # прислать файл проекта в чат с ботом
            fpath, f = CRM.file_path(data.get("id"), "o")
            if not f:
                raise CrmError("Файл не найден")
            if not BOT:
                raise CrmError("Бот не запущен")
            ok, why = BOT.send_file(u["tg_id"], f, fpath)
            if not ok:
                raise CrmError(f"Telegram не принял файл: {why}")
            return h.reply(200, {"ok": True}) or True
    except CrmError as e:
        return h.reply(400, {"ok": False, "error": str(e)}) or True
    except (ValueError, TypeError):
        return h.reply(400, {"ok": False, "error": "Неверные данные"}) or True
    h.reply(404, {"ok": False})
    return True


def serve_file(h, q):
    if not CRM or not CRM.check_sig(q.get("id", ""), q.get("v", ""), q.get("e", ""), q.get("s", "")):
        return h.reply(403, {"ok": False, "error": "Ссылка устарела — откройте файл заново из «Студии»"})
    path, f = CRM.file_path(q["id"], q["v"])
    if not path or not os.path.exists(path):
        return h.reply(404, {"ok": False})
    mime = "image/jpeg" if q["v"] == "t" else (f["mime"] or "application/octet-stream")
    inline = mime in INLINE_OK and not q.get("dl")
    name = f["name"] or "файл"
    size = os.path.getsize(path)
    h.send_response(200)
    h.send_header("Content-Type", mime if mime in INLINE_OK else "application/octet-stream")
    h.send_header("Content-Length", str(size))
    h.send_header("Content-Disposition", f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{urllib.parse.quote(name)}")
    h.send_header("Cache-Control", "private, max-age=3600")
    h.send_header("X-Content-Type-Options", "nosniff")
    if not inline:                                       # вложение: в браузере как страница не выполнится
        h.send_header("Content-Security-Policy", "sandbox; default-src 'none'")
    h.end_headers()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(256 * 1024)
            if not chunk:
                break
            h.wfile.write(chunk)
