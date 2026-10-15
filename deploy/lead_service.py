#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Приём заявок с сайта dumskaya-design.com.

Слушает 127.0.0.1:8095 (Caddy проксирует сюда /api/lead). Заявку:
  1) сразу дописывает в файл leads.jsonl — так она не потеряется, даже если почта и Telegram недоступны;
  2) отправляет в Telegram (бот → чат);
  3) отправляет письмом через SMTP (например, Gmail с паролем приложения).
Только стандартная библиотека Python 3, без установки пакетов.

Настройки — переменные окружения (файл lead.env, его читает systemd):
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  SMTP_HOST=smtp.gmail.com  SMTP_PORT=587  SMTP_USER  SMTP_PASSWORD  MAIL_TO
  LEADS_FILE=/home/deploy/dumskaya/leads.jsonl  PORT=8095
"""
import html
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
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
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
}


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def send_telegram(lead):
    if not (TG_TOKEN and TG_CHAT):
        return False
    lines = [
        "<b>Заявка с сайта</b>",
        f"<b>Имя:</b> {html.escape(lead['name'])}",
        f"<b>Контакт:</b> {html.escape(lead['contact'])}",
    ]
    if lead.get("model"):
        lines.append(f"<b>Интересует:</b> {html.escape(lead['model'])}")
    if lead.get("message"):
        lines.append(f"<b>Сообщение:</b>\n{html.escape(lead['message'])}")
    lines.append(f"<i>{html.escape(lead.get('lang', ''))} · https://dumskaya-design.com{html.escape(lead.get('page', ''))}</i>")
    data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": "\n".join(lines), "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read()).get("ok", False)


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

    def reply(self, code, payload, html_page=None):
        if html_page is not None:
            body = html_page.encode()
            ctype = "text/html; charset=utf-8"
        else:
            body = json.dumps(payload).encode()
            ctype = "application/json"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/") == "/api/lead/health":
            return self.reply(200, {"ok": True, "telegram": bool(TG_TOKEN and TG_CHAT), "email": bool(SMTP_USER and SMTP_PASSWORD)})
        self.reply(404, {"ok": False})

    def do_POST(self):
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
    if "--test" in sys.argv:
        lead = {"name": "Проверка", "contact": "test@example.com", "message": "Тестовая заявка с сервера",
                "page": "/contact", "model": "", "lang": "ru", "time": datetime.now(timezone.utc).isoformat()}
        print("доставлено:", deliver(lead))
        return
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    log(f"слушаю 127.0.0.1:{PORT}; telegram={'да' if TG_TOKEN and TG_CHAT else 'нет'}, почта={'да' if SMTP_USER and SMTP_PASSWORD else 'нет'}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
