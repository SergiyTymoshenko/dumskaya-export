#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Учёт проектов студии — для разработчика и дизайнера (кнопка «Студия» в боте, страница crm_app.html).

Проект: номер по внутреннему учёту, название, заказчик, город, площадь, тариф, сумма договора (в евро), статус.
Операции проекта (вся история):
  • оплата заказчика — сумма, валюта, дата, способ;
  • бонус («откат») — от подрядчика (с привязкой к нему и этапу) или от поставщика, фабрики;
  • перепродажа — студия посредник: закупка и продажа, доход — разница.
Подрядчики в проекте — с этапами работ: сумма заказа и бонус студии с неё (процент, по умолчанию 10 %, сумма,
«не платит» или «пока неизвестно»). Долг подрядчика = ожидаемые бонусы − полученные бонусы от него в этом проекте.
Подрядчик в проекте — студии (Ирины) или заказчика (side='client', решено 27.10.2026): прораб заказчика обычно бонусов
не платит — у его этапов бонус «не платит», в его кабинете о бонусах студии ничего нет (если Ирина всё же укажет бонус —
как у всех).
Суммы в евро, гривне, долларе, злотом; в евро — по курсу центробанка на дату (fx.py) или по курсу, введённому вручную.
Баланс проекта: договор − оплаты заказчика по договору. Доход студии: оплаты (договор и доп. услуги) + полученные бонусы
+ наценка на товарах и перепродаже.
Товары, которые заказчик покупает через студию (orders): цена для заказчика, закупка (заказчик её не видит), авансы,
планируемая и фактическая поставка; доставлен и оплачен полностью — «Выполнено». Оплата за товар — не доход студии,
доход — наценка (продажа − закупка).
Доп. услуги (services): разовые (чертежи) и помесячные (авторское сопровождение, 1000 €/мес) — начисления и оплаты,
месяцы закрываются оплатами по порядку.
Ещё: заказчики (телефон, почта, как удобнее связаться; у проекта — основной и ещё несколько), файлы проекта (обмерный план,
опросник, до, визуализации, документация, после, другое) — в ~/dumskaya/crm/files, ссылки на них подписаны и действуют
12 часов; удалённые файлы 30 дней лежат в ~/dumskaya/crm/trash.
Кабинет заказчика, подрядчика и его работников в боте, разговоры и права на документы — crm_portal.py.

Данные — ~/dumskaya/crm.db (SQLite). Резервные копии (на сервере, 7 дней) — backups.py.
Только стандартная библиотека Python 3.

   python3 crm.py --backup-now     — архив данных сейчас (то же, что python3 backups.py --now)
"""
import calendar
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone

try:
    from fx import CODES, CURRENCIES
except ImportError:  # pragma: no cover
    CURRENCIES, CODES = [("EUR", "€", "евро")], ["EUR"]

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bratislava")
except Exception:  # noqa: BLE001
    TZ = timezone(timedelta(hours=1))

APP = os.path.expanduser("~/dumskaya")
CRM_DB = os.environ.get("CRM_DB", os.path.join(APP, "crm.db"))
FILES_DIR = os.environ.get("CRM_FILES", os.path.join(APP, "crm", "files"))
BACKUP_DIR = os.environ.get("BACKUP_DIR", os.path.join(APP, "backups"))
BOT_DB = os.environ.get("BOT_DB", os.path.join(APP, "bot.db"))
TRASH_KEEP = 30                         # удалённые файлы проектов лежат в корзине 30 дней
DEFAULT_PCT = 10                        # бонус студии с заказа подрядчика по умолчанию, %
FILE_MAX = 60 * 1024 * 1024            # один файл — до 60 МБ
MIN_FREE = 2 * 1024 ** 3               # оставлять на диске сервера хотя бы 2 ГБ (сервер общий)
LINK_HOURS = 12

STATUSES = [("active", "В работе"), ("paused", "На паузе"), ("done", "Завершён"), ("cancelled", "Отменён")]
KINDS = {"payment": "Оплата заказчика", "commission": "Бонус", "resale": "Перепродажа"}
FILE_CATS = [("measure", "Обмерный план"), ("brief", "Опросник"), ("before", "До"), ("plan", "Планировочные решения"),
             ("visual", "Визуализации"), ("docs", "Документация"), ("after", "После"), ("other", "Другое")]
PHOTO_CATS = ("before", "visual", "after")
# служебные разделы файлов: фото товаров (в карточке товара) и вложения переписки — в разделах «Файлы проекта» их нет
EXTRA_CATS = [("goods", "Фото товаров"), ("chat", "Из переписки"), ("work", "От подрядчиков")]
# что видно в кабинете: заказчику — всё, кроме «Другое» (там бывают счета с закупкой); подрядчику — обмеры, фото,
# визуализации и документация (опросник заказчика — нет)
CLIENT_CATS = ("measure", "brief", "before", "plan", "visual", "docs", "after")
CONTRACTOR_CATS = ("measure", "before", "plan", "visual", "docs", "after")
# версии документов (решено 25.10.2026): планировочные решения — «Вариант 1, 2…», визуализации — «Первый вариант, Правка 1,
# Правка 2…» (раунд — весь раздел; сколько правок входит в пакет — «Пакеты» в ⚙︎); в остальных разделах версии у документа
# с одним названием (чертежи технолога: версия 1, 2…). Фото и визуализации — по помещениям.
ROUND_CATS = ("plan", "visual")
# порядок файлов в разделе (решено 27.10.2026): Ирина передвигает файлы и фото — files.pos (1, 2, 3…); так — в «Студии», в кабинетах
# и в листании фото. Файлы, которые не передвигали, — по порядковому номеру в имени файла (решено 27.10.2026, вечер):
# «08. План демонтажа» раньше «10. План монтажа…», «13-14. …» — после «12. …»; без номера — по имени (IMG_0012 раньше IMG_0103).
# В разделе, который Ирина расставила, новые файлы — в конце (по номеру между собой); «По номерам» — снова по номерам.
def _nat(s):
    return [(0, int(t), "") if t.isdigit() else (1, 0, t) for t in re.split(r"(\d+)", (s or "").strip().lower()) if t]


def file_key(f):
    return (f.get("pos") is None, f.get("pos") or 0, _nat(f.get("name") or f.get("title")), f.get("id") or 0)


def sort_files(rows):
    return sorted(rows, key=file_key)


# о новых файлах студии — сообщение заказчику (решено 27.10.2026): обмерный план, планировки, визуализации, документация,
# «После»; о фото «До» (старые фото объекта), «Другое» (заказчик не видит) и опроснике (его заполняет сам заказчик) — нет.
# Несколько файлов подряд — одно сообщение: ждём, пока FILE_NOTE_QUIET секунд не будет новых (но не дольше FILE_NOTE_MAX)
NOTIFY_CATS = ("measure", "plan", "visual", "docs", "after")
FILE_NOTE_QUIET = 90
FILE_NOTE_MAX = 600
ROOM_CATS = ("before", "visual", "after")
# стадия проекта (решено 25.10.2026): первые семь — проект дизайна; дальше — если заказчик продолжил со студией
STAGES = [("measure", "Замер"), ("plan", "Разработка планировочных решений"), ("plan_ok", "Согласование планировочных решений"),
          ("concept", "Разработка концепции"), ("visual", "Разработка 3D-визуализаций"), ("visual_ok", "Согласование визуализаций"),
          ("docs", "Разработка технической документации"), ("repair", "Ремонтные работы"),
          ("furniture_ok", "Согласование мебельных чертежей с производством"), ("furniture_make", "Изготовление мебели"),
          ("furniture_install", "Установка мебели"), ("soft", "Комплектация мягкой мебелью"), ("done", "Завершён")]
DESIGN_STAGES = ("measure", "plan", "plan_ok", "concept", "visual", "visual_ok", "docs")
# пакеты: цена за м² для пересчёта при смене пакета и сколько правок визуализаций входит (по сайту; меняется в ⚙︎)
TARIFF_INFO = {"Экспресс": {"rate": 20, "revisions": 1}, "Мебель": {"rate": 35, "revisions": 1}, "Базовый": {"rate": 35, "revisions": 1},
               "Премиум": {"rate": 50, "revisions": 2}, "Премиум+": {"rate": 70, "revisions": 2}}
ORDER_STATUSES = [("ordered", "Заказан"), ("delivered", "Доставлен — ждёт доплаты"), ("done", "Выполнено"), ("cancelled", "Отменён")]
SERVICE_KINDS = [("once", "Разовая"), ("monthly", "Помесячно")]
PROJECT_PEOPLE_MAX = 10              # заказчиков у проекта (обычно до 5)
REMIND_GRACE = 7                     # не оплачено через 7 дней после срока — второе напоминание
CONTACT_PREFS = ["Звонок", "WhatsApp", "Telegram", "Viber", "E-mail", "SMS"]
# заявки: при получении — что это (заявка, реклама или предложение сотрудничества, спам, игнорировать), дальше у настоящих —
# в работе, стала проектом, закрыта (решено 24.10.2026)
LEAD_STATUSES = [("new", "Новая"), ("lead", "Заявка"), ("work", "В работе"), ("project", "Стала проектом"), ("closed", "Закрыта"),
                 ("ad", "Реклама, сотрудничество"), ("spam", "Спам"), ("ignore", "Игнорировать")]
LEAD_TRIAGE = ["lead", "ad", "spam", "ignore"]          # «что это» — при получении, и кнопками в сообщении бота
LEAD_FLOW = ["work", "project", "closed"]               # «как идёт» — у настоящих заявок
LEAD_HIDDEN = ["ad", "spam", "ignore"]                  # не заявки: во «Все» не попадают, у каждого своя кнопка
TEST_CONTACTS = ("заявка отправлена с сервера", "test@example.com")   # пробные заявки мастера настройки и проверки
LEADS_ARCHIVE_DAYS = 30             # заявки, пришедшие до «Студии»: за 30 дней — «В работе», старше — «Закрыта»
LEADS_TRASH_DAYS = 30               # удалённая заявка 30 дней в «Удалённых» (можно вернуть), потом имя, контакт и текст стираются
PAY_METHODS = ["Банковский перевод", "Наличные", "Карта", "Другое"]
DEFAULTS = {
    "tariffs": ["Экспресс", "Мебель", "Базовый", "Премиум", "Премиум+", "Авторское сопровождение", "Индивидуальный"],
    "trades": ["Прораб", "Мебельщик", "Шторница", "Кондиционерщик", "Двери", "Окна", "Электрик", "Сантехник",
               "Плиточник", "Маляр", "Полы", "Свет", "Камень и столешницы", "Стекло и зеркала", "Другое"],
    "commission_cats": ["Мебель", "Шторы", "Свет", "Кухня", "Сантехника", "Двери", "Окна", "Отделочные материалы",
                        "Техника", "Декор", "Другое"],
    # что поставляют поставщики (плитка, свет, полы, сантехника…) — поставщик работает в проекте как подрядчик (решено 24.10.2026)
    "supply_cats": ["Плитка", "Свет", "Напольные покрытия", "Сантехника", "Обои и краски", "Двери", "Окна", "Кухни", "Мебель",
                    "Бытовая техника", "Шторы и текстиль", "Камень и столешницы", "Стекло и зеркала", "Декор", "Другое"],
    # исполнители, которым платит студия (замерщик, чертёжник, 3D-визуализатор): пишет им только Ирина (решено 24.10.2026)
    "hired_cats": ["Замерщик", "Чертёжник", "3D-визуализатор", "Другое"],
    # помещения — группы фото и визуализаций (решено 25.10.2026); порядок — как фото в проектах на сайте
    "rooms": ["Гостиная-кухня", "Гостиная", "Кухня", "Хозяйская спальня", "Санузел хозяев", "Кабинет", "Детская",
              "Гостевая спальня", "Гостевой санузел", "Гардеробная", "Постирочная", "Прихожая", "Балкон, терраса"],
}
CONTRACTOR_KINDS = [("", "Подрядчик (работы)"), ("supplier", "Поставщик (материалы)"), ("hired", "Исполнитель студии (платит студия)")]

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT, email TEXT, messenger TEXT,
  contact_pref TEXT, city TEXT, note TEXT, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, title TEXT NOT NULL, client_id INTEGER, city TEXT, country TEXT,
  address TEXT, area REAL, tariff TEXT, total_eur REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'active',
  started TEXT, finished TEXT, note TEXT, created_by TEXT, created TEXT, updated TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS projects_number ON projects(number) WHERE number IS NOT NULL AND number != '';
CREATE TABLE IF NOT EXISTS ops (            -- операции проекта; у перепродажи amount — продажа, buy — закупка
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, kind TEXT NOT NULL, day TEXT NOT NULL,
  title TEXT, category TEXT, method TEXT, counterparty TEXT,
  amount REAL NOT NULL, currency TEXT NOT NULL, rate REAL NOT NULL, rate_src TEXT, amount_eur REAL NOT NULL,
  buy REAL, buy_currency TEXT, buy_rate REAL, buy_rate_src TEXT, buy_eur REAL,
  note TEXT, created_by TEXT, created TEXT, updated TEXT,
  link_id INTEGER, stage_id INTEGER);         -- бонус от подрядчика проекта (project_contractors) и за какой этап
CREATE INDEX IF NOT EXISTS ops_project ON ops(project_id);
CREATE INDEX IF NOT EXISTS ops_day ON ops(day);
CREATE TABLE IF NOT EXISTS contractors (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, trade TEXT, company TEXT, phone TEXT, email TEXT,
  contact_pref TEXT, city TEXT, note TEXT, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS project_contractors (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, contractor_id INTEGER NOT NULL, trade TEXT,
  note TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS stages (         -- этапы работ подрядчика в проекте: сумма заказа и бонус студии с неё
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, link_id INTEGER NOT NULL, title TEXT, day TEXT,
  amount REAL NOT NULL DEFAULT 0, currency TEXT NOT NULL, rate REAL NOT NULL, rate_src TEXT, amount_eur REAL NOT NULL DEFAULT 0,
  pct REAL, commission REAL, commission_eur REAL,   -- commission NULL — бонус пока неизвестен
  note TEXT, created_by TEXT, created TEXT, updated TEXT);
CREATE INDEX IF NOT EXISTS stages_link ON stages(link_id);
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, category TEXT NOT NULL, name TEXT, path TEXT,
  thumb TEXT, mime TEXT, size INTEGER, tg_file_id TEXT, note TEXT, created_by TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS project_stages (    -- стадии проекта: когда какая началась (решено 25.10.2026)
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, stage TEXT NOT NULL, day TEXT NOT NULL, who TEXT, created TEXT);
CREATE INDEX IF NOT EXISTS project_stages_p ON project_stages(project_id, id);
CREATE TABLE IF NOT EXISTS tariff_changes (    -- смена пакета: сумма договора пересчитана (только вверх) или прежняя
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, day TEXT NOT NULL, old_tariff TEXT, new_tariff TEXT,
  old_total REAL, new_total REAL, area REAL, rate REAL, recalc INTEGER, note TEXT, who TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS doc_rounds (        -- вариант планировки или правка визуализаций, которую заказчик согласовал
  project_id INTEGER NOT NULL, category TEXT NOT NULL, ver INTEGER NOT NULL, agreed TEXT, agreed_by TEXT,
  PRIMARY KEY(project_id, category, ver));
CREATE INDEX IF NOT EXISTS files_project ON files(project_id);
CREATE TABLE IF NOT EXISTS file_notes (        -- новые файлы студии, о которых ещё не сообщили заказчику (решено 27.10.2026)
  file_id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, by_tg INTEGER, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS leads (            -- заявки с сайта (в файле leads.jsonl — они же, без статусов)
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, name TEXT, contact TEXT, message TEXT, message_ru TEXT,
  message_lang TEXT, page TEXT, model TEXT, model_name TEXT, lang TEXT, routed TEXT,
  status TEXT NOT NULL DEFAULT 'new', note TEXT, project_id INTEGER, updated TEXT, updated_by TEXT,
  src TEXT UNIQUE, deleted TEXT);            -- src: время + имя + контакт — одна заявка не попадёт дважды (и удалённая не вернётся)
CREATE INDEX IF NOT EXISTS leads_ts ON leads(ts);
CREATE TABLE IF NOT EXISTS project_clients (   -- ещё заказчики проекта (основной — projects.client_id)
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, client_id INTEGER NOT NULL, created TEXT,
  UNIQUE(project_id, client_id));
CREATE TABLE IF NOT EXISTS orders (            -- товар, который заказчик покупает через студию
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, title TEXT NOT NULL, code TEXT, url TEXT, image_url TEXT,
  file_id INTEGER, qty REAL, day TEXT NOT NULL,
  price REAL NOT NULL, currency TEXT NOT NULL, rate REAL NOT NULL, rate_src TEXT, price_eur REAL NOT NULL,
  buy REAL, buy_currency TEXT, buy_rate REAL, buy_rate_src TEXT, buy_eur REAL, supplier TEXT,  -- закупка: заказчик не видит
  planned TEXT, delivered TEXT, cancelled TEXT, note_client TEXT, note TEXT,
  created_by TEXT, created TEXT, updated TEXT);
CREATE INDEX IF NOT EXISTS orders_project ON orders(project_id);
CREATE TABLE IF NOT EXISTS services (          -- доп. услуги: разовые и помесячные (суммы — в евро)
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, title TEXT NOT NULL, kind TEXT NOT NULL,
  amount REAL NOT NULL, start TEXT NOT NULL, months INTEGER, stopped TEXT, cancelled TEXT, note TEXT,
  created_by TEXT, created TEXT, updated TEXT);
CREATE INDEX IF NOT EXISTS services_project ON services(project_id);
CREATE TABLE IF NOT EXISTS invites (           -- одноразовые ссылки в кабинет: заказчику или подрядчику
  token TEXT PRIMARY KEY, kind TEXT NOT NULL, ref_id INTEGER NOT NULL, project_id INTEGER, lang TEXT,
  created_by TEXT, created TEXT, expires TEXT, used_by INTEGER, used TEXT);
CREATE TABLE IF NOT EXISTS crew (              -- работники подрядчика (технолог, установщик…): подключает сам подрядчик
  id INTEGER PRIMARY KEY AUTOINCREMENT, contractor_id INTEGER NOT NULL, name TEXT NOT NULL, position TEXT, phone TEXT,
  tg_id INTEGER, tg_name TEXT, tg_since TEXT, removed TEXT, created_by TEXT, created TEXT, updated TEXT);
CREATE INDEX IF NOT EXISTS crew_contractor ON crew(contractor_id);
CREATE TABLE IF NOT EXISTS project_crew (      -- кто из работников подрядчика на этом объекте (выбирает подрядчик)
  project_id INTEGER NOT NULL, crew_id INTEGER NOT NULL, created_by TEXT, created TEXT, PRIMARY KEY(project_id, crew_id));
CREATE TABLE IF NOT EXISTS assistants (        -- сотрудники студии (ассистент, визуализатор, чертёжник, комплектатор):
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, position TEXT, phone TEXT, email TEXT,   -- добавляет Ирина
  tg_id INTEGER, tg_name TEXT, tg_since TEXT, note TEXT, removed TEXT, created_by TEXT, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS project_assistants (  -- на какие проекты Ирина назначила сотрудника (видит только их, без денег)
  project_id INTEGER NOT NULL, assistant_id INTEGER NOT NULL, created_by TEXT, created TEXT, PRIMARY KEY(project_id, assistant_id));
CREATE TABLE IF NOT EXISTS threads (           -- разговоры проекта: client — студия и заказчики; pc — заказчики и подрядчик
  id INTEGER PRIMARY KEY AUTOINCREMENT,        -- (студия видит); org — студия и подрядчик; worker — студия и работник
  project_id INTEGER NOT NULL, kind TEXT NOT NULL,   -- (подрядчик видит); group — группа, которую собрала студия;
                                                     -- staff — Ирина и сотрудник студии; sgroup — Ирина и сотрудники (видят только они)
  contractor_id INTEGER, crew_id INTEGER, title TEXT, studio_joined TEXT, created_by TEXT, created TEXT, updated TEXT);
CREATE INDEX IF NOT EXISTS threads_project ON threads(project_id);
CREATE TABLE IF NOT EXISTS thread_members (thread_id INTEGER NOT NULL, kind TEXT NOT NULL, ref_id INTEGER NOT NULL,
  PRIMARY KEY(thread_id, kind, ref_id));       -- участники группы: contractor (руководитель) или crew (работник)
CREATE TABLE IF NOT EXISTS thread_read (thread_id INTEGER NOT NULL, tg_id INTEGER NOT NULL, last_id INTEGER NOT NULL,
  PRIMARY KEY(thread_id, tg_id));              -- до какого сообщения прочитано; tg_id 0 — студия
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, author_kind TEXT NOT NULL, author_tg INTEGER,
  author_name TEXT, text TEXT, lang TEXT, tr TEXT, file_id INTEGER, created TEXT NOT NULL, deleted TEXT, thread_id INTEGER);
CREATE INDEX IF NOT EXISTS messages_project ON messages(project_id, id);
CREATE TABLE IF NOT EXISTS chat_read (project_id INTEGER NOT NULL, tg_id INTEGER NOT NULL, last_id INTEGER NOT NULL,
  PRIMARY KEY(project_id, tg_id));             -- из первой версии переписки (переносится в thread_read)
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, who TEXT, action TEXT, entity TEXT, entity_id INTEGER, details TEXT);
"""


class CrmError(Exception):
    """Ошибка, которую можно показать человеку как есть."""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today():
    return datetime.now(TZ).date()


def _text(v, n=500):
    v = str(v if v is not None else "").strip()
    return v[:n]


def _money(v, field="Сумма", allow_zero=False):
    s = str(v if v is not None else "").replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        x = round(float(s), 2)
    except ValueError:
        raise CrmError(f"{field}: введите число") from None
    if x < 0 or (x == 0 and not allow_zero):
        raise CrmError(f"{field}: должна быть больше нуля")
    if x > 1e9:
        raise CrmError(f"{field}: слишком большое число")
    return x


def _day(v, field="Дата", required=True):
    v = _text(v, 10)
    if not v and not required:
        return None
    try:
        return date.fromisoformat(v).isoformat()
    except ValueError:
        raise CrmError(f"{field}: укажите дату") from None


def _cur(v):
    c = str(v or "EUR").upper()
    if c not in CODES:
        raise CrmError("Валюта: выберите из списка (" + ", ".join(CODES) + ")")
    return c


def _row(r):
    return dict(r) if r is not None else None


def _debt(stages, ops):
    """Бонусы подрядчика в проекте. stages — его этапы, ops — полученные от него бонусы.
    Считается в валюте его этапов (если все в одной), иначе в евро: так оплата в той же валюте закрывает долг ровно,
    без хвостов от разницы курсов. Возвращает ожидаемое, полученное, долг — в этой валюте и в евро."""
    known = [s for s in stages if s["commission"] is not None]
    curs = {s["currency"] for s in (known or stages)} or {o["currency"] for o in ops}
    cur = next(iter(curs)) if len(curs) == 1 else "EUR"
    k = 1.0                                             # сколько единиц валюты долга в одном евро
    if cur != "EUR":
        for pairs in ([(s["commission"], s["commission_eur"]) for s in known if s["currency"] == cur],
                      [(s["amount"], s["amount_eur"]) for s in stages if s["currency"] == cur],
                      [(o["amount"], o["amount_eur"]) for o in ops if o["currency"] == cur]):
            a, e = sum(x for x, _ in pairs), sum(y or 0 for _, y in pairs)
            if a > 0 and e > 0:
                k = a / e
                break

    def in_cur(amount, currency, amount_eur):
        return amount if currency == cur else (amount_eur or 0) * k
    expected = sum(in_cur(s["commission"], s["currency"], s["commission_eur"]) for s in known)
    received = sum(in_cur(o["amount"], o["currency"], o["amount_eur"]) for o in ops)
    debt = expected - received if expected - received > 0.005 else 0.0
    out_stages = []
    for s in stages:
        got = sum(in_cur(o["amount"], o["currency"], o["amount_eur"]) for o in ops if o.get("stage_id") == s["id"])
        out_stages.append(dict(s, received=round(got, 2)))
    return {"currency": cur, "rate": round(k, 6), "expected": round(expected, 2), "received": round(received, 2),
            "debt": round(debt, 2), "expected_eur": round(expected / k, 2), "received_eur": round(sum(o["amount_eur"] for o in ops), 2),
            "debt_eur": round(debt / k, 2), "unknown": len(stages) - len(known),
            "order": round(sum(in_cur(s["amount"], s["currency"], s["amount_eur"]) for s in stages), 2),
            "order_eur": round(sum(s["amount_eur"] for s in stages), 2), "stages": out_stages, "ops": len(ops)}


def add_months(d, k):
    """Тот же день через k месяцев (31-е → последний день короткого месяца)."""
    y, m = divmod(d.month - 1 + k, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def service_money(s, pays, on=None):
    """Начисления и оплаты доп. услуги (в евро). Разовая — одно начисление на всю сумму (срок — дата услуги);
    помесячная — каждый месяц с даты начала до «остановлена» или до числа месяцев, только наступившие. Оплаты закрывают
    начисления по порядку. Статус начисления: paid — оплачено, due — к оплате, overdue — не оплачено больше 7 дней после
    срока, upcoming — срок ещё не наступил. Отменённая услуга ничего не начисляет."""
    on = on or today()
    start = date.fromisoformat(s["start"])
    stop = date.fromisoformat(s["stopped"]) if s.get("stopped") else None
    dues, nxt = [], None
    if s.get("cancelled"):
        pass
    elif s["kind"] == "once":
        dues.append(start)
    else:
        for k in range(600):
            due = add_months(start, k)
            if (s.get("months") and k >= int(s["months"])) or (stop and due > stop):
                break
            if due > on:
                nxt = due
                break
            dues.append(due)
    amount = round(float(s["amount"]), 2)
    paid = round(sum(p["amount_eur"] for p in pays), 2)
    left, charges = paid, []
    for due in dues:
        got = round(min(amount, max(0.0, left)), 2)
        left -= got
        st = ("paid" if got >= amount - 0.005 else "upcoming" if due > on
              else "overdue" if (on - due).days > REMIND_GRACE else "due")
        charges.append({"due": due.isoformat(), "amount": amount, "paid": got, "status": st})
    charged = round(amount * len(dues), 2)
    return {"charges": charges, "charged": charged, "paid": paid, "debt": round(max(0.0, charged - paid), 2),
            "prepaid": round(max(0.0, paid - charged), 2), "next": {"due": nxt.isoformat(), "amount": amount} if nxt else None,
            "overdue": sum(1 for c in charges if c["status"] == "overdue"),
            "status": "cancelled" if s.get("cancelled") else "stopped" if stop and stop <= on else "active"}


def order_money(o, pays):
    """Оплаты заказчика за товар — в валюте товара (оплата в той же валюте закрывает цену ровно, без хвостов от курса).
    Статус: ordered — заказан, delivered — доставлен, но не оплачен полностью, done — доставлен и оплачен, cancelled."""
    k = (o["price"] / o["price_eur"]) if o["price_eur"] else 1.0      # единиц валюты товара в одном евро
    paid = round(sum(p["amount"] if p["currency"] == o["currency"] else p["amount_eur"] * k for p in pays), 2)
    rest = round(o["price"] - paid, 2) if o["price"] - paid > 0.005 else 0.0
    st = "cancelled" if o.get("cancelled") else ("done" if not rest else "delivered") if o.get("delivered") else "ordered"
    margin = round(o["price_eur"] - o["buy_eur"], 2) if o.get("buy_eur") is not None else None
    return {"paid": paid, "paid_eur": round(sum(p["amount_eur"] for p in pays), 2), "rest": rest,
            "rest_eur": round(rest / k, 2) if k else rest, "status": st, "margin": margin if st != "cancelled" else None}


class Crm:
    def __init__(self, path=CRM_DB, rates=None, files_dir=FILES_DIR, backup_dir=BACKUP_DIR):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path, self.files_dir, self.backup_dir = path, files_dir, backup_dir
        self.trash_dir = os.path.join(os.path.dirname(os.path.abspath(files_dir)), "trash")
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.rates = rates
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.executescript(SCHEMA)
            # колонки, добавленные позже: этапы подрядчиков, удаление заявок, товары и услуги, кабинеты (25.10.2026)
            for table, col, typ in (("ops", "link_id", "INTEGER"), ("ops", "stage_id", "INTEGER"), ("leads", "deleted", "TEXT"),
                                    ("ops", "order_id", "INTEGER"), ("ops", "service_id", "INTEGER"),
                                    ("stages", "src", "TEXT"), ("stages", "confirmed", "TEXT"), ("stages", "confirmed_by", "TEXT"),
                                    ("stages", "disputed", "TEXT"), ("stages", "disputed_by", "TEXT"), ("stages", "dispute_note", "TEXT"),
                                    ("clients", "tg_id", "INTEGER"), ("clients", "tg_name", "TEXT"), ("clients", "tg_since", "TEXT"),
                                    ("contractors", "tg_id", "INTEGER"), ("contractors", "tg_name", "TEXT"),
                                    ("contractors", "tg_since", "TEXT"), ("contractors", "messenger", "TEXT"),
                                    # работники подрядчиков, разговоры, права на документы, наблюдатель (24.10.2026, вечер)
                                    ("contractors", "observer", "INTEGER"), ("messages", "thread_id", "INTEGER"),
                                    ("files", "owner_kind", "TEXT"), ("files", "owner_contractor", "INTEGER"),
                                    ("files", "owner_crew", "INTEGER"), ("files", "vis", "TEXT"), ("files", "see_client", "INTEGER"),
                                    ("files", "see_crew", "INTEGER"), ("files", "thread_id", "INTEGER"), ("files", "title", "TEXT"),
                                    # поставщики и сотрудники студии (24.10.2026, ночь)
                                    ("contractors", "kind", "TEXT"), ("files", "owner_assistant", "INTEGER"),
                                    # личные разговоры Ирины с сотрудником студии (staff) — 24.10.2026, ночь
                                    ("threads", "assistant_id", "INTEGER"),
                                    # стадия проекта; помещение, версия и «ждёт решения Ирины» у файлов (25.10.2026)
                                    ("projects", "stage", "TEXT"), ("files", "room", "TEXT"), ("files", "ver", "INTEGER"),
                                    ("files", "review", "INTEGER"),
                                    # заказчик согласовал конкретное фото (решено 25.10.2026, вечер): дата и кто отметил
                                    ("files", "agreed", "TEXT"), ("files", "agreed_by", "TEXT"),
                                    # порядок файлов в разделе (решено 27.10.2026)
                                    ("files", "pos", "INTEGER"),
                                    # чей подрядчик в проекте (решено 27.10.2026): прораб заказчика бонусы обычно не платит
                                    ("project_contractors", "side", "TEXT"),
                                    # заявка на товар партнёра (Замлинский и др.): отдать ему или оставить себе — решает студия (28.10.2026)
                                    ("leads", "partner", "TEXT"), ("leads", "partner_id", "INTEGER"), ("leads", "handoff", "TEXT"),
                                    ("leads", "handoff_at", "TEXT"), ("leads", "handoff_by", "TEXT")):
                if col not in {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            self.db.execute("CREATE INDEX IF NOT EXISTS messages_thread ON messages(thread_id, id)")
            self._threads_from_v1()
            # 25.10.2026: документы подрядчиков и сотрудников заказчик видит только одобренные Ириной — то, что он уже
            # видел до этого, остаётся видимым (считается одобренным)
            if not self.db.execute("SELECT 1 FROM settings WHERE key='mig_approval'").fetchone():
                self.db.execute("UPDATE files SET see_client=1 WHERE owner_kind IN ('contractor', 'crew') AND vis='client' AND see_client IS NULL")
                self.db.execute("UPDATE files SET see_client=1 WHERE owner_kind='assistant' AND see_client IS NULL AND category IN "
                                f"({','.join('?' * len(CLIENT_CATS))})", CLIENT_CATS)
                self.db.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('mig_approval', '2026-10-25')")
            # 25.10.2026, вечер: согласование — у каждого фото, а не у всего варианта (правки). Вариант, отмеченный раньше
            # «Заказчик согласовал», переносится на все его файлы с той же датой; doc_rounds остаётся как было
            if not self.db.execute("SELECT 1 FROM settings WHERE key='mig_file_agreed'").fetchone():
                self.db.execute("""UPDATE files SET
                      agreed = (SELECT r.agreed FROM doc_rounds r WHERE r.project_id=files.project_id AND r.category=files.category
                                AND r.ver=COALESCE(files.ver, 1) AND r.agreed IS NOT NULL),
                      agreed_by = (SELECT r.agreed_by FROM doc_rounds r WHERE r.project_id=files.project_id AND r.category=files.category
                                AND r.ver=COALESCE(files.ver, 1) AND r.agreed IS NOT NULL)
                    WHERE agreed IS NULL AND EXISTS (SELECT 1 FROM doc_rounds r WHERE r.project_id=files.project_id
                          AND r.category=files.category AND r.ver=COALESCE(files.ver, 1) AND r.agreed IS NOT NULL)""")
                self.db.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('mig_file_agreed', '2026-10-25')")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        self.secret = self.setting("link_secret") or self._new_secret()

    # ---------- база ----------
    def q(self, sql, *args):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def one(self, sql, *args):
        with self.lock:
            return _row(self.db.execute(sql, args).fetchone())

    def run(self, sql, *args):
        with self.lock:
            return self.db.execute(sql, args).lastrowid

    def setting(self, key, value=None):
        if value is None:
            r = self.one("SELECT value FROM settings WHERE key=?", key)
            return r["value"] if r else None
        self.run("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", key, value)
        return value

    def _threads_from_v1(self):
        """Переписка первой версии (одна на проект, студия и заказчики) → разговор «client» проекта; прочитанное — туда же."""
        for r in self.db.execute("SELECT DISTINCT project_id FROM messages WHERE thread_id IS NULL").fetchall():
            pid = r[0]
            t = self.db.execute("SELECT id FROM threads WHERE project_id=? AND kind='client'", (pid,)).fetchone()
            tid = t[0] if t else self.db.execute("INSERT INTO threads(project_id, kind, created) VALUES(?, 'client', ?)",
                                                 (pid, now())).lastrowid
            self.db.execute("UPDATE messages SET thread_id=? WHERE project_id=? AND thread_id IS NULL", (tid, pid))
            self.db.execute("UPDATE files SET thread_id=? WHERE category='chat' AND thread_id IS NULL AND id IN "
                            "(SELECT file_id FROM messages WHERE thread_id=? AND file_id IS NOT NULL)", (tid, tid))
            for cr in self.db.execute("SELECT tg_id, last_id FROM chat_read WHERE project_id=?", (pid,)).fetchall():
                self.db.execute("INSERT OR IGNORE INTO thread_read(thread_id, tg_id, last_id) VALUES(?, ?, ?)", (tid, cr[0], cr[1]))

    def _new_secret(self):
        return self.setting("link_secret", secrets.token_hex(24))

    def lists(self):
        """Справочники: тарифы, виды работ, категории бонусов (меняются в настройках) и постоянные списки."""
        out = {}
        for k, v in DEFAULTS.items():
            try:
                out[k] = json.loads(self.setting(k) or "null") or v
            except ValueError:
                out[k] = v
        try:
            pct = float(self.setting("default_pct") or DEFAULT_PCT)
        except ValueError:
            pct = DEFAULT_PCT
        out.update(statuses=STATUSES, lead_statuses=LEAD_STATUSES, lead_triage=LEAD_TRIAGE, lead_flow=LEAD_FLOW, lead_hidden=LEAD_HIDDEN, kinds=KINDS, file_cats=FILE_CATS, photo_cats=PHOTO_CATS, contact_prefs=CONTACT_PREFS,
                   pay_methods=PAY_METHODS, currencies=CURRENCIES, default_pct=pct, order_statuses=ORDER_STATUSES,
                   service_kinds=SERVICE_KINDS, client_cats=CLIENT_CATS, contractor_cats=CONTRACTOR_CATS, people_max=PROJECT_PEOPLE_MAX,
                   contractor_kinds=CONTRACTOR_KINDS, round_cats=ROUND_CATS, room_cats=ROOM_CATS, stages=STAGES,
                   design_stages=DESIGN_STAGES, tariff_info=self.tariff_info())
        return out

    def tariff_info(self):
        """Пакеты: цена за м² и сколько правок визуализаций входит — по сайту, Ирина меняет в ⚙︎."""
        try:
            saved = json.loads(self.setting("tariff_info") or "{}") or {}
        except ValueError:
            saved = {}
        out = {k: dict(v) for k, v in TARIFF_INFO.items()}
        for k, v in saved.items():
            if isinstance(v, dict):
                out.setdefault(k, {}).update({x: v[x] for x in ("rate", "revisions") if x in v})
        return out

    def save_lists(self, data, who):
        for k in DEFAULTS:
            if k in data:
                items = [_text(x, 60) for x in (data[k] or []) if _text(x, 60)]
                if not items:
                    raise CrmError("Список не может быть пустым")
                self.setting(k, json.dumps(list(dict.fromkeys(items)), ensure_ascii=False))
        if isinstance(data.get("tariff_info"), dict):          # пакеты: цена за м² и правки
            info = {}
            for k, v in data["tariff_info"].items():
                name = _text(k, 60)
                if not name or not isinstance(v, dict):
                    continue
                x = {}
                if v.get("rate") not in (None, ""):
                    x["rate"] = _money(v["rate"], f"Цена за м² — «{name}»", allow_zero=True)
                if v.get("revisions") not in (None, ""):
                    r = int(_money(v["revisions"], f"Правки — «{name}»", allow_zero=True))
                    if r > 10:
                        raise CrmError(f"Правки — «{name}»: не больше 10")
                    x["revisions"] = r
                info[name] = x
            self.setting("tariff_info", json.dumps(info, ensure_ascii=False))
        if "default_pct" in data:
            pct = _money(data["default_pct"], "Бонус по умолчанию")
            if pct > 100:
                raise CrmError("Бонус по умолчанию: не больше 100 %")
            self.setting("default_pct", str(pct))
        self.audit(who, "edit", "settings", 0, data)
        return self.lists()

    def audit(self, who, action, entity, entity_id, details=None):
        self.run("INSERT INTO audit(ts, who, action, entity, entity_id, details) VALUES(?, ?, ?, ?, ?, ?)",
                 now(), who, action, entity, entity_id, json.dumps(details or {}, ensure_ascii=False, default=str)[:4000])

    # ---------- курсы ----------
    def _convert(self, amount, currency, day, manual_rate=None):
        """(курс к евро, откуда курс, сумма в евро). Курс — сколько единиц валюты в одном евро."""
        currency = (currency or "EUR").upper()
        if currency == "EUR":
            return 1.0, "", amount
        if manual_rate not in (None, "", 0, "0"):
            rate = _money(manual_rate, "Курс")
            return rate, "вручную", round(amount / rate, 2)
        if not self.rates:
            raise CrmError("Курсы валют недоступны — укажите курс вручную")
        try:
            rate, used, src = self.rates.rate(currency, day)
        except Exception as e:  # noqa: BLE001
            raise CrmError(f"Не удалось получить курс {currency} ({e}) — укажите курс вручную") from None
        return rate, f"{src} {used}".strip(), round(amount / rate, 2)

    def rate(self, currency, day):
        rate, src, _ = self._convert(1.0, currency, _day(day))
        return {"currency": currency, "rate": rate, "src": src}

    # ---------- проекты ----------
    def extras(self, project_id=None):
        """Доп. услуги и товары проектов с деньгами: {project_id: {"services": [...], "orders": [...]}}."""
        flt, args = ("WHERE project_id=?", (int(project_id),)) if project_id else ("", ())
        pays = {}
        for o in self.q(f"SELECT * FROM ops {flt + ' AND' if flt else 'WHERE'} kind='payment' AND "
                        f"(order_id IS NOT NULL OR service_id IS NOT NULL) ORDER BY day, id", *args):
            pays.setdefault(("o", o["order_id"]) if o["order_id"] else ("s", o["service_id"]), []).append(o)
        out = {}
        for s in self.q(f"SELECT * FROM services {flt} ORDER BY start, id", *args):
            s["money"] = service_money(s, pays.get(("s", s["id"]), []))
            s["payments"] = pays.get(("s", s["id"]), [])
            out.setdefault(s["project_id"], {"services": [], "orders": []})["services"].append(s)
        for o in self.q(f"SELECT * FROM orders {flt} ORDER BY day, id", *args):
            o["money"] = order_money(o, pays.get(("o", o["id"]), []))
            o["payments"] = pays.get(("o", o["id"]), [])
            out.setdefault(o["project_id"], {"services": [], "orders": []})["orders"].append(o)
        return out

    def project_rows(self):
        """Все проекты с итогами: оплачено по договору, доп. услуги и товары, доп. доход, сколько всего должен заказчик.
        paid — оплаты по договору (без оплат за товары и услуги), balance — договор − paid."""
        rows = self.q("""
            SELECT p.*, c.name AS client_name, c.phone AS client_phone,
              COALESCE((SELECT SUM(amount_eur) FROM ops o WHERE o.project_id=p.id AND o.kind='payment'
                        AND o.order_id IS NULL AND o.service_id IS NULL), 0) AS paid,
              COALESCE((SELECT SUM(amount_eur) FROM ops o WHERE o.project_id=p.id AND o.kind='payment' AND o.service_id IS NOT NULL), 0) AS paid_services,
              COALESCE((SELECT SUM(amount_eur) FROM ops o WHERE o.project_id=p.id AND o.kind='commission'), 0) AS bonus,
              COALESCE((SELECT SUM(amount_eur - buy_eur) FROM ops o WHERE o.project_id=p.id AND o.kind='resale'), 0) AS margin,
              (SELECT MAX(day) FROM ops o WHERE o.project_id=p.id) AS last_op,
              (SELECT COUNT(*) FROM files f WHERE f.project_id=p.id AND f.category NOT IN ('goods', 'chat')) AS files,
              (SELECT COUNT(*) FROM files f WHERE f.project_id=p.id AND f.review=1) AS review
            FROM projects p LEFT JOIN clients c ON c.id=p.client_id ORDER BY p.updated DESC""")
        debts = {}
        for m in self.link_money().values():
            d = debts.setdefault(m["project_id"], [0.0, 0.0])
            d[0] += m["debt_eur"]
            d[1] += m["expected_eur"]
        ex = self.extras()
        for r in rows:
            e = ex.get(r["id"]) or {"services": [], "orders": []}
            r["services_debt"] = round(sum(s["money"]["debt"] for s in e["services"]), 2)
            r["services_overdue"] = sum(s["money"]["overdue"] for s in e["services"])
            r["orders_rest"] = round(sum(o["money"]["rest_eur"] for o in e["orders"] if o["money"]["status"] != "cancelled"), 2)
            r["orders_count"] = sum(1 for o in e["orders"] if o["money"]["status"] != "cancelled")
            r["services_count"] = sum(1 for s in e["services"] if not s["cancelled"])
            r["margin"] += sum(o["money"]["margin"] or 0 for o in e["orders"])
            for k in ("paid", "paid_services", "bonus", "margin"):
                r[k] = round(r[k], 2)
            r["extra"] = round(r["bonus"] + r["margin"], 2)
            r["balance"] = round((r["total_eur"] or 0) - r["paid"], 2)
            r["income"] = round(r["paid"] + r["paid_services"] + r["extra"], 2)
            r["client_debt"] = round(max(0.0, r["balance"]) + r["services_debt"] + r["orders_rest"], 2)
            r["contractor_debt"], r["bonus_expected"] = (round(x, 2) for x in debts.get(r["id"], (0, 0)))
        return rows

    def link_money(self, project_id=None):
        """{link_id: бонусы подрядчика в проекте (_debt) + project_id, contractor_id, trade}."""
        flt, args = ("WHERE project_id=?", (int(project_id),)) if project_id else ("", ())
        links = self.q(f"SELECT * FROM project_contractors {flt}", *args)
        stages = self.q(f"SELECT * FROM stages {flt} ORDER BY day, id", *args)
        ops = self.q(f"SELECT * FROM ops {flt + ' AND' if flt else 'WHERE'} kind='commission' AND link_id IS NOT NULL ORDER BY day, id", *args)
        out = {}
        for link in links:
            m = _debt([x for x in stages if x["link_id"] == link["id"]], [o for o in ops if o["link_id"] == link["id"]])
            m.update(link_id=link["id"], project_id=link["project_id"], contractor_id=link["contractor_id"], trade=link["trade"],
                     side=link["side"] or "studio")
            out[link["id"]] = m
        return out

    def project(self, pid):
        p = next((r for r in self.project_rows() if r["id"] == int(pid)), None)
        if not p:
            raise CrmError("Проект не найден")
        ops = self.q("SELECT * FROM ops WHERE project_id=? ORDER BY day DESC, id DESC", p["id"])
        for o in ops:                              # оплата за товар — не доход студии (доход — наценка товара)
            o["income"] = round(0 if o["order_id"] else o["amount_eur"] - (o["buy_eur"] or 0) if o["kind"] == "resale" else o["amount_eur"], 2)
        links = self.q("""SELECT l.id AS link_id, l.trade AS link_trade, l.note AS link_note, l.side AS link_side, c.*
                          FROM project_contractors l JOIN contractors c ON c.id=l.contractor_id
                          WHERE l.project_id=? ORDER BY l.id""", p["id"])
        money = self.link_money(p["id"])
        for link in links:
            link["money"] = money.get(link["link_id"]) or _debt([], [])
        files = [self.file_view(f) for f in sort_files(self.q("SELECT * FROM files WHERE project_id=? AND category NOT IN ('goods', 'chat') "
                                                              "ORDER BY id", p["id"]))]
        names = {c["id"]: c["name"] for c in self.q("SELECT id, name FROM contractors")}
        crew_names = {c["id"]: c["name"] for c in self.q("SELECT id, name FROM crew")}
        for f in files:                     # кто загрузил (подрядчик или его работник) — для раздела «От подрядчиков»
            f["owner_name"] = crew_names.get(f.get("owner_crew")) or names.get(f.get("owner_contractor")) or ""
        client = self.one("SELECT * FROM clients WHERE id=?", p["client_id"]) if p["client_id"] else None
        ex = self.extras(p["id"]).get(p["id"]) or {"services": [], "orders": []}
        for o in ex["orders"]:
            o["photo"] = self.order_photo(o)
        history = self.q("SELECT ts, who, action, entity, entity_id FROM audit WHERE (entity='project' AND entity_id=?) OR "
                         "(entity IN ('op', 'file', 'link', 'stage', 'order', 'service', 'pclient', 'access', 'pcrew', 'thread', 'passist') AND (details LIKE ? OR details LIKE ?)) "
                         "ORDER BY id DESC LIMIT 50", p["id"], f'%"project_id": {p["id"]},%', f'%"project_id": {p["id"]}}}%')
        invites = self.q("SELECT kind, ref_id, expires, created FROM invites WHERE project_id=? AND used_by IS NULL AND expires > ?",
                         p["id"], now())
        return {"project": p, "ops": ops, "contractors": links, "files": files, "client": client, "history": history,
                "people": self.project_people(p["id"]), "services": ex["services"], "orders": ex["orders"],
                "chat": self.chat_summary(p["id"]), "invites": invites, "stages": self.stage_log(p["id"]),
                "rounds": self.rounds(p["id"]),
                "tariff_changes": self.q("SELECT * FROM tariff_changes WHERE project_id=? ORDER BY id", p["id"])}

    def order_photo(self, o):
        """Фото товара: загруженное в карточку (подписанная ссылка) или картинка со страницы товара."""
        if o.get("file_id"):
            f = self.one("SELECT * FROM files WHERE id=? AND project_id=?", o["file_id"], o["project_id"])
            if f and f.get("path"):
                v = self.file_view(f)
                return v["thumb_url"] or v["url"]
        return o.get("image_url") or None

    def project_people(self, pid):
        """Заказчики проекта: основной и ещё (project_clients) — с отметкой, подключён ли кабинет в боте."""
        p = self.one("SELECT client_id FROM projects WHERE id=?", int(pid))
        if not p:
            return []
        rows = []
        if p["client_id"]:
            c = self.one("SELECT * FROM clients WHERE id=?", p["client_id"])
            if c:
                rows.append(dict(c, main=True))
        for c in self.q("""SELECT c.* FROM project_clients x JOIN clients c ON c.id=x.client_id
                           WHERE x.project_id=? ORDER BY x.id""", int(pid)):
            if c["id"] != p["client_id"]:
                rows.append(dict(c, main=False))
        return rows

    def add_project_client(self, d, who):
        pid, cid = int(d.get("project_id") or 0), int(d.get("client_id") or 0)
        p = self.one("SELECT id, client_id FROM projects WHERE id=?", pid)
        if not p or not self.one("SELECT id FROM clients WHERE id=?", cid):
            raise CrmError("Проект или заказчик не найден")
        if cid == p["client_id"] or self.one("SELECT id FROM project_clients WHERE project_id=? AND client_id=?", pid, cid):
            raise CrmError("Этот заказчик уже в проекте")
        if len(self.project_people(pid)) >= PROJECT_PEOPLE_MAX:
            raise CrmError(f"В проекте уже {PROJECT_PEOPLE_MAX} заказчиков — больше добавить нельзя")
        if not p["client_id"]:                       # первый заказчик проекта — основной
            self.run("UPDATE projects SET client_id=?, updated=? WHERE id=?", cid, now(), pid)
        else:
            self.run("INSERT INTO project_clients(project_id, client_id, created) VALUES(?, ?, ?)", pid, cid, now())
        self.audit(who, "add", "pclient", cid, {"project_id": pid, "client_id": cid})
        return self.project(pid)

    def remove_project_client(self, d, who):
        """Убрать заказчика из проекта (в контактах остаётся). Основного — только если есть кто-то ещё: он станет основным."""
        pid, cid = int(d.get("project_id") or 0), int(d.get("client_id") or 0)
        p = self.one("SELECT id, client_id FROM projects WHERE id=?", pid)
        if not p:
            raise CrmError("Проект не найден")
        if cid == p["client_id"]:
            nxt = self.one("SELECT id, client_id FROM project_clients WHERE project_id=? ORDER BY id LIMIT 1", pid)
            self.run("UPDATE projects SET client_id=?, updated=? WHERE id=?", nxt["client_id"] if nxt else None, now(), pid)
            if nxt:
                self.run("DELETE FROM project_clients WHERE id=?", nxt["id"])
        else:
            if not self.one("SELECT id FROM project_clients WHERE project_id=? AND client_id=?", pid, cid):
                raise CrmError("Этого заказчика нет в проекте")
            self.run("DELETE FROM project_clients WHERE project_id=? AND client_id=?", pid, cid)
        self.audit(who, "delete", "pclient", cid, {"project_id": pid, "client_id": cid})
        return self.project(pid)

    def save_project(self, d, who):
        pid = int(d.get("id") or 0)
        title = _text(d.get("title"), 200)
        if not title:
            raise CrmError("Укажите название проекта")
        number = _text(d.get("number"), 40)
        if number and self.one("SELECT id FROM projects WHERE number=? AND id!=?", number, pid):
            raise CrmError(f"Номер {number} уже есть у другого проекта")
        status = d.get("status") or "active"
        if status not in dict(STATUSES):
            raise CrmError("Неизвестный статус")
        client_id = int(d.get("client_id") or 0) or None
        if client_id and not self.one("SELECT id FROM clients WHERE id=?", client_id):
            raise CrmError("Заказчик не найден")
        area = _text(d.get("area"), 20)
        fields = dict(number=number or None, title=title, client_id=client_id, city=_text(d.get("city"), 80),
                      country=_text(d.get("country"), 80), address=_text(d.get("address"), 200),
                      area=_money(area, "Площадь") if area else None, tariff=_text(d.get("tariff"), 60),
                      total_eur=_money(d.get("total_eur") or 0, "Сумма договора", allow_zero=True), status=status,
                      started=_day(d.get("started"), "Начало", False), finished=_day(d.get("finished"), "Окончание", False),
                      note=_text(d.get("note"), 3000))
        if pid:
            if not self.one("SELECT id FROM projects WHERE id=?", pid):
                raise CrmError("Проект не найден")
            sets = ", ".join(f"{k}=?" for k in fields)
            self.run(f"UPDATE projects SET {sets}, updated=? WHERE id=?", *fields.values(), now(), pid)
            if client_id:                            # стал основным — в «ещё заказчиках» он больше не нужен
                self.run("DELETE FROM project_clients WHERE project_id=? AND client_id=?", pid, client_id)
            self.audit(who, "edit", "project", pid, fields)
        else:
            cols = ", ".join(fields)
            pid = self.run(f"INSERT INTO projects({cols}, created_by, created, updated) VALUES({', '.join('?' * len(fields))}, ?, ?, ?)",
                           *fields.values(), who, now(), now())
            self.audit(who, "add", "project", pid, fields)
        return self.project(pid)

    def running_services(self, pid, on):
        """Помесячные услуги проекта, которые на дату on идут и будут начисляться дальше (не отменены, не остановлены, не закончились)."""
        out = []
        for sv in self.q("SELECT * FROM services WHERE project_id=? AND kind='monthly' AND cancelled IS NULL", int(pid)):
            start = date.fromisoformat(sv["start"])
            if start > on or (sv["stopped"] and date.fromisoformat(sv["stopped"]) <= on):
                continue
            if sv["months"] and add_months(start, int(sv["months"]) - 1) <= on:
                continue
            out.append(sv)
        return out

    def set_project_status(self, d, who):
        """Завершить проект (дата окончания; помесячные услуги можно остановить этой датой) или вернуть в работу
        (дата окончания стирается — история остаётся в журнале). Решено 24.10.2026: завершённый проект можно вернуть,
        если заказчику понадобилась доп. услуга, поставка или работа подрядчика."""
        pid = int(d.get("id") or 0)
        p = self.one("SELECT * FROM projects WHERE id=?", pid)
        if not p:
            raise CrmError("Проект не найден")
        status = d.get("status")
        if status not in dict(STATUSES):
            raise CrmError("Неизвестный статус")
        details = {"project_id": pid, "status": status, "was": p["status"]}
        if status == "done":
            fin = _day(d.get("finished") or today().isoformat(), "Дата окончания")
            if p["started"] and fin < p["started"]:
                raise CrmError("Дата окончания раньше начала проекта")
            stopped = []
            if d.get("stop_services"):
                for sv in self.running_services(pid, date.fromisoformat(fin)):
                    self.run("UPDATE services SET stopped=?, updated=? WHERE id=?", fin, now(), sv["id"])
                    stopped.append(sv["title"])
            self.run("UPDATE projects SET status='done', finished=?, updated=? WHERE id=?", fin, now(), pid)
            details.update(finished=fin, stopped_services=stopped)
            if p["stage"] != "done":                       # стадия «Завершён» — вместе со статусом
                self._log_stage(pid, "done", fin, who)
        else:
            self.run("UPDATE projects SET status=?, finished=CASE WHEN ?='done' THEN finished ELSE NULL END, updated=? WHERE id=?",
                     status, status, now(), pid)
            if p["stage"] == "done" and status != "cancelled":   # вернули в работу — прежняя стадия (Ирина поставит новую)
                prev = self.one("SELECT stage FROM project_stages WHERE project_id=? AND stage!='done' ORDER BY id DESC LIMIT 1", pid)
                self._log_stage(pid, prev["stage"] if prev else None, today().isoformat(), who)
        self.audit(who, "edit", "project", pid, details)
        return self.project(pid)

    # ---------- стадия проекта (решено 25.10.2026) ----------
    def stage_log(self, pid):
        return self.q("SELECT stage, day, who FROM project_stages WHERE project_id=? AND stage IS NOT NULL ORDER BY id", int(pid))

    def _log_stage(self, pid, stage, day, who):
        self.run("UPDATE projects SET stage=?, updated=? WHERE id=?", stage, now(), pid)
        if stage:
            self.run("INSERT INTO project_stages(project_id, stage, day, who, created) VALUES(?, ?, ?, ?, ?)",
                     pid, stage, day, _text(who, 120), now())

    def set_project_stage(self, d, who):
        """Текущая стадия проекта (замер, планировки, концепция, визуализации, документация, ремонт, мебель…). «Завершён» —
        то же, что «Завершить проект»; рабочая стадия у завершённого проекта возвращает его в работу (заказчик продолжил)."""
        pid = int(d.get("id") or d.get("project_id") or 0)
        p = self.one("SELECT * FROM projects WHERE id=?", pid)
        if not p:
            raise CrmError("Проект не найден")
        stage = d.get("stage")
        if stage not in dict(STAGES):
            raise CrmError("Выберите стадию")
        if stage == "done":
            r = self.set_project_status({"id": pid, "status": "done", "finished": d.get("day"), "stop_services": d.get("stop_services")}, who)
            return dict(r, stage_changed=p["stage"] != "done")
        day = _day(d.get("day") or today().isoformat(), "Дата")
        if p["stage"] == stage:
            return dict(self.project(pid), stage_changed=False)
        if p["status"] in ("done", "cancelled"):
            self.run("UPDATE projects SET status='active', finished=NULL WHERE id=?", pid)
        self._log_stage(pid, stage, day, who)
        self.audit(who, "edit", "project", pid, {"project_id": pid, "stage": stage, "was_stage": p["stage"], "day": day})
        return dict(self.project(pid), stage_changed=True)

    # ---------- смена пакета: пересчёт только вверх или прежняя сумма (решено 25.10.2026) ----------
    def change_tariff(self, d, who):
        pid = int(d.get("id") or d.get("project_id") or 0)
        p = self.one("SELECT * FROM projects WHERE id=?", pid)
        if not p:
            raise CrmError("Проект не найден")
        new = _text(d.get("tariff"), 60)
        if not new:
            raise CrmError("Выберите пакет")
        if new == (p["tariff"] or ""):
            raise CrmError("Это и есть текущий пакет проекта")
        day = _day(d.get("day") or today().isoformat(), "Дата")
        old_total = round(p["total_eur"] or 0, 2)
        area, rate = p["area"], None
        if d.get("mode") == "recalc":
            area = _money(d.get("area") or p["area"] or 0, "Площадь")
            rate = _money(d.get("rate"), "Цена за м²")
            new_total = round(area * rate, 2)
            if new_total < old_total - 0.005:
                raise CrmError(f"Пересчёт даёт {new_total:.2f} €, это меньше нынешней суммы договора {old_total:.2f} €. "
                               "Сумма при смене пакета только растёт — оставьте прежнюю")
        elif d.get("mode") == "keep":
            new_total = old_total
        else:
            raise CrmError("Пересчитать сумму или оставить прежнюю?")
        self.run("UPDATE projects SET tariff=?, total_eur=?, area=?, updated=? WHERE id=?", new, new_total, area, now(), pid)
        self.run("""INSERT INTO tariff_changes(project_id, day, old_tariff, new_tariff, old_total, new_total, area, rate, recalc, note, who, created)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", pid, day, p["tariff"], new, old_total, new_total, area, rate,
                 1 if d.get("mode") == "recalc" else 0, _text(d.get("note"), 500), _text(who, 120), now())
        self.audit(who, "edit", "project", pid, {"project_id": pid, "tariff": new, "was_tariff": p["tariff"], "total_eur": new_total,
                                                 "was_total": old_total, "day": day})
        return self.project(pid)

    # ---------- документы: версии, помещения, одобрение Ирины (решено 25.10.2026) ----------
    def rounds(self, pid):
        """Согласованные заказчиком варианты планировок и правки визуализаций."""
        return self.q("SELECT category, ver, agreed, agreed_by FROM doc_rounds WHERE project_id=? AND agreed IS NOT NULL ORDER BY category, ver",
                      int(pid))

    def set_round(self, d, who):
        pid, cat, ver = int(d.get("project_id") or 0), d.get("category"), int(d.get("ver") or 0)
        if cat not in ROUND_CATS or ver < 1 or not self.one("SELECT id FROM projects WHERE id=?", pid):
            raise CrmError("Вариант не найден")
        if d.get("agreed"):
            self.run("""INSERT INTO doc_rounds(project_id, category, ver, agreed, agreed_by) VALUES(?, ?, ?, ?, ?)
                        ON CONFLICT(project_id, category, ver) DO UPDATE SET agreed=excluded.agreed, agreed_by=excluded.agreed_by""",
                     pid, cat, ver, _day(d.get("day") or today().isoformat(), "Дата"), _text(who, 120))
        else:
            self.run("DELETE FROM doc_rounds WHERE project_id=? AND category=? AND ver=?", pid, cat, ver)
        self.audit(who, "edit", "file", 0, {"project_id": pid, "round": [cat, ver], "agreed": bool(d.get("agreed"))})
        return self.project(pid)

    def next_ver(self, pid, cat, title=None):
        """Номер новой версии: в планировках и визуализациях — следующий вариант (правка) всего раздела, в остальных
        разделах — следующая версия документа с этим названием."""
        if cat in ROUND_CATS:
            r = self.one("SELECT MAX(COALESCE(ver, 1)) AS v FROM files WHERE project_id=? AND category=?", int(pid), cat)
        else:
            r = self.one("SELECT MAX(COALESCE(ver, 1)) AS v FROM files WHERE project_id=? AND category=? AND COALESCE(title, name)=?",
                         int(pid), cat, title or "")
        return int((r or {}).get("v") or 0) + 1

    def file_meta(self, f, ver=None, room=None, title=None, new_version=False):
        """Версия, помещение и подпись нового файла: ver — номер (в планировках и визуализациях) или «новая» (new_version)."""
        cat = f["category"]
        ttl = _text(title, 200) or None
        v = None
        if cat in ROUND_CATS:                             # последний вариант раздела (без этого файла): к нему или новый
            r = self.one("SELECT MAX(COALESCE(ver, 1)) AS v FROM files WHERE project_id=? AND category=? AND id!=?",
                         f["project_id"], cat, f["id"])
            top = int((r or {}).get("v") or 0)
            v = top + 1 if new_version and top else max(1, min(int(ver or top or 1), top or 1))
        elif new_version and ttl:                         # новая версия документа с тем же названием
            r = self.one("SELECT MAX(COALESCE(ver, 1)) AS v FROM files WHERE project_id=? AND category=? AND COALESCE(title, name)=? AND id!=?",
                         f["project_id"], cat, ttl, f["id"])
            v = int((r or {}).get("v") or 0) + 1 if r and r.get("v") else None
        rm = _text(room, 60) if cat in ROOM_CATS else ""
        self.run("UPDATE files SET ver=?, room=?, title=COALESCE(?, title) WHERE id=?", v, rm or None, ttl, f["id"])

    def set_file_meta(self, d, who):
        """Ирина в «Студии»: помещение, вариант (правка) и подпись файла."""
        f = self.one("SELECT * FROM files WHERE id=?", int(d.get("id") or 0))
        if not f:
            raise CrmError("Файл не найден")
        sets = {}
        if "room" in d:
            sets["room"] = (_text(d.get("room"), 60) or None) if f["category"] in ROOM_CATS else None
        if "ver" in d:
            v = int(d.get("ver") or 0) or None
            if v is not None and not 1 <= v <= 50:
                raise CrmError("Номер версии — от 1 до 50")
            sets["ver"] = v
        if "title" in d:
            sets["title"] = _text(d.get("title"), 200) or None
        if sets:
            self.run(f"UPDATE files SET {', '.join(k + '=?' for k in sets)} WHERE id=?", *sets.values(), f["id"])
            self.audit(who, "edit", "file", f["id"], dict(sets, project_id=f["project_id"]))
        return self.project(f["project_id"])

    def set_file_agreed(self, d, who):
        """Ирина отмечает под фото (вариант планировки, визуализация): заказчик его согласовал — или снимает отметку."""
        f = self.one("SELECT * FROM files WHERE id=?", int(d.get("id") or 0))
        if not f:
            raise CrmError("Файл не найден")
        if f["category"] not in ROUND_CATS:
            raise CrmError("Согласование отмечается только у планировок и визуализаций")
        on = bool(d.get("agreed"))
        self.run("UPDATE files SET agreed=?, agreed_by=? WHERE id=?", today().isoformat() if on else None, _text(who, 120) if on else None, f["id"])
        self.audit(who, "edit", "file", f["id"], {"project_id": f["project_id"], "agreed": on})
        return self.project(f["project_id"])

    def approve_file(self, d, who):
        """Документ подрядчика, исполнителя, работника или сотрудника студии: Ирина показывает его заказчику (show) или нет.
        Возвращает (файл, стал ли он видим заказчику только что)."""
        f = self.one("SELECT * FROM files WHERE id=?", int(d.get("id") or 0))
        if not f:
            raise CrmError("Файл не найден")
        show = bool(d.get("show"))
        self.run("UPDATE files SET see_client=?, review=NULL WHERE id=?", 1 if show else 0, f["id"])
        self.audit(who, "edit", "file", f["id"], {"project_id": f["project_id"], "approved": show})
        return self.one("SELECT * FROM files WHERE id=?", f["id"]), show and f["see_client"] != 1

    def touch(self, pid):
        self.run("UPDATE projects SET updated=? WHERE id=?", now(), pid)

    # ---------- операции ----------
    def save_op(self, d, who):
        oid = int(d.get("id") or 0)
        pid = int(d.get("project_id") or 0)
        if not self.one("SELECT id FROM projects WHERE id=?", pid):
            raise CrmError("Проект не найден")
        kind = d.get("kind")
        if kind not in KINDS:
            raise CrmError("Неизвестный вид операции")
        day = _day(d.get("day"))
        cur = _cur(d.get("currency"))
        amount = _money(d.get("amount"), "Цена продажи" if kind == "resale" else "Сумма")
        link_id = stage_id = order_id = service_id = None
        counterparty = _text(d.get("counterparty"), 120)
        if kind == "payment" and d.get("order_id"):            # оплата за товар (аванс или доплата)
            o = self.one("SELECT id, title FROM orders WHERE id=? AND project_id=?", int(d["order_id"]), pid)
            if not o:
                raise CrmError("Товар в этом проекте не найден")
            order_id = o["id"]
        elif kind == "payment" and d.get("service_id"):        # оплата доп. услуги
            s = self.one("SELECT id FROM services WHERE id=? AND project_id=?", int(d["service_id"]), pid)
            if not s:
                raise CrmError("Услуга в этом проекте не найдена")
            service_id = s["id"]
        if kind == "commission" and d.get("link_id"):
            link = self.one("""SELECT l.id, c.name FROM project_contractors l JOIN contractors c ON c.id=l.contractor_id
                               WHERE l.id=? AND l.project_id=?""", int(d["link_id"]), pid)
            if not link:
                raise CrmError("Подрядчик в этом проекте не найден")
            link_id, counterparty = link["id"], link["name"]
            if d.get("stage_id"):
                if not self.one("SELECT id FROM stages WHERE id=? AND link_id=?", int(d["stage_id"]), link_id):
                    raise CrmError("Этап не найден")
                stage_id = int(d["stage_id"])
        rate, src, eur = self._convert(amount, cur, day, d.get("rate") if d.get("manual_rate") else None)
        f = dict(project_id=pid, kind=kind, day=day, title=_text(d.get("title"), 200), category=_text(d.get("category"), 60),
                 method=_text(d.get("method"), 60), counterparty=counterparty,
                 amount=amount, currency=cur, rate=rate, rate_src=src, amount_eur=eur,
                 buy=None, buy_currency=None, buy_rate=None, buy_rate_src=None, buy_eur=None, note=_text(d.get("note"), 2000),
                 link_id=link_id, stage_id=stage_id, order_id=order_id, service_id=service_id)
        if kind == "resale":
            if not f["title"]:
                raise CrmError("Укажите, что перепродано")
            bcur = _cur(d.get("buy_currency") or cur)
            buy = _money(d.get("buy"), "Цена закупки")
            brate, bsrc, beur = self._convert(buy, bcur, day, d.get("buy_rate") if d.get("manual_buy_rate") else None)
            f.update(buy=buy, buy_currency=bcur, buy_rate=brate, buy_rate_src=bsrc, buy_eur=beur)
        if oid:
            if not self.one("SELECT id FROM ops WHERE id=? AND project_id=?", oid, pid):
                raise CrmError("Операция не найдена")
            sets = ", ".join(f"{k}=?" for k in f)
            self.run(f"UPDATE ops SET {sets}, updated=? WHERE id=?", *f.values(), now(), oid)
            self.audit(who, "edit", "op", oid, f)
        else:
            oid = self.run(f"INSERT INTO ops({', '.join(f)}, created_by, created, updated) VALUES({', '.join('?' * len(f))}, ?, ?, ?)",
                           *f.values(), who, now(), now())
            self.audit(who, "add", "op", oid, f)
        self.touch(pid)
        return self.project(pid)

    # ---------- товары заказчика ----------
    IMAGE_HOSTS = ("https://dumskaya-design.com/", "https://www.dumskaya-design.com/", "https://dumskaya-home.com/",
                   "https://www.dumskaya-home.com/")

    def save_order(self, d, who):
        """Товар, который заказчик покупает через студию: цена для заказчика, закупка (заказчик не видит), поставка."""
        oid, pid = int(d.get("id") or 0), int(d.get("project_id") or 0)
        if not self.one("SELECT id FROM projects WHERE id=?", pid):
            raise CrmError("Проект не найден")
        title = _text(d.get("title"), 200)
        if not title:
            raise CrmError("Укажите, что за товар")
        day = _day(d.get("day") or today().isoformat(), "Дата заказа")
        cur = _cur(d.get("currency"))
        price = _money(d.get("price"), "Цена для заказчика")
        rate, src, price_eur = self._convert(price, cur, day, d.get("rate") if d.get("manual_rate") else None)
        url = _text(d.get("url"), 500)
        if url and not re.match(r"https?://[^\s]+$", url):
            raise CrmError("Ссылка на товар: начните с https://")
        image = _text(d.get("image_url"), 500)
        if image and not image.startswith(self.IMAGE_HOSTS):
            image = ""                                     # картинки — только с наших сайтов
        fid = int(d.get("file_id") or 0) or None
        if fid and not self.one("SELECT id FROM files WHERE id=? AND project_id=? AND category='goods'", fid, pid):
            fid = None
        qty = _text(d.get("qty"), 20)
        f = dict(project_id=pid, title=title, code=_text(d.get("code"), 40), url=url, image_url=image, file_id=fid,
                 qty=_money(qty, "Количество") if qty else None, day=day, price=price, currency=cur, rate=rate, rate_src=src,
                 price_eur=price_eur, buy=None, buy_currency=None, buy_rate=None, buy_rate_src=None, buy_eur=None,
                 supplier=_text(d.get("supplier"), 120), planned=_day(d.get("planned"), "Плановая поставка", False),
                 delivered=_day(d.get("delivered"), "Доставлен", False), note_client=_text(d.get("note_client"), 1000),
                 note=_text(d.get("note"), 2000))
        if str(d.get("buy") or "").strip():                 # закупку можно внести позже
            bcur = _cur(d.get("buy_currency") or cur)
            buy = _money(d.get("buy"), "Закупка")
            brate, bsrc, beur = self._convert(buy, bcur, day, d.get("buy_rate") if d.get("manual_buy_rate") else None)
            f.update(buy=buy, buy_currency=bcur, buy_rate=brate, buy_rate_src=bsrc, buy_eur=beur)
        old = self.one("SELECT * FROM orders WHERE id=? AND project_id=?", oid, pid) if oid else None
        if oid and not old:
            raise CrmError("Товар не найден")
        f["cancelled"] = (old and old["cancelled"] or now()) if d.get("cancelled") else None
        if oid:
            self.run(f"UPDATE orders SET {', '.join(f'{k}=?' for k in f)}, updated=? WHERE id=?", *f.values(), now(), oid)
            self.audit(who, "edit", "order", oid, f)
        else:
            oid = self.run(f"INSERT INTO orders({', '.join(f)}, created_by, created, updated) VALUES({', '.join('?' * len(f))}, ?, ?, ?)",
                           *f.values(), who, now(), now())
            self.audit(who, "add", "order", oid, f)
        self.touch(pid)
        return dict(self.project(pid), saved_id=oid, was=old)

    def save_service(self, d, who):
        """Доп. услуга: разовая (чертежи — сумма и срок оплаты) или помесячная (авторское сопровождение — сумма в месяц,
        с какого числа, сколько месяцев или пока не остановлена). Суммы — в евро."""
        sid, pid = int(d.get("id") or 0), int(d.get("project_id") or 0)
        if not self.one("SELECT id FROM projects WHERE id=?", pid):
            raise CrmError("Проект не найден")
        title = _text(d.get("title"), 200)
        if not title:
            raise CrmError("Укажите, что за услуга")
        kind = d.get("kind")
        if kind not in dict(SERVICE_KINDS):
            raise CrmError("Выберите: разовая или помесячно")
        months = None
        if kind == "monthly" and str(d.get("months") or "").strip():
            try:
                months = int(str(d["months"]).strip())
            except ValueError:
                raise CrmError("Сколько месяцев: введите число") from None
            if not 1 <= months <= 120:
                raise CrmError("Сколько месяцев: от 1 до 120 (или оставьте пустым — пока не остановите)")
        start = _day(d.get("start"), "Срок оплаты" if kind == "once" else "Первый платёж")
        stopped = _day(d.get("stopped"), "Остановлена", False) if kind == "monthly" else None
        if stopped and stopped < start:
            raise CrmError("Дата остановки раньше первого платежа")
        old = self.one("SELECT * FROM services WHERE id=? AND project_id=?", sid, pid) if sid else None
        if sid and not old:
            raise CrmError("Услуга не найдена")
        f = dict(project_id=pid, title=title, kind=kind, amount=_money(d.get("amount"), "Сумма" if kind == "once" else "Сумма в месяц"),
                 start=start, months=months, stopped=stopped, note=_text(d.get("note"), 2000),
                 cancelled=(old and old["cancelled"] or now()) if d.get("cancelled") else None)
        if sid:
            self.run(f"UPDATE services SET {', '.join(f'{k}=?' for k in f)}, updated=? WHERE id=?", *f.values(), now(), sid)
            self.audit(who, "edit", "service", sid, f)
        else:
            sid = self.run(f"INSERT INTO services({', '.join(f)}, created_by, created, updated) VALUES({', '.join('?' * len(f))}, ?, ?, ?)",
                           *f.values(), who, now(), now())
            self.audit(who, "add", "service", sid, f)
        self.touch(pid)
        return dict(self.project(pid), saved_id=sid, was=old)

    # ---------- заявки с сайта ----------
    @staticmethod
    def lead_src(lead):
        return hashlib.sha1(f"{lead.get('time')}|{lead.get('name')}|{lead.get('contact')}".encode()).hexdigest()[:20]

    def add_lead(self, lead, status=None, note=""):
        """Заявка с сайта → в учёт (если её там ещё нет). Возвращает номер заявки."""
        src = self.lead_src(lead)
        if (lead.get("contact") or "").strip().lower() in TEST_CONTACTS:
            status, note = "test", "Пробная заявка при настройке сервиса"
        self.run("""INSERT OR IGNORE INTO leads(ts, name, contact, message, message_ru, message_lang, page, model, model_name, lang,
                    routed, status, note, src, updated) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                 _text(lead.get("time"), 40) or now(), _text(lead.get("name"), 120), _text(lead.get("contact"), 160),
                 _text(lead.get("message"), 4000), _text(lead.get("message_ru"), 6000), _text(lead.get("message_lang"), 10),
                 _text(lead.get("page"), 300), _text(lead.get("model"), 40), _text(lead.get("model_name"), 200),
                 _text(lead.get("lang"), 5), _text(lead.get("routed"), 300), status or "new", _text(note, 500), src, now())
        return self.one("SELECT id FROM leads WHERE src=?", src)["id"]

    def lead_partner(self, lid, partner_id, name):
        """Заявка на товар партнёра: кому её можно отдать (решение — за студией, кнопками)."""
        self.run("UPDATE leads SET partner_id=?, partner=? WHERE id=?", int(partner_id), _text(name, 120), int(lid))

    def set_lead_handoff(self, lid, mode, who, routed):
        """Студия решила: заявку отдаём партнёру (partner) или оставляем себе (self)."""
        if mode not in ("partner", "self"):
            raise CrmError("Неизвестное решение")
        self.run("UPDATE leads SET handoff=?, handoff_at=?, handoff_by=?, routed=?, updated=?, updated_by=? WHERE id=?",
                 mode, now(), _text(who, 120), _text(routed, 300), now(), _text(who, 120), int(lid))
        self.audit(who, "edit", "lead", int(lid), {"handoff": mode})

    def lead_routed(self, lid, routed, model_name=""):
        self.run("UPDATE leads SET routed=?, model_name=COALESCE(NULLIF(?, ''), model_name) WHERE id=?",
                 _text(routed, 300), _text(model_name, 200), int(lid))

    def import_leads(self, path, log=print):
        """Заявки из файла leads.jsonl, которых ещё нет в учёте (пришли до «Студии» или пока учёт не работал).
        Пришедшие до «Студии»: последние 30 дней — «В работе», старше — «Закрыта»; новые — «Новая»."""
        if not os.path.exists(path):
            return 0
        first_run = not self.one("SELECT id FROM leads LIMIT 1")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=LEADS_ARCHIVE_DAYS)).isoformat()
        added = 0
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    lead = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(lead, dict) or self.one("SELECT id FROM leads WHERE src=?", self.lead_src(lead)):
                    continue
                if first_run:
                    old = str(lead.get("time") or "") < cutoff
                    self.add_lead(lead, "closed" if old else "work", "Пришла до запуска «Студии» — статус поставлен автоматически")
                else:
                    self.add_lead(lead)
                added += 1
        if added:
            log(f"учёт: заявок из файла добавлено {added}")
        return added

    def leads_list(self):
        rows = self.q("""SELECT l.id, l.ts, l.name, l.contact, substr(COALESCE(NULLIF(l.message_ru, ''), l.message), 1, 160) AS snippet,
                                l.model, l.model_name, l.lang, l.status, l.project_id, l.routed, p.title AS project_title, l.deleted,
                                l.partner, l.partner_id, l.handoff
                         FROM leads l LEFT JOIN projects p ON p.id=l.project_id
                         WHERE l.status != 'test' AND (l.deleted IS NULL OR l.deleted >= ?) ORDER BY l.ts DESC, l.id DESC""",
                      self._trash_cutoff())
        return {"leads": rows, "statuses": LEAD_STATUSES, "trash_days": LEADS_TRASH_DAYS}

    @staticmethod
    def _trash_cutoff():
        return (datetime.now(timezone.utc) - timedelta(days=LEADS_TRASH_DAYS)).isoformat(timespec="seconds")

    def _live_lead(self, lid):
        """Заявка, которую можно менять: есть и не удалена."""
        r = self.one("SELECT id, name, contact, status, note, project_id, deleted FROM leads WHERE id=? AND status != 'test'", int(lid or 0))
        if not r:
            raise CrmError("Заявка не найдена")
        if r["deleted"]:
            raise CrmError("Заявка удалена — сначала верните её")
        return r

    def delete_leads(self, ids, who):
        """Удалить заявки: 30 дней лежат в «Удалённых» (можно вернуть), потом имя, контакт и текст стираются.
        Сама строка остаётся отметкой, чтобы заявка не вернулась из файла leads.jsonl. Проект из заявки остаётся."""
        if not isinstance(ids, (list, tuple)):
            ids = [ids]
        done = 0
        for lid in ids[:1000]:
            try:
                r = self._live_lead(int(lid))
            except (CrmError, TypeError, ValueError):
                continue
            self.run("UPDATE leads SET deleted=?, updated=?, updated_by=? WHERE id=?", now(), now(), who, r["id"])
            self.audit(who, "delete", "lead", r["id"], {"status": r["status"]})
            done += 1
        if not done:
            raise CrmError("Заявка не найдена")
        return {"deleted": done}

    def restore_lead(self, d, who):
        lid = int(d.get("id") or 0)
        r = self.one("SELECT id FROM leads WHERE id=? AND deleted IS NOT NULL AND deleted >= ?", lid, self._trash_cutoff())
        if not r:
            raise CrmError("Заявки нет среди удалённых")
        self.run("UPDATE leads SET deleted=NULL, updated=?, updated_by=? WHERE id=?", now(), who, lid)
        self.audit(who, "restore", "lead", lid, {})
        return self.lead(lid)

    def purge_leads(self):
        """Удалённые больше 30 дней назад: имя, контакт, текст и заметки стираются (и в истории изменений)."""
        old = [r["id"] for r in self.q("""SELECT id FROM leads WHERE deleted IS NOT NULL AND deleted < ?
                                          AND (name IS NOT NULL OR contact IS NOT NULL OR message IS NOT NULL)""",
                                       self._trash_cutoff())]
        for lid in old:
            self.run("""UPDATE leads SET name=NULL, contact=NULL, message=NULL, message_ru=NULL, note=NULL, page=NULL,
                        routed=NULL, model_name=NULL WHERE id=?""", lid)
            self.run("UPDATE audit SET details=NULL WHERE entity='lead' AND entity_id=?", lid)
        return len(old)

    def lead(self, lid):
        r = self.one("""SELECT l.*, p.title AS project_title, p.number AS project_number FROM leads l
                        LEFT JOIN projects p ON p.id=l.project_id WHERE l.id=? AND (l.deleted IS NULL OR l.deleted >= ?)""",
                     int(lid or 0), self._trash_cutoff())
        if not r:
            raise CrmError("Заявка не найдена")
        r.pop("src", None)
        r["history"] = self.q("SELECT ts, who, action, details FROM audit WHERE entity='lead' AND entity_id=? ORDER BY id DESC LIMIT 20", r["id"])
        return r

    def save_lead(self, d, who):
        lid = int(d.get("id") or 0)
        row = self._live_lead(lid)
        status = d.get("status")
        if status not in dict(LEAD_STATUSES):
            raise CrmError("Неизвестный статус заявки")
        if row["project_id"] and status in LEAD_HIDDEN:
            raise CrmError("Из этой заявки уже сделан проект")
        f = dict(status=status, note=_text(d.get("note"), 2000))
        self.run("UPDATE leads SET status=?, note=?, updated=?, updated_by=? WHERE id=?", f["status"], f["note"], now(), who, lid)
        self.audit(who, "edit", "lead", lid, f)
        if (status == "spam") != (row["status"] == "spam"):     # «Спам» — отправитель блокируется, вернули — разблокируется
            try:
                import lead_filter
                (lead_filter.block_sender if status == "spam" else lead_filter.unblock_sender)(row["contact"])
            except Exception:  # noqa: BLE001 — блокировка не мешает сменить статус
                pass
        return self.lead(lid)

    def set_lead_status(self, lid, status, who):
        """Статус заявки кнопкой в сообщении бота; заметка остаётся."""
        cur = self._live_lead(lid)
        return self.save_lead({"id": lid, "status": status, "note": cur["note"] or ""}, who)

    def lead_to_project(self, d, who):
        """Из заявки — заказчик (новый или выбранный) и проект; заявка → «Стала проектом»."""
        lid = self._live_lead(d.get("lead_id"))["id"]
        c, pd = d.get("client") or {}, d.get("project") or {}
        if not _text(pd.get("title"), 200):                       # проверить до того, как создавать заказчика
            raise CrmError("Укажите название проекта")
        number = _text(pd.get("number"), 40)
        if number and self.one("SELECT id FROM projects WHERE number=?", number):
            raise CrmError(f"Номер {number} уже есть у другого проекта")
        cid = int(c.get("id") or 0)
        if cid and not self.one("SELECT id FROM clients WHERE id=?", cid):
            raise CrmError("Заказчик не найден")
        if not cid:
            cid = self.save_client(c, who)["id"]
        pr = self.save_project(dict(pd, client_id=cid), who)
        pid = pr["project"]["id"]
        self.run("UPDATE leads SET status='project', project_id=?, updated=?, updated_by=? WHERE id=?", pid, now(), who, lid)
        self.audit(who, "edit", "lead", lid, {"status": "project", "project_id": pid})
        return pr

    # ---------- этапы работ подрядчика ----------
    def save_stage(self, d, who, origin="studio"):
        """Этап подрядчика. Вносит студия или сам подрядчик (origin="contractor", из кабинета); заказчик подтверждает сумму.
        Изменилась сумма или валюта — подтверждение снимается, заказчика спросят снова."""
        sid, pid, lid = int(d.get("id") or 0), int(d.get("project_id") or 0), int(d.get("link_id") or 0)
        link = self.one("SELECT c.kind FROM project_contractors l JOIN contractors c ON c.id=l.contractor_id WHERE l.id=? AND l.project_id=?", lid, pid)
        if not link:
            raise CrmError("Подрядчик в этом проекте не найден")
        if link["kind"] == "hired":
            raise CrmError("Исполнителю студии платит студия: суммы работ на подтверждение заказчику у него не ведутся")
        day = _day(d.get("day") or today().isoformat())
        cur = _cur(d.get("currency"))
        amount = _money(d.get("amount") or 0, "Сумма заказа", allow_zero=True)
        mode = d.get("mode")
        pct = commission = None
        if mode == "pct":
            pct = _money(d.get("pct"), "Процент")
            if pct > 100:
                raise CrmError("Процент: не больше 100")
            if amount <= 0:
                raise CrmError("Чтобы посчитать бонус в процентах, укажите сумму заказа")
            commission = round(amount * pct / 100, 2)
        elif mode == "sum":
            commission = _money(d.get("commission"), "Бонус студии")
        elif mode == "none":                         # бонуса не будет (прораб заказчика — обычно так)
            commission = 0.0
        elif mode != "unknown":
            raise CrmError("Выберите, как считать бонус студии")
        if amount <= 0 and not commission:
            raise CrmError("Укажите сумму заказа или бонус студии")
        rate, src, amount_eur = self._convert(amount, cur, day, d.get("rate") if d.get("manual_rate") else None)
        f = dict(project_id=pid, link_id=lid, title=_text(d.get("title"), 120), day=day, amount=amount, currency=cur,
                 rate=rate, rate_src=src, amount_eur=amount_eur, pct=pct, commission=commission,
                 commission_eur=round(commission / rate, 2) if commission is not None else None, note=_text(d.get("note"), 1000))
        old = None
        if sid:
            old = self.one("SELECT * FROM stages WHERE id=? AND project_id=? AND link_id=?", sid, pid, lid)
            if not old:
                raise CrmError("Этап не найден")
            if old["amount"] != amount or old["currency"] != cur:      # другая сумма — заказчик подтверждает заново
                f.update(confirmed=None, confirmed_by=None, disputed=None, disputed_by=None, dispute_note=None)
            self.run(f"UPDATE stages SET {', '.join(f'{k}=?' for k in f)}, updated=? WHERE id=?", *f.values(), now(), sid)
            self.audit(who, "edit", "stage", sid, f)
        else:
            f["src"] = origin
            sid = self.run(f"INSERT INTO stages({', '.join(f)}, created_by, created, updated) VALUES({', '.join('?' * len(f))}, ?, ?, ?)",
                           *f.values(), who, now(), now())
            self.audit(who, "add", "stage", sid, f)
        self.touch(pid)
        return dict(self.project(pid), saved_id=sid, was=old)

    # ---------- заказчики и подрядчики ----------
    def save_client(self, d, who):
        cid = int(d.get("id") or 0)
        name = _text(d.get("name"), 120)
        if not name:
            raise CrmError("Укажите имя заказчика")
        pref = _text(d.get("contact_pref"), 30)
        f = dict(name=name, phone=_text(d.get("phone"), 60), email=_text(d.get("email"), 120),
                 messenger=_text(d.get("messenger"), 120), contact_pref=pref if pref in CONTACT_PREFS else "",
                 city=_text(d.get("city"), 80), note=_text(d.get("note"), 2000))
        if f["email"] and not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+$", f["email"]):
            raise CrmError("E-mail записан с ошибкой")
        return self._save("clients", "client", cid, f, who)

    def save_contractor(self, d, who):
        cid = int(d.get("id") or 0)
        name = _text(d.get("name"), 120)
        if not name:
            raise CrmError("Укажите имя подрядчика")
        pref = _text(d.get("contact_pref"), 30)
        kind = d.get("kind") if d.get("kind") in ("supplier", "hired") else None   # поставщик, исполнитель студии или подрядчик
        f = dict(name=name, kind=kind, trade=_text(d.get("trade"), 60), company=_text(d.get("company"), 120),
                 phone=_text(d.get("phone"), 60), email=_text(d.get("email"), 120), messenger=_text(d.get("messenger"), 120),
                 contact_pref=pref if pref in CONTACT_PREFS else "", city=_text(d.get("city"), 80), note=_text(d.get("note"), 2000))
        if f["email"] and not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+$", f["email"]):
            raise CrmError("E-mail записан с ошибкой")
        return self._save("contractors", "contractor", cid, f, who)

    def _save(self, table, entity, rid, f, who):
        if rid:
            if not self.one(f"SELECT id FROM {table} WHERE id=?", rid):
                raise CrmError("Запись не найдена")
            self.run(f"UPDATE {table} SET {', '.join(f'{k}=?' for k in f)}, updated=? WHERE id=?", *f.values(), now(), rid)
            self.audit(who, "edit", entity, rid, f)
        else:
            rid = self.run(f"INSERT INTO {table}({', '.join(f)}, created, updated) VALUES({', '.join('?' * len(f))}, ?, ?)",
                           *f.values(), now(), now())
            self.audit(who, "add", entity, rid, f)
        return self.one(f"SELECT * FROM {table} WHERE id=?", rid)

    def link_contractor(self, d, who):
        pid, cid = int(d.get("project_id") or 0), int(d.get("contractor_id") or 0)
        c = self.one("SELECT id, observer FROM contractors WHERE id=?", cid)
        if not self.one("SELECT id FROM projects WHERE id=?", pid) or not c:
            raise CrmError("Проект или подрядчик не найден")
        if c["observer"]:
            raise CrmError("«Разработчик ПО» — наблюдатель: он и так видит все проекты, добавлять его не нужно")
        trade, note = _text(d.get("trade"), 60), _text(d.get("note"), 500)
        side = "client" if d.get("side") == "client" else None
        lid = int(d.get("id") or 0)
        if lid:
            self.run("UPDATE project_contractors SET trade=?, note=? WHERE id=? AND project_id=?", trade, note, lid, pid)
        else:
            lid = self.run("INSERT INTO project_contractors(project_id, contractor_id, trade, note, side, created) VALUES(?, ?, ?, ?, ?, ?)",
                           pid, cid, trade, note, side, now())
        self.audit(who, "edit" if d.get("id") else "add", "link", lid, {"project_id": pid, "contractor_id": cid, "trade": trade, "side": side})
        self.touch(pid)
        return dict(self.project(pid), saved_id=lid, new=not d.get("id"))

    def set_link_side(self, d, who):
        """Чей подрядчик в проекте (решено 27.10.2026): студии (Ирины) или заказчика. Стал подрядчиком заказчика — у его
        этапов, за которые бонус ещё не получен, бонус «не платит» (прораб заказчика обычно не платит; если всё-таки
        платит — Ирина укажет бонус в этапе). Полученные бонусы остаются. Обратно к студии — этапы не меняются."""
        lid = int(d.get("id") or d.get("link_id") or 0)
        link = self.one("SELECT l.*, c.kind FROM project_contractors l JOIN contractors c ON c.id=l.contractor_id WHERE l.id=?", lid)
        if not link:
            raise CrmError("Подрядчик в этом проекте не найден")
        if link["kind"] == "hired":
            raise CrmError("Исполнителю студии платит студия — он всегда от студии")
        side = "client" if d.get("side") == "client" else None
        cleared = 0
        with self.lock:
            self.db.execute("UPDATE project_contractors SET side=? WHERE id=?", (side, lid))
            if side == "client" and link["side"] != "client":
                cleared = self.db.execute(
                    "UPDATE stages SET commission=0, commission_eur=0, pct=NULL, updated=? WHERE link_id=? AND (commission IS NULL OR commission != 0) "
                    "AND id NOT IN (SELECT stage_id FROM ops WHERE kind='commission' AND link_id=? AND stage_id IS NOT NULL)",
                    (now(), lid, lid)).rowcount
        self.audit(who, "edit", "link", lid, {"project_id": link["project_id"], "side": side, "stages_no_bonus": cleared})
        self.touch(link["project_id"])
        return dict(self.project(link["project_id"]), saved_id=lid)

    # ---------- удаление ----------
    def delete(self, entity, rid, who):
        rid = int(rid or 0)
        if entity == "op":
            o = self.one("SELECT * FROM ops WHERE id=?", rid)
            if not o:
                raise CrmError("Операция не найдена")
            self.run("DELETE FROM ops WHERE id=?", rid)
            self.audit(who, "delete", "op", rid, o)
            self.touch(o["project_id"])
            return self.project(o["project_id"])
        if entity == "link":
            link = self.one("SELECT * FROM project_contractors WHERE id=?", rid)
            if not link:
                raise CrmError("Не найдено")
            if self.one("SELECT id FROM stages WHERE link_id=? LIMIT 1", rid) or self.one("SELECT id FROM ops WHERE link_id=? LIMIT 1", rid):
                raise CrmError("У подрядчика в этом проекте есть этапы или полученные бонусы — сначала удалите их")
            self.run("DELETE FROM project_contractors WHERE id=?", rid)
            if not self.one("SELECT id FROM project_contractors WHERE project_id=? AND contractor_id=?", link["project_id"], link["contractor_id"]):
                self.run("DELETE FROM project_crew WHERE project_id=? AND crew_id IN (SELECT id FROM crew WHERE contractor_id=?)",
                         link["project_id"], link["contractor_id"])
            self.audit(who, "delete", "link", rid, link)
            return self.project(link["project_id"])
        if entity == "stage":
            st = self.one("SELECT * FROM stages WHERE id=?", rid)
            if not st:
                raise CrmError("Этап не найден")
            self.run("UPDATE ops SET stage_id=NULL WHERE stage_id=?", rid)      # полученные бонусы остаются за подрядчиком
            self.run("DELETE FROM stages WHERE id=?", rid)
            self.audit(who, "delete", "stage", rid, st)
            self.touch(st["project_id"])
            return self.project(st["project_id"])
        if entity == "file":
            f = self.one("SELECT * FROM files WHERE id=?", rid)
            if not f:
                raise CrmError("Файл не найден")
            trash = os.path.join(self.trash_dir, today().isoformat())   # 30 дней в корзине, потом удаляется
            for p in (f["path"], f["thumb"]):
                if p:
                    try:
                        os.makedirs(trash, exist_ok=True)
                        os.replace(os.path.join(self.files_dir, p), os.path.join(trash, f"{f['project_id']}-{os.path.basename(p)}"))
                    except OSError:
                        pass
            self.run("DELETE FROM files WHERE id=?", rid)
            self.audit(who, "delete", "file", rid, f)
            return self.project(f["project_id"])
        if entity == "lead":
            return self.delete_leads([rid], who)
        if entity == "order":
            o = self.one("SELECT * FROM orders WHERE id=?", rid)
            if not o:
                raise CrmError("Товар не найден")
            if self.one("SELECT id FROM ops WHERE order_id=? LIMIT 1", rid):
                raise CrmError("За этот товар есть оплаты — удалите их или отметьте товар «Отменён»")
            self.run("DELETE FROM orders WHERE id=?", rid)
            self.audit(who, "delete", "order", rid, o)
            if o["file_id"]:                                        # фото товара — в корзину
                try:
                    self.delete("file", o["file_id"], who)
                except CrmError:
                    pass
            self.touch(o["project_id"])
            return self.project(o["project_id"])
        if entity == "service":
            s = self.one("SELECT * FROM services WHERE id=?", rid)
            if not s:
                raise CrmError("Услуга не найдена")
            if self.one("SELECT id FROM ops WHERE service_id=? LIMIT 1", rid):
                raise CrmError("За эту услугу есть оплаты — удалите их или отметьте услугу «Остановлена» / «Отменена»")
            self.run("DELETE FROM services WHERE id=?", rid)
            self.audit(who, "delete", "service", rid, s)
            self.touch(s["project_id"])
            return self.project(s["project_id"])
        if entity == "project":
            p = self.one("SELECT * FROM projects WHERE id=?", rid)
            if not p:
                raise CrmError("Проект не найден")
            if any(self.one(f"SELECT id FROM {t} WHERE project_id=? LIMIT 1", rid) for t in ("ops", "files", "orders", "services", "messages")):
                raise CrmError("В проекте есть операции, товары, услуги, переписка или файлы — удалить нельзя. Поставьте статус «Отменён».")
            self.run("DELETE FROM project_contractors WHERE project_id=?", rid)
            self.run("DELETE FROM project_clients WHERE project_id=?", rid)
            self.run("DELETE FROM project_crew WHERE project_id=?", rid)
            self.run("DELETE FROM project_assistants WHERE project_id=?", rid)
            for t in self.q("SELECT id FROM threads WHERE project_id=?", rid):
                self.run("DELETE FROM thread_members WHERE thread_id=?", t["id"])
                self.run("DELETE FROM thread_read WHERE thread_id=?", t["id"])
            self.run("DELETE FROM threads WHERE project_id=?", rid)
            self.run("DELETE FROM projects WHERE id=?", rid)
            self.audit(who, "delete", "project", rid, p)
            return {}
        if entity == "client":
            c = self.one("SELECT * FROM clients WHERE id=?", rid)
            if not c:
                raise CrmError("Заказчик не найден")
            if self.one("SELECT id FROM projects WHERE client_id=? LIMIT 1", rid) or \
                    self.one("SELECT id FROM project_clients WHERE client_id=? LIMIT 1", rid):
                raise CrmError("У заказчика есть проекты — сначала уберите его из проектов")
            self.run("DELETE FROM clients WHERE id=?", rid)
            self.audit(who, "delete", "client", rid, c)
            return {}
        if entity == "contractor":
            c = self.one("SELECT * FROM contractors WHERE id=?", rid)
            if not c:
                raise CrmError("Подрядчик не найден")
            if self.one("SELECT id FROM project_contractors WHERE contractor_id=? LIMIT 1", rid):
                raise CrmError("Подрядчик указан в проектах — сначала уберите его оттуда")
            self.run("UPDATE crew SET removed=?, tg_id=NULL WHERE contractor_id=? AND removed IS NULL", now(), rid)
            self.run("DELETE FROM contractors WHERE id=?", rid)
            self.audit(who, "delete", "contractor", rid, c)
            return {}
        raise CrmError("Неизвестно, что удалять")

    # ---------- файлы ----------
    def disk(self):
        used = 0
        for root, _, names in os.walk(self.files_dir):
            for n in names:
                try:
                    used += os.path.getsize(os.path.join(root, n))
                except OSError:
                    pass
        try:
            free = shutil.disk_usage(self.files_dir if os.path.isdir(self.files_dir) else APP).free
        except OSError:
            free = None
        return {"used": used, "free": free}

    def add_file(self, pid, category, name, stream, size, mime, who, tg_file_id=None, note=""):
        """Сохранить файл проекта. stream — объект с read(); size — сколько байт читать."""
        pid = int(pid or 0)
        if not self.one("SELECT id FROM projects WHERE id=?", pid):
            raise CrmError("Проект не найден")
        if category not in dict(FILE_CATS + EXTRA_CATS):
            raise CrmError("Неизвестный раздел файлов")
        if size <= 0:
            raise CrmError("Пустой файл")
        if size > FILE_MAX:
            raise CrmError(f"Файл больше {FILE_MAX // 2**20} МБ — пришлите его в бот как документ или разделите")
        os.makedirs(os.path.join(self.files_dir, str(pid)), exist_ok=True)
        if shutil.disk_usage(self.files_dir).free - size < MIN_FREE:
            raise CrmError("На сервере заканчивается место — файл не сохранён. Напишите разработчику.")
        name = _text(os.path.basename(name or "файл"), 150) or "файл"
        fid = self.run("INSERT INTO files(project_id, category, name, mime, size, tg_file_id, note, created_by, created) "
                       "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)", pid, category, name, _text(mime, 100), 0, tg_file_id, _text(note, 500), who, now())
        ext = os.path.splitext(name)[1].lower()
        ext = ext if re.fullmatch(r"\.[a-z0-9]{1,8}", ext) else ""
        rel = f"{pid}/{fid}{ext}"
        full = os.path.join(self.files_dir, rel)
        got = 0
        try:
            with open(full + ".part", "wb") as out:
                while got < size:
                    chunk = stream.read(min(1024 * 1024, size - got))
                    if not chunk:
                        break
                    out.write(chunk)
                    got += len(chunk)
            if got != size:
                raise CrmError("Файл пришёл не полностью — попробуйте ещё раз")
            os.replace(full + ".part", full)
        except BaseException:
            self.run("DELETE FROM files WHERE id=?", fid)
            try:
                os.remove(full + ".part")
            except OSError:
                pass
            raise
        self.run("UPDATE files SET path=?, size=? WHERE id=?", rel, got, fid)
        self.audit(who, "add", "file", fid, {"project_id": pid, "category": category, "name": name, "size": got})
        self.touch(pid)
        return self.file_view(self.one("SELECT * FROM files WHERE id=?", fid))

    def add_tg_only(self, pid, category, name, size, mime, who, tg_file_id):
        """Файл больше 20 МБ, присланный в бот: Telegram не отдаёт такие боту на скачивание — храним ссылку на него
        в Telegram; в «Студии» его можно прислать себе в чат."""
        pid = int(pid or 0)
        if not self.one("SELECT id FROM projects WHERE id=?", pid) or category not in dict(FILE_CATS + EXTRA_CATS):
            raise CrmError("Проект или раздел не найден")
        fid = self.run("INSERT INTO files(project_id, category, name, mime, size, tg_file_id, created_by, created) "
                       "VALUES(?, ?, ?, ?, ?, ?, ?, ?)", pid, category, _text(name, 150) or "файл", _text(mime, 100), int(size or 0),
                       tg_file_id, who, now())
        self.audit(who, "add", "file", fid, {"project_id": pid, "category": category, "name": name, "telegram": True})
        self.touch(pid)
        return self.file_view(self.one("SELECT * FROM files WHERE id=?", fid))

    def set_thumb(self, fid, data):
        f = self.one("SELECT * FROM files WHERE id=?", int(fid))
        if not f:
            raise CrmError("Файл не найден")
        if not data or len(data) > 2 * 1024 * 1024:
            raise CrmError("Неподходящее превью")
        rel = f"{f['project_id']}/{f['id']}-thumb.jpg"
        with open(os.path.join(self.files_dir, rel), "wb") as out:
            out.write(data)
        self.run("UPDATE files SET thumb=? WHERE id=?", rel, f["id"])
        return self.file_view(self.one("SELECT * FROM files WHERE id=?", f["id"]))

    def set_file_vis(self, d, who):
        """Кто видит файл (решает студия): see_client / see_crew — 1 видят, 0 не видят, None — по умолчанию
        (у файлов студии — по разделу, у файлов подрядчиков — как выбрал подрядчик, у вложений разговора — только участники)."""
        f = self.one("SELECT * FROM files WHERE id=?", int(d.get("id") or 0))
        if not f:
            raise CrmError("Файл не найден")
        vals = []
        for k in ("see_client", "see_crew"):
            v = d.get(k, f[k])
            vals.append(None if v in (None, "", "default") else 1 if str(v) in ("1", "True", "true") else 0)
        # решила про заказчика (да или нет) — документ больше не ждёт её решения
        self.run("UPDATE files SET see_client=?, see_crew=?, review=CASE WHEN ? IS NULL THEN review ELSE NULL END WHERE id=?",
                 vals[0], vals[1], vals[0], f["id"])
        self.audit(who, "edit", "file", f["id"], {"project_id": f["project_id"], "see_client": vals[0], "see_crew": vals[1]})
        return self.file_view(self.one("SELECT * FROM files WHERE id=?", f["id"]))

    def move_file(self, fid, category, who, by_tg=None):
        if category not in dict(FILE_CATS):
            raise CrmError("Неизвестный раздел файлов")
        f = self.one("SELECT * FROM files WHERE id=?", int(fid))
        if not f:
            raise CrmError("Файл не найден")
        self.run("UPDATE files SET category=?, pos=NULL WHERE id=?", category, f["id"])     # в новом разделе — по номеру
        if f["category"] not in NOTIFY_CATS:     # перенесла из «До» или «Другое» в документацию — заказчику сообщение
            self.note_new_file(dict(f, category=category), by_tg)
        self.audit(who, "edit", "file", f["id"], {"project_id": f["project_id"], "category": category})
        return self.project(f["project_id"])

    def set_file_order(self, d, who):
        """Новый порядок файлов раздела (решено 27.10.2026): ids — файлы раздела в том порядке, как их расставила Ирина.
        Файлы раздела, которых нет в списке (добавили, пока она передвигала), — после них, по номеру.
        reset — раздел снова по порядковым номерам в именах файлов (как до того, как его расставляли)."""
        pid, cat = int(d.get("project_id") or 0), d.get("category")
        if not self.one("SELECT id FROM projects WHERE id=?", pid):
            raise CrmError("Проект не найден")
        if cat not in dict(FILE_CATS + [("work", "")]):
            raise CrmError("Неизвестный раздел файлов")
        if d.get("reset"):
            self.run("UPDATE files SET pos=NULL WHERE project_id=? AND category=?", pid, cat)
            self.audit(who, "edit", "file", 0, {"project_id": pid, "category": cat, "order": "по номерам"})
            return self.project(pid)
        try:
            ids = [int(x) for x in (d.get("ids") or [])]
        except (TypeError, ValueError):
            raise CrmError("Неверный порядок файлов") from None
        have = [r["id"] for r in sort_files(self.q("SELECT id, pos, name, title FROM files WHERE project_id=? AND category=?", pid, cat))]
        known = set(have)
        order = list(dict.fromkeys(i for i in ids if i in known))
        if not order:
            raise CrmError("В этом разделе нет таких файлов")
        rest = [i for i in have if i not in set(order)]
        with self.lock:
            for n, i in enumerate(order, 1):
                self.db.execute("UPDATE files SET pos=? WHERE id=?", (n, i))
            for i in rest:
                self.db.execute("UPDATE files SET pos=NULL WHERE id=?", (i,))
        self.audit(who, "edit", "file", order[0], {"project_id": pid, "category": cat, "order": order[:200]})
        return self.project(pid)

    # ---------- новые файлы — сообщение заказчику (решено 27.10.2026) ----------
    def note_new_file(self, f, by_tg=None):
        """Файл студии в разделе, о котором сообщаем заказчику, — в очередь; отправляет бот (portal_file_notes),
        когда новых файлов в проекте нет FILE_NOTE_QUIET секунд. Файлы подрядчиков, исполнителей и сотрудников
        сюда не попадают: о них заказчику сообщение, когда Ирина покажет."""
        if not f or f.get("category") not in NOTIFY_CATS or f.get("owner_kind") or f.get("thread_id"):
            return False
        self.run("INSERT OR IGNORE INTO file_notes(file_id, project_id, by_tg, created) VALUES(?, ?, ?, ?)",
                 int(f["id"]), int(f["project_id"]), int(by_tg) if by_tg else None, time.time())
        return True

    def due_file_notes(self, at=None, quiet=FILE_NOTE_QUIET, most=FILE_NOTE_MAX):
        """Проекты, где пора сообщить о новых файлах: {project_id: [файлы по порядку раздела]}; из очереди они
        убираются (удалённые за это время файлы — просто пропадают). by_tg — кто добавил (ему не сообщаем)."""
        at = time.time() if at is None else at
        out = {}
        for r in self.q("SELECT project_id, MIN(created) AS a, MAX(created) AS b FROM file_notes GROUP BY project_id"):
            if r["b"] > at - quiet and r["a"] > at - most:
                continue
            pid = r["project_id"]
            with self.lock:
                rows = sort_files([dict(x) for x in self.db.execute(
                    "SELECT f.*, n.by_tg AS note_by FROM file_notes n JOIN files f ON f.id=n.file_id WHERE n.project_id=?", (pid,)).fetchall()])
                self.db.execute("DELETE FROM file_notes WHERE project_id=? AND created<=?", (pid, r["b"]))
            if rows:
                out[pid] = rows
        return out

    def sign(self, fid, variant, exp=None):
        exp = exp or int(time.time()) + LINK_HOURS * 3600
        mac = hmac.new(self.secret.encode(), f"{fid}:{variant}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        return f"/api/crm/file?id={fid}&v={variant}&e={exp}&s={mac}"

    def check_sig(self, fid, variant, exp, sig):
        try:
            if int(exp) < time.time():
                return False
        except ValueError:
            return False
        good = hmac.new(self.secret.encode(), f"{fid}:{variant}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        return hmac.compare_digest(good, sig or "")

    def file_view(self, f):
        v = dict(f)
        image = (f.get("mime") or "").startswith("image/")
        v["url"] = self.sign(f["id"], "o") if f.get("path") else None
        v["thumb_url"] = self.sign(f["id"], "t") if f.get("thumb") else (v["url"] if image and (f.get("size") or 0) < 1.5 * 2**20 else None)
        v["image"] = image
        v.pop("path", None)
        v.pop("thumb", None)
        return v

    def file_path(self, fid, variant):
        f = self.one("SELECT * FROM files WHERE id=?", int(fid))
        if not f:
            return None, None
        rel = f["thumb"] if variant == "t" else f["path"]
        return (os.path.join(self.files_dir, rel) if rel else None), f      # без пути — файл хранится в Telegram

    # ---------- деньги ----------
    @staticmethod
    def period_bounds(period, d=None):
        d = d or today()
        if period == "month":
            a = d.replace(day=1)
        elif period == "quarter":
            a = d.replace(month=(d.month - 1) // 3 * 3 + 1, day=1)
        elif period == "year":
            a = d.replace(month=1, day=1)
        else:
            return None, None
        return a.isoformat(), d.isoformat()

    def income_rows(self, a=None, b=None):
        """Операции за период (день a … b, любой край можно не задавать) и наценка товаров заказчиков — строкой
        вида «перепродажа» в день заказа (у отменённых и без закупки наценки нет)."""
        cond, args = [], []
        if a:
            cond.append("o.day>=?")
            args.append(a)
        if b:
            cond.append("o.day<=?")
            args.append(b)
        where = ("WHERE " + " AND ".join(cond)) if cond else ""
        rows = self.q(f"""SELECT o.*, p.city, p.tariff, p.title AS project_title, p.number AS project_number
                          FROM ops o JOIN projects p ON p.id=o.project_id {where}""", *args)
        for o in self.q(f"""SELECT o.id, o.project_id, o.day, o.title, o.price_eur, o.buy_eur, p.city, p.tariff
                            FROM orders o JOIN projects p ON p.id=o.project_id
                            {where + ' AND' if where else 'WHERE'} o.cancelled IS NULL AND o.buy_eur IS NOT NULL""", *args):
            rows.append({"kind": "resale", "day": o["day"], "project_id": o["project_id"], "city": o["city"], "tariff": o["tariff"],
                         "amount_eur": o["price_eur"], "buy_eur": o["buy_eur"], "title": o["title"], "is_order": True})
        return rows

    def stats(self, period="month"):
        """Доход за период (по дате операции): оплаты заказчиков, бонусы, наценка; по месяцам, городам, тарифам;
        сколько заказчики ещё должны по проектам в работе."""
        a, b = self.period_bounds(period)
        args = (a, b) if a else ()
        rows = self.income_rows(a, b)
        n_ops = sum(1 for o in rows if not o.get("is_order"))

        def income(o):              # оплата за товар — не доход (доход — наценка товара, она здесь отдельной строкой)
            return 0.0 if o.get("order_id") else o["amount_eur"] - (o["buy_eur"] or 0) if o["kind"] == "resale" else o["amount_eur"]
        tot = {"payment": 0.0, "commission": 0.0, "resale": 0.0}
        cities, tariffs, projects = {}, {}, {}
        changes = {}                                 # смена пакета: доход до смены — старому пакету, после — новому
        for c in self.q("SELECT * FROM tariff_changes ORDER BY day, id"):
            changes.setdefault(c["project_id"], []).append(c)

        def tariff_on(o):
            ch = changes.get(o["project_id"])
            if not ch:
                return o["tariff"]
            t = ch[0]["old_tariff"]
            for c in ch:
                if o["day"] >= c["day"]:
                    t = c["new_tariff"]
            return t
        for o in rows:
            x = income(o)
            if not x:
                continue
            tot[o["kind"]] += x
            cities[o["city"] or "—"] = cities.get(o["city"] or "—", 0) + x
            tk = tariff_on(o) or "—"
            tariffs[tk] = tariffs.get(tk, 0) + x
            projects[o["project_id"]] = projects.get(o["project_id"], 0) + x
        # смены пакета за период: сколько проектов и на сколько выросли договоры
        ups = {}
        for c in self.q("SELECT * FROM tariff_changes" + (" WHERE day>=? AND day<=?" if a else ""), *args):
            u = ups.setdefault((c["old_tariff"] or "—", c["new_tariff"] or "—"), {"from": c["old_tariff"] or "—", "to": c["new_tariff"] or "—",
                                                                                  "n": 0, "plus": 0.0})
            u["n"] += 1
            u["plus"] += (c["new_total"] or 0) - (c["old_total"] or 0)
        # по месяцам: последние 12 месяцев, за «всё время» — с первой операции
        first = self.one("SELECT MIN(day) AS d FROM ops")["d"]
        t = today()
        y, mo = divmod(t.year * 12 + t.month - 1 - 11, 12)          # первое число месяца 11 месяцев назад
        start = date.fromisoformat(first).replace(day=1) if period == "all" and first else date(y, mo + 1, 1)
        months, m = [], start
        while m <= t:
            months.append(m.strftime("%Y-%m"))
            m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        by_month = {k: {"month": k, "payment": 0.0, "commission": 0.0, "resale": 0.0} for k in months}
        for o in self.income_rows(start.isoformat(), None):
            k = o["day"][:7]
            if k in by_month:
                by_month[k][o["kind"]] += income(o)
        months_out = []
        for k in months:
            r = by_month[k]
            months_out.append({kk: round(v, 2) if isinstance(v, float) else v for kk, v in r.items()}
                              | {"total": round(r["payment"] + r["commission"] + r["resale"], 2)})
        all_rows = self.project_rows()
        owing = [p for p in all_rows if p["status"] in ("active", "paused") and p["client_debt"] > 0.005]
        names = {p["id"]: p for p in all_rows}
        # подрядчики должны бонусы: по всем проектам, кроме отменённых; по подрядчику и его проектам
        people = {c["id"]: c for c in self.q("SELECT id, name, trade FROM contractors")}
        owe = {}
        for m in self.link_money().values():
            pr = names.get(m["project_id"])
            if m["debt"] <= 0 or not pr or pr["status"] == "cancelled":
                continue
            c = owe.setdefault(m["contractor_id"], {"id": m["contractor_id"], "name": (people.get(m["contractor_id"]) or {}).get("name", "—"),
                                                     "trade": m["trade"] or (people.get(m["contractor_id"]) or {}).get("trade") or "",
                                                     "debt_eur": 0.0, "projects": []})
            c["debt_eur"] += m["debt_eur"]
            c["projects"].append({"id": pr["id"], "number": pr["number"] or "", "title": pr["title"], "debt": m["debt"],
                                  "currency": m["currency"], "debt_eur": m["debt_eur"]})
        owe_list = sorted(owe.values(), key=lambda c: -c["debt_eur"])
        # бонусы за период — от кого
        sources = {}
        for o in rows:
            if o["kind"] == "commission":
                k = o["counterparty"] or "Не указано"
                sources[k] = sources.get(k, 0) + o["amount_eur"]
        top = sorted(projects.items(), key=lambda kv: -kv[1])[:8]
        new = self.q("SELECT COUNT(*) AS n, COALESCE(SUM(total_eur), 0) AS s FROM projects WHERE " +
                     ("COALESCE(started, substr(created, 1, 10))>=? AND COALESCE(started, substr(created, 1, 10))<=?" if a else "1"), *args)[0]
        return {
            "period": period, "from": a, "to": b,
            "income": round(sum(tot.values()), 2), "payments": round(tot["payment"], 2),
            "bonuses": round(tot["commission"], 2), "margin": round(tot["resale"], 2), "ops": n_ops,
            "projects_with_income": len(projects), "new_projects": new["n"], "new_contracts": round(new["s"], 2),
            "months": months_out,
            "by_city": [[k, round(v, 2)] for k, v in sorted(cities.items(), key=lambda kv: -kv[1]) if abs(v) > 0.005],
            "by_tariff": [[k, round(v, 2)] for k, v in sorted(tariffs.items(), key=lambda kv: -kv[1]) if abs(v) > 0.005],
            "tariff_ups": [dict(u, plus=round(u["plus"], 2)) for u in sorted(ups.values(), key=lambda u: -u["plus"])],
            "top_projects": [[names[k]["number"] or "", names[k]["title"], round(v, 2), k] for k, v in top if k in names],
            "owing": round(sum(p["client_debt"] for p in owing), 2),
            "owing_projects": [[p["number"] or "", p["title"], p["client_debt"], p["id"]] for p in sorted(owing, key=lambda p: -p["client_debt"])[:10]],
            "contractors_owe": round(sum(c["debt_eur"] for c in owe_list), 2),
            "owe_contractors": [dict(c, debt_eur=round(c["debt_eur"], 2)) for c in owe_list[:15]],
            "bonus_sources": [[k, round(v, 2)] for k, v in sorted(sources.items(), key=lambda kv: -kv[1])[:8] if abs(v) > 0.005],
        }

    # ---------- переписка: сколько непрочитанного у студии ----------
    # студия читает переписку вместе (tg_id 0 в chat_read): открыла Ирина — прочитано у студии
    def unread_for_studio(self):
        """Непрочитанные у студии по проектам: все разговоры (и те, где заказчик пишет подрядчику — студия их видит)."""
        return {r["project_id"]: r["n"] for r in self.q("""
            SELECT m.project_id, COUNT(*) AS n FROM messages m LEFT JOIN thread_read r ON r.thread_id=m.thread_id AND r.tg_id=0
            WHERE m.author_kind!='studio' AND m.deleted IS NULL AND m.id > COALESCE(r.last_id, 0) GROUP BY m.project_id""")}

    def chat_summary(self, pid):
        last = self.one("SELECT * FROM messages WHERE project_id=? AND deleted IS NULL ORDER BY id DESC LIMIT 1", int(pid))
        n = self.one("SELECT COUNT(*) AS n FROM messages WHERE project_id=? AND deleted IS NULL", int(pid))["n"]
        out = {"count": n, "unread": self.unread_for_studio().get(int(pid), 0), "last": None,
               "threads": self.one("SELECT COUNT(*) AS n FROM threads WHERE project_id=?", int(pid))["n"]}
        if last:
            try:
                ru = (json.loads(last["tr"] or "{}") or {}).get("ru")
            except ValueError:
                ru = None
            out["last"] = {"author_kind": last["author_kind"], "author_name": last["author_name"], "created": last["created"],
                           "text": ru or last["text"] or "", "file": bool(last["file_id"])}
        return out

    # ---------- всё для приложения ----------
    def state(self):
        projects = self.project_rows()
        clients = self.q("SELECT * FROM clients ORDER BY name COLLATE NOCASE")
        by_client = {}
        for p in projects:
            if p["client_id"]:
                by_client.setdefault(p["client_id"], []).append(p["id"])
        for x in self.q("SELECT project_id, client_id FROM project_clients ORDER BY id"):
            if x["project_id"] not in by_client.get(x["client_id"], []):
                by_client.setdefault(x["client_id"], []).append(x["project_id"])
        unread = self.unread_for_studio()
        for p in projects:
            p["unread"] = unread.get(p["id"], 0)
        for c in clients:
            c["projects"] = by_client.get(c["id"], [])
        contractors = self.q("""SELECT c.*, (SELECT COUNT(*) FROM project_contractors l WHERE l.contractor_id=c.id) AS projects
                                FROM contractors c ORDER BY c.observer IS NOT NULL, c.kind IS NOT NULL, c.trade, c.name COLLATE NOCASE""")
        crew = self.q("SELECT id, contractor_id, name, position, phone, tg_id, tg_name, tg_since FROM crew WHERE removed IS NULL ORDER BY name")
        for c in contractors:
            c["crew"] = [w for w in crew if w["contractor_id"] == c["id"]]
        status = {p["id"]: p["status"] for p in projects}
        links = []
        for m in self.link_money().values():
            links.append({k: m[k] for k in ("link_id", "project_id", "contractor_id", "trade", "currency", "expected", "received",
                                            "debt", "expected_eur", "received_eur", "debt_eur", "unknown", "order", "order_eur")}
                         | {"stages": len(m["stages"])})
        for c in contractors:
            mine = [x for x in links if x["contractor_id"] == c["id"] and status.get(x["project_id"]) != "cancelled"]
            c["debt_eur"] = round(sum(x["debt_eur"] for x in mine), 2)
            c["received_eur"] = round(sum(x["received_eur"] for x in mine), 2)
        assistants = self.q("SELECT id, name, position, phone, email, tg_id, tg_name, tg_since, note FROM assistants WHERE removed IS NULL "
                            "ORDER BY name COLLATE NOCASE")
        on = {}
        for x in self.q("SELECT x.assistant_id, x.project_id FROM project_assistants x JOIN projects p ON p.id=x.project_id "
                        "WHERE p.status != 'cancelled'"):
            on.setdefault(x["assistant_id"], []).append(x["project_id"])
        for a in assistants:
            a["projects"] = on.get(a["id"], [])
            inv = self.one("SELECT expires FROM invites WHERE kind='assistant' AND ref_id=? AND used_by IS NULL AND expires > ?", a["id"], now())
            a["invite_until"] = inv["expires"] if inv else None
        cities = sorted({x for x in [p["city"] for p in projects] + [c["city"] for c in clients] + [c["city"] for c in contractors] if x})
        leads_new = self.one("SELECT COUNT(*) AS n FROM leads WHERE status='new' AND deleted IS NULL")["n"]
        return {"projects": projects, "clients": clients, "contractors": contractors, "links": links, "cities": cities, "assistants": assistants,
                "lists": self.lists(), "disk": self.disk(), "leads_new": leads_new, "unread": sum(unread.values())}

    # ---------- уборка раз в день ----------
    def backup_if_due(self, log=print):
        """Раз в день: из корзины удаляются файлы, удалённые больше 30 дней назад, и старые удалённые заявки.
        (Резервные копии баз — backups.py: архив на сервере за 7 дней.)"""
        d = today().isoformat()
        if self.setting("backup_day") == d:
            return False
        if os.path.isdir(self.trash_dir):
            old = (today() - timedelta(days=TRASH_KEEP)).isoformat()
            for day_dir in os.listdir(self.trash_dir):
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day_dir) and day_dir < old:
                    shutil.rmtree(os.path.join(self.trash_dir, day_dir), ignore_errors=True)
        self.purge_leads()
        self.setting("backup_day", d)
        return True


if __name__ == "__main__":
    if "--backup-now" in sys.argv:          # архив данных сейчас — то же, что python3 backups.py --now
        import backups
        sys.exit(0 if backups.make_data_zip() else 1)
    else:
        print(__doc__)
