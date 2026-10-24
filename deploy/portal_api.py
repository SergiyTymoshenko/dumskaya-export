#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Адреса /api/portal/* сервиса заявок — кабинеты в боте («Мой проект», страница portal_app.html): заказчик, подрядчик
(и поставщик), работник подрядчика, сотрудник студии, наблюдатель — и разговоры проекта (в том числе для «Студии»).

Кто есть кто — по подписи Telegram (заголовок X-Telegram-Init-Data), как в «Студии»; что кому видно — crm_portal.py:
  • заказчик, подрядчик и работник видят только свои проекты и только то, что им положено (работнику — без денег);
  • дизайнер студии пишет в любой разговор и может посмотреть кабинет глазами заказчика, подрядчика, работника
    или своего сотрудника (?preview=client | contractor&link=… | worker&crew=… | assistant&assistant=…);
  • сотрудник студии — назначенные проекты без денег и контактов; пишет во все разговоры проекта от имени студии;
  • наблюдатель «Разработчик ПО» (подрядчик-заглушка для тестирования, привязан к Telegram разработчика) видит всё,
    тоже может смотреть глазами любого, но ничего не пишет и не меняет.
Уведомления в Telegram (новое сообщение, сумма на подтверждение, документ…) отправляет бот в фоне — ответ не ждёт Telegram."""
import json
import threading
import time
import urllib.parse
from collections import defaultdict, deque

from crm import FILE_MAX, CrmError
from crm_portal import STUDIO, ui_lang
from langs import pack, public_list

CRM = None            # ставит lead_service.py
PORTAL = None
BOT = None
CHECK = None          # check_init_data из site_stats (подпись Telegram)
TOKEN = ""
CHAT_FILE_MAX = 20 * 1024 * 1024       # вложение в разговоре — до 20 МБ (больше Telegram не перешлёт)
CHAT_RATE = defaultdict(deque)          # Telegram ID → время последних сообщений
CHAT_MAX, CHAT_WINDOW = 30, 600         # не больше 30 сообщений за 10 минут
SIZES = ("m", "l", "xl")
_lock = threading.Lock()


class Denied(Exception):
    """Нет доступа к этому проекту или разговору — ответ 403 без подробностей."""


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
    """Кто открыл кабинет: {"tg", "name", "lang", "size", "designer", "observer", "user"} или None (нет подписи, нет в боте)."""
    uid, tu = init_user(h)
    u = BOT.user(uid) if uid and BOT else None
    if not u or u["status"] != "active":
        return None
    if tu.get("language_code"):                      # язык Telegram — запоминаем (если человек не выбрал сам)
        code = str(tu["language_code"])[:8]
        if BOT.s.get(f"tg:lang:{uid}") != code:
            BOT.s.put(f"tg:lang:{uid}", code)
    name = " ".join(x for x in (tu.get("first_name"), tu.get("last_name")) if x) or u["name"] or str(uid)
    designer = u["role"] == "designer"
    return {"tg": uid, "name": name, "lang": BOT.lang_of(uid), "size": BOT.s.get(f"ui:size:{uid}") or ("l" if designer else "m"),
            "designer": designer, "observer": not designer and PORTAL.is_observer(uid), "user": u}


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


def _fake(**kw):
    v = {"tg": 0, "studio": False, "observer": False, "client": None, "heads": set(), "crew": set(), "staff": set(), "preview": True}
    v.update(kw)
    return v


def viewer_for(w, pid, q):
    """Кто смотрит проект. Дизайнер и наблюдатель могут посмотреть глазами заказчика, подрядчика или работника (preview) —
    тогда только чтение. Человек без роли в проекте — Denied."""
    pid = int(pid or 0)
    if not CRM.one("SELECT id FROM projects WHERE id=?", pid):
        raise Denied()
    pv = q.get("preview")
    if pv and (w["designer"] or w["observer"]):
        if pv == "client":
            return _fake(client={"id": 0, "name": ""})
        if pv == "contractor":
            link = CRM.one("SELECT contractor_id FROM project_contractors WHERE id=? AND project_id=?", int(q.get("link") or 0), pid)
            if not link:
                raise CrmError("Подрядчик в этом проекте не найден")
            return _fake(heads={link["contractor_id"]})
        if pv == "worker":
            x = CRM.one("SELECT crew_id FROM project_crew WHERE project_id=? AND crew_id=?", pid, int(q.get("crew") or 0))
            if not x:
                raise CrmError("Этого работника нет на объекте")
            return _fake(crew={x["crew_id"]})
        if pv == "assistant":
            x = CRM.one("SELECT assistant_id FROM project_assistants WHERE project_id=? AND assistant_id=?", pid, int(q.get("assistant") or 0))
            if not x:
                raise CrmError("Этот сотрудник не назначен на проект")
            return _fake(staff={x["assistant_id"]})
    if w["designer"]:
        return dict(PORTAL.viewer(w["tg"], pid, designer=True), preview=False)
    v = dict(PORTAL.viewer(w["tg"], pid), preview=False)
    if not (v["client"] or v["heads"] or v["crew"] or v["observer"] or v["staff"]):
        raise Denied()
    if PORTAL.crm.one("SELECT status FROM projects WHERE id=?", pid)["status"] == "cancelled":
        raise Denied()
    return v


def roles_of(v):
    return [r for r, ok in (("assistant", v.get("staff")), ("client", v["client"]), ("contractor", v["heads"]), ("worker", v["crew"]),
                            ("observer", v["observer"] and not v.get("preview"))) if ok]


def project_view(w, q):
    pid = int(q.get("id") or 0)
    v = viewer_for(w, pid, q)
    roles = roles_of(v)
    want = q.get("as") if q.get("as") in roles else None
    role = want or (roles[0] if roles else "")
    if v["studio"] and not v.get("preview"):
        raise CrmError("Откройте проект в «Студии»")
    if role == "client":
        out = PORTAL.client_view(pid, v["tg"] or None)
    elif role == "contractor":
        out = PORTAL.contractor_view(pid, v["heads"], v["tg"] or None)
    elif role == "worker":
        out = PORTAL.worker_view(pid, v["crew"], v["tg"] or None)
    elif role == "assistant":
        out = PORTAL.assistant_view(pid, v["staff"], v["tg"] or None)
    elif role == "observer":
        out = PORTAL.observer_view(pid, v["tg"])
    else:
        raise Denied()
    out["roles"] = roles if not v.get("preview") else [role]
    out["preview"] = bool(v.get("preview"))
    out["readonly"] = bool(v.get("preview") or role == "observer")
    if role == "observer":
        out["preview_links"] = {"contractors": [{"link": c["link_id"], "name": c["name"], "trade": c["trade"]} for c in out["participants"]["contractors"]],
                                "crew": [{"id": x["id"], "name": x["name"], "position": x["position"]}
                                         for c in out["participants"]["contractors"] for x in c["crew"] if x["assigned"]]}
    return out


def thread_for(w, tid, q, write=False):
    """Разговор и права на него у этого человека: (разговор, viewer, access). Denied — не видит."""
    t = PORTAL.thread(tid)
    if not t:
        raise Denied()
    v = viewer_for(w, t["project_id"], q)
    acc = PORTAL.access(v, t)
    if not acc or (write and (acc != "write" or v.get("preview") or (v["observer"] and not v["studio"]))):
        raise Denied()
    return t, v, acc


def chat_lang(w, v):
    return "ru" if v["studio"] or v.get("preview") and w["designer"] else w["lang"]


def handle_get(h, path, query):
    if not path.startswith("/api/portal/"):
        return False
    if path == "/api/portal/app":
        import crm_api
        h.reply(200, None, html_page=crm_api.page("portal_app.html"), telegram_frame=True)
        return True
    if path == "/api/portal/i18n":                   # тексты кабинета на языке (кроме пяти основных — они в самой странице)
        code = ui_lang(dict(urllib.parse.parse_qsl(query)).get("lang"))
        return h.reply(200, {"lang": code, "ui": pack(code).get("ui") or {}}) or True
    if not (CRM and PORTAL and BOT):
        return _deny(h, 503, "Кабинет сейчас недоступен")
    w = who(h)
    if not w:
        return _deny(h)
    q = dict(urllib.parse.parse_qsl(query))
    try:
        if path == "/api/portal/me":
            projects = PORTAL.projects_for(w["tg"])
            heads = [{"id": c["id"], "name": c["name"], "trade": c["trade"] or "", "company": c["company"] or "", "kind": c["kind"] or ""}
                     for c in PORTAL.my_contractors(w["tg"])]
            crews = [{"id": x["id"], "name": x["name"], "position": x["position"] or "", "head": x["head_name"]} for x in PORTAL.crews_of(w["tg"])]
            staff = [{"id": a["id"], "name": a["name"], "position": a["position"] or ""} for a in PORTAL.assistants_of(w["tg"])]
            if not (projects or heads or crews or staff or w["designer"] or w["observer"]):
                return _deny(h, 403, "no_projects")
            return h.reply(200, {"name": w["name"], "lang": w["lang"], "size": w["size"], "designer": w["designer"],
                                 "observer": w["observer"], "projects": projects, "heads": heads, "crews": crews, "staff": staff,
                                 "studio": STUDIO, "translate": BOT.can_translate(), "langs": public_list()}) or True
        if path == "/api/portal/project":
            v = project_view(w, q)
            # дизайнер и наблюдатель в просмотре может выбрать язык, как у заказчика
            lang = ui_lang(q["lang"]) if v.get("preview") and q.get("lang") else w["lang"]
            misses = PORTAL.localize(v, lang)             # названия услуг, товаров, этапов — на языке человека
            if misses and BOT.can_translate():
                bg(BOT.fill_labels, misses, lang)         # переводы появятся при следующем открытии
            v["lang"] = lang
            return h.reply(200, v) or True
        if path == "/api/portal/threads":
            pid = int(q.get("project") or 0)
            v = viewer_for(w, pid, q)
            lang = "ru" if v["studio"] else ui_lang(q["lang"]) if v.get("preview") and q.get("lang") else w["lang"]
            return h.reply(200, {"threads": PORTAL.threads_for(v, pid, lang), "readonly": bool(v.get("preview") or (v["observer"] and not v["studio"]))}) or True
        if path == "/api/portal/chat":
            t, v, acc = thread_for(w, q.get("thread"), q)
            lang = chat_lang(w, v)
            rows = PORTAL.messages(t["id"], v, lang, q.get("after") or 0)
            ro = bool(v.get("preview") or acc != "write" or (v["observer"] and not v["studio"]))
            if rows and not v.get("preview") and (v["studio"] or not v["observer"]):
                PORTAL.mark_read(t["id"], 0 if v["studio"] else w["tg"], rows[-1]["id"])
            return h.reply(200, {"messages": rows, "lang": lang, "readonly": ro, "thread": PORTAL.thread_info(t, v, acc, lang)}) or True
        if path == "/api/portal/team":                   # бригада подрядчика: кто подключён, на каких объектах
            c = PORTAL.head_check(w["tg"], q.get("contractor"))
            projects = CRM.q("""SELECT DISTINCT p.id, p.title, p.number, p.status FROM projects p JOIN project_contractors l ON l.project_id=p.id
                                WHERE l.contractor_id=? AND p.status != 'cancelled' ORDER BY p.id DESC""", c["id"])
            for p in projects:
                p["title"] = BOT.loc(p["title"], w["lang"])
            return h.reply(200, {"contractor": {"id": c["id"], "name": c["name"], "trade": c["trade"] or "", "kind": c["kind"] or ""},
                                 "team": PORTAL.team(c["id"]), "projects": projects}) or True
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


def team_action(w, d):
    """Подрядчик управляет своей бригадой: добавить работника, ссылка в бот, изменить, убрать, отметить на объекте."""
    act = d.get("action")
    who_ = w["name"] + " (подрядчик)"
    if act == "add":
        c = PORTAL.head_check(w["tg"], d.get("contractor_id"))
        wid = PORTAL.crew_add(c["id"], d, who_)
        return {"team": PORTAL.team(c["id"]), "crew_id": wid}
    wk = PORTAL.crew_get(d.get("crew_id"))
    c = PORTAL.head_check(w["tg"], wk["contractor_id"])
    if act == "edit":
        PORTAL.crew_edit(wk["id"], d, who_)
    elif act == "invite":
        if not BOT.username:
            raise CrmError("Бот сейчас недоступен — попробуйте через минуту")
        inv = PORTAL.make_invite("crew", wk["id"], None, d.get("lang") or w["lang"], who_)
        link = f"https://t.me/{BOT.username}?start=pj_{inv['token']}"
        return {"team": PORTAL.team(c["id"]), "link": link, "expires": inv["expires"],
                "text": BOT.invite_text(inv["lang"], "crew", wk["name"], c["name"], link)}
    elif act == "remove":
        tg = PORTAL.crew_remove(wk["id"], who_)
        if tg:
            bg(BOT.portal_unlinked, tg)
    elif act == "assign":
        r = PORTAL.crew_assign(d.get("project_id"), wk["id"], bool(d.get("on")), who_)
        if r["changed"] and wk["tg_id"]:
            if d.get("on"):
                bg(BOT.portal_event, "crew_assigned", crew_id=wk["id"], project_id=int(d.get("project_id")))
            else:
                bg(BOT.sync_portal_menu, wk["tg_id"])
    else:
        raise CrmError("Неизвестное действие")
    return {"team": PORTAL.team(c["id"])}


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
        if path == "/api/portal/upload":
            n = int(h.headers.get("Content-Length") or 0)
            mime = h.headers.get("Content-Type", "application/octet-stream")
            if q.get("thread"):                          # вложение в разговор (фото, PDF…) — потом сообщение с ним
                t, v, _ = thread_for(w, q.get("thread"), q, write=True)
                if n > CHAT_FILE_MAX:
                    h.close_connection = True
                    return h.reply(413, {"ok": False, "error": "file_too_big"}) or True
                f = CRM.add_file(t["project_id"], "chat", q.get("name") or "file", h.rfile, n, mime, w["name"])
                CRM.run("UPDATE files SET thread_id=? WHERE id=?", t["id"], f["id"])
                if v["studio"] and q.get("client") == "1" and t["kind"] not in ("client", "pc"):   # студия: «заказчик тоже увидит»
                    CRM.run("UPDATE files SET see_client=1 WHERE id=?", f["id"])
                return h.reply(200, {"id": f["id"], "name": f["name"], "url": f["url"], "image": f["image"]}) or True
            pid = int(q.get("project") or 0)              # документ подрядчика или работника — «От подрядчиков»;
            v = viewer_for(w, pid, q)                      # сотрудник студии — в раздел проекта (cat)
            if v.get("preview") or not (v["heads"] or v["crew"] or v["staff"]):
                raise Denied()
            if n > FILE_MAX:
                h.close_connection = True
                return h.reply(413, {"ok": False, "error": "file_too_big"}) or True
            if v["staff"] and not (v["heads"] or v["crew"]):
                f = PORTAL.upload_studio(v, pid, q.get("cat"), q.get("name") or "file", h.rfile, n, mime, q.get("vis"), q.get("title"), w["name"])
                bg(BOT.portal_event, "doc_new", file_id=f["id"])
                return h.reply(200, f) or True
            f = PORTAL.upload(v, pid, q.get("name") or "file", h.rfile, n, mime, q.get("vis"), q.get("title"), w["name"])
            bg(BOT.portal_event, "doc_new", file_id=f["id"])
            return h.reply(200, f) or True
        if path == "/api/portal/thumb":                   # превью фото документа (делает телефон): подрядчика, работника, сотрудника студии
            fid = int(q.get("id") or 0)
            f = CRM.one("SELECT * FROM files WHERE id=? AND (category='work' OR owner_kind='assistant')", fid)
            if not f:
                raise Denied()
            v = viewer_for(w, f["project_id"], q)
            if not PORTAL._file_out(f, v)["can_edit"] or v.get("preview"):
                raise Denied()
            n = int(h.headers.get("Content-Length") or 0)
            if n <= 0 or n > 2 * 1024 * 1024:
                raise CrmError("Неподходящее превью")
            CRM.set_thumb(fid, h.rfile.read(n))
            return h.reply(200, {"ok": True}) or True
        d = _body(h)
        if path == "/api/portal/chat":
            t, v, _ = thread_for(w, d.get("thread_id"), q, write=True)
            if not _rate_ok(w["tg"]):
                return h.reply(429, {"ok": False, "error": "rate"}) or True
            kind, name = PORTAL.author(v, t)
            m = PORTAL.post(t["id"], kind, w["tg"], name, d.get("text"), d.get("file_id"))
            bg(BOT.chat_fanout, m["id"])
            return h.reply(200, {"ok": True, "id": m["id"]}) or True
        if path == "/api/portal/thread":                 # начать разговор: заказчик — с подрядчиком; студия — с кем угодно
            pid = int(d.get("project_id") or 0)
            v = viewer_for(w, pid, q)
            if v.get("preview") or (v["observer"] and not v["studio"]):
                raise Denied()
            kind = d.get("kind")
            if v["studio"] or v["staff"]:
                if kind not in ("client", "org", "worker"):
                    raise CrmError("Неизвестный разговор")
            elif kind == "pc" and (v["client"] or int(d.get("contractor_id") or 0) in v["heads"]):
                c = CRM.one("SELECT tg_id FROM contractors WHERE id=?", int(d.get("contractor_id") or 0)) or {}
                if v["client"] and not c.get("tg_id"):
                    raise CrmError("Этот подрядчик ещё не подключён к боту")
            else:
                raise Denied()
            t = PORTAL.ensure_thread(pid, kind, d.get("contractor_id"), d.get("crew_id"), w["name"])
            return h.reply(200, PORTAL.thread_info(t, v, None, "ru" if v["studio"] else w["lang"])) or True
        if path == "/api/portal/read":
            t, v, _ = thread_for(w, d.get("thread_id"), q)
            if not v.get("preview") and (v["studio"] or not v["observer"]):
                PORTAL.mark_read(t["id"], 0 if v["studio"] else w["tg"], d.get("last_id") or 0)
            return h.reply(200, {"ok": True}) or True
        if path == "/api/portal/file":                   # свой документ: кто видит, подпись, удалить
            f = CRM.one("SELECT project_id FROM files WHERE id=?", int(d.get("id") or 0))
            if not f:
                raise Denied()
            v = viewer_for(w, f["project_id"], q)
            if v.get("preview"):
                raise Denied()
            return h.reply(200, {"file": PORTAL.edit_file(v, d, w["name"])}) or True
        if path == "/api/portal/team":
            return h.reply(200, team_action(w, d)) or True
        if path == "/api/portal/stage":
            act = d.get("action")
            if act in ("confirm", "dispute"):
                st = PORTAL.client_stage(w["tg"], d.get("id"), act, d.get("note"), w["name"])
                bg(BOT.portal_event, "stage_" + act, stage_id=st["id"], by=w["name"])
                return h.reply(200, PORTAL.client_view(st["project_id"], w["tg"])) or True
            if act == "save":
                r = PORTAL.contractor_stage(w["tg"], d, w["name"] + " (подрядчик)")
                bg(BOT.portal_event, "stage_saved", stage_id=r["stage_id"], was=r["was"], by=w["name"], by_contractor=True)
                return h.reply(200, PORTAL.contractor_view(r["project_id"], PORTAL.contractor_ids(w["tg"], r["project_id"]), w["tg"])) or True
            if act == "delete":
                r = PORTAL.contractor_delete_stage(w["tg"], d, w["name"] + " (подрядчик)")
                return h.reply(200, PORTAL.contractor_view(r["project_id"], PORTAL.contractor_ids(w["tg"], r["project_id"]), w["tg"])) or True
            raise CrmError("Неизвестное действие")
        if path == "/api/portal/ui":                     # язык и размер текста — свои у каждого
            if d.get("lang"):
                BOT.s.put(f"ui:lang:{w['tg']}", ui_lang(d["lang"]))
                BOT.sync_portal_menu(w["tg"])
            if d.get("size") in SIZES:
                BOT.s.put(f"ui:size:{w['tg']}", d["size"])
            return h.reply(200, {"lang": BOT.lang_of(w["tg"]), "size": BOT.s.get(f"ui:size:{w['tg']}") or w["size"]}) or True
    except Denied:
        return _deny(h)
    except CrmError as e:
        return h.reply(400, {"ok": False, "error": str(e)}) or True
    except (ValueError, TypeError):
        return h.reply(400, {"ok": False, "error": "Неверные данные"}) or True
    h.reply(404, {"ok": False})
    return True
