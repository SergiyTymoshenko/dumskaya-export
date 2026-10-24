#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Курсы валют к евро на дату — для учёта проектов студии (crm.py): итог и баланс проекта в евро,
а оплаты и закупки могут быть в другой валюте.

Источники — центробанки:
  • Европейский центральный банк — справочные курсы евро (USD, PLN и др.): за последние
    90 дней и вся история с 1999 года (файлы ЕЦБ, скачиваются по мере надобности);
  • Национальный банк Украины — гривна (ЕЦБ её не публикует) и валюты, которых нет у ЕЦБ (AED, KZT…):
    курс к гривне, к евро — через курс евро НБУ на ту же дату.
ЕЦБ не публикует курсы в выходные и праздники — берётся последний курс до этой даты.
Курсы хранятся в ~/dumskaya/fx.db: каждый скачивается один раз. Только стандартная библиотека Python 3.

   python3 fx.py UAH 2026-10-20        — курс с сервера: сколько гривен в одном евро
"""
import csv
import io
import json
import os
import re
import sqlite3
import sys
import threading
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta

FX_DB = os.environ.get("FX_DB", os.path.expanduser("~/dumskaya/fx.db"))
ECB_DAILY = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
ECB_HIST = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
NBU = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?date={}&json"
TIMEOUT = 15

# валюты в формах учёта: код, знак, название
# (решено 24.10.2026: студия работает с евро, гривной, долларом и злотым; курс других валют fx.py тоже умеет)
CURRENCIES = [("EUR", "€", "евро"), ("UAH", "₴", "гривна"), ("USD", "$", "доллар США"), ("PLN", "zł", "польский злотый")]
CODES = [c for c, _, _ in CURRENCIES]
# валюты, которые публикует ЕЦБ (остальные — через НБУ)
ECB_CURS = {"USD", "JPY", "BGN", "CZK", "DKK", "GBP", "HUF", "PLN", "RON", "SEK", "CHF", "ISK", "NOK", "TRY", "AUD", "BRL",
            "CAD", "CNY", "HKD", "IDR", "ILS", "INR", "KRW", "MXN", "MYR", "NZD", "PHP", "SGD", "THB", "ZAR"}


class RateError(Exception):
    pass


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "dumskaya-design.com studio accounting"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


class Rates:
    def __init__(self, path=FX_DB, fetch=_get, today=date.today):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.lock = threading.Lock()
        self.fetch, self.today = fetch, today
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS fx (day TEXT, cur TEXT, rate REAL, src TEXT, PRIMARY KEY (day, cur, src));
                CREATE TABLE IF NOT EXISTS fx_meta (key TEXT PRIMARY KEY, value TEXT);""")

    # ---------- ЕЦБ ----------
    def _ecb_store(self, rows):
        with self.lock:
            self.db.execute("BEGIN")
            self.db.executemany("INSERT OR REPLACE INTO fx(day, cur, rate, src) VALUES(?, ?, ?, 'ECB')", rows)
            self.db.execute("COMMIT")

    def _ecb_90d(self):
        root = ET.fromstring(self.fetch(ECB_DAILY))
        rows = []
        for cube in root.iter():
            if cube.get("time"):
                day = cube.get("time")
                rows += [(day, c.get("currency"), float(c.get("rate"))) for c in cube if c.get("currency")]
        self._ecb_store(rows)
        self._meta("ecb_90d", self.today().isoformat())

    def _ecb_history(self):
        z = zipfile.ZipFile(io.BytesIO(self.fetch(ECB_HIST)))
        text = z.read(z.namelist()[0]).decode("utf-8")
        rows = []
        reader = csv.reader(io.StringIO(text))
        head = [h.strip() for h in next(reader)]
        for line in reader:
            if not line or not re.match(r"\d{4}-\d{2}-\d{2}", line[0]):
                continue
            for cur, v in zip(head[1:], line[1:]):
                v = v.strip()
                if cur and v and v != "N/A":
                    rows.append((line[0], cur, float(v)))
        self._ecb_store(rows)
        self._meta("ecb_hist", self.today().isoformat())

    def _meta(self, key, value=None):
        with self.lock:
            if value is None:
                r = self.db.execute("SELECT value FROM fx_meta WHERE key=?", (key,)).fetchone()
                return r[0] if r else None
            self.db.execute("INSERT OR REPLACE INTO fx_meta(key, value) VALUES(?, ?)", (key, value))

    def _ecb_lookup(self, cur, d):
        with self.lock:
            return self.db.execute("SELECT day, rate FROM fx WHERE src='ECB' AND cur=? AND day<=? AND day>=? ORDER BY day DESC LIMIT 1",
                                   (cur, d.isoformat(), (d - timedelta(days=10)).isoformat())).fetchone()

    def ecb(self, cur, d):
        """(курс, дата курса) у ЕЦБ: последний опубликованный не позже d."""
        got = self._ecb_lookup(cur, d)
        recent = (self.today() - d).days <= 85
        stale = got is None or (recent and got[0] < d.isoformat() and self._meta("ecb_90d") != self.today().isoformat())
        if stale:
            try:
                if recent:
                    self._ecb_90d()
                elif self._meta("ecb_hist") is None:
                    self._ecb_history()
            except Exception as e:  # noqa: BLE001
                if got is None:
                    raise RateError(f"ЕЦБ не ответил: {type(e).__name__}") from None
            got = self._ecb_lookup(cur, d) or got
        if got is None:
            raise RateError(f"у ЕЦБ нет курса {cur} на {d.isoformat()}")
        return got[1], got[0]

    # ---------- НБУ ----------
    def nbu(self, cur, d):
        """Гривен за единицу валюты у НБУ на дату (НБУ устанавливает курс и на выходные)."""
        d = min(d, self.today())
        with self.lock:
            r = self.db.execute("SELECT rate FROM fx WHERE src='NBU' AND cur=? AND day=?", (cur, d.isoformat())).fetchone()
        if r:
            return r[0]
        try:
            data = json.loads(self.fetch(NBU.format(d.strftime("%Y%m%d"))))
        except Exception as e:  # noqa: BLE001
            raise RateError(f"НБУ не ответил: {type(e).__name__}") from None
        rows = [(d.isoformat(), x["cc"], float(x["rate"])) for x in data if x.get("cc") and x.get("rate")]
        with self.lock:
            self.db.executemany("INSERT OR REPLACE INTO fx(day, cur, rate, src) VALUES(?, ?, ?, 'NBU')", rows)
        for day, c, rate in rows:
            if c == cur:
                return rate
        raise RateError(f"у НБУ нет курса {cur} на {d.isoformat()}")

    # ---------- курс к евро ----------
    def rate(self, cur, d=None):
        """Сколько единиц валюты в одном евро на дату d: (курс, дата курса, источник)."""
        cur = (cur or "EUR").upper()
        d = d or self.today()
        if isinstance(d, str):
            d = date.fromisoformat(d)
        if cur == "EUR":
            return 1.0, d.isoformat(), ""
        if cur in ECB_CURS:
            r, used = self.ecb(cur, min(d, self.today()))
            return r, used, "ЕЦБ"
        eur = self.nbu("EUR", d)
        if cur == "UAH":
            return eur, min(d, self.today()).isoformat(), "НБУ"
        return eur / self.nbu(cur, d), min(d, self.today()).isoformat(), "НБУ"


if __name__ == "__main__":
    cur = (sys.argv[1] if len(sys.argv) > 1 else "UAH").upper()
    day = sys.argv[2] if len(sys.argv) > 2 else None
    r, used, src = Rates().rate(cur, day)
    print(f"1 € = {r:.4f} {cur} (курс {src} на {used})")
