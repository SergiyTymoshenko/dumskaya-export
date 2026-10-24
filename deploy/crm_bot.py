#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Учёт проектов в чате бота (часть класса Bot): фото и документы, присланные разработчиком или дизайнером,
сохраняются в проект. Бот спрашивает: в какой проект → что это (до, после, визуализация, документация).
Несколько фото сразу (альбом) — один вопрос на все. И обратно: файл проекта из «Студии» — в чат (send_file).
Только стандартная библиотека Python 3."""
import html
import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from crm import FILE_CATS, CrmError

PENDING_MAX_AGE = 30 * 60          # присланные файлы ждут выбора проекта полчаса
TG_DOWNLOAD_MAX = 20 * 1024 * 1024  # больше Telegram боту скачать не даёт
TG_UPLOAD_MAX = 50 * 1024 * 1024
PAGE = 8


def esc(s):
    return html.escape(str(s or ""), quote=False)


def short(p, n=38):
    t = (f"{p['number']} · " if p.get("number") else "") + (p.get("title") or "")
    return t if len(t) <= n else t[:n - 1] + "…"


class CrmBotMixin:
    # ---------- адрес «Студии» ----------
    def studio_url(self):
        url = self.stats_app_url()
        return url.replace("/api/stats/app", "/api/crm/app") if url else None

    def studio_button(self, text="📁 Открыть в «Студии»", pid=None):
        url = self.studio_url()
        if not url:
            return None
        return [(text, {"web_app": {"url": url + (f"?project={pid}" if pid else "")}})]

    # ---------- приём файлов ----------
    def _pending(self, uid):
        try:
            d = json.loads(self.s.get(f"crm:pending:{uid}") or "{}")
        except ValueError:
            d = {}
        if not d or time.time() - d.get("ts", 0) > PENDING_MAX_AGE:
            return {"ts": time.time(), "files": [], "msg": None, "pid": None}
        return d

    def _save_pending(self, uid, d):
        self.s.put(f"crm:pending:{uid}", json.dumps(d, ensure_ascii=False))

    @staticmethod
    def file_of(m):
        """Файл из сообщения: фото (самое крупное и превью около 800 px), документ или видео; иначе None."""
        if m.get("photo"):
            sizes = sorted(m["photo"], key=lambda s: s.get("width", 0))
            big = sizes[-1]
            thumb = next((s for s in sizes if s.get("width", 0) >= 600), big)
            return {"kind": "photo", "id": big["file_id"], "size": big.get("file_size", 0), "mime": "image/jpeg",
                    "name": f"фото-{big.get('file_unique_id', 'x')}.jpg", "thumb": thumb["file_id"]}
        for kind in ("document", "video"):
            d = m.get(kind)
            if d:
                name = d.get("file_name") or f"{kind}-{d.get('file_unique_id', 'x')}"
                return {"kind": kind, "id": d["file_id"], "size": d.get("file_size", 0),
                        "mime": d.get("mime_type") or mimetypes.guess_type(name)[0] or "application/octet-stream",
                        "name": name, "thumb": None}
        return None

    def crm_intake(self, u, m):
        uid = u["tg_id"]
        f = self.file_of(m)
        if not f:
            return False
        if not getattr(self, "crm", None):
            self.send(uid, "Учёт проектов сейчас не запущен — файл не сохранён.")
            return True
        d = self._pending(uid)
        d["files"].append(f)
        d["ts"] = time.time()
        if d.get("msg"):                            # вопрос уже задан (альбом или ещё файлы) — обновить число
            self._save_pending(uid, d)
            self.api("editMessageText", chat_id=uid, message_id=d["msg"], parse_mode="HTML",
                     text=self._ask_text(d), reply_markup=self.kb(self._ask_rows(d)))
            return True
        r = self.api("sendMessage", chat_id=uid, text=self._ask_text(d), parse_mode="HTML",
                     reply_markup=self.kb(self._ask_rows(d)))
        d["msg"] = (r.get("result") or {}).get("message_id")
        self._save_pending(uid, d)
        return True

    def _what(self, d):
        n = len(d["files"])
        photos = sum(1 for f in d["files"] if f["kind"] == "photo")
        if photos == n:
            return f"{n} фото"
        return f"{n} {'файл' if n == 1 else 'файла' if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 'файлов'}"

    def _ask_text(self, d):
        if d.get("pid"):
            p = self.crm.one("SELECT number, title FROM projects WHERE id=?", d["pid"]) or {}
            return f"<b>{esc(self._what(d))}</b> → «{esc(short(p, 80))}».\nЧто это?"
        return f"<b>{esc(self._what(d))}</b> — в какой проект сохранить?"

    def _ask_rows(self, d, offset=0):
        if d.get("pid"):
            return [[(name, f"cf:c:{key}") for key, name in FILE_CATS[:2]],
                    [(name, f"cf:c:{key}") for key, name in FILE_CATS[2:]],
                    [("← Другой проект", "cf:b"), ("Отмена", "cf:x")]]
        projects = [p for p in self.crm.project_rows() if p["status"] in ("active", "paused")] or self.crm.project_rows()
        rows = [[(short(p), f"cf:p:{p['id']}")] for p in projects[offset:offset + PAGE]]
        nav = []
        if offset:
            nav.append(("← Назад", f"cf:m:{max(0, offset - PAGE)}"))
        if len(projects) > offset + PAGE:
            nav.append(("Ещё проекты →", f"cf:m:{offset + PAGE}"))
        if nav:
            rows.append(nav)
        if not projects:
            btn = self.studio_button("📁 Создать проект в «Студии»")
            if btn:
                rows.append(btn)
        rows.append([("Отмена", "cf:x")])
        return rows

    def crm_button(self, admin, msg, parts):
        uid = admin["tg_id"]
        d = self._pending(uid)
        act = parts[1]
        if act == "x" or not d["files"]:
            self.s.drop(f"crm:pending:{uid}")
            return self.edit(msg, "Отменено — файлы не сохранены." if act == "x" else "Эти файлы уже не ждут сохранения — пришлите их ещё раз.")
        if act == "m":
            return self.api("editMessageReplyMarkup", chat_id=uid, message_id=msg["message_id"],
                            reply_markup=self.kb(self._ask_rows(d, int(parts[2]))))
        if act == "b":
            d["pid"] = None
        elif act == "p":
            d["pid"] = int(parts[2])
        elif act == "c":
            return self._store(admin, msg, d, parts[2])
        self._save_pending(uid, d)
        self.edit(msg, self._ask_text(d), self._ask_rows(d))

    def _download(self, file_id):
        r = self.api("getFile", file_id=file_id)
        path = (r.get("result") or {}).get("file_path")
        if not path:
            raise CrmError(r.get("description") or "Telegram не отдал файл")
        return urllib.request.urlopen(f"https://api.telegram.org/file/bot{self.token}/{path}", timeout=120)

    def _store(self, admin, msg, d, cat):
        uid, pid = admin["tg_id"], d.get("pid")
        if cat not in dict(FILE_CATS) or not pid:
            return
        self.edit(msg, f"Сохраняю {esc(self._what(d))}…")
        who = admin["name"] or str(uid)
        saved, failed = 0, []
        for f in d["files"]:
            ref = f"{f['kind']}:{f['id']}"
            try:
                if f["size"] and f["size"] > TG_DOWNLOAD_MAX:     # большой файл остаётся в Telegram
                    self.crm.add_tg_only(pid, cat, f["name"], f["size"], f["mime"], who, ref)
                else:
                    with self._download(f["id"]) as r:
                        size = int(r.headers.get("Content-Length") or f["size"] or 0)
                        rec = self.crm.add_file(pid, cat, f["name"], r, size, f["mime"], who, tg_file_id=ref)
                    if f.get("thumb"):
                        try:
                            with self._download(f["thumb"]) as t:
                                self.crm.set_thumb(rec["id"], t.read(2 * 1024 * 1024))
                        except Exception:  # noqa: BLE001  превью не обязательно
                            pass
                saved += 1
            except Exception as e:  # noqa: BLE001
                failed.append(f"{f['name']}: {e}")
                self.log(f"учёт: файл не сохранён — {f['name']}: {type(e).__name__}: {e}")
        self.s.drop(f"crm:pending:{uid}")
        p = self.crm.one("SELECT number, title FROM projects WHERE id=?", pid) or {}
        text = f"✅ Сохранено {saved} из {len(d['files'])} в «{esc(short(p, 80))}» → {esc(dict(FILE_CATS)[cat])}."
        if failed:
            text += "\n\nНе сохранились:\n" + "\n".join(esc(x)[:200] for x in failed[:5])
        btn = self.studio_button("📁 Открыть проект", pid)
        self.edit(msg, text, [btn] if btn else None)

    # ---------- файл проекта → в чат ----------
    def send_file(self, chat_id, f, path):
        """Прислать файл проекта в чат: из Telegram по ссылке на него или с сервера (до 50 МБ)."""
        caption = f["name"] or ""
        ref = f.get("tg_file_id") or ""
        if ":" in ref:
            kind, fid = ref.split(":", 1)
            method, field = {"photo": ("sendPhoto", "photo"), "video": ("sendVideo", "video")}.get(kind, ("sendDocument", "document"))
            r = self.api(method, chat_id=chat_id, caption=caption[:1000], **{field: fid})
            if r.get("ok"):
                return True, ""
            if not path:
                return False, r.get("description") or "ошибка"
        if not path or not os.path.exists(path):
            return False, "файла нет на сервере"
        if os.path.getsize(path) > TG_UPLOAD_MAX:
            return False, "файл больше 50 МБ — откройте его по ссылке в «Студии»"
        with open(path, "rb") as fh:
            data = fh.read()
        boundary = uuid.uuid4().hex
        name = (f["name"] or "file").replace('"', "")
        body = b"".join([
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n".encode() + caption[:1000].encode() + b"\r\n",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename*=UTF-8''{urllib.parse.quote(name)}\r\n"
            f"Content-Type: {f.get('mime') or 'application/octet-stream'}\r\n\r\n".encode(), data, b"\r\n",
            f"--{boundary}--\r\n".encode()])
        req = urllib.request.Request(f"https://api.telegram.org/bot{self.token}/sendDocument", data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                res = json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                res = json.loads(e.read())
            except ValueError:
                res = {"ok": False, "description": str(e)}
        except Exception as e:  # noqa: BLE001
            res = {"ok": False, "description": f"{type(e).__name__}: {e}"}
        return bool(res.get("ok")), res.get("description") or ""
