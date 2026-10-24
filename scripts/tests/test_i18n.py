"""Проверка переводов кабинета и бота на европейские языки (deploy/i18n/<код>.json, список — deploy/langs.py):
у каждого языка есть файл, в нём все тексты кабинета (как в portal_app.html), бота (portal_bot.T) и словаря видов работ
и пакетов (crm_portal.FIXED); подстановки {…}, теги <b>/<i>, переносы строк и значки — как в оригинале; в языках
на латинице нет кириллицы. Нужен Node.js (тексты кабинета читаются из страницы).

   python3 scripts/tests/test_i18n.py      — в конце «OK: N проверок»"""
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "deploy"))
import crm_portal  # noqa: E402
import langs  # noqa: E402
import portal_bot  # noqa: E402

ok = 0
problems = []


def check(cond, what):
    global ok
    if cond:
        ok += 1
    else:
        problems.append(what)


page = os.path.join(REPO, "deploy", "portal_app.html")
js = """
const s = require('fs').readFileSync(process.argv[1], 'utf8');
const js = s.slice(s.indexOf('<script>\\n(()') + 8, s.lastIndexOf('</script>'));
const I = new Function(js.slice(js.indexOf('const I18N = {'), js.indexOf('  const pickLang')) + '; return I18N;')();
process.stdout.write(JSON.stringify(I));
"""
UI = json.loads(subprocess.run(["node", "-e", js, page], capture_output=True, text=True, check=True).stdout)
BOT = portal_bot.T
FIXED = crm_portal.FIXED
PH = re.compile(r"\{[a-z_]+\}")
TAGS = re.compile(r"</?[bi]>")
SYMBOLS = "✓⚠️🧾💬📁👁＋→←✈︎🟢📋🔗🧪📎🛋🚚🔔👥✅"
CYR = re.compile(r"[А-Яа-яЁёІіЇїЄєҐґЎў]")
CYRILLIC_LANGS = {"ru", "uk", "bg", "sr", "mk", "be"}


def same_shape(src, out, where):
    check(sorted(PH.findall(src)) == sorted(PH.findall(out)), f"{where}: подстановки {sorted(set(PH.findall(src)))} → {sorted(set(PH.findall(out)))}")
    check(sorted(TAGS.findall(src)) == sorted(TAGS.findall(out)), f"{where}: теги <b>/<i>")
    check(src.count("\n") == out.count("\n"), f"{where}: переносы строк {src.count(chr(10))} → {out.count(chr(10))}")
    for ch in SYMBOLS:
        if ch in src:
            check(ch in out, f"{where}: значок {ch}")
    check(bool(out.strip()), f"{where}: пусто")


# пять основных языков — в коде: всё на месте
for code in langs.BUILTIN:
    check(set(UI[code]) == set(UI["en"]), f"кабинет {code}: тексты не совпадают с английскими")
    for k, v in BOT.items():
        check(code in v, f"бот {code}: нет {k}")

for code in langs.CODES:
    if code in langs.BUILTIN:
        continue
    path = os.path.join(REPO, "deploy", "i18n", f"{code}.json")
    check(os.path.exists(path), f"{code}: нет файла deploy/i18n/{code}.json")
    if not os.path.exists(path):
        continue
    try:
        data = json.load(open(path, encoding="utf-8"))
    except ValueError as e:
        problems.append(f"{code}: файл не читается: {e}")
        continue
    ui, bot, fixed = data.get("ui") or {}, data.get("bot") or {}, data.get("fixed") or {}
    check(set(ui) == set(UI["en"]), f"{code}: кабинет — нет {sorted(set(UI['en']) - set(ui))[:8]}, лишние {sorted(set(ui) - set(UI['en']))[:8]}")
    check(set(bot) == set(BOT), f"{code}: бот — нет {sorted(set(BOT) - set(bot))[:8]}, лишние {sorted(set(bot) - set(BOT))[:8]}")
    check(set(fixed) == set(FIXED), f"{code}: словарь — нет {sorted(set(FIXED) - set(fixed))[:8]}")
    for k, v in ui.items():
        if k in UI["en"]:
            same_shape(UI["en"][k], str(v), f"{code} кабинет.{k}")
    for k, v in bot.items():
        if k in BOT:
            same_shape(BOT[k]["en"], str(v), f"{code} бот.{k}")
    for k, v in fixed.items():
        check(bool(str(v).strip()), f"{code} словарь.{k}: пусто")
    if code not in CYRILLIC_LANGS:
        left = [k for k, v in list(ui.items()) + list(bot.items()) + list(fixed.items()) if CYR.search(str(v))]
        check(not left, f"{code}: кириллица в текстах {left[:6]}")
    else:
        latin_heavy = [k for k, v in ui.items() if len(re.findall(r"[A-Za-z]", re.sub(r"DUMSKAYA DESIGN|Telegram|WhatsApp|E-mail|\{[a-z_]+\}", "", str(v)))) > 12]
        check(len(latin_heavy) < 5, f"{code}: много латиницы — не переведено? {latin_heavy[:6]}")
    check(langs.ui_lang(code) == code, f"{code}: код языка не узнаётся")

# коды Telegram → язык кабинета
for src, want in (("nb", "no"), ("nn", "no"), ("pt-br", "pt"), ("sr-Latn", "sr"), ("cs", "cs"), ("be", "be"), ("ca", "es"), ("zh", "en"), ("", "en")):
    check(langs.ui_lang(src) == want, f"ui_lang({src!r}) → {langs.ui_lang(src)}, нужно {want}")

if problems:
    print("\n".join("✗ " + p for p in problems[:80]))
    print(f"НЕ ПРОШЛО: {len(problems)} замечаний, {ok} проверок прошли")
    sys.exit(1)
print(f"OK: {ok} проверок, языков: {len(langs.CODES)}")
