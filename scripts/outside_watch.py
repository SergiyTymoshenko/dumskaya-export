#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сторож сайта СНАРУЖИ — запускается на GitHub (.github/workflows/site-watch.yml) примерно раз в 5 минут.
Нужен на случай, когда сервер сайта выключился целиком: тогда его собственный сторож (deploy/site_monitor.py)
и бот молчат вместе с ним. Отправляет от имени того же бота студии (бот на сервере это не мешает).

За один запуск: до трёх попыток открыть сайт (с паузой 20 с). Не открылся в двух запусках подряд (~10 минут) —
сообщение разработчику (если сам сервер жив — через ~30 минут: о коротком падении уже сообщил сторож на сервере): что не так и жив ли сам сервер (отвечают ли его порты 22/80/443 — так видно, лежит
только сайт или весь сервер). Пока не починится — напоминание раз в 3 часа; когда снова открывается — сообщение.
Состояние между запусками — файл в папке .watch (её сохраняет кеш GitHub Actions).

Настройки — переменные окружения: TELEGRAM_BOT_TOKEN (секрет репозитория), BOT_OWNER_ID (по умолчанию 633722),
SITE_URL, SITE_SERVER. --test — только проверочное сообщение в бот.
Только стандартная библиотека Python 3."""
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
OWNER = os.environ.get("BOT_OWNER_ID", "").strip() or "633722"
URL = os.environ.get("SITE_URL", "").strip() or "https://dumskaya-design.com/"
SERVER = os.environ.get("SITE_SERVER", "").strip() or "62.238.124.237"
STATE = os.path.join(os.environ.get("WATCH_DIR", ".watch"), "state.json")
TG_API = os.environ.get("TG_API", "https://api.telegram.org")
MARKER = "DUMSKAYA"
RUNS_DEAD, RUNS_ALIVE = 2, 6     # запусков подряд до сообщения: сервер молчит (~10 мин) / сервер жив (~30 мин —
                                 # тогда о падении уже сообщил сторож на самом сервере, снаружи — только если затянулось)
REMIND = 3 * 3600
TRIES, PAUSE = 3, int(os.environ.get("WATCH_PAUSE", "20"))


def tg(text):
    data = urllib.parse.urlencode({"chat_id": OWNER, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(f"{TG_API}/bot{TOKEN}/sendMessage", data=data, timeout=20) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:  # noqa: BLE001
        print("telegram:", type(e).__name__, e)
        return False


def check():
    req = urllib.request.Request(URL, headers={"User-Agent": "dumskaya-outside-watch/1.0", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read(400_000).decode("utf-8", "replace")
            if r.status != 200:
                return False, f"ответ {r.status}"
            return (True, "") if MARKER in body else (False, "открывается чужая или пустая страница")
    except urllib.error.HTTPError as e:
        return False, f"ошибка {e.code}"
    except urllib.error.URLError as e:
        r = str(e.reason)
        if "timed out" in r:
            return False, "не ответил за 25 секунд"
        if "refused" in r.lower():
            return False, "соединение отклонено"
        if "CERTIFICATE" in r.upper() or "SSL" in r.upper():
            return False, f"ошибка HTTPS: {r}"
        return False, r
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def port_open(p):
    try:
        with socket.create_connection((SERVER, p), timeout=6):
            return True
    except OSError:
        return False


def minutes(sec):
    m = int(sec // 60)
    return f"{m} мин" if m < 120 else f"{m // 60} ч {m % 60} мин"


def load():
    try:
        return json.load(open(STATE))
    except (OSError, ValueError):
        return {}


def save(st):
    """Записывает состояние; если оно изменилось — помечает, что кеш нужно сохранить (шаг cache/save)."""
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    if st != load():
        json.dump(st, open(STATE, "w"))
        open(os.path.join(os.path.dirname(STATE), "changed"), "w").close()


def main():
    try:                                   # пометка «состояние изменилось» — только от этого запуска
        os.remove(os.path.join(os.path.dirname(STATE), "changed"))
    except OSError:
        pass
    if not TOKEN:
        print("Секрет TELEGRAM_BOT_TOKEN не задан в настройках репозитория — проверка пропущена.")
        return 0
    if "--test" in sys.argv:
        ok, why = check()
        state = "сайт сейчас открывается" if ok else f"сайт сейчас НЕ открывается: {why}"
        sent = tg(f"✅ Сторож сайта снаружи (GitHub) подключён: проверяет {URL} примерно раз в 5 минут; "
                  f"если сайт не откроется ~10 минут — придёт сообщение. Сейчас: {state}.")
        print("тестовое сообщение:", "отправлено" if sent else "НЕ отправлено (проверьте токен и что в боте нажат «Старт»)")
        return 0 if sent else 1
    st, now = load(), time.time()
    ok, why = check()
    for _ in range(TRIES - 1):
        if ok:
            break
        time.sleep(PAUSE)
        ok, why = check()
    print(f"{URL}: {'открывается' if ok else 'НЕ открывается — ' + why}")
    if ok:
        if st.get("alerted"):
            tg(f"🟢 <b>Сайт снова открывается</b> (проверка снаружи, GitHub) — не открывался ~{minutes(now - st['since'])}.")
        save({})
        return 0
    st["runs"] = st.get("runs", 0) + 1
    st.setdefault("since", now)
    if st.get("alerted") and now - st.get("reminded", now) < REMIND:
        save(st)
        return 0
    alive = [p for p in (22, 80, 443) if port_open(p)]
    if st["runs"] < (RUNS_ALIVE if alive else RUNS_DEAD):
        save(st)
        return 0
    if alive:
        where = (f"Сервер сайта на связи (отвечают порты {', '.join(map(str, alive))}) — лежит сам сайт; "
                 "от бота на сервере должно было прийти сообщение с причиной. Если его нет — не работает и сервис бота.")
    else:
        where = ("Сервер сайта не отвечает вообще (ни SSH, ни веб-порты) — он выключен или недоступен по сети, "
                 "бот на нём тоже молчит. Проверьте сервер в панели Hetzner: включён ли, нет ли сообщений о сбое.")
    if st.get("alerted"):
        text = f"🔴 Сайт всё ещё не открывается (проверка снаружи) — ~{minutes(now - st['since'])}: {why}.\n{where}"
    else:
        text = f"🔴 <b>Сайт не открывается</b> — проверка снаружи (GitHub), ~{minutes(now - st['since'])}.\n{URL} — {why}.\n\n{where}"
    if tg(text):
        st["alerted"] = st.get("alerted") or now
        st["reminded"] = now
    save(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
