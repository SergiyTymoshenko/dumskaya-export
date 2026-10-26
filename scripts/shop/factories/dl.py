#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Скачать на Mac фото, чертежи и техкарты фабрики в папку выгрузки — по списку из репозитория
content/shop/sources/<фабрика>/files.json (адрес у фабрики → путь в выгрузке).

   python3 scripts/shop/factories/dl.py minotti            # из папки сайта (~/dumskaya-site)

Папка выгрузки — ~/Documents/dumskaya-export (или EXPORT_DIR). Уже скачанное пропускает, поэтому
прерванную докачку можно просто запустить ещё раз. Недокачанные куски прошлых запусков (*.part) удаляет.
Качает curl'ом по 4 файла сразу (не чаще, чтобы не нагружать сайт фабрики). В конце пишет, сколько не скачалось;
повторный запуск докачает их. Ошибка с одним файлом не останавливает остальные."""
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, unquote

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
EXPORT = os.path.expanduser(os.environ.get("EXPORT_DIR") or "~/Documents/dumskaya-export")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36 DumskayaCatalog/1.0"


def fetch(job):
    url, rel = job
    dst = os.path.join(EXPORT, rel)
    tmp = f"{dst}.part{threading.get_ident()}"
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        safe = quote(unquote(url), safe=":/?=&;,+@~#%!$'()*[]")       # пробелы и буквы с акцентами в именах файлов фабрик
        r = subprocess.run(["curl", "-sfL", "--retry", "2", "--max-time", "120", "-A", UA, "-o", tmp, safe])
        if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, dst)
            return True
    except OSError as e:
        print(f"  ошибка {rel}: {e}", flush=True)
    if os.path.exists(tmp):
        os.remove(tmp)
    return False


def main():
    f = sys.argv[1]
    src = os.path.join(ROOT, "content/shop/sources", f, "files.json")
    files = json.load(open(src, encoding="utf-8"))["files"]
    def have(v):                                     # уже скачан (размер не сверяем: CDN фабрики пережимает фото со временем)
        p = os.path.join(EXPORT, v["file"])
        return os.path.exists(p) and os.path.getsize(p) > 0
    for top in {os.path.join(EXPORT, *v["file"].split("/")[:3]) for v in files.values()}:   # недокачанное прошлых запусков
        for dp, _, names in os.walk(top):
            for n in names:
                if re.search(r"\.part\d*$", n):
                    os.remove(os.path.join(dp, n))
    jobs = [(u, v["file"]) for u, v in files.items() if not have(v)]
    print(f"{f}: файлов в списке {len(files)}, скачать {len(jobs)} → {EXPORT}", flush=True)
    ok = bad = 0
    t0 = time.time()
    with ThreadPoolExecutor(4) as ex:
        for i, done in enumerate(ex.map(fetch, jobs), 1):
            ok += done
            bad += not done
            if i % 200 == 0 or i == len(jobs):
                print(f"  {i} из {len(jobs)} ({time.time() - t0:.0f} с), не скачалось: {bad}", flush=True)
    print(f"ГОТОВО: скачано {ok}, не скачалось {bad}" + (" — запустите ещё раз, докачает" if bad else ""))


if __name__ == "__main__":
    main()
