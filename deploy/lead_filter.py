#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Спам в форме заявки (решено 29.10.2026): заблокированные отправители и предложения «IT-услуг» (SEO, «добавим сайт
в индекс Google», разработка сайтов, реклама, трафик, ссылки…) в бот не приходят, в «Студию» и в статистику заявок
не попадают. Отправителю форма отвечает как обычно («спасибо») — чтобы он не подбирал обход.

Кто заблокирован — ~/dumskaya/blocked.json: адреса и телефоны (contacts), домены почты (domains), IP (ips).
Пополняется само: заявку отметили «🚫 Спам» (кнопкой в боте или в «Студии») — её отправитель (контакт и IP, с которого
он писал) блокируется; вернули из спама — разблокируется. Отсеянное пишется в ~/dumskaya/leads-blocked.jsonl
(с причиной) — посмотреть, не отсеялось ли лишнее.

   python3 ~/dumskaya/deploy/lead_filter.py --list                 — кто заблокирован и что отсеяно за 30 дней
   python3 ~/dumskaya/deploy/lead_filter.py --block <почта|телефон|домен|IP>
   python3 ~/dumskaya/deploy/lead_filter.py --unblock <то же>
Только стандартная библиотека Python 3."""
import json
import os
import re
import sys
import threading
from datetime import datetime, timedelta, timezone

APP = os.path.expanduser("~/dumskaya")
BLOCK_FILE = os.environ.get("LEAD_BLOCK_FILE", os.path.join(APP, "blocked.json"))
LEADS_FILE = os.environ.get("LEADS_FILE", os.path.join(APP, "leads.jsonl"))
BLOCKED_LOG = os.environ.get("LEADS_BLOCKED_FILE", os.path.join(APP, "leads-blocked.jsonl"))
_lock = threading.Lock()

# первые заблокированные (29.10.2026, по скриншотам владельца): спам «узнать вашу цену» на валлийском и «SEO-индекс»
SEED = {"contacts": ["aveyekoha655@gmail.com", "domains@search-dumskaya-home.com"], "domains": ["search-dumskaya-home.com"], "ips": []}

# предложения IT-услуг: SEO, индекс, сайты, реклама, трафик, ссылки, рассылки — на английском и русском (и в переводе)
IT_RE = re.compile(r"""(?ix)
    \bseo\b | search\s+(engine\s+)?(index|optimi[sz]ation|ranking|results) | google'?s?\s+(search\s+)?(index|first\s+page|top|ranking)
  | (submit|list|add|register)\s+(your\s+)?(site|website|domain|business|\S+\.(com|net|org|site|online))\b
  | domain\s*submi | submit\w*\.(site|com|net|online) | \bbacklinks?\b | link\s*building | guest\s*post
  | (web|website|app|mobile\s+app|wordpress|shopify)\s+(design|development|developer|redesign|agency)
  | (build|redesign|create)\s+(you\s+)?(a\s+)?(new\s+)?(website|web\s*site|app)\b
  | digital\s+marketing | (social\s+media|smm)\s+(marketing|management|growth) | lead\s+generation
  | (more|targeted|organic|website)\s+traffic | \btraffic\s+to\s+your | ranking\s+(on|in)\s+google | rank\s+(higher|\#?1|first)
  | page\s*speed\s+(fix|optimi) | outsourc\w+\s+(development|team) | virtual\s+assistant | (ai|chat)\s*bot\s+for\s+your\s+(business|website)
  | продвижени\w*\s+(сайт|в\s+поиск) | раскрутк\w+ | поисков\w+\s+(оптимизац|индекс|выдач) | разработк\w+\s+(сайт|приложени)
  | создани\w+\s+сайт | (добав\w+|регистрац\w+)\s+(ваш\w*\s+)?(сайт|домен)\w*\s+в\s+(индекс|поиск|google) | индекс\w*\s+google
  | (контекстн|таргет)\w+\s+реклам | ссылочн\w+\s+(масс|продвиж) | лидогенерац
""")
# письмо с домена, который выдаёт себя за наш (search-dumskaya-home.com, dumskaya-design-seo.net…)
FAKE_DOMAIN_RE = re.compile(r"(?i)@(?!dumskaya-(design|home)\.com$)[\w.-]*dumskaya[\w.-]*$")
# рассылка «хотел узнать вашу цену» на случайных языках (валлийский и т. п.): так студии никто не пишет
ODD_LANGS = {"cy", "eo", "la", "gd", "haw", "zu", "xh", "yo", "ig", "sw", "mi", "sm", "ht"}


def _norm(c):
    c = (c or "").strip().lower()
    return re.sub(r"[\s()\-.]", "", c) if not ("@" in c or re.search(r"[a-z]", c)) else c


def load():
    try:
        with open(BLOCK_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        d = {}
    d["unblocked"] = sorted(set(d.get("unblocked") or []))      # сняты из начального списка — не возвращать
    for k in ("contacts", "domains", "ips"):
        d[k] = sorted({*(d.get(k) or []), *(x for x in SEED[k] if x not in d["unblocked"])})
    return d


def _save(d):
    os.makedirs(os.path.dirname(BLOCK_FILE), exist_ok=True)
    with open(BLOCK_FILE + ".tmp", "w", encoding="utf-8") as fh:
        json.dump({k: d.get(k) or [] for k in ("contacts", "domains", "ips", "unblocked")}, fh, ensure_ascii=False, indent=1)
    os.replace(BLOCK_FILE + ".tmp", BLOCK_FILE)


def _kind(v):
    v = (v or "").strip().lower()
    if re.fullmatch(r"[\d.]+|[0-9a-f:]+", v) and ("." in v or ":" in v) and not v.startswith("+"):
        return "ips", v
    if "@" not in v and re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", v):
        return "domains", v
    return "contacts", _norm(v)


def block(*values):
    """Заблокировать адреса, телефоны, домены, IP. Возвращает, что добавлено."""
    added = []
    with _lock:
        d = load()
        for v in values:
            if not (v or "").strip():
                continue
            k, x = _kind(v)
            if x in d["unblocked"]:
                d["unblocked"].remove(x)
            if x and x not in d[k]:
                d[k].append(x)
                added.append(x)
        _save(d)
    return added


def unblock(*values):
    with _lock:
        d = load()
        gone = []
        for v in values:
            k, x = _kind(v)
            if x in d[k]:
                d[k].remove(x)
                gone.append(x)
            if x in SEED[k] and x not in d["unblocked"]:      # из начального списка — запомнить, что сняли
                d["unblocked"].append(x)
        _save(d)
    return gone


def ips_of(contact):
    """С каких IP писал этот отправитель (по leads.jsonl)."""
    c, out = _norm(contact), set()
    try:
        with open(LEADS_FILE, encoding="utf-8") as fh:
            for line in fh:
                try:
                    x = json.loads(line)
                except ValueError:
                    continue
                if _norm(x.get("contact")) == c and x.get("ip") and x["ip"] not in ("127.0.0.1", "::1"):
                    out.add(x["ip"])
    except OSError:
        pass
    return sorted(out)


def block_sender(contact):
    """Заявку отметили «Спам»: заблокировать контакт и IP, с которых он писал."""
    return block(contact, *ips_of(contact)) if (contact or "").strip() else []


def unblock_sender(contact):
    return unblock(contact, *ips_of(contact)) if (contact or "").strip() else []


def reason(lead, blocked=None):
    """Почему заявка — спам (текст) или None. Смотрит и на перевод, если он уже есть."""
    d = blocked or load()
    contact = _norm(lead.get("contact"))
    if contact and contact in d["contacts"]:
        return "отправитель заблокирован"
    dom = contact.rsplit("@", 1)[1] if "@" in contact else ""
    if dom and any(dom == x or dom.endswith("." + x) for x in d["domains"]):
        return f"домен {dom} заблокирован"
    if lead.get("ip") and lead["ip"] in d["ips"]:
        return "IP заблокирован"
    if "@" in contact and FAKE_DOMAIN_RE.search(contact):
        return "почта с домена, похожего на наш"
    text = " ".join(str(lead.get(k) or "") for k in ("name", "message", "message_ru", "model"))
    m = IT_RE.search(text)
    if m:
        return f"предложение IT-услуг («{m.group(0).strip()[:40]}»)"
    if (lead.get("message_lang") or "").lower() in ODD_LANGS:
        return f"рассылка на языке «{lead['message_lang']}»"
    return None


def log_blocked(lead, why):
    try:
        os.makedirs(os.path.dirname(BLOCKED_LOG), exist_ok=True)
        with _lock, open(BLOCKED_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(dict(lead, blocked=why), ensure_ascii=False) + "\n")
    except OSError:
        pass


def recent(days=30):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    out = []
    try:
        with open(BLOCKED_LOG, encoding="utf-8") as fh:
            for line in fh:
                try:
                    x = json.loads(line)
                except ValueError:
                    continue
                if str(x.get("time") or "") >= since:
                    out.append(x)
    except OSError:
        pass
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--block"] and len(a) > 1:
        print("заблокировано:", ", ".join(block(*a[1:])) or "уже было")
    elif a[:1] == ["--unblock"] and len(a) > 1:
        print("разблокировано:", ", ".join(unblock(*a[1:])) or "не было в списке")
    elif a[:1] in (["--list"], []):
        d = load()
        for k, t in (("contacts", "адреса и телефоны"), ("domains", "домены"), ("ips", "IP")):
            print(f"{t}: {', '.join(d[k]) or '—'}")
        r = recent()
        print(f"\nотсеяно за 30 дней: {len(r)}")
        for x in r[-20:]:
            print(f"  {x.get('time', '')[:16]} · {x.get('contact', '')} · {x.get('blocked')}")
    else:
        print(__doc__)
