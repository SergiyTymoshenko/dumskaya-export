#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Приём заявок с сайта dumskaya-design.com.

Слушает 127.0.0.1:8095 (Caddy проксирует сюда /api/lead). Заявку:
  1) сразу дописывает в файл leads.jsonl — так она не потеряется, даже если почта и Telegram недоступны;
  2) отправляет в Telegram-бот студии (bot.py): разработчику и дизайнерам, а заявку на товар партнёра —
     ещё и людям этого партнёра — поставщику и его сотрудникам (партнёр товара — в shop-products.json, собирается из сайта при выкладке);
  3) отправляет письмом через SMTP (например, Gmail с паролем приложения).
В этом же процессе работает сам бот (приём пользователей, роли) — см. bot.py, и сторож сайта: если сайт
не отвечает, разработчику в бот приходит сообщение — см. site_monitor.py.
И статистика посетителей по журналу Caddy (site_stats.py): мини-приложение «Графики» в боте, утром — строка разработчику.
И учёт проектов студии (crm.py, crm_api.py, страница crm_app.html — кнопка «Студия» в боте).
И кабинеты заказчика, подрядчика и его работников с разговорами (crm_portal.py, portal_api.py, portal_bot.py, страница portal_app.html —
кнопка «Мой проект» в боте); напоминания об оплате доп. услуг — раз в минуту вместе с остальными фоновыми делами.
И IndexNow (indexnow.py): раз в час сообщает Bing, Яндексу и Seznam о новых и изменённых страницах обоих сайтов.
Только стандартная библиотека Python 3, без установки пакетов.

Настройки — переменные окружения (файл lead.env, его читает systemd):
  TELEGRAM_BOT_TOKEN  BOT_OWNER_ID (Telegram ID разработчика)  BOT_DB=/home/deploy/dumskaya/bot.db
  SMTP_HOST=smtp.gmail.com  SMTP_PORT=587  SMTP_USER  SMTP_PASSWORD  MAIL_TO
  LEADS_FILE=/home/deploy/dumskaya/leads.jsonl  PORT=8095
  Перевод (translate.py), по порядку: OPENAI_SUB_BASE_URL (ChatGPT по подписке) → OPENAI_API_KEY (платный ChatGPT)
  → ANTHROPIC_API_KEY (Claude) → DEEPL_API_KEY; вписывает мастер: с Mac — npm run translate
"""
import json
import os
import re
import smtplib
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8095"))
LEADS_FILE = os.environ.get("LEADS_FILE", os.path.expanduser("~/dumskaya/leads.jsonl"))
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BOT_OWNER = os.environ.get("BOT_OWNER_ID", "")
BOT_DB = os.environ.get("BOT_DB", os.path.expanduser("~/dumskaya/bot.db"))
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_TO = os.environ.get("MAIL_TO", SMTP_USER)

LIMITS = {"name": 120, "contact": 160, "message": 3000, "page": 300, "model": 40, "lang": 5}
# страна и город доставки (форма dumskaya-home.com): дописывается первой строкой сообщения — так её видят бот, «Студия»,
# перевод и ответ клиенту, без отдельной колонки в учёте
DELIVERY = {"ru": "Доставка", "ua": "Доставка", "en": "Delivery to", "sk": "Doručenie", "de": "Lieferung nach",
            "fr": "Livraison", "es": "Entrega en"}
RATE = defaultdict(deque)          # ip → время последних заявок
RATE_MAX, RATE_WINDOW = 5, 600     # не больше 5 заявок за 10 минут с одного адреса
HIT_RATE = defaultdict(deque)      # ip → время последних нажатий на контакты
HIT_MAX = 20                       # не больше 20 нажатий за 10 минут с одного адреса
TIME_RATE = defaultdict(deque)     # ip → время последних сообщений «время на странице»
TIME_MAX = 120                     # не больше 120 за 10 минут с одного адреса
PERIODS = ("1h", "24h", "7", "30", "90", "365", "all")
ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex"   # всё под /api — не в поиск (robots.txt тоже закрывает /api/)
lock = threading.Lock()

THANKS = {
    "ru": ("Заявка отправлена", "Мы свяжемся с вами в течение рабочего дня.", "Вернуться на сайт"),
    "ua": ("Заявку надіслано", "Ми зв’яжемося з вами протягом робочого дня.", "Повернутися на сайт"),
    "en": ("Request sent", "We will get back to you within one working day.", "Back to the website"),
    "sk": ("Žiadosť bola odoslaná", "Ozveme sa vám do jedného pracovného dňa.", "Späť na web"),
    "de": ("Anfrage gesendet", "Wir melden uns innerhalb eines Werktags.", "Zurück zur Website"),
    "fr": ("Demande envoyée", "Nous répondons sous un jour ouvré.", "Retour au site"),
    "es": ("Consulta enviada", "Respondemos en un día laborable.", "Volver a la web"),
}
HOME_SITE = "dumskaya-home.com"           # каталог товаров фабрик: заявки оттуда — в тот же бот, с пометкой сайта


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot import Bot  # noqa: E402
from site_monitor import HOME_SITE_DIR, HOME_URL, SiteMonitor  # noqa: E402
from site_stats import (BOT as BOT_UA, CONTACTS, SiteStats, check_init_data, exclude_add, exclude_remove,  # noqa: E402
                        is_own, mark_own, me_data, record_hit, record_time, web)
from site_stats import home as stats_home  # noqa: E402  статистика каталога dumskaya-home.com — тот же код, свой журнал
from site_stats import web_all as stats_all  # noqa: E402  «Все»: оба сайта вместе
from translate import chain as translate_chain, lang_from, purpose as translate_purpose, translate_lead  # noqa: E402
import crm_api  # noqa: E402  учёт проектов студии: /api/crm/*
import portal_api  # noqa: E402  кабинет заказчика и подрядчика, переписка: /api/portal/*
from crm import Crm  # noqa: E402
from crm_portal import Portal  # noqa: E402
from fx import Rates  # noqa: E402
import backups  # noqa: E402  резервные копии: архив на сервере (7 дней) и копия в Telegram
import server_info  # noqa: E402  страница разработчика «Сервер и ИИ»: сервер, данные, расход языковых моделей
import indexnow  # noqa: E402  IndexNow: раз в час новые и изменённые страницы сайтов — в Bing, Яндекс, Seznam

BOT = None


def send_telegram(lead):
    if not BOT:
        return False
    return bool(BOT.route_lead(lead))


def page_url(lead):
    p = lead.get("page", "") or ""
    return p if p.startswith("https://") else "https://dumskaya-design.com" + p


def send_mail(lead):
    if not (SMTP_USER and SMTP_PASSWORD and MAIL_TO):
        return False
    m = EmailMessage()
    m["Subject"] = f"Заявка с сайта: {lead['name']}"
    m["From"] = f"DUMSKAYA DESIGN — сайт <{SMTP_USER}>"
    m["To"] = MAIL_TO
    if "@" in lead["contact"] and " " not in lead["contact"]:
        m["Reply-To"] = lead["contact"]
    body = [
        f"Имя: {lead['name']}",
        f"Контакт: {lead['contact']}",
        f"Интересует: {lead['model']}" if lead.get("model") else "",
        "",
        lead.get("message", ""),
        "",
    ]
    if lead.get("message_ru"):
        body += [f"Перевод на русский {lang_from(lead.get('message_lang'))}:".replace("  ", " "), lead["message_ru"], ""]
    body += [
        f"Страница: {page_url(lead)}",
        f"Язык: {lead.get('lang', '')}",
        f"Время: {lead['time']}",
    ]
    m.set_content("\n".join(x for x in body if x is not None))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(SMTP_USER, SMTP_PASSWORD)
        s.send_message(m)
    return True


def deliver(lead):
    with translate_purpose("lead"):    # перевод сообщения на русский (если оно не по-русски и задан ключ сервиса)
        translate_lead(lead, log=log)
    crm = getattr(BOT, "crm", None)
    if crm:                            # в «Студию» → «Заявки»; номер нужен для кнопки «Открыть заявку» в сообщении
        try:
            lead["crm_id"] = crm.add_lead(lead)
        except Exception as e:  # noqa: BLE001
            log(f"учёт: заявка не записана: {type(e).__name__}: {e}")
    ok = []
    for name, fn in (("telegram", send_telegram), ("email", send_mail)):
        try:
            if fn(lead):
                ok.append(name)
        except Exception as e:  # noqa: BLE001
            log(f"{name}: ошибка {type(e).__name__}: {e}")
    if crm and lead.get("crm_id") and (lead.get("routed") or lead.get("model_name")):
        try:
            crm.lead_routed(lead["crm_id"], lead.get("routed") or "", lead.get("model_name") or "")
        except Exception as e:  # noqa: BLE001
            log(f"учёт: кому передана заявка — не записано: {e}")
    log(f"заявка от {lead['name']!r}: доставлено {ok or 'никуда (сохранено в файл)'}")
    return ok


class Handler(BaseHTTPRequestHandler):
    server_version = "dd-lead"

    def log_message(self, fmt, *args):
        pass

    def client_ip(self):
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() or self.client_address[0]

    def reply(self, code, payload, html_page=None, telegram_frame=False):
        if html_page is not None:
            body = html_page.encode()
            ctype = "text/html; charset=utf-8"
        else:
            body = json.dumps(payload, ensure_ascii=False).encode()
            ctype = "application/json; charset=utf-8"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", ROBOTS)          # ответы сервиса (кабинеты, «Студия», файлы) — не для поисковиков
        if telegram_frame:       # мини-приложение: Telegram Web открывает его во фрейме
            self.send_header("Content-Security-Policy", "frame-ancestors 'self' https://web.telegram.org")
        else:
            self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if crm_api.handle_get(self, path.rstrip("/"), query) or portal_api.handle_get(self, path.rstrip("/"), query):
            return
        if path.rstrip("/") == "/api/stats/app":           # графики посетителей — мини-приложение Telegram
            try:
                page = crm_api.page("stats_app.html")
            except OSError:
                return self.reply(404, {"ok": False})
            return self.reply(200, None, html_page=page, telegram_frame=True)
        if path.rstrip("/") == "/api/stats/site":          # работает ли сайт (что показывала /site): только разработчику
            if not self.stats_owner():
                return self.reply(403, {"ok": False})
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            mon = getattr(BOT, "monitor_home" if (q.get("site") or [""])[0] == "home" else "monitor", None)
            return self.reply(200, mon.status_data() if mon else {"running": False})
        if path.rstrip("/") == "/api/stats/server/app":    # «Сервер и ИИ» — страница (данные — только разработчику)
            try:
                page = crm_api.page("server_app.html")
            except OSError:
                return self.reply(404, {"ok": False})
            return self.reply(200, None, html_page=page, telegram_frame=True)
        if path.rstrip("/") == "/api/stats/server":        # нагрузка, память, диск, данные, бот, расход ИИ: только разработчику
            if not self.stats_owner():
                return self.reply(403, {"ok": False})
            return self.reply(200, server_info.snapshot(BOT))
        if path.rstrip("/") == "/api/stats/me":            # «Не считать нас»: только у разработчика
            if not self.stats_owner():
                return self.reply(403, {"ok": False})
            return self.reply(200, me_data(self.client_ip()))
        if path.rstrip("/") == "/api/stats/data":
            if not self.stats_admin():
                return self.reply(403, {"ok": False})
            q = dict(urllib.parse.parse_qsl(query))
            period = q.get("p") or q.get("days") or "7"
            # «Графики»: сайт студии, каталог или оба вместе («Все»)
            fn = stats_home().web if q.get("site") == "home" else stats_all if q.get("site") == "all" else web
            try:
                return self.reply(200, fn(period if period in PERIODS else "7"))
            except PermissionError:
                return self.reply(503, {"ok": False, "error": "log"})
            except Exception as e:  # noqa: BLE001
                log(f"статистика: ошибка {type(e).__name__}: {e}")
                return self.reply(500, {"ok": False})
        if self.path.rstrip("/") == "/api/lead/health":
            people = len(BOT.active(("owner", "designer"))) if BOT else 0
            return self.reply(200, {"ok": True, "telegram": bool(BOT and people), "recipients": people,
                                    "email": bool(SMTP_USER and SMTP_PASSWORD)})
        self.reply(404, {"ok": False})

    def stats_admin(self):
        """Разработчик или дизайнер студии — по подписи Telegram из мини-приложения; иначе None.
        Адрес, с которого студия открыла «Графики», запоминается: её визиты на сайт с него не считаются."""
        uid = check_init_data(self.headers.get("X-Telegram-Init-Data", ""), TG_TOKEN)
        u = BOT.user(uid) if uid and BOT else None
        if not (u and BOT.is_admin(u)):
            return None
        try:
            mark_own(self.client_ip(), u["name"] or str(u["tg_id"]))
        except OSError as e:
            log(f"статистика: свой адрес не записан: {e}")
        return u

    def stats_owner(self):
        """Только разработчик: список своих адресов меняет он (дизайнеру этот блок не показывается)."""
        u = self.stats_admin()
        return u if u and u["role"] == "owner" else None

    def hit(self):
        """Сообщение скрипта на страницах сайта: нажатие на телефон, e-mail или мессенджер (hits.jsonl) или «время
        на странице» — сколько секунд страница была на экране (times.jsonl). В оба файла — страница и обезличенный ключ
        посетителя (хеш IP + браузера с солью сервера), без самого IP."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n).decode("utf-8", "replace")) if 0 < n <= 400 else {}
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        kind, page = str(data.get("t") or ""), str(data.get("p") or "")[:200]
        ua, ip = self.headers.get("User-Agent", ""), self.client_ip()
        st = stats_home() if self.site() == HOME_SITE else None      # каталог пишет в свои файлы (times-home, hits-home)
        rec_time, rec_hit = (st.record_time, st.record_hit) if st else (record_time, record_hit)
        valid = page.startswith("/") and ua.startswith("Mozilla/") and not BOT_UA.search(ua) and not is_own(ip)
        if valid and kind == "time":
            try:
                secs = int(data.get("s") or 0)
            except (TypeError, ValueError):
                secs = 0
            act = data.get("i")                       # было ли на странице действие человека; старые страницы не присылают
            act = None if act is None else bool(act)
            if 0 < secs <= 6 * 3600 and self.allow(TIME_RATE, ip, TIME_MAX):
                try:
                    rec_time(page, secs, ip, ua, act, bool(data.get("w")))
                except OSError as e:
                    log(f"время на странице: не записано: {e}")
        elif valid and kind in CONTACTS and self.allow(HIT_RATE, ip, HIT_MAX):
            try:
                rec_hit(kind, page, ip, ua)
            except OSError as e:
                log(f"нажатия: не записано: {e}")
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", ROBOTS)
        self.end_headers()

    def site(self):
        """С какого сайта запрос: dumskaya-home.com (каталог) или сайт студии — по адресу, который передаёт Caddy."""
        host = (self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "").split(":")[0].strip().lower()
        return HOME_SITE if host == HOME_SITE or host.endswith("." + HOME_SITE) else "dumskaya-design.com"

    @staticmethod
    def allow(rate, ip, limit):
        """Не больше limit сообщений за 10 минут с одного адреса."""
        now = time.time()
        with lock:
            if len(rate) > 5000:                     # адреса, от которых давно ничего не было, — забыть
                for k in [k for k, q in rate.items() if not q or now - q[-1] > RATE_WINDOW]:
                    del rate[k]
            q = rate[ip]
            while q and now - q[0] > RATE_WINDOW:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def do_POST(self):
        path, _, query = self.path.partition("?")
        if crm_api.handle_post(self, path.rstrip("/"), query) or portal_api.handle_post(self, path.rstrip("/"), query):
            return
        if self.path.split("?")[0].rstrip("/") == "/api/hit":
            return self.hit()
        if self.path.split("?")[0].rstrip("/") == "/api/stats/exclude":
            u = self.stats_owner()
            if not u:
                return self.reply(403, {"ok": False})
            try:
                data = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 2000)) or b"{}")
            except ValueError:
                return self.reply(400, {"ok": False})
            ip = self.client_ip()
            try:
                if data.get("action") == "add":           # адрес берётся из самого запроса, а не из присланных данных
                    exclude_add(ip, u["name"] or str(u["tg_id"]))
                elif data.get("action") == "remove":
                    exclude_remove(str(data.get("net") or ""))
                else:
                    return self.reply(400, {"ok": False})
            except ValueError:
                return self.reply(400, {"ok": False})
            log(f"статистика: свои адреса изменены ({data.get('action')}) — {u['name']}")
            return self.reply(200, me_data(ip))
        if self.path.split("?")[0].rstrip("/") != "/api/lead":
            return self.reply(404, {"ok": False})
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 20000:
            return self.reply(400, {"ok": False, "error": "size"})
        raw = self.rfile.read(length).decode("utf-8", "replace")
        is_json = "json" in (self.headers.get("Content-Type") or "")
        try:
            data = json.loads(raw) if is_json else {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
        except ValueError:
            return self.reply(400, {"ok": False, "error": "format"})
        if not isinstance(data, dict):
            return self.reply(400, {"ok": False, "error": "format"})
        lang = str(data.get("lang") or "ru")[:5]
        lang = lang if lang in THANKS else "ru"
        if str(data.get("website") or "").strip():          # ловушка для ботов
            return self.reply(200, {"ok": True})
        lead = {k: str(data.get(k) or "").strip()[:n] for k, n in LIMITS.items()}
        lead["lang"] = lang
        country = re.sub(r"\s+", " ", str(data.get("country") or "")).strip()[:100]
        if country:
            sep = " : " if lang == "fr" else ": "
            lead["message"] = (f"{DELIVERY.get(lang, 'Доставка')}{sep}{country}\n\n{lead['message']}".strip())[:LIMITS["message"] + 120]
        lead["site"] = self.site()
        if lead["site"] == HOME_SITE and lead["page"].startswith("/"):     # в учёте и «Студии» видно, с какого сайта заявка
            lead["page"] = ("https://" + HOME_SITE + lead["page"])[:LIMITS["page"]]
        if len(lead["name"]) < 1 or len(lead["contact"]) < 3:
            return self.reply(422, {"ok": False, "error": "fields"})
        ip = self.client_ip()
        now = time.time()
        with lock:
            q = RATE[ip]
            while q and now - q[0] > RATE_WINDOW:
                q.popleft()
            if len(q) >= RATE_MAX:
                return self.reply(429, {"ok": False, "error": "rate"})
            q.append(now)
        lead["time"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        lead["ip"] = ip
        try:
            os.makedirs(os.path.dirname(LEADS_FILE), exist_ok=True)
            with lock, open(LEADS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(lead, ensure_ascii=False) + "\n")
        except OSError as e:
            log(f"не удалось записать файл заявок: {e}")
        delivered = deliver(lead)
        if is_json:
            return self.reply(200 if delivered else 502, {"ok": bool(delivered)})
        t, txt, back = THANKS[lang]
        home = "/" if lang == ("en" if lead["site"] == HOME_SITE else "ru") else f"/{lang}"
        page = (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                f"<title>{t}</title><body style='font:17px/1.6 system-ui;max-width:560px;margin:15vh auto;padding:0 20px'>"
                f"<h1 style='font-weight:400'>{t}</h1><p>{txt}</p><p><a href='{home}'>{back}</a></p>")
        self.reply(200, None, html_page=page)


def main():
    global BOT
    if TG_TOKEN:
        BOT = Bot(TG_TOKEN, BOT_OWNER, BOT_DB, log=log)
        try:                                        # учёт вызовов языковых моделей (страница «Сервер и ИИ»)
            server_info.install(BOT.s)
        except Exception as e:  # noqa: BLE001
            log(f"учёт расхода ИИ не включён: {type(e).__name__}: {e}")
    if "--test" in sys.argv:
        lead = {"name": "Проверка", "contact": "test@example.com", "message": "Тестовая заявка с сервера",
                "page": "/contact", "model": "", "lang": "ru", "time": datetime.now(timezone.utc).isoformat()}
        print("доставлено:", deliver(lead))
        return
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    if BOT:
        BOT.monitor = SiteMonitor(BOT, log=log)     # сторож сайта: «сайт не отвечает» разработчику в бот
        BOT.monitor_home = SiteMonitor(BOT, url=HOME_URL, log=log, name="Магазин", key="monh",   # и магазина dumskaya-home.com
                                       mode_file="home-mode", site_dir=HOME_SITE_DIR)
        BOT.stats = SiteStats(BOT, log=log)         # посетители по журналу Caddy: «Графики» и строка в 9:00
        crm_api.BOT = BOT                           # размер текста в «Студии» и графиках, файлы проекта → в чат
        try:                                        # учёт проектов студии (кнопка «Студия»)
            crm_api.CRM = BOT.crm = Crm(rates=Rates())
            BOT.stats.hooks.append(BOT.crm.backup_if_due)   # раз в день — уборка корзины и старых удалённых заявок
            BOT.crm.import_leads(LEADS_FILE, log=log)         # заявки из файла, которых ещё нет в «Студии»
            # кабинет заказчика и подрядчика («Мой проект»), переписка с заказчиками, напоминания об оплате услуг
            crm_api.PORTAL = portal_api.PORTAL = BOT.portal = Portal(BOT.crm)
            portal_api.CRM, portal_api.BOT, portal_api.CHECK, portal_api.TOKEN = BOT.crm, BOT, check_init_data, TG_TOKEN
            BOT.stats.hooks.append(BOT.portal_reminders)
            if BOT.portal.ensure_observer(BOT.owner):        # «Разработчик ПО» — наблюдатель для тестирования (один раз)
                log("кабинет: создан наблюдатель «Разработчик ПО» (видит всё; удалить — в «Студии», Контакты → Подрядчики)")
        except Exception as e:  # noqa: BLE001
            log(f"учёт проектов не запущен: {type(e).__name__}: {e}")
        # резервные копии: каждую ночь архив данных на сервере (7 дней); в Telegram не копируем (решено 25.10.2026),
        # на Мак — тоже (24.10.2026); весь сервер копирует Hetzner
        backups.on_start(BOT)                       # убрать отметки прежней копии в Telegram
        BOT.stats.hooks.append(lambda log=log: backups.daily_tick(BOT, getattr(BOT, "crm", None), log=log))
        # IndexNow (решено 25.10.2026): раз в час и через минуту после запуска — новые, изменённые и удалённые страницы
        # обоих сайтов в Bing, Яндекс и Seznam; dumskaya-home.com — когда откроется на домене. Свой поток, статистику не держит
        indexnow.BOT = BOT
        BOT.stats.hooks.append(indexnow.tick)
        BOT.start()
        BOT.monitor.start()
        BOT.monitor_home.start()
        BOT.stats.start()
    log(f"слушаю 127.0.0.1:{PORT}; бот={'да' if BOT else 'нет'}, почта={'да' if SMTP_USER and SMTP_PASSWORD else 'нет'}, "
        f"перевод={' → '.join({'sub': 'ChatGPT-подписка', 'openai': 'ChatGPT', 'deepl': 'DeepL', 'claude': 'Claude'}[p] for p in translate_chain()) or 'нет'}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
