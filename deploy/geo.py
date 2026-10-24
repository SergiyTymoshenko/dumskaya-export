#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Страна и город посетителя по IP-адресу — для режима «1 час» в графиках статистики (site_stats.py).

База — DB-IP «IP to City Lite» (https://db-ip.com, лицензия CC BY 4.0): файл формата MaxMind DB на самом сервере,
~/dumskaya/geo/dbip-city-lite.mmdb. Адреса посетителей никуда не отправляются — поиск идёт в этом файле.
Точность — примерно до города; мобильный интернет часто показывает город оператора, а не человека.

Новый выпуск базы выходит в начале каждого месяца. Сервис заявок скачивает его сам (около 60 МБ раз в месяц),
проверяет и только потом подменяет старый файл; не получилось — работает со старым, попробует через 6 часов.
Страна — по-русски из самой базы; регион и город — по-русски для частых (geo_names_ru.json), остальные — латиницей.
Только стандартная библиотека Python 3.

   python3 geo.py 8.8.8.8 2a02:8388::1     — проверка с сервера
   python3 geo.py --update                  — скачать свежую базу сейчас
"""
import gzip
import ipaddress
import json
import mmap
import os
import re
import shutil
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

GEO_DIR = os.environ.get("GEO_DIR", os.path.expanduser("~/dumskaya/geo"))
GEO_FILE = os.path.join(GEO_DIR, "dbip-city-lite.mmdb")
MONTH_FILE = GEO_FILE + ".month"                  # какой выпуск сейчас в файле: ГГГГ-ММ
URL = os.environ.get("GEO_URL", "https://download.db-ip.com/free/dbip-city-lite-{}.mmdb.gz")
NAMES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geo_names_ru.json")
RETRY = 6 * 3600                                  # после неудачной загрузки — следующая попытка через 6 часов
MIN_FREE = 600 * 1024 * 1024                      # свободного места на диске для загрузки (файл ~130 МБ + запас)
CREDIT = "DB-IP.com, CC BY 4.0"

META = b"\xab\xcd\xefMaxMind.com"


class MMDB:
    """Чтение файла MaxMind DB (формат v2): дерево поиска по битам адреса + раздел данных.
    Файл отображается в память (mmap) — читаются только нужные страницы, весь файл в память не грузится."""

    def __init__(self, path):
        self.fh = open(path, "rb")
        try:
            self.buf = mmap.mmap(self.fh.fileno(), 0, access=mmap.ACCESS_READ)
        except Exception:
            self.fh.close()
            raise
        i = self.buf.rfind(META, max(0, len(self.buf) - 128 * 1024))
        if i < 0:
            self.close()
            raise ValueError("это не файл MaxMind DB")
        start = i + len(META)
        self.meta, _ = self._decode(start, start)
        self.node_count = int(self.meta["node_count"])
        self.record_size = int(self.meta["record_size"])
        if self.record_size not in (24, 28, 32):
            self.close()
            raise ValueError(f"неизвестный размер записи {self.record_size}")
        self.node_bytes = self.record_size // 4
        self.tree_size = self.node_count * self.node_bytes
        self.data_start = self.tree_size + 16
        self.ip_version = int(self.meta["ip_version"])
        self.v4_start = 0
        if self.ip_version == 6:                  # адреса IPv4 в такой базе лежат в ::a.b.c.d
            node = 0
            for _ in range(96):
                if node >= self.node_count:
                    break
                node = self._record(node, 0)
            self.v4_start = node

    def close(self):
        try:
            self.buf.close()
        finally:
            self.fh.close()

    def _record(self, node, bit):
        b, o = self.buf, node * self.node_bytes
        if self.record_size == 24:
            o += bit * 3
            return int.from_bytes(b[o:o + 3], "big")
        if self.record_size == 28:
            if bit == 0:
                return ((b[o + 3] & 0xF0) << 20) | int.from_bytes(b[o:o + 3], "big")
            return ((b[o + 3] & 0x0F) << 24) | int.from_bytes(b[o + 4:o + 7], "big")
        o += bit * 4
        return int.from_bytes(b[o:o + 4], "big")

    def _decode(self, off, base):
        """Значение по смещению off → (значение, смещение после него). base — откуда считаются указатели."""
        b = self.buf
        ctrl = b[off]
        off += 1
        kind = ctrl >> 5
        if kind == 1:                             # указатель на значение в другом месте раздела данных
            ss, v = (ctrl >> 3) & 3, ctrl & 7
            if ss == 0:
                p = (v << 8) | b[off]
            elif ss == 1:
                p = ((v << 16) | int.from_bytes(b[off:off + 2], "big")) + 2048
            elif ss == 2:
                p = ((v << 24) | int.from_bytes(b[off:off + 3], "big")) + 526336
            else:
                p = int.from_bytes(b[off:off + 4], "big")
            value, _ = self._decode(base + p, base)
            return value, off + ss + 1
        if kind == 0:                             # расширенный тип — номер в следующем байте
            kind = 7 + b[off]
            off += 1
        size = ctrl & 0x1F
        if size == 29:
            size, off = 29 + b[off], off + 1
        elif size == 30:
            size, off = 285 + int.from_bytes(b[off:off + 2], "big"), off + 2
        elif size == 31:
            size, off = 65821 + int.from_bytes(b[off:off + 3], "big"), off + 3
        if kind == 2:                             # строка
            return b[off:off + size].decode("utf-8", "replace"), off + size
        if kind == 7:                             # словарь
            d = {}
            for _ in range(size):
                k, off = self._decode(off, base)
                d[k], off = self._decode(off, base)
            return d, off
        if kind == 11:                            # массив
            out = []
            for _ in range(size):
                v, off = self._decode(off, base)
                out.append(v)
            return out, off
        if kind == 3:                             # double
            return struct.unpack(">d", b[off:off + 8])[0], off + 8
        if kind == 15:                            # float
            return struct.unpack(">f", b[off:off + 4])[0], off + 4
        if kind in (5, 6, 9, 10):                 # беззнаковые целые
            return int.from_bytes(b[off:off + size], "big"), off + size
        if kind == 8:                             # int32
            v = int.from_bytes(b[off:off + size], "big")
            return (v - (1 << 32) if size == 4 and v >= 1 << 31 else v), off + size
        if kind == 4:                             # байты
            return bytes(b[off:off + size]), off + size
        if kind == 14:                            # логическое: значение — сам размер
            return bool(size), off
        return None, off                          # контейнер кэша и маркер конца — в записях не встречаются

    def get(self, ip):
        """Запись базы для адреса или None (адреса нет в базе: локальный, служебный)."""
        a = ipaddress.ip_address(ip)
        if a.version == 6 and a.ipv4_mapped:
            a = a.ipv4_mapped
        if a.version == 6 and self.ip_version == 4:
            return None
        node = self.v4_start if a.version == 4 and self.ip_version == 6 else 0
        packed, nc = a.packed, self.node_count
        for i in range(len(packed) * 8):
            if node >= nc:
                break
            node = self._record(node, (packed[i >> 3] >> (7 - (i & 7))) & 1)
        if node == nc:
            return None
        if node < nc:
            raise ValueError("повреждено дерево поиска")
        return self._decode(node - nc + self.tree_size, self.data_start)[0]


# ---------- русские названия ----------
_names = None


def names():
    global _names
    if _names is None:
        try:
            with open(NAMES_FILE, encoding="utf-8") as fh:
                _names = json.load(fh)
        except (OSError, ValueError):
            _names = {}
    return _names


def flag(cc):
    """Флаг страны из двух букв кода (🇺🇸)."""
    cc = (cc or "").upper()
    if len(cc) != 2 or not cc.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in cc)


def describe(rec):
    """Запись базы → {cc, flag, place: «США, Флорида, Майами»}. Регион не повторяется, если город — его центр
    с тем же названием (Братиславский край + Братислава → «Словакия, Братислава»)."""
    if not rec:
        return None
    country = rec.get("country") or rec.get("registered_country") or {}
    cc = country.get("iso_code") or ""
    cn = country.get("names") or {}
    country_ru = cn.get("ru") or cn.get("en") or cc
    region_en = ((rec.get("subdivisions") or [{}])[0].get("names") or {}).get("en", "")
    city_en = re.sub(r"\s*\(.*?\)", "", ((rec.get("city") or {}).get("names") or {}).get("en", "")).strip()
    n = names()
    region = (n.get("regions", {}).get(cc) or {}).get(region_en) or region_en
    city = (n.get("cities", {}).get(cc) or {}).get(city_en) or city_en
    parts = [country_ru] if country_ru else []
    if region and not (city_en and (region_en == city_en or region_en.startswith(city_en + " "))):
        parts.append(region)
    if city and city not in parts:
        parts.append(city)
    return {"cc": cc, "flag": flag(cc), "place": ", ".join(parts)}


# ---------- поиск с кэшем ----------
_db = {"reader": None, "mtime": None, "checked": 0}
_cache = {}
_lock = threading.Lock()


def _reader():
    now = time.time()
    if now - _db["checked"] < 60 and _db["reader"] is not None:
        return _db["reader"]
    _db["checked"] = now
    try:
        mtime = os.stat(GEO_FILE).st_mtime
    except OSError:
        mtime = None
    if mtime != _db["mtime"]:
        old, _db["reader"] = _db["reader"], None
        if old:
            try:
                old.close()
            except Exception:  # noqa: BLE001
                pass
        _cache.clear()
        _db["mtime"] = mtime
        if mtime is not None:
            try:
                _db["reader"] = MMDB(GEO_FILE)
            except (OSError, ValueError, KeyError) as e:
                print(f"гео: не открывается {GEO_FILE}: {e}", file=sys.stderr)
    return _db["reader"]


def available():
    with _lock:
        return _reader() is not None


def lookup(ip):
    """{cc, flag, place} для адреса или None (базы ещё нет, адрес локальный или его нет в базе)."""
    if not ip:
        return None
    with _lock:
        if ip in _cache:
            return _cache[ip]
        r = _reader()
        if r is None:
            return None
        try:
            out = describe(r.get(ip))
        except (ValueError, IndexError, KeyError, UnicodeError):
            out = None
        if len(_cache) > 5000:
            _cache.clear()
        _cache[ip] = out
        return out


# ---------- загрузка свежего выпуска ----------
_tried = {"at": 0}


def installed_month():
    try:
        with open(MONTH_FILE, encoding="utf-8") as fh:
            m = fh.read().strip()
        return m if re.fullmatch(r"\d{4}-\d{2}", m) and os.path.exists(GEO_FILE) else None
    except OSError:
        return None


def _months(now):
    cur = now.strftime("%Y-%m")
    prev = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    return cur, prev


def _download(month, log):
    """Скачать выпуск month во временный файл, проверить и подменить рабочий. True — получилось; None — выпуска нет."""
    os.makedirs(GEO_DIR, exist_ok=True)
    if shutil.disk_usage(GEO_DIR).free < MIN_FREE:
        log("гео: мало места на диске — базу городов не обновляю")
        return False
    tmp = GEO_FILE + ".tmp"
    req = urllib.request.Request(URL.format(month), headers={"User-Agent": "dumskaya-design.com stats (geo update)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, gzip.GzipFile(fileobj=r) as gz, open(tmp, "wb") as out:
            shutil.copyfileobj(gz, out, 1024 * 1024)
    except urllib.error.HTTPError as e:
        _rm(tmp)
        if e.code == 404:
            return None
        log(f"гео: загрузка {month} — ответ {e.code}")
        return False
    except (OSError, EOFError, ValueError) as e:
        _rm(tmp)
        log(f"гео: загрузка {month} не удалась: {type(e).__name__}: {e}")
        return False
    try:                                          # проверка: файл открывается и находит известный адрес
        test = MMDB(tmp)
        try:
            ok = "City" in str(test.meta.get("database_type", "")) and \
                 ((test.get("8.8.8.8") or {}).get("country") or {}).get("iso_code") == "US"
        finally:
            test.close()
    except (OSError, ValueError, KeyError, IndexError):
        ok = False
    if not ok:
        _rm(tmp)
        log(f"гео: скачанный выпуск {month} не прошёл проверку — оставляю прежний")
        return False
    os.chmod(tmp, 0o644)
    os.replace(tmp, GEO_FILE)
    with open(MONTH_FILE + ".tmp", "w", encoding="utf-8") as fh:
        fh.write(month)
    os.replace(MONTH_FILE + ".tmp", MONTH_FILE)
    log(f"гео: база городов обновлена (выпуск {month})")
    return True


def _rm(p):
    try:
        os.remove(p)
    except OSError:
        pass


def update(log=print, force=False, now=None):
    """Свежий выпуск базы, если его ещё нет. Дёшево, когда база актуальна; вызывать можно хоть каждую минуту."""
    now = now or datetime.now(timezone.utc)
    cur, prev = _months(now)
    have = installed_month()
    if have == cur or (not force and time.time() - _tried["at"] < RETRY):
        return have
    if have == prev and now.day <= 2:             # выпуск месяца появляется в первые дни — не спешим
        return have
    _tried["at"] = time.time()
    got = _download(cur, log)
    if got is None and (have or "") < prev:       # выпуск этого месяца ещё не вышел — берём прошлый
        got = _download(prev, log)
        if got:
            return prev
    return cur if got else have


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--update"]:
        print("выпуск:", update(force=True) or "нет")
        sys.exit(0)
    if not available():
        print(f"базы нет: {GEO_FILE} — скачать: python3 {sys.argv[0]} --update")
        sys.exit(1)
    print("выпуск:", installed_month(), "·", CREDIT)
    for ip in args or ["8.8.8.8"]:
        g = lookup(ip)
        print(ip, "→", f"{g['flag']} {g['place']}" if g else "не найден")
