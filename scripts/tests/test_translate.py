"""Проверка порядка сервисов перевода (deploy/translate.py, решено 25.10.2026): сначала модели ChatGPT по подписке
(API на сервере), потом платный ChatGPT, потом Claude; лимит или сбой — тот же текст переводит следующий, сервис
с ошибкой пропускается на время; учёт — по сервисам. И мастер настройки (deploy/lead_setup.py): подписка и платный
ключ из файла проекта УЧЕТ, адрес подписки вручную, ключи на экран не выводятся. Сеть не нужна — ответы подменены.

   python3 scripts/tests/test_translate.py      — в конце «OK: N проверок»"""
import io
import json
import os
import re
import sys
import tempfile
import time
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "deploy"))
for k in list(os.environ):
    if k.startswith(("OPENAI_", "ANTHROPIC_", "DEEPL_", "TRANSLATE_")):
        del os.environ[k]
import translate as T  # noqa: E402

ok = 0


def check(cond, what):
    global ok
    if not cond:
        raise AssertionError(what)
    ok += 1


CALLS = []          # (сервис, адрес, модель)
FAIL = {}           # сервис → текст ошибки


def who(url):
    return "sub" if "127.0.0.1" in url else "openai" if "api.openai.com" in url else "claude" if "anthropic" in url else "deepl"


def fake_post(url, body, headers, timeout=12):
    p = who(url)
    CALLS.append((p, url, body.get("model"), headers.get("Authorization") or headers.get("x-api-key")))
    if p in FAIL:
        raise RuntimeError(FAIL[p])
    if p == "deepl":
        return {"translations": [{"detected_source_language": "EN", "text": "Здравствуйте (DeepL)"}]}
    sys_txt = body.get("system") or body["messages"][0]["content"]
    m = re.search(r"into (\w+)", sys_txt)
    text = f"[{m.group(1)}] перевод ({p})" if m else f"Здравствуйте ({p})"
    reply = json.dumps({"lang": "en", "text": text} if m else {"lang": "en", "ru": text}, ensure_ascii=False)
    if p == "claude":
        return {"content": [{"type": "text", "text": reply}], "usage": {"input_tokens": 10, "output_tokens": 5}}
    return {"choices": [{"message": {"content": reply}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


T._post = fake_post
USED = []
T.USAGE_HOOK = lambda ev: USED.append(ev)
EN = "Hello! I would like a quote for a sofa with delivery to Vienna."

# ---------- 1. порядок ----------
check(T.chain() == [] and T.provider() is None and T.to_russian(EN) is None, "ничего не настроено — без перевода")
os.environ.update({"OPENAI_API_KEY": "sk-paid-0123456789", "ANTHROPIC_API_KEY": "sk-ant-0123456789", "TRANSLATE_PROVIDER": "claude"})
check(T.chain() == ["openai", "claude"], "прежний TRANSLATE_PROVIDER больше не решает — порядок: платный ChatGPT, потом Claude")
os.environ.update({"OPENAI_SUB_BASE_URL": "http://127.0.0.1:8317/v1", "OPENAI_SUB_MODEL": "gpt-5.4-mini", "DEEPL_API_KEY": "x:fx"})
check(T.chain() == ["sub", "openai", "claude", "deepl"] and T.provider() == "sub", "подписка первой, потом платный ChatGPT, Claude, DeepL")
os.environ["TRANSLATE_ORDER"] = "claude,sub"
check(T.chain() == ["claude", "sub"], "свой порядок — TRANSLATE_ORDER")
del os.environ["TRANSLATE_ORDER"]

# ---------- 2. всё работает — переводит подписка ----------
CALLS.clear()
r = T.to_russian(EN)
check(r == ("en", "Здравствуйте (sub)") and [c[0] for c in CALLS] == ["sub"], "заявку переводит подписка, другие не вызываются")
check(CALLS[0][1] == "http://127.0.0.1:8317/v1/chat/completions" and CALLS[0][3] is None, "адрес подписки, без ключа, если ключа нет")
os.environ["OPENAI_SUB_API_KEY"] = "sub-key-123"
CALLS.clear()
check(T.translate_text("Dobrý deň", "de")[1] == "[German] перевод (sub)" and CALLS[0][3] == "Bearer sub-key-123", "переписку — тоже подписка; ключ шлюза, если задан")
check(USED[-1]["provider"] == "sub" and USED[-1]["model"] == "gpt-5.4-mini" and USED[-1]["ok"], "учёт: вызов записан на подписку")

# ---------- 3. лимит подписки — платный ChatGPT; подписка пропускается, пока не пройдёт пауза ----------
FAIL["sub"] = "ответ 429 retry-after 120: usage limit reached"
CALLS.clear()
check(T.translate_text("Dobrý deň", "de")[1] == "[German] перевод (openai)" and [c[0] for c in CALLS] == ["sub", "openai"],
      "лимит подписки — тот же текст сразу переводит платный ChatGPT")
until, why = T.paused("sub")
check(why == "лимит" and 100 < until - time.time() <= 121, f"подписка на паузе столько, сколько сказал сервис ({why})")
CALLS.clear()
T.translate_text("Ahoj", "de")
check([c[0] for c in CALLS] == ["openai"], "пока пауза — подписку не дёргаем, сразу платный")
check([u["provider"] for u in USED[-3:]] == ["sub", "openai", "openai"] and not USED[-3]["ok"], "учёт: ошибка подписки и переводы платного")
del FAIL["sub"]
T._PAUSE["sub"] = (time.time() - 1, "лимит")          # пауза прошла
CALLS.clear()
T.translate_text("Ahoj", "de")
check([c[0] for c in CALLS] == ["sub"] and not T.paused("sub"), "пауза прошла — снова подписка")

# ---------- 4. сбои: подписка не отвечает, платный без денег — Claude ----------
FAIL["sub"] = "URLError: <urlopen error [Errno 111] Connection refused>"
FAIL["openai"] = "ответ 429: You exceeded your current quota (insufficient_quota)"
CALLS.clear()
check(T.translate_text("Ahoj", "fr")[1] == "[French] перевод (claude)" and [c[0] for c in CALLS] == ["sub", "openai", "claude"],
      "подписка не отвечает, у платного кончились деньги — переводит Claude")
check(T.paused("sub")[1] == "не отвечает" and 100 < T.paused("sub")[0] - time.time() <= 121, "не отвечает — пауза 2 минуты")
check(T.paused("openai")[1] == "лимит" and T.paused("openai")[0] - time.time() > 800, "нет денег на платном — пауза 15 минут")
T.reset_pauses()
FAIL["claude"] = "ответ 401: invalid x-api-key"
CALLS.clear()
check(T.to_russian(EN) == ("en", "Здравствуйте (DeepL)") and [c[0] for c in CALLS] == ["sub", "openai", "claude", "deepl"], "заявку — DeepL последним")
CALLS.clear()
try:
    T.translate_text("Ahoj", "is")
    raised = False
except RuntimeError as e:
    raised = "401" in str(e)
check(raised and "deepl" not in [c[0] for c in CALLS], "исландского у DeepL нет — его не зовём; все не смогли — ошибка последнего")
CALLS.clear()
T.translate_text("Ahoj", "de")
check([c[0] for c in CALLS] == ["deepl"], "трое на паузе — сразу тот, кто работает")
T._PAUSE["deepl"] = (time.time() + 60, "не отвечает")
CALLS.clear()
T.translate_text("Ahoj", "de")
check([c[0] for c in CALLS] == ["sub", "openai", "claude", "deepl"], "все на паузе — пробуем всё равно по порядку")
T.reset_pauses()
FAIL.clear()

# ---------- 5. ошибка этого текста, а не сервиса — подписку не выключаем ----------
FAIL["sub"] = "ответ 400: context length exceeded"
CALLS.clear()
T.translate_text("Ahoj", "de")
check([c[0] for c in CALLS] == ["sub", "sub", "openai"] and not T.paused("sub"), "400 (повтор без доп. параметров, потом платный) — подписка не на паузе")
FAIL.clear()

# ---------- 6. «Сервер и ИИ»: порядок без ключей ----------
import server_info  # noqa: E402
T._PAUSE["openai"] = (time.time() + 600, "лимит")
cfg = server_info.llm_config()
dump = json.dumps(cfg, ensure_ascii=False)
check(cfg["provider"] == "sub" and [x["provider"] for x in cfg["chain"] if x["configured"]] == ["sub", "openai", "claude", "deepl"],
      "страница: порядок сервисов")
sub = cfg["chain"][0]
check(sub["via"] == "127.0.0.1:8317" and sub["model"] == "gpt-5.4-mini" and sub["key"] is True, "подписка: адрес (хост), модель, «ключ есть»")
check(cfg["chain"][1].get("paused_why") == "лимит", "видно, что платный сейчас на паузе")
check("sub-key-123" not in dump and "sk-paid" not in dump and "sk-ant" not in dump, "ключей на странице нет")
T.reset_pauses()

# ---------- 7. мастер настройки ----------
for k in list(os.environ):
    if k.startswith(("OPENAI_", "ANTHROPIC_", "DEEPL_", "TRANSLATE_")):
        del os.environ[k]
import lead_setup as L  # noqa: E402
L.APP = os.path.dirname(os.path.join(ROOT, "deploy"))     # translate.py — из репозитория
L.list_models = lambda base, key: (base.rstrip("/") if base.rstrip("/").endswith("/v1") else base.rstrip("/") + "/v1",
                                   ["gpt-5", "gpt-5.4-mini", "gpt-5.4"])
env_file = tempfile.NamedTemporaryFile("w", suffix=".env", delete=False)
env_file.write("DATABASE_URL=postgres://u:p@db/x\n"
               "CHATGPT_SUB_BASE_URL=http://127.0.0.1:8317\nCHATGPT_SUB_API_KEY=sub-key-777\n"
               "OPENAI_API_KEY=sk-paid-999999999\nOPENAI_MODEL=gpt-5.4-mini\nTELEGRAM_TOKEN=123:abc\n")
env_file.close()
g = dict(L.groups(L.read_project_env(env_file.name)))
check(set(g) == {"CHATGPT_SUB", "OPENAI"} and g["CHATGPT_SUB"] == {"base": "http://127.0.0.1:8317", "key": "sub-key-777"}
      and g["OPENAI"] == {"key": "sk-paid-999999999", "model": "gpt-5.4-mini"}, f"из файла УЧЕТ — только ChatGPT, по наборам: {g}")


def run_wizard(answers, secrets, vals):
    a, s_ = list(answers), list(secrets)
    L.ask = lambda prompt, default="": (a.pop(0) if a else "") or default
    L.ask_secret = lambda prompt: s_.pop(0) if s_ else ""
    out = io.StringIO()
    with redirect_stdout(out):
        L.setup_translate(vals, step="1")
    return out.getvalue()


vals = {"OPENAI_API_KEY": "sk-old", "TRANSLATE_PROVIDER": "openai"}
CALLS.clear()
out = run_wizard(["1", env_file.name], [""], vals)
check(vals["OPENAI_SUB_BASE_URL"] == "http://127.0.0.1:8317/v1" and vals["OPENAI_SUB_API_KEY"] == "sub-key-777"
      and vals["OPENAI_SUB_MODEL"] == "gpt-5.4-mini", "мастер: подписка из файла УЧЕТ — адрес (с /v1), ключ, модель")
check(vals["OPENAI_API_KEY"] == "sk-paid-999999999" and vals["OPENAI_BASE_URL"] == "" and vals["TRANSLATE_PROVIDER"] == "", "платный ключ — вторым")
check("ChatGPT по подписке → платный ChatGPT" in out and "sub-key-777" not in out and "sk-paid" not in out, "порядок показан, ключей на экране нет")
check({c[0] for c in CALLS} == {"sub", "openai"}, "каждый проверен пробным переводом")
check(vals["TRANSLATE_SOURCE"] == env_file.name, "путь к файлу УЧЕТ запомнен для следующего раза")

# подписки в файле нет — адрес вручную; прежний шлюз из lead.env предлагается сам
vals = {"OPENAI_API_KEY": "gw-key", "OPENAI_BASE_URL": "http://127.0.0.1:9000/v1", "OPENAI_MODEL": "gpt-5"}
out = run_wizard(["2", ""], ["", "", ""], vals)
check(vals["OPENAI_SUB_BASE_URL"] == "http://127.0.0.1:9000/v1" and vals["OPENAI_SUB_API_KEY"] == "gw-key"
      and not vals["OPENAI_API_KEY"] and not vals["OPENAI_BASE_URL"], "прежний шлюз (не api.openai.com) стал подпиской, платного нет")
check("Подписка ChatGPT не подключена" not in out and "ChatGPT по подписке" in out, "порядок: подписка")
vals = {}
out = run_wizard(["2", ""], ["", "", ""], vals)
check(not any(vals.get(k) for k in ("OPENAI_SUB_BASE_URL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")) and "Перевод не включён" in out,
      "ничего не вписали — перевод не включён")
vals = {"OPENAI_SUB_BASE_URL": "x", "OPENAI_API_KEY": "y"}
run_wizard(["-"], [], vals)
check(not vals["OPENAI_SUB_BASE_URL"] and not vals["OPENAI_API_KEY"], "«-» — перевод выключен")
os.unlink(env_file.name)

print(f"OK: {ok} проверок")
