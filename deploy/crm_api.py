#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Адреса /api/crm/* сервиса заявок — учёт проектов студии (crm.py) для страницы «Студия» (crm_app.html).

Всё, кроме самой страницы и файлов, — только разработчику и дизайнеру: по подписи Telegram (заголовок
X-Telegram-Init-Data), как у графиков. Файлы отдаются по подписанным ссылкам (действуют 12 часов): так их можно
открыть в браузере и скачать. Опасные для сайта типы (HTML, SVG…) отдаются только как вложение и в «песочнице».
"""
import hashlib
import html
import json
import os
import urllib.parse

from crm import FILE_MAX, CrmError

CRM = None            # ставит lead_service.py
BOT = None
INLINE_OK = ("image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf", "video/mp4", "text/plain")
SIZES = ("m", "l", "xl")       # размер текста в «Студии» и графиках: обычный, крупный, очень крупный


def ui_size(u):
    """Размер текста у человека: что выбрал сам, иначе у дизайнера — крупный (решено 24.10.2026), у остальных — обычный."""
    v = BOT.s.get(f"ui:size:{u['tg_id']}") if BOT else None
    return v if v in SIZES else ("l" if u["role"] == "designer" else "m")


HERE = os.path.dirname(os.path.abspath(__file__))


def _version():
    """Версия запущенного кода — внизу «Студии» и графиков, мелко: коммит · когда выложено · откуда.
    Файл VERSION пишут выкладка с Мака (scripts/deploy.sh) и автовыкладка (GitHub); читается при запуске сервиса,
    поэтому показывает именно то, что работает. Нет файла — отпечаток кода."""
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8") as fh:
            v = " ".join(fh.read().split())[:80]
        if v:
            return v
    except OSError:
        pass
    h = hashlib.sha256()
    for name in sorted(os.listdir(HERE)):
        if name.endswith((".py", ".html")):
            with open(os.path.join(HERE, name), "rb") as fh:
                h.update(name.encode() + b"\0" + fh.read())
    return "код " + h.hexdigest()[:7]


VERSION = _version()


def page(name):
    """Страница мини-приложения с версией внизу (метка __STUDIO_VERSION__)."""
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return fh.read().replace("__STUDIO_VERSION__", html.escape(VERSION))


def app_page():
    return page("crm_app.html")


def studio_user(h):
    """Заявки, проекты, деньги, заказчики и подрядчики — только у дизайнера. Разработчику в «Студии» — сайт и доступ
    к боту (решено 24.10.2026)."""
    u = h.stats_admin()
    return u if u and u["role"] == "designer" else None


# Письмо заказчику. Кнопка ✉️ в «Студии» открывает эту страницу в браузере (из Telegram ссылки mailto: открываются не везде),
# а она — «Почту» с готовым письмом. Адрес, тема и текст — после «#»: на сервер не уходят и в журнал не попадают.
MAIL_PAGE = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>Письмо — DUMSKAYA DESIGN</title>
<style>
:root { color-scheme: light dark; --bg: #f6f5f2; --fg: #141414; --mut: #505050; --btn: #1a5fb4; }
@media (prefers-color-scheme: dark) { :root { --bg: #161616; --fg: #f2f2f2; --mut: #c4c4c4; --btn: #3d8bfd; } }
body { margin: 0; background: var(--bg); color: var(--fg); font: 20px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
  padding: 32px 20px; max-width: 560px; margin: 0 auto; text-align: center; }
a.btn { display: block; background: var(--btn); color: #fff; text-decoration: none; font-weight: 600; border-radius: 14px;
  padding: 18px 16px; margin: 24px 0 16px; }
p { color: var(--mut); margin: 10px 0; overflow-wrap: anywhere; }
b { color: var(--fg); }
</style></head><body>
<h1 style="font-size:24px;margin:0 0 8px">Письмо заказчику</h1>
<p id="to"></p>
<a class="btn" id="go" href="#">✉️ Открыть в «Почте»</a>
<p>Если «Почта» не открылась сама — нажмите кнопку. Потом вернитесь в Telegram.</p>
<script>
(function () {
  var q = new URLSearchParams(location.hash.slice(1)), to = (q.get('to') || '').trim();
  if (!/^[^\s@<>"]+@[^\s@<>"]+\.[^\s@<>"]+$/.test(to)) { document.getElementById('to').textContent = 'Нет адреса e-mail.'; document.getElementById('go').remove(); return; }
  var enc = function (s) { return encodeURIComponent(s || '').replace(/%0A/g, '%0D%0A'); };
  var url = 'mailto:' + encodeURIComponent(to).replace('%40', '@') + '?subject=' + enc(q.get('s')) + '&body=' + enc(q.get('b'));
  var t = document.getElementById('to'); t.append('Кому: '); var b = document.createElement('b'); b.textContent = to; t.append(b);
  document.getElementById('go').href = url;
  setTimeout(function () { location.href = url; }, 150);
})();
</script></body></html>"""


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
    if path == "/api/crm/ui":                       # размер текста и роль — нужны и графикам, работает и без учёта
        u = h.stats_admin()
        return h.reply(200, {"size": ui_size(u), "role": u["role"]} if u else {"size": "m"}) or True
    if path == "/api/crm/mail":                     # письмо заказчику: открыть «Почту» из браузера (адрес и текст — в #…)
        h.reply(200, None, html_page=MAIL_PAGE)
        return True
    if path == "/api/crm/access":                   # доступ к боту: люди, запросы, партнёры — работает и без учёта
        u = h.stats_admin()
        if not u or not BOT:
            return h.reply(403, {"ok": False, "error": "Нет доступа"}) or True
        return h.reply(200, BOT.access_state(u)) or True
    if not CRM:
        h.reply(503, {"ok": False, "error": "Учёт не запущен"})
        return True
    u = studio_user(h)
    if not u:
        h.reply(403, {"ok": False, "error": "Нет доступа: заявки и проекты студии — у дизайнера."})
        return True
    try:
        if path == "/api/crm/state":
            out = CRM.state()
            out["me"] = {"name": u["name"], "role": u["role"], "size": ui_size(u)}
            return h.reply(200, out) or True
        if path == "/api/crm/project":
            return h.reply(200, CRM.project(q.get("id"))) or True
        if path == "/api/crm/stats":
            p = q.get("p", "month")
            return h.reply(200, CRM.stats(p if p in ("month", "quarter", "year", "all") else "month")) or True
        if path == "/api/crm/rate":
            return h.reply(200, CRM.rate(q.get("cur", "EUR").upper(), q.get("day", ""))) or True
        if path == "/api/crm/leads":
            return h.reply(200, CRM.leads_list()) or True
        if path == "/api/crm/lead":
            return h.reply(200, CRM.lead(q.get("id"))) or True
    except CrmError as e:
        return h.reply(400, {"ok": False, "error": str(e)}) or True
    h.reply(404, {"ok": False})
    return True


def handle_post(h, path, query):
    if not path.startswith("/api/crm/"):
        return False
    if path == "/api/crm/access":
        u = h.stats_admin()
        if not u or not BOT:
            return h.reply(403, {"ok": False, "error": "Нет доступа"}) or True
        try:
            return h.reply(200, BOT.access_action(u, _json_body(h, 5000))) or True
        except CrmError as e:
            return h.reply(400, {"ok": False, "error": str(e)}) or True
        except (ValueError, TypeError):
            return h.reply(400, {"ok": False, "error": "Неверные данные"}) or True
    if path == "/api/crm/ui":
        u = h.stats_admin()
        if not u or not BOT:
            return h.reply(403, {"ok": False, "error": "Нет доступа"}) or True
        try:
            size = _json_body(h, 2000).get("size")
        except (CrmError, ValueError):
            size = None
        if size not in SIZES:
            return h.reply(400, {"ok": False, "error": "Неизвестный размер"}) or True
        BOT.s.put(f"ui:size:{u['tg_id']}", size)
        return h.reply(200, {"size": size}) or True
    if not CRM:
        h.reply(503, {"ok": False, "error": "Учёт не запущен"})
        return True
    u = studio_user(h)
    if not u:
        h.reply(403, {"ok": False, "error": "Нет доступа: заявки и проекты студии — у дизайнера."})
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
                  "lead": CRM.save_lead, "lead_project": CRM.lead_to_project, "lead_restore": CRM.restore_lead,
                  "lists": CRM.save_lists}.get(entity)
            if not fn:
                raise CrmError("Неизвестно, что сохранять")
            return h.reply(200, fn(d, who)) or True
        if path == "/api/crm/delete":
            if data.get("entity") == "leads":           # несколько заявок сразу (например, весь спам)
                return h.reply(200, CRM.delete_leads(data.get("ids") or [], who)) or True
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
