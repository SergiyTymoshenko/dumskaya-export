#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Адреса /api/crm/* сервиса заявок — учёт проектов студии (crm.py) для страницы «Студия» (crm_app.html).

Всё, кроме самой страницы и файлов, — только разработчику и дизайнеру: по подписи Telegram (заголовок
X-Telegram-Init-Data), как у графиков. Здесь же — товары и доп. услуги заказчика, заказчики проекта, ссылки в кабинет
(/api/crm/invite — заказчику из проекта, подрядчику или поставщику один раз, работнику подрядчика, сотруднику студии),
закрыть кабинет (/api/crm/unlink), сотрудники студии и на каких они проектах,
карточка товара с нашего сайта (/api/crm/card), группы проекта, бригады подрядчиков, кто видит документ; после сохранения —
сообщения в Telegram (after_save). К проекту добавляются участники и разговоры (crm_portal.py); сами разговоры —
portal_api.py (те же адреса, что у кабинетов). Файлы отдаются по подписанным ссылкам (действуют 12 часов): так их можно
открыть в браузере и скачать. Опасные для сайта типы (HTML, SVG…) отдаются только как вложение и в «песочнице».
"""
import hashlib
import html
import json
import os
import re
import threading
import urllib.parse

from crm import FILE_MAX, CrmError
from langs import studio_list

CRM = None            # ставит lead_service.py
BOT = None
PORTAL = None         # кабинеты заказчиков и подрядчиков (crm_portal.py)
INLINE_OK = ("image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf", "video/mp4", "text/plain")
SIZES = ("m", "l", "xl")       # размер текста в «Студии» и графиках: обычный, крупный, очень крупный


def ui_size(u):
    """Размер текста у человека: что выбрал сам, иначе у дизайнера — крупный (решено 24.10.2026), у остальных — обычный."""
    v = BOT.s.get(f"ui:size:{u['tg_id']}") if BOT else None
    return v if v in SIZES else ("l" if u["role"] == "designer" else "m")


HERE = os.path.dirname(os.path.abspath(__file__))


def _version():
    """Версия запущенного кода — внизу «Студии» и графиков, мелко: коммит · когда выложено · откуда.
    Файл VERSION пишет выкладка с Мака (scripts/deploy.sh); читается при запуске сервиса,
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
        return fh.read().replace("__STUDIO_VERSION__", html.escape(VERSION)).replace(
            "__VERSION_SHORT__", html.escape(VERSION.split()[-1] if VERSION.startswith("код ") else VERSION.split()[0]))


def app_page():
    return page("crm_app.html")


def studio_user(h):
    """Заявки, проекты, деньги, заказчики и подрядчики — только у дизайнера. Разработчику в «Студии» — сайт и доступ
    к боту (решено 24.10.2026)."""
    u = h.stats_admin()
    return u if u and u["role"] == "designer" else None


def portal_bg(fn, *args, **kw):
    """Уведомление в Telegram — в фоне: «Студия» не ждёт Telegram и перевод."""
    def run():
        try:
            fn(*args, **kw)
        except Exception as e:  # noqa: BLE001
            if BOT:
                BOT.log(f"кабинет: уведомление не отправлено: {type(e).__name__}: {e}")
    threading.Thread(target=run, daemon=True).start()


def enrich(r):
    """Проект для «Студии»: ещё участники (заказчики, подрядчики и их бригады) и разговоры с непрочитанным."""
    if PORTAL and isinstance(r, dict) and isinstance(r.get("project"), dict):
        pid = r["project"]["id"]
        v = PORTAL.viewer(0, pid, designer=True)
        r["participants"] = PORTAL.participants(pid)
        r["assistants"] = PORTAL.project_assistants(pid)        # сотрудники студии: кто назначен на проект
        r["threads"] = PORTAL.threads_for(v, pid, "ru")         # последнее сообщение — в переводе на русский
        for f in r.get("files", []):
            f["audience"] = PORTAL.audience(f)
    return r


def after_save(entity, d, r, who):
    """Что сообщить в Telegram после сохранения в «Студии»: заказчику — новый товар или услуга (если отмечено
    «Сообщить заказчику»), товар доставлен; сумма работ подрядчика — заказчику на подтверждение; подрядчику — что его
    добавили в проект."""
    if not BOT or not hasattr(BOT, "portal_event"):
        return
    was, sid = r.get("was"), r.get("saved_id")
    if entity == "order" and d.get("notify"):
        o = CRM.one("SELECT delivered FROM orders WHERE id=?", sid) or {}
        if not was:
            portal_bg(BOT.portal_event, "order_new", order_id=sid)
        elif o.get("delivered") and not was.get("delivered"):
            portal_bg(BOT.portal_event, "order_delivered", order_id=sid)
    elif entity == "service" and d.get("notify") and not was:
        portal_bg(BOT.portal_event, "service_new", service_id=sid)
    elif entity == "stage" and d.get("ask", True):        # «Попросить заказчика подтвердить сумму» (по умолчанию — да)
        st = CRM.one("SELECT amount, currency FROM stages WHERE id=?", sid) or {}
        if not was or was.get("amount") != st.get("amount") or was.get("currency") != st.get("currency"):
            portal_bg(BOT.portal_event, "stage_saved", stage_id=sid, was=was, by=who, by_contractor=False)
    elif entity == "link" and r.get("new"):
        portal_bg(BOT.portal_event, "link_new", link_id=sid)
    elif entity in ("group", "sgroup"):                    # группа: новым участникам — сообщение на их языке
        if r.get("new_members"):
            portal_bg(BOT.portal_event, "group_new", thread_id=r["thread_id"], only=r["new_members"])
    elif entity == "passist" and d.get("on") and r.get("changed_tg"):   # сотрудника студии назначили на проект
        portal_bg(BOT.portal_event, "assistant_assigned", assistant_id=int(d.get("assistant_id") or 0), project_id=int(d.get("project_id") or 0))
    elif entity == "pcrew" and d.get("on") and r.get("changed_tg"):
        portal_bg(BOT.portal_event, "crew_assigned", crew_id=int(d.get("crew_id") or 0), project_id=int(d.get("project_id") or 0))
    elif entity in ("pclient", "pclient_remove"):          # убран из проекта: других проектов нет — кабинет закрывается;
        c = CRM.one("SELECT tg_id FROM clients WHERE id=?", int(d.get("client_id") or 0)) or {}   # добавлен снова — открывается
        if c.get("tg_id"):
            portal_bg(BOT.portal_unlinked if entity == "pclient_remove" else BOT.portal_relinked, c["tg_id"])


def inv_ref(data):
    return int(data.get("ref_id") or 0)


def portal_save(entity):
    """Сохранения кабинетов из «Студии»: группа, бригада подрядчика, работник на объекте, кто видит документ."""
    if not PORTAL:
        return None

    def group(d, who):
        old = {(m["kind"], m["ref_id"]) for m in PORTAL.members(d["id"])} if d.get("id") else set()
        th = PORTAL.save_group(d.get("project_id"), d, who)
        new = [m for m in PORTAL.members(th["id"]) if (m["kind"], m["ref_id"]) not in old]
        return dict(CRM.project(th["project_id"]), saved_id=th["id"], thread_id=th["id"], new_members=new)

    def sgroup(d, who):                                    # группа Ирины с сотрудниками студии проекта
        old = {m["ref_id"] for m in PORTAL.members(d["id"])} if d.get("id") else set()
        th = PORTAL.save_staff_group(d.get("project_id"), d, who)
        new = [m for m in PORTAL.members(th["id"]) if m["ref_id"] not in old]
        return dict(CRM.project(th["project_id"]), saved_id=th["id"], thread_id=th["id"], new_members=new)

    def group_delete(d, who):
        th = PORTAL.thread(d.get("id"))
        if not th or th["kind"] not in ("group", "sgroup"):
            raise CrmError("Группа не найдена")
        if CRM.one("SELECT id FROM messages WHERE thread_id=? LIMIT 1", th["id"]):
            raise CrmError("В группе уже есть сообщения — удалить её нельзя (переписка проекта сохраняется)")
        CRM.run("DELETE FROM thread_members WHERE thread_id=?", th["id"])
        CRM.run("DELETE FROM threads WHERE id=?", th["id"])
        CRM.audit(who, "delete", "thread", th["id"], {"project_id": th["project_id"]})
        return CRM.project(th["project_id"])

    def crew(d, who):
        if d.get("id"):
            wid = PORTAL.crew_edit(d["id"], d, who)
        else:
            if not CRM.one("SELECT id FROM contractors WHERE id=? AND observer IS NULL", int(d.get("contractor_id") or 0)):
                raise CrmError("Подрядчик не найден")
            wid = PORTAL.crew_add(d["contractor_id"], d, who)
        r = {"ok": True, "saved_id": wid}
        if d.get("project_id"):
            PORTAL.crew_assign(d["project_id"], wid, True, who)
            r = dict(CRM.project(int(d["project_id"])), saved_id=wid)
        return r

    def crew_remove(d, who):
        tg = PORTAL.crew_remove(d.get("id"), who)
        if tg and BOT:
            portal_bg(BOT.portal_unlinked, tg)
        return CRM.project(int(d["project_id"])) if d.get("project_id") else {"ok": True}

    def pcrew(d, who):
        r = PORTAL.crew_assign(d.get("project_id"), d.get("crew_id"), bool(d.get("on")), who)
        if r["changed"] and not d.get("on") and r["crew"]["tg_id"] and BOT:
            portal_bg(BOT.sync_portal_menu, r["crew"]["tg_id"])
        return dict(CRM.project(int(d["project_id"])), changed_tg=bool(r["changed"] and r["crew"]["tg_id"]))

    def file_vis(d, who):
        f = CRM.set_file_vis(d, who)
        return CRM.project(f["project_id"])

    def assistant(d, who):                                 # сотрудник студии: добавить или изменить
        aid = PORTAL.assistant_save(d, who)
        if d.get("project_id") and not d.get("id"):        # добавлен из проекта — сразу назначен на него
            PORTAL.assistant_assign(d["project_id"], aid, True, who)
            return dict(CRM.project(int(d["project_id"])), saved_id=aid)
        return {"ok": True, "saved_id": aid}

    def assistant_remove(d, who):
        tg = PORTAL.assistant_remove(d.get("id"), who)
        if tg and BOT:
            portal_bg(BOT.portal_unlinked, tg)
        return CRM.project(int(d["project_id"])) if d.get("project_id") else {"ok": True}

    def passist(d, who):                                   # сотрудник на проекте (или снят)
        r = PORTAL.assistant_assign(d.get("project_id"), d.get("assistant_id"), bool(d.get("on")), who)
        if r["changed"] and not d.get("on") and r["assistant"]["tg_id"] and BOT:
            portal_bg(BOT.sync_portal_menu, r["assistant"]["tg_id"])
        return dict(CRM.project(int(d["project_id"])), changed_tg=bool(r["changed"] and r["assistant"]["tg_id"]))

    return {"group": group, "sgroup": sgroup, "group_delete": group_delete, "crew": crew, "crew_remove": crew_remove, "pcrew": pcrew,
            "file_vis": file_vis, "assistant": assistant, "assistant_remove": assistant_remove, "passist": passist}.get(entity)


CARD_HOSTS = ("dumskaya-design.com", "www.dumskaya-design.com", "dumskaya-home.com", "www.dumskaya-home.com")


def product_card(url, code=""):
    """Карточка товара для заказа: по артикулу магазина студии (TDD-001…) или по ссылке на наш сайт — название, фото
    (og:image) и ссылка. Чужие сайты не открываем: ссылка на товар у фабрики сохраняется как есть, фото — загрузить."""
    url, code = url.strip(), code.strip().upper()
    if code and not url:
        try:
            from bot import SITE, load_products
            it = load_products().get(code)
        except ImportError:
            it = None
        if not it:
            raise CrmError(f"Артикула {code} нет в магазине на сайте")
        url = SITE + it["path"]
    p = urllib.parse.urlparse(url)
    if p.scheme != "https" or p.hostname not in CARD_HOSTS:
        raise CrmError("Карточку можно подтянуть только с dumskaya-design.com или dumskaya-home.com")
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (DUMSKAYA DESIGN studio card)"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            page_html = resp.read(600_000).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        raise CrmError(f"Страница не открылась: {e}") from None

    def meta(prop):
        m = re.search(r'<meta[^>]+(?:property|name)=["\']' + re.escape(prop) + r'["\'][^>]*content=["\']([^"\']+)', page_html, re.I) or \
            re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']' + re.escape(prop) + r'["\']', page_html, re.I)
        return html.unescape(m.group(1)).strip() if m else ""
    title = meta("og:title") or (lambda m: html.unescape(m.group(1)).strip() if m else "")(re.search(r"<title>([^<]+)</title>", page_html, re.I))
    title = re.sub(r"\s*\|\s*DUMSKAYA (DESIGN|HOME)\s*$", "", title)
    image = meta("og:image")
    if image and not image.startswith("http"):
        image = urllib.parse.urljoin(url, image)
    m = re.search(r"\((TDD-[\w-]+|[A-Z]{2,5}-[A-Z]?\d+)\)", title)
    return {"url": url, "title": re.sub(r"\s*\([^)]*\)\s*$", "", title), "image_url": image if image.startswith("https://") else "",
            "code": code or (m.group(1) if m else "")}


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
<h1 id="h" style="font-size:24px;margin:0 0 8px">Письмо заказчику</h1>
<p id="to"></p>
<a class="btn" id="go" href="#">✉️ Открыть в «Почте»</a>
<p id="hint">Если «Почта» не открылась сама — нажмите кнопку. Потом вернитесь в Telegram.</p>
<script>
(function () {
  var q = new URLSearchParams(location.hash.slice(1)), to = (q.get('to') || '').trim();
  // l — язык кабинета заказчика или подрядчика (из «Студии» — по-русски, как раньше)
  var L = { uk: ['Лист', 'Відкрити в «Пошті»', 'Якщо «Пошта» не відкрилася сама — натисніть кнопку. Потім поверніться в Telegram.', 'Кому: ', 'Немає адреси e-mail.'],
    en: ['E-mail', 'Open in Mail', 'If Mail did not open by itself, tap the button. Then come back to Telegram.', 'To: ', 'No e-mail address.'],
    sk: ['E-mail', 'Otvoriť v aplikácii Mail', 'Ak sa aplikácia Mail neotvorila sama, ťuknite na tlačidlo. Potom sa vráťte do Telegramu.', 'Komu: ', 'Chýba e-mailová adresa.'],
    de: ['E-Mail', 'In Mail öffnen', 'Falls Mail sich nicht von selbst geöffnet hat, tippen Sie auf die Schaltfläche. Kehren Sie danach zu Telegram zurück.', 'An: ', 'Keine E-Mail-Adresse.'],
    ru: ['Письмо', 'Открыть в «Почте»', 'Если «Почта» не открылась сама — нажмите кнопку. Потом вернитесь в Telegram.', 'Кому: ', 'Нет адреса e-mail.'] }[q.get('l')];
  if (L) { document.documentElement.lang = q.get('l'); document.getElementById('h').textContent = L[0]; document.getElementById('go').textContent = '✉️ ' + L[1]; document.getElementById('hint').textContent = L[2]; }
  if (!/^[^\s@<>"]+@[^\s@<>"]+\.[^\s@<>"]+$/.test(to)) { document.getElementById('to').textContent = L ? L[4] : 'Нет адреса e-mail.'; document.getElementById('go').remove(); return; }
  var enc = function (s) { return encodeURIComponent(s || '').replace(/%0A/g, '%0D%0A'); };
  var url = 'mailto:' + encodeURIComponent(to).replace('%40', '@') + '?subject=' + enc(q.get('s')) + '&body=' + enc(q.get('b'));
  var t = document.getElementById('to'); t.append(L ? L[3] : 'Кому: '); var b = document.createElement('b'); b.textContent = to; t.append(b);
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
        return h.reply(200, {"size": ui_size(u), "role": u["role"], "observer": bool(PORTAL and PORTAL.is_observer(u["tg_id"]))}
                       if u else {"size": "m"}) or True
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
            out["langs"] = studio_list()                  # языки кабинетов: ссылка-приглашение, «перевод с …»
            return h.reply(200, out) or True
        if path == "/api/crm/project":
            return h.reply(200, enrich(CRM.project(q.get("id")))) or True
        if path == "/api/crm/stats":
            p = q.get("p", "month")
            return h.reply(200, CRM.stats(p if p in ("month", "quarter", "year", "all") else "month")) or True
        if path == "/api/crm/rate":
            return h.reply(200, CRM.rate(q.get("cur", "EUR").upper(), q.get("day", ""))) or True
        if path == "/api/crm/leads":
            return h.reply(200, CRM.leads_list()) or True
        if path == "/api/crm/lead":
            return h.reply(200, CRM.lead(q.get("id"))) or True
        if path == "/api/crm/card":                      # карточка товара с нашего сайта: название, фото, ссылка
            return h.reply(200, product_card(q.get("url") or "", q.get("code") or "")) or True
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
                  "lists": CRM.save_lists, "order": CRM.save_order, "service": CRM.save_service,
                  "pclient": CRM.add_project_client, "pclient_remove": CRM.remove_project_client,
                  "project_status": CRM.set_project_status}.get(entity)
            if not fn:
                fn = portal_save(entity)
            if not fn:
                raise CrmError("Неизвестно, что сохранять")
            r = fn(d, who)
            if isinstance(r, dict):
                after_save(entity, d, r, who)
                for k in ("was", "new_members", "thread_id", "changed_tg"):
                    r.pop(k, None)
            return h.reply(200, enrich(r)) or True
        if path == "/api/crm/invite":                    # ссылка в кабинет заказчику или подрядчику
            if not PORTAL or not BOT or not BOT.username:
                raise CrmError("Бот сейчас недоступен — попробуйте через минуту")
            inv = PORTAL.make_invite(data.get("kind"), data.get("ref_id"), data.get("project_id"), data.get("lang") or "ru", who)
            link = f"https://t.me/{BOT.username}?start=pj_{inv['token']}"
            kind = inv["kind"]
            if kind == "crew":                           # работнику — от имени его подрядчика
                w = CRM.one("SELECT c.name FROM crew w JOIN contractors c ON c.id=w.contractor_id WHERE w.id=?", inv_ref(data)) or {}
                title = w.get("name") or ""
            elif kind in ("contractor", "assistant"):    # подрядчику (поставщику) и сотруднику студии — без проекта
                title = ""
                c = CRM.one("SELECT kind FROM contractors WHERE id=?", inv_ref(data)) if kind == "contractor" else None
                if c and c.get("kind") in ("supplier", "hired"):   # поставщику и исполнителю студии — свой текст
                    kind = c["kind"]
            else:
                p = CRM.one("SELECT title FROM projects WHERE id=?", int(data.get("project_id") or 0)) or {}
                title = BOT.loc(p.get("title") or "", inv["lang"]) if hasattr(BOT, "loc") else p.get("title") or ""   # название — на его языке
            return h.reply(200, dict(inv, link=link, text=BOT.invite_text(inv["lang"], kind, inv["name"], title, link),
                                     token=None)) or True
        if path == "/api/crm/unlink":                    # закрыть кабинет: Telegram отвязать от заказчика или подрядчика
            if not PORTAL:
                raise CrmError("Кабинет сейчас недоступен")
            tg = PORTAL.unlink(data.get("kind"), data.get("ref_id"), who)
            if tg and BOT:
                portal_bg(BOT.portal_unlinked, tg)
            pid = int(data.get("project_id") or 0)
            return h.reply(200, enrich(CRM.project(pid)) if pid else {"ok": True}) or True
        if path == "/api/crm/delete":
            if data.get("entity") == "leads":           # несколько заявок сразу (например, весь спам)
                return h.reply(200, CRM.delete_leads(data.get("ids") or [], who)) or True
            tgs = []
            if data.get("entity") == "contractor":      # удалён подрядчик (и наблюдатель): у него и его бригады кабинет закрывается
                rid = int(data.get("id") or 0)
                tgs = [r["tg_id"] for r in CRM.q("SELECT tg_id FROM contractors WHERE id=? AND tg_id IS NOT NULL UNION "
                                                 "SELECT tg_id FROM crew WHERE contractor_id=? AND removed IS NULL AND tg_id IS NOT NULL", rid, rid)]
            r = CRM.delete(data.get("entity"), data.get("id"), who)
            for tg in tgs:
                if BOT:
                    portal_bg(BOT.portal_unlinked, tg)
            return h.reply(200, enrich(r)) or True
        if path == "/api/crm/move":
            return h.reply(200, enrich(CRM.move_file(data.get("id"), data.get("category"), who))) or True
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
