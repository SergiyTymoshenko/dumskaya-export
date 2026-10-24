#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Настройка отправки заявок с сайта в Telegram и на почту — по шагам, с проверкой каждого шага.
Запускается на сервере от пользователя deploy (с Mac:  npm run leads):
    python3 ~/dumskaya/deploy/lead_setup.py

Что делает:
  1) Telegram: проверяет токен бота студии, записывает ID разработчика, бот пишет вам пробное сообщение;
  2) почта: проверяет вход в Gmail по паролю приложения;
  3) перевод сообщений заказчиков и переписки — по порядку (решено 25.10.2026): модели ChatGPT по подписке (API на этом
     сервере), платный ChatGPT, Claude. Из проекта УЧЕТ на этом сервере (вы указываете путь к его файлу настроек, мастер
     берёт из него только переменные OpenAI / ChatGPT; решено 24.10.2026) или вручную; каждый проверяет пробным переводом;
  4) записывает ~/dumskaya/lead.env (доступ только у владельца), перезапускает сервис заявок
     (нужен пароль sudo) и отправляет пробную заявку тем же путём, что и форма на сайте.
Только перевод (с Mac — npm run translate):  python3 ~/dumskaya/deploy/lead_setup.py --translate
Токен и пароль на экран не выводятся. Enter на любом вопросе — оставить как есть.
"""
import getpass
import json
import os
import re
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


# ---------- Перевод ----------
# Порядок (решено 25.10.2026): 1) модели ChatGPT по подписке — API (шлюз) на этом сервере, 2) платный API ChatGPT,
# 3) Claude (Anthropic). Не ответил сервис или кончился лимит — тот же текст переводит следующий (translate.py).
SUB_VARS = ("OPENAI_SUB_BASE_URL", "OPENAI_SUB_API_KEY", "OPENAI_SUB_MODEL")
PAID_VARS = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL")
TR_VARS = SUB_VARS + PAID_VARS + ("ANTHROPIC_API_KEY", "TRANSLATE_MODEL", "DEEPL_API_KEY", "TRANSLATE_ORDER", "TRANSLATE_PROVIDER")
OPENAI_PREFER = ("gpt-5.4-mini", "gpt-5-mini", "gpt-4.1-mini", "gpt-4o-mini")
NAME = r"(?:OPENAI|CHATGPT)[A-Z0-9_]*"
ROLE = r"(API_KEY|KEY|TOKEN|SECRET|API_BASE|BASE_URL|BASE|URL|ENDPOINT|HOST|MODEL)"
TIER_NAME = {"sub": "ChatGPT по подписке", "openai": "платный ChatGPT", "claude": "Claude", "deepl": "DeepL"}


def host_of(url):
    return re.sub(r"^https?://", "", url or "").split("/")[0].split("@")[-1]


def check_translate(env, tier=None):
    """Пробный перевод с этими настройками (без записи в lead.env); tier — проверить только этот сервис.
    (получилось ли, перевод или причина)."""
    sys.path.insert(0, os.path.join(APP, "deploy"))
    try:
        import translate
    except ImportError:
        return False, "на сервере ещё нет translate.py — сначала выложите сайт (npm run deploy)"
    saved = {k: os.environ.pop(k, None) for k in TR_VARS}
    os.environ.update({k: v for k, v in env.items() if v and k in TR_VARS})
    if tier:
        os.environ["TRANSLATE_ORDER"] = tier
    if hasattr(translate, "reset_pauses"):
        translate.reset_pauses()
    try:
        r = translate.to_russian("Hello! I would like a quote for a sofa with delivery to Vienna.")
        if r and any("Ѐ" <= c <= "ӿ" for c in r[1]):
            return True, f"«{r[1][:90]}»"
        return False, f"сервис ответил без перевода: {r}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:300]
    finally:
        for k in TR_VARS:
            os.environ.pop(k, None)
        os.environ.update({k: v for k, v in saved.items() if v})
        if hasattr(translate, "reset_pauses"):
            translate.reset_pauses()


def parse_env(text):
    """Только переменные OpenAI / ChatGPT из указанного файла настроек: .env (KEY=VALUE, export KEY=VALUE),
    systemd (Environment=…), docker compose (KEY: value, - KEY=value). Остальное в файле не читается в настройки,
    значения на экран не выводятся."""
    out = {}
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        if ln.startswith("Environment="):
            for m in re.finditer(r'"?(' + NAME + r')=([^"\s]*)"?', ln[len("Environment="):]):
                out.setdefault(m.group(1), m.group(2))
            continue
        m = re.match(r"(?:export\s+|-\s*)?(" + NAME + r")\s*[=:]\s*(.*)$", ln)
        if m:
            v = re.sub(r"\s+#.*$", "", m.group(2)).strip().strip("\"'")
            if v:
                out.setdefault(m.group(1), v)
    return out


def read_project_env(path):
    """Файл настроек проекта УЧЕТ по пути, который указали вы: обычным чтением, а если файл чужого пользователя — через
    sudo cat (только чтение). Возвращает переменные OpenAI / ChatGPT из него."""
    path = os.path.expanduser(path.strip())
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read(256 * 1024)
    except PermissionError:
        r = subprocess.run(["sudo", "cat", "--", path], capture_output=True, text=True)
        if r.returncode != 0:
            raise OSError(r.stderr.strip() or "не удалось прочитать файл") from None
        text = r.stdout
    return parse_env(text)


def groups(env):
    """Переменные — по наборам: CHATGPT_SUB_BASE_URL + CHATGPT_SUB_API_KEY → набор CHATGPT_SUB {адрес, ключ}.
    Возвращает [(имя набора, {"key", "base", "model"})]."""
    g = {}
    for k, v in env.items():
        m = re.match(r"^(.*?)_?" + ROLE + r"(?:_[A-Z0-9_]*)?$", k)
        if not m:
            continue
        role = m.group(2)
        kind = "key" if role in ("API_KEY", "KEY", "TOKEN", "SECRET") else "model" if role == "MODEL" else "base"
        g.setdefault(m.group(1) or k, {}).setdefault(kind, v)
    return [(n, x) for n, x in g.items() if x.get("key") or x.get("base")]


def list_models(base, key):
    """(адрес с /v1 или без — какой ответил, модели) — или (base, []) если список моделей не получить."""
    tries = [base.rstrip("/")]
    if not tries[0].endswith("/v1"):
        tries.append(tries[0] + "/v1")
    for b in tries:
        try:
            req = urllib.request.Request(b + "/models", headers={"Authorization": "Bearer " + key} if key else {})
            with urllib.request.urlopen(req, timeout=20) as r:
                return b, [m.get("id", "") for m in json.loads(r.read()).get("data", []) if m.get("id")]
        except Exception:  # noqa: BLE001
            continue
    return base.rstrip("/"), []


def pick_model(ids):
    """Модель для перевода: первая из предпочтительных (небольшие и быстрые), иначе любая mini, иначе первая GPT."""
    for m in OPENAI_PREFER:
        if m in ids:
            return m
    minis = sorted((i for i in ids if i.startswith("gpt-") and "mini" in i), reverse=True)
    gpts = sorted((i for i in ids if i.startswith("gpt-")), reverse=True)
    return (minis or gpts or ids or [OPENAI_PREFER[0]])[0]


def try_tier(tier, key, base, model, where):
    """Проверить подписку (sub) или платный ChatGPT (openai): переменные для lead.env или None."""
    if tier == "openai":
        base = base or "https://api.openai.com/v1"
    base, ids = list_models(base, key)
    model = model or pick_model(ids)
    if tier == "sub":
        mvar, env = "OPENAI_SUB_MODEL", {"OPENAI_SUB_BASE_URL": base, "OPENAI_SUB_API_KEY": key, "OPENAI_SUB_MODEL": model}
    else:
        mvar, env = "OPENAI_MODEL", {"OPENAI_API_KEY": key, "OPENAI_MODEL": model,
                                     "OPENAI_BASE_URL": "" if host_of(base) == "api.openai.com" else base}
    say(f"  Проверяю {TIER_NAME[tier]}: модель {model}" + ("" if host_of(base) == "api.openai.com" else f", адрес {host_of(base)}") + "…")
    good, info = check_translate(env, tier)
    if not good:
        bad(f"{TIER_NAME[tier]} ({where}) не перевёл: {info}")
        if ids:
            say(f"  {D}Модели на этом адресе: {', '.join(ids[:20])}{X}")
        m = ask("Другая модель — впишите её название (Enter — пропустить)")
        if not m:
            return None
        env[mvar] = m
        good, info = check_translate(env, tier)
        if not good:
            bad(f"и с моделью {m} не перевёл: {info}")
            return None
    ok(f"{TIER_NAME[tier]} переводит: {info}")
    return env


def from_project(path):
    """Подписка и платный ChatGPT из файла настроек проекта УЧЕТ. Шлюз (адрес не api.openai.com) — подписка,
    ключ api.openai.com — платный. Возвращает, что нашлось: {"sub": env, "openai": env}."""
    env = read_project_env(path)
    if not env:
        raise OSError("в этом файле нет переменных OpenAI / ChatGPT — проверьте путь")
    say(f"  В файле: {', '.join(env)}")
    found = {}
    for name, g in groups(env):
        gate = bool(g.get("base")) and host_of(g["base"]) != "api.openai.com"
        tier = "sub" if gate else "openai"
        if tier in found or (tier == "openai" and not g.get("key")):
            continue
        say(f"  {name}: " + (f"адрес {host_of(g['base'])} — считаю API подписки ChatGPT" if gate else "ключ api.openai.com — платный ChatGPT"))
        got = try_tier(tier, g.get("key", ""), g.get("base", ""), g.get("model", ""), path)
        if got:
            found[tier] = got
    return found


def setup_translate(vals, step="3"):
    head(f"{step}. Перевод: сообщения заказчиков, переписка в кабинете проекта, названия на языке заказчика")
    say(f"  {D}Порядок: 1) модели ChatGPT по подписке (API на этом сервере), 2) платный ChatGPT, 3) Claude. Не ответил")
    say(f"  или кончился лимит — тот же текст сразу переводит следующий.{X}")
    cur = [t for t, k in (("sub", "OPENAI_SUB_BASE_URL"), ("openai", "OPENAI_API_KEY"), ("claude", "ANTHROPIC_API_KEY"), ("deepl", "DEEPL_API_KEY"))
           if vals.get(k)]
    if cur:
        say("  Сейчас: " + " → ".join(TIER_NAME[t] for t in cur) + ".")
    say(f"  {D}1 — из проекта УЧЕТ: путь к его файлу настроек на этом сервере (например, /home/<пользователь>/<проект>/.env).")
    say("      Из файла берутся только переменные OpenAI / ChatGPT, файл не меняется, ключи на экран не выводятся;")
    say("      если файл чужого пользователя — спросит пароль sudo; адрес API подписки, если его там нет, — спросит;")
    say("  2 — вписать вручную: адрес API подписки, ключ платного ChatGPT (sk-…), ключ Claude (sk-ant-…);")
    say(f"  «-» — выключить перевод; Enter — оставить как есть.{X}")
    choice = ask("Ваш выбор", "" if cur else "1")
    if not choice:
        note("Перевод не изменён." if cur else "Перевод не включён — заявки приходят как есть.")
        return
    if choice == "-":
        for k in TR_VARS:
            vals[k] = ""
        note("Перевод выключен.")
        return
    found = {}
    if choice == "1":
        for attempt in range(3):
            path = ask("Путь к файлу настроек проекта УЧЕТ (Enter — вписать вручную)", vals.get("TRANSLATE_SOURCE") or "")
            if not path:
                break
            try:
                found = from_project(path)
            except OSError as e:
                bad(f"не получилось: {e}")
                continue
            vals["TRANSLATE_SOURCE"] = path
            break
    old_gate = vals.get("OPENAI_BASE_URL") and host_of(vals["OPENAI_BASE_URL"]) != "api.openai.com"
    if "sub" not in found:                      # подписки в файле нет — адрес вручную (или прежний шлюз из lead.env)
        note("API подписки ChatGPT не найден в настройках." if choice == "1" else "Подписка ChatGPT.")
        dflt = vals.get("OPENAI_SUB_BASE_URL") or (vals.get("OPENAI_BASE_URL") if old_gate else "")
        for attempt in range(3):
            base = ask("Адрес API подписки ChatGPT на этом сервере, например http://127.0.0.1:8317/v1 (Enter — пропустить)", dflt)
            if not base:
                break
            key = ask_secret("Ключ этого API, если он его просит (Enter — без ключа)") or (
                vals.get("OPENAI_SUB_API_KEY") or (vals.get("OPENAI_API_KEY") if old_gate and base == dflt else ""))
            got = try_tier("sub", key, base, vals.get("OPENAI_SUB_MODEL", "") if base == vals.get("OPENAI_SUB_BASE_URL") else "", "ввода")
            if got:
                found["sub"] = got
                break
    if "openai" not in found:
        have = vals.get("OPENAI_API_KEY") and not old_gate
        key = ask_secret("Ключ платного ChatGPT (sk-…)" + (" — Enter: оставить прежний" if have else " — Enter: пропустить"))
        if key:
            got = try_tier("openai", key, "", "", "ввода")
            if got:
                found["openai"] = got
        elif have:
            found["openai"] = {k: vals.get(k, "") for k in PAID_VARS}
    claude = vals.get("ANTHROPIC_API_KEY", "")
    key = ask_secret("Ключ Claude (sk-ant-…) — третьим, запасной" + (" — Enter: оставить прежний" if claude else " — Enter: пропустить"))
    if key:
        good, info = check_translate({"ANTHROPIC_API_KEY": key, "TRANSLATE_MODEL": vals.get("TRANSLATE_MODEL", "")}, "claude")
        if good:
            ok(f"Claude переводит: {info}")
            claude = key
        else:
            bad(f"ключ Claude не сработал: {info}")
    for k in SUB_VARS + PAID_VARS:
        vals[k] = ""
    for env in found.values():
        vals.update(env)
    vals["ANTHROPIC_API_KEY"] = claude
    vals["TRANSLATE_PROVIDER"] = ""                   # прежняя настройка «кто переводит» — теперь порядок
    order = [t for t, k in (("sub", "OPENAI_SUB_BASE_URL"), ("openai", "OPENAI_API_KEY"), ("claude", "ANTHROPIC_API_KEY"), ("deepl", "DEEPL_API_KEY"))
             if vals.get(k)]
    if order:
        ok("Порядок перевода: " + " → ".join(TIER_NAME[t] for t in order))
        if "sub" not in order:
            note("Подписка ChatGPT не подключена — переводят платные модели. Запустите ещё раз, когда будет адрес её API.")
    else:
        note("Перевод не включён. Запустите ещё раз: с Mac — npm run translate")


# ---------- Сервис ----------
def restart_and_test(vals, step="4", message="Это пробная заявка: если вы её видите, форма на сайте работает."):
    head(f"{step}. Сохраняю настройки и перезапускаю сервис заявок")
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

    head(f"{int(step) + 1}. Пробная заявка — тем же путём, что и форма на сайте")
    mode = open(os.path.join(APP, "mode")).read().strip() if os.path.exists(os.path.join(APP, "mode")) else "preview"
    url = "http://127.0.0.1:8088/api/lead" if mode == "preview" else "http://127.0.0.1:8095/api/lead"
    lead = {"name": "Проверка настройки", "contact": "заявка отправлена с сервера",
            "message": message,
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
    global SAVED
    if "--translate" in sys.argv:                  # только перевод: с Mac — npm run translate
        setup_translate(vals, step="1")
        write_env(lines, vals)
        SAVED = True
        ok(f"настройки записаны в {ENV}")
        msg = ("Hello! This is a test request. If a Russian translation is shown below, translation of client "
               "messages works." if any(vals.get(k) for k in ("OPENAI_SUB_BASE_URL", "OPENAI_API_KEY", "DEEPL_API_KEY", "ANTHROPIC_API_KEY")) else
               "Это пробная заявка: перевод выключен.")
        restart_and_test(vals, step="2", message=msg)
        say(f"\n{B}Готово.{X} Поменять ключ или выключить перевод: с Mac — npm run translate")
        return
    setup_telegram(vals)
    setup_mail(vals)
    setup_translate(vals)
    write_env(lines, vals)
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
