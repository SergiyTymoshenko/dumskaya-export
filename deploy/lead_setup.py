#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Настройка отправки заявок с сайта в Telegram и на почту — по шагам, с проверкой каждого шага.
Запускается на сервере от пользователя deploy (с Mac:  npm run leads):
    python3 ~/dumskaya/deploy/lead_setup.py

Что делает:
  1) Telegram: проверяет токен бота студии, записывает ID разработчика, бот пишет вам пробное сообщение;
  2) почта: проверяет вход в Gmail по паролю приложения;
  3) записывает ~/dumskaya/lead.env (доступ только у владельца), перезапускает сервис заявок
     (нужен пароль sudo) и отправляет пробную заявку тем же путём, что и форма на сайте.
Токен и пароль на экран не выводятся. Enter на любом вопросе — оставить как есть.
"""
import getpass
import json
import os
import smtplib
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ~/dumskaya
ENV = os.path.join(APP, "lead.env")
EXAMPLE = os.path.join(APP, "deploy", "lead.env.example")
B, D, G, R, Y, X = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[33m", "\033[0m"
SAVED = False


def say(t=""): print(t, flush=True)
def ok(t): say(f"  {G}✓{X} {t}")
def bad(t): say(f"  {R}✗{X} {t}")
def note(t): say(f"  {Y}!{X} {t}")
def head(t): say(f"\n{B}{t}{X}")


def ask(prompt, default=""):
    hint = f" [{default}]" if default else ""
    try:
        v = input(f"  {prompt}{hint}: ").strip()
    except EOFError:
        v = ""
    return v or default


def ask_secret(prompt):
    try:
        return getpass.getpass(f"  {prompt} (символы не видны): ").strip()
    except EOFError:
        return ""


def mask(s):
    return f"{s[:4]}…{s[-3:]}" if len(s) > 10 else "…"


# ---------- lead.env ----------
def read_env():
    src = ENV if os.path.exists(ENV) else EXAMPLE
    lines = open(src, encoding="utf-8").read().splitlines() if os.path.exists(src) else []
    vals = {}
    for ln in lines:
        if "=" in ln and not ln.lstrip().startswith("#"):
            k, v = ln.split("=", 1)
            vals[k.strip()] = v.strip()
    return lines, vals


def write_env(lines, vals):
    out, seen = [], set()
    for ln in lines:
        if "=" in ln and not ln.lstrip().startswith("#"):
            k = ln.split("=", 1)[0].strip()
            if k in vals:
                out.append(f"{k}={vals[k]}"); seen.add(k); continue
        out.append(ln)
    out += [f"{k}={v}" for k, v in vals.items() if k not in seen]
    tmp = ENV + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ENV)


# ---------- Telegram ----------
def tg(token, method, **params):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode() if params else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:  # noqa: BLE001
            return {"ok": False, "error_code": e.code, "description": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error_code": 0, "description": f"нет связи с Telegram: {e}"}


def setup_telegram(vals):
    head("1. Telegram-бот студии — заявки с сайта, пользователи и партнёры")
    token = vals.get("TELEGRAM_BOT_TOKEN", "")
    if token:
        say(f"  Сейчас указан бот с токеном {mask(token)}.")
    say(f"  {D}Нужен отдельный бот студии (не тот, что работает в другом сервисе): @BotFather → /newbot →")
    say("  имя, например «DUMSKAYA студия» → username латиницей с «bot» на конце. BotFather пришлёт токен")
    say(f"  вида 123456789:AAE…  Там же: /setjoingroups → выберите бота → Disable (в группы бот не добавляется).{X}")
    for attempt in range(3):
        new = ask_secret("Вставьте токен бота (Enter — оставить текущий)")
        if not new and not token:
            note("Бот пропущен — заявки будут приходить только на почту.")
            return
        cand = new or token
        me = tg(cand, "getMe")
        if me.get("ok"):
            token = cand
            ok(f"бот @{me['result']['username']} найден")
            break
        bad(f"Telegram не принял токен: {me.get('description')}")
        if attempt == 2:
            note("Бот пропущен. Запустите настройку ещё раз, когда будет правильный токен.")
            return
    bot = me["result"]["username"]
    vals["TELEGRAM_BOT_TOKEN"] = token
    vals.setdefault("BOT_DB", os.path.join(APP, "bot.db"))
    if vals.get("TELEGRAM_CHAT_ID"):
        vals["TELEGRAM_CHAT_ID"] = ""          # старый способ (один чат) больше не нужен: получатели — в боте
    while True:
        owner = ask("Telegram ID разработчика — получает все уведомления и принимает пользователей",
                    vals.get("BOT_OWNER_ID") or "633722")
        if owner.isdigit():
            break
        bad("Telegram ID — только цифры.")
    vals["BOT_OWNER_ID"] = owner
    say(f"\n  Откройте в Telegram бота {B}@{bot}{X} с этого аккаунта и нажмите «Старт» (если ещё не нажимали).")
    for attempt in range(3):
        r = tg(token, "sendMessage", chat_id=owner,
               text=f"Бот @{bot} подключается к сайту dumskaya-design.com. Через минуту он заработает — нажмите /start.")
        if r.get("ok"):
            ok("бот написал вам — проверьте Telegram")
            return
        bad(f"бот не может написать вам: {r.get('description')}")
        if attempt < 2:
            ask(f"Откройте @{bot}, нажмите «Старт» и потом Enter здесь")
    note("Не дозвонились до вашего аккаунта — после настройки откройте бота и нажмите «Старт».")


# ---------- Почта ----------
def check_smtp(host, port, user, password):
    try:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(user, password)
        return True, ""
    except smtplib.SMTPAuthenticationError as e:
        return False, f"Gmail не принял пароль ({e.smtp_code}). Нужен именно пароль приложения, а не пароль от почты."
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def setup_mail(vals):
    head("2. Почта — копия каждой заявки письмом")
    say(f"  {D}Письма уходят через Gmail. Нужен «пароль приложения» — это не пароль от почты:")
    say("  1) войдите в Google-аккаунт, с которого будут уходить письма;")
    say("  2) включите двухэтапную аутентификацию, если её нет: myaccount.google.com/signinoptions/two-step-verification")
    say("  3) откройте myaccount.google.com/apppasswords, введите название «Сайт DUMSKAYA» → «Создать»;")
    say(f"  4) Google покажет пароль из 16 букв — его и вставьте ниже.{X}")
    host, port = vals.get("SMTP_HOST") or "smtp.gmail.com", int(vals.get("SMTP_PORT") or 587)
    user = ask("Gmail, с которого отправлять", vals.get("SMTP_USER") or "dumskaya.design@gmail.com")
    have = vals.get("SMTP_PASSWORD", "")
    for attempt in range(3):
        pw = ask_secret("Пароль приложения" + (" (Enter — оставить текущий)" if have else " (Enter — пропустить почту)"))
        pw = pw.replace(" ", "") or (have if user == vals.get("SMTP_USER") else "")
        if not pw:
            note("Почта не изменена." if have else "Почта пропущена — заявки будут приходить только в Telegram.")
            return
        good, err = check_smtp(host, port, user, pw)
        if good:
            ok(f"вход в {user} работает")
            vals.update(SMTP_HOST=host, SMTP_PORT=str(port), SMTP_USER=user, SMTP_PASSWORD=pw)
            break
        bad(err)
        if attempt == 2:
            note("Почта пропущена. Запустите настройку ещё раз с новым паролем приложения.")
            return
    to = ask("Куда присылать заявки (можно несколько адресов через запятую)", vals.get("MAIL_TO") or user)
    vals["MAIL_TO"] = ",".join(a.strip() for a in to.split(",") if a.strip())
    ok(f"заявки будут приходить на {vals['MAIL_TO']}")


# ---------- Сервис ----------
def restart_and_test(vals):
    head("3. Сохраняю настройки и перезапускаю сервис заявок")
    if subprocess.run(["systemctl", "cat", "dumskaya-lead"], capture_output=True).returncode != 0:
        bad("Сервис заявок ещё не установлен — сначала выложите сайт (npm run deploy), потом запустите настройку снова.")
        return
    say("  Нужен пароль sudo пользователя deploy (тот же, что при выкладке; символы не видны).")
    if subprocess.run(["sudo", "systemctl", "restart", "dumskaya-lead"]).returncode != 0:
        bad("Не удалось перезапустить сервис. Настройки сохранены — перезапуск можно повторить: sudo systemctl restart dumskaya-lead")
        return
    health = None
    for _ in range(10):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen("http://127.0.0.1:8095/api/lead/health", timeout=3) as r:
                health = json.loads(r.read()); break
        except Exception:  # noqa: BLE001
            pass
    if not health:
        bad("Сервис не отвечает. Последние строки журнала:")
        subprocess.run(["sudo", "journalctl", "-u", "dumskaya-lead", "-n", "15", "--no-pager"])
        return
    ok(f"сервис работает: бот — {'да, получателей заявок: ' + str(health.get('recipients')) if health.get('telegram') else 'нет'}, "
       f"почта — {'да' if health.get('email') else 'нет'}")
    if not (health.get("telegram") or health.get("email")):
        note("Ни Telegram, ни почта не настроены — заявки только сохраняются в файл leads.jsonl.")
        return

    head("4. Пробная заявка — тем же путём, что и форма на сайте")
    mode = open(os.path.join(APP, "mode")).read().strip() if os.path.exists(os.path.join(APP, "mode")) else "preview"
    url = "http://127.0.0.1:8088/api/lead" if mode == "preview" else "http://127.0.0.1:8095/api/lead"
    lead = {"name": "Проверка настройки", "contact": "заявка отправлена с сервера",
            "message": "Это пробная заявка: если вы её видите, форма на сайте работает.",
            "model": "", "lang": "ru", "page": "/contact-studio-interior-design-bratislava-vienna"}
    req = urllib.request.Request(url, data=json.dumps(lead).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            res = json.loads(r.read())
    except urllib.error.HTTPError as e:
        res = {"ok": False, "code": e.code}
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "error": str(e)}
    if res.get("ok"):
        ok("заявка принята — проверьте Telegram и почту (письмо может попасть в «Спам» — отметьте «Не спам»)")
    else:
        bad(f"заявка не доставлена ({res}). Журнал сервиса:")
        subprocess.run(["sudo", "journalctl", "-u", "dumskaya-lead", "-n", "15", "--no-pager"])


def main():
    if not sys.stdin.isatty():
        sys.exit("Запускайте в терминале: ssh -t <сервер> 'python3 ~/dumskaya/deploy/lead_setup.py' (или с Mac: npm run leads)")
    say(f"{B}Настройка заявок с сайта dumskaya-design.com{X}")
    say(f"{D}Enter на любом вопросе — оставить как есть. Токен и пароль на экран не выводятся.{X}")
    lines, vals = read_env()
    setup_telegram(vals)
    setup_mail(vals)
    write_env(lines, vals)
    global SAVED
    SAVED = True
    ok(f"настройки записаны в {ENV} (доступ только у пользователя {getpass.getuser()})")
    restart_and_test(vals)
    say(f"\n{B}Готово.{X} Повторить или поменять настройки: с Mac — npm run leads")
    if vals.get("TELEGRAM_BOT_TOKEN"):
        say("Дальше: попросите Ирину открыть бота и нажать «Старт» — вам придёт запрос с кнопками, нажмите «Дизайнер студии».\n"
            "  Товары магазина студии закрепятся за ней автоматически: заявки на них придут ей, вам — копия.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("\nОстановлено." + (" Настройки уже сохранены." if SAVED else " Ничего не сохранено."))
