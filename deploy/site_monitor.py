#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сторож сайта: раз в минуту открывает https://dumskaya-design.com/ с сервера, как посетитель
(DNS → Caddy → HTTPS → файлы сайта). Если сайт не отвечает 3 проверки подряд, разработчику в бот приходит
«🔴 Сайт не отвечает» — с причиной и тем, что сделать; пока не починится — напоминание раз в час;
когда снова отвечает — «🟢 Сайт снова работает». Сертификат HTTPS: если до конца меньше 14 дней
(Caddy продлевает его сам за 30 дней), — предупреждение раз в сутки.

Работает в процессе сервиса заявок вместе с ботом (lead_service.py) и только в режиме live (файл ~/dumskaya/mode):
пока домен не переключён на сервер, проверять нечего. Состояние хранится в базе бота — перезапуск сервиса
(например, при выкладке) не даёт повторных сообщений.

Этот сторож живёт на том же сервере: если сервер выключится целиком, сообщить будет некому —
для этого нужна проверка снаружи.
Только стандартная библиотека Python 3."""
import os
import re
import shutil
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bratislava")
except Exception:  # noqa: BLE001
    TZ = None

URL = os.environ.get("SITE_MONITOR_URL", "https://dumskaya-design.com/")
MARKER = "DUMSKAYA"                      # слово, которое точно есть на главной: страница наша, а не заглушка
EVERY = 60                               # секунд между проверками
FAILS = 3                                # подряд неудачных проверок до сообщения (~3 минуты)
REMIND = 3600                            # напоминание, пока сайт лежит
CERT_WARN_DAYS = 14
APP = os.path.expanduser("~/dumskaya")
CADDYFILE = "/etc/caddy/Caddyfile"
SITE_DIR = "/var/www/dumskaya/site"
HOST_ALIAS = "eurox"                     # как сервер называется в ssh на Mac


def esc(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def hhmm(ts):
    d = datetime.fromtimestamp(ts, TZ) if TZ else datetime.fromtimestamp(ts)
    return d.strftime("%d.%m %H:%M")


def minutes(sec):
    m = int(sec // 60)
    return f"{m} мин" if m < 120 else f"{m // 60} ч {m % 60} мин"


def check(url=URL, timeout=20):
    """(ok, причина, мс). ok — ответ 200 и на странице есть MARKER."""
    t0 = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": "dumskaya-site-monitor/1.0", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(400_000).decode("utf-8", "replace")
            ms = int((time.monotonic() - t0) * 1000)
            if r.status != 200:
                return False, f"ответ {r.status}", ms
            if MARKER not in body:
                return False, "открывается чужая или пустая страница", ms
            return True, "", ms
    except urllib.error.HTTPError as e:
        return False, f"ошибка {e.code} {esc(e.reason)}", int((time.monotonic() - t0) * 1000)
    except urllib.error.URLError as e:
        r = e.reason
        if isinstance(r, ssl.SSLCertVerificationError):
            why = f"ошибка сертификата HTTPS: {esc(r.verify_message or r)}"
        elif isinstance(r, ssl.SSLError):
            why = f"ошибка HTTPS: {esc(r)}"
        elif isinstance(r, socket.timeout) or "timed out" in str(r):
            why = "не ответил за 20 секунд"
        elif isinstance(r, ConnectionRefusedError) or "refused" in str(r).lower():
            why = "соединение отклонено (на порту 443 никто не слушает)"
        elif isinstance(r, socket.gaierror):
            why = "домен не находится в DNS"
        else:
            why = esc(r)
        return False, why, int((time.monotonic() - t0) * 1000)
    except (socket.timeout, TimeoutError):
        return False, "не ответил за 20 секунд", int((time.monotonic() - t0) * 1000)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {esc(e)}", int((time.monotonic() - t0) * 1000)


def cert_days(url=URL, timeout=15):
    """Сколько дней осталось сертификату HTTPS (None — не удалось узнать)."""
    host = urllib.parse.urlsplit(url).hostname
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=timeout) as s, ctx.wrap_socket(s, server_hostname=host) as t:
            end = ssl.cert_time_to_seconds(t.getpeercert()["notAfter"])
        return int((end - time.time()) // 86400)
    except Exception:  # noqa: BLE001
        return None


def diagnose():
    """Что видно на сервере: подсказки, почему сайт мог упасть и что делать."""
    tips = []
    try:
        caddy = subprocess.run(["systemctl", "is-active", "caddy"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        caddy = ""
    if caddy and caddy != "active":
        tips.append(f"• Caddy не работает (<code>{esc(caddy)}</code>) — значит, лежит и EuroExchange. "
                    f"Причина и откат нашего сайта, чтобы сосед поднялся: <code>ssh -t {HOST_ALIAS} 'sudo bash ~/dumskaya/deploy/server-doctor.sh'</code>")
    try:
        cf = open(CADDYFILE, encoding="utf-8", errors="replace").read()
        linked = re.search(r"^\s*import\s+sites/(\*|dumskaya)\.caddy\s*$", cf, re.M)
        if not linked:
            tips.append("• В основном Caddyfile нет строки <code>import sites/*.caddy</code> — похоже, его перезаписала "
                        "выкладка EuroExchange. Подключить сайт снова — выкладка с Mac: "
                        "<code>cd ~/dumskaya-site &amp;&amp; npm run deploy</code>")
    except OSError:
        pass
    if os.path.isdir(os.path.dirname(SITE_DIR)) and not os.path.isfile(os.path.join(SITE_DIR, "index.html")):
        tips.append("• На сервере нет файлов сайта — выложите заново: <code>cd ~/dumskaya-site &amp;&amp; npm run deploy</code>")
    try:
        du = shutil.disk_usage("/")
        if du.free < 1_000_000_000 or du.free / du.total < 0.03:
            tips.append(f"• На диске сервера почти нет места: свободно {du.free // 1_000_000} МБ")
    except OSError:
        pass
    if not tips:
        tips.append("• На сервере видимых причин нет (Caddy работает, сайт подключён, файлы на месте). "
                    f"Посмотреть журнал Caddy: <code>ssh {HOST_ALIAS} 'sudo journalctl -u caddy -n 30 --no-pager'</code> "
                    "— и пришлите вывод Claude.")
    return "\n".join(tips)


class SiteMonitor:
    def __init__(self, bot, url=URL, log=print, check_fn=check, cert_fn=cert_days, diag_fn=diagnose,
                 clock=time.time, live_fn=None, retry_wait=10):
        self.bot, self.url, self.log, self.retry_wait = bot, url, log, retry_wait
        self.check_fn, self.cert_fn, self.diag_fn, self.clock = check_fn, cert_fn, diag_fn, clock
        self.live_fn = live_fn or self.is_live
        self.stop = threading.Event()
        self.fails = 0
        self.last = None                      # (время, ok, причина, мс) — для /site
        self._cert = (0.0, None)              # (когда проверяли, дней до конца сертификата) — для «Студии»

    # ---------- состояние в базе бота ----------
    def get(self, k, default=None):
        v = self.bot.s.get(f"mon:{k}")
        return default if v in (None, "") else v

    def put(self, k, v):
        if v is None:
            self.bot.s.drop(f"mon:{k}")
        else:
            self.bot.s.put(f"mon:{k}", str(v))

    @staticmethod
    def is_live():
        try:
            return open(os.path.join(APP, "mode")).read().strip() == "live"
        except OSError:
            return False

    def say(self, text):
        return self.bot.notify(text, roles=("owner",))

    # ---------- одна проверка ----------
    def tick(self):
        if not self.live_fn():
            self.fails = 0
            return
        now = self.clock()
        ok, why, ms = self.check_fn(self.url)
        if not ok:                            # перепроверка через 10 с: короткий сбой (перезагрузка Caddy) не считаем
            self.stop.wait(self.retry_wait)
            ok, why, ms = self.check_fn(self.url)
        self.last = (now, ok, why, ms)
        down_since = self.get("down_since")
        if ok:
            self.fails = 0
            if down_since:
                if self.get("alerted"):
                    self.say(f"🟢 <b>Сайт снова работает</b>\n{esc(self.url)} — не отвечал {minutes(now - float(down_since))} "
                             f"(с {hhmm(float(down_since))}). Ответ за {ms} мс.")
                self.put("down_since", None); self.put("alerted", None); self.put("reminded", None)
            self.check_cert(now)
            return
        self.fails += 1
        if not down_since:
            self.put("down_since", now)
            down_since = now
        down_since = float(down_since)
        if not self.get("alerted") and self.fails >= FAILS:
            self.put("alerted", now); self.put("reminded", now)
            self.log(f"сайт не отвечает: {why}")
            self.say(f"🔴 <b>Сайт не отвечает</b>\n{esc(self.url)} — {why}\n"
                     f"Проверка с сервера, {self.fails} раза подряд с {hhmm(down_since)}.\n\n"
                     f"<b>Что видно на сервере:</b>\n{self.diag_fn()}\n\n"
                     "Когда сайт снова ответит, придёт сообщение.")
        elif self.get("alerted") and now - float(self.get("reminded", now)) >= REMIND:
            self.put("reminded", now)
            self.say(f"🔴 Сайт всё ещё не отвечает — {minutes(now - down_since)}: {why}\n\n{self.diag_fn()}")

    def check_cert(self, now):
        if now - float(self.get("cert_checked", 0)) < 6 * 3600:
            return
        self.put("cert_checked", now)
        days = self.cert_fn(self.url)
        if days is None or days >= CERT_WARN_DAYS:
            return
        if now - float(self.get("cert_warned", 0)) >= 86400:
            self.put("cert_warned", now)
            self.say(f"⚠️ <b>Сертификат HTTPS</b> сайта истекает через {days} дн. Caddy продлевает его сам за 30 дней — "
                     f"раз не продлил, что-то мешает. Журнал: <code>ssh {HOST_ALIAS} 'sudo journalctl -u caddy -n 50 --no-pager | grep -i -E \"tls|acme|certif\"'</code>")

    def status(self):
        """Текст для команды /site."""
        if not self.live_fn():
            return "Сайт ещё не переключён на сервер (режим просмотра) — сторож не проверяет."
        if not self.last:
            return "Сторож сайта запущен, первая проверка — в течение минуты."
        t, ok, why, ms = self.last
        down = self.get("down_since")
        head = (f"🟢 Сайт отвечает: {ms} мс" if ok else
                f"🔴 Сайт не отвечает с {hhmm(float(down))}: {why}" if down else f"🔴 Сайт не отвечает: {why}")
        days = self.cert_fn(self.url)
        cert = f"\nСертификат HTTPS: ещё {days} дн." if days is not None else ""
        return f"{head}\n{esc(self.url)} · проверка {hhmm(t)}, раз в минуту{cert}"

    def status_data(self):
        """То же для «Студии» (вкладка «Сайт», только разработчику): цифрами, без HTML."""
        out = {"running": True, "live": bool(self.live_fn()), "url": self.url}
        if not out["live"] or not self.last:
            return out
        t, ok, why, ms = self.last
        down = self.get("down_since")
        now = time.time()
        if now - self._cert[0] > 600:            # сертификат — не чаще раза в 10 минут
            self._cert = (now, self.cert_fn(self.url))
        out.update(checked=t, ok=bool(ok), why=why or "", ms=ms, down_since=float(down) if down else None,
                   cert_days=self._cert[1], every=EVERY)
        return out

    # ---------- поток ----------
    def start(self):
        t = threading.Thread(target=self.loop, name="site-monitor", daemon=True)
        t.start()
        return t

    def loop(self):
        self.stop.wait(30)                    # после запуска сервиса даём Caddy и сети подняться
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001
                self.log(f"сторож сайта: ошибка {type(e).__name__}: {e}")
            self.stop.wait(EVERY)
