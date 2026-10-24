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
И статистика посетителей по журналу Caddy (site_stats.py): отчёт разработчику в 9:00, команда /stats.
Только стандартная библиотека Python 3, без установки пакетов.

Настройки — переменные окружения (файл lead.env, его читает systemd):
  TELEGRAM_BOT_TOKEN  BOT_OWNER_ID (Telegram ID разработчика)  BOT_DB=/home/deploy/dumskaya/bot.db
  SMTP_HOST=smtp.gmail.com  SMTP_PORT=587  SMTP_USER  SMTP_PASSWORD  MAIL_TO
  LEADS_FILE=/home/deploy/dumskaya/leads.jsonl  PORT=8095
  Перевод сообщений заказчиков на русский (translate.py): DEEPL_API_KEY или ANTHROPIC_API_KEY (+ TRANSLATE_MODEL)
"""
import json
import os
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
RATE = defaultdict(deque)          # ip → время последних заявок
RATE_MAX, RATE_WINDOW = 5, 600     # не больше 5 заявок за 10 минут с одного адреса
lock = threading.Lock()

THANKS = {
    "ru": ("Заявка отправлена", "Мы свяжемся с вами в течение рабочего дня.", "Вернуться на сайт"),
    "ua": ("Заявку надіслано", "Ми зв’яжемося з вами протягом робочого дня.", "Повернутися на сайт"),
    "en": ("Request sent", "We will get back to you within one working day.", "Back to the website"),
    "sk": ("Žiadosť bola odoslaná", "Ozveme sa vám do jedného pracovného dňa.", "Späť na web"),
    "de": ("Anfrage gesendet", "Wir melden uns innerhalb eines Werktags.", "Zurück zur Website"),
}


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot import Bot  # noqa: E402
from site_monitor import SiteMonitor  # noqa: E402
from site_stats import SiteStats, check_init_data, exclude_add, exclude_remove, me_data, web_data  # noqa: E402
from translate import lang_from, provider, translate_lead  # noqa: E402

BOT = None


def send_telegram(lead):
    if not BOT:
        return False
    return bool(BOT.route_lead(lead))


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
        f"Страница: https://dumskaya-design.com{lead.get('page', '')}",
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
    translate_lead(lead, log=log)      # перевод сообщения на русский (если оно не по-русски и задан ключ сервиса)
    ok = []
    for name, fn in (("telegram", send_telegram), ("email", send_mail)):
        try:
            if fn(lead):
                ok.append(name)
        except Exception as e:  # noqa: BLE001
            log(f"{name}: ошибка {type(e).__name__}: {e}")
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
        if telegram_frame:       # мини-приложение: Telegram Web открывает его во фрейме
            self.send_header("Content-Security-Policy", "frame-ancestors 'self' https://web.telegram.org")
        else:
            self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path.rstrip("/") == "/api/stats/app":           # графики посетителей — мини-приложение Telegram
            try:
                page = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats_app.html"), encoding="utf-8").read()
            except OSError:
                return self.reply(404, {"ok": False})
            return self.reply(200, None, html_page=page, telegram_frame=True)
        if path.rstrip("/") == "/api/stats/me":            # «Не считать нас»: только у разработчика
            if not self.stats_owner():
                return self.reply(403, {"ok": False})
            return self.reply(200, me_data(self.client_ip()))
        if path.rstrip("/") == "/api/stats/data":
            if not self.stats_admin():
                return self.reply(403, {"ok": False})
            days = dict(urllib.parse.parse_qsl(query)).get("days", "7")
            try:
                return self.reply(200, web_data(int(days) if days.isdigit() else 7))
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
        """Разработчик или дизайнер студии — по подписи Telegram из мини-приложения; иначе None."""
        uid = check_init_data(self.headers.get("X-Telegram-Init-Data", ""), TG_TOKEN)
        u = BOT.user(uid) if uid and BOT else None
        return u if u and BOT.is_admin(u) else None

    def stats_owner(self):
        """Только разработчик: список своих адресов меняет он (дизайнеру этот блок не показывается)."""
        u = self.stats_admin()
        return u if u and u["role"] == "owner" else None

    def do_POST(self):
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
        home = "/" if lang == "ru" else f"/{lang}"
        page = (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                f"<title>{t}</title><body style='font:17px/1.6 system-ui;max-width:560px;margin:15vh auto;padding:0 20px'>"
                f"<h1 style='font-weight:400'>{t}</h1><p>{txt}</p><p><a href='{home}'>{back}</a></p>")
        self.reply(200, None, html_page=page)


def main():
    global BOT
    if TG_TOKEN:
        BOT = Bot(TG_TOKEN, BOT_OWNER, BOT_DB, log=log)
    if "--test" in sys.argv:
        lead = {"name": "Проверка", "contact": "test@example.com", "message": "Тестовая заявка с сервера",
                "page": "/contact", "model": "", "lang": "ru", "time": datetime.now(timezone.utc).isoformat()}
        print("доставлено:", deliver(lead))
        return
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    if BOT:
        BOT.monitor = SiteMonitor(BOT, log=log)     # сторож сайта: «сайт не отвечает» разработчику в бот
        BOT.stats = SiteStats(BOT, log=log)         # посетители по журналу Caddy: отчёт в 9:00 и /stats
        BOT.start()
        BOT.monitor.start()
        BOT.stats.start()
    log(f"слушаю 127.0.0.1:{PORT}; бот={'да' if BOT else 'нет'}, почта={'да' if SMTP_USER and SMTP_PASSWORD else 'нет'}, "
        f"перевод={ {'deepl': 'DeepL', 'claude': 'Claude'}.get(provider(), 'нет') }")
    srv.serve_forever()


if __name__ == "__main__":
    main()
