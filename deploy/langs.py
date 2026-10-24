#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Языки кабинетов в боте (решено 24.10.2026): государственные языки европейских стран. Человек выбирает язык кабинета
сам (⚙︎ или 🌐 в кабинете), по умолчанию — язык его Telegram. На этот язык бот пишет ему сообщения, переводит разговоры,
названия услуг, товаров, этапов и подписи документов.

Тексты кабинета и бота: русский, украинский, английский, словацкий, немецкий — в коде (portal_app.html, portal_bot.py,
crm_portal.FIXED); остальные языки — файлы deploy/i18n/<код>.json: {"ui": {…}, "bot": {…}, "fixed": {…}} (готовые
переводы, проверка — scripts/tests/test_i18n.py). Добавить язык: строка в LANGS и файл с переводом.
Только стандартная библиотека Python 3."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
I18N_DIR = os.path.join(HERE, "i18n")

# код, как называется на самом языке, по-русски (для Ирины), по-английски (для сервиса перевода), формат чисел и дат,
# «с …ого» (перевод с языка), «на …ом» (оригинал на языке)
LANGS = [
    ("ru", "Русский", "Русский", "Russian", "ru-RU", "русского", "русском"),
    ("uk", "Українська", "Украинский", "Ukrainian", "uk-UA", "украинского", "украинском"),
    ("en", "English", "Английский", "English", "en-GB", "английского", "английском"),
    ("sk", "Slovenčina", "Словацкий", "Slovak", "sk-SK", "словацкого", "словацком"),
    ("de", "Deutsch", "Немецкий", "German", "de-AT", "немецкого", "немецком"),
    ("cs", "Čeština", "Чешский", "Czech", "cs-CZ", "чешского", "чешском"),
    ("pl", "Polski", "Польский", "Polish", "pl-PL", "польского", "польском"),
    ("hu", "Magyar", "Венгерский", "Hungarian", "hu-HU", "венгерского", "венгерском"),
    ("fr", "Français", "Французский", "French", "fr-FR", "французского", "французском"),
    ("it", "Italiano", "Итальянский", "Italian", "it-IT", "итальянского", "итальянском"),
    ("es", "Español", "Испанский", "Spanish", "es-ES", "испанского", "испанском"),
    ("pt", "Português", "Португальский", "European Portuguese", "pt-PT", "португальского", "португальском"),
    ("nl", "Nederlands", "Нидерландский", "Dutch", "nl-NL", "нидерландского", "нидерландском"),
    ("ro", "Română", "Румынский", "Romanian", "ro-RO", "румынского", "румынском"),
    ("bg", "Български", "Болгарский", "Bulgarian", "bg-BG", "болгарского", "болгарском"),
    ("hr", "Hrvatski", "Хорватский", "Croatian", "hr-HR", "хорватского", "хорватском"),
    ("sl", "Slovenščina", "Словенский", "Slovenian", "sl-SI", "словенского", "словенском"),
    ("sr", "Српски", "Сербский", "Serbian (Cyrillic script)", "sr-RS", "сербского", "сербском"),
    ("bs", "Bosanski", "Боснийский", "Bosnian", "bs-BA", "боснийского", "боснийском"),
    ("mk", "Македонски", "Македонский", "Macedonian", "mk-MK", "македонского", "македонском"),
    ("sq", "Shqip", "Албанский", "Albanian", "sq-AL", "албанского", "албанском"),
    ("el", "Ελληνικά", "Греческий", "Greek", "el-GR", "греческого", "греческом"),
    ("tr", "Türkçe", "Турецкий", "Turkish", "tr-TR", "турецкого", "турецком"),
    ("lt", "Lietuvių", "Литовский", "Lithuanian", "lt-LT", "литовского", "литовском"),
    ("lv", "Latviešu", "Латышский", "Latvian", "lv-LV", "латышского", "латышском"),
    ("et", "Eesti", "Эстонский", "Estonian", "et-EE", "эстонского", "эстонском"),
    ("fi", "Suomi", "Финский", "Finnish", "fi-FI", "финского", "финском"),
    ("sv", "Svenska", "Шведский", "Swedish", "sv-SE", "шведского", "шведском"),
    ("da", "Dansk", "Датский", "Danish", "da-DK", "датского", "датском"),
    ("no", "Norsk", "Норвежский", "Norwegian (Bokmål)", "nb-NO", "норвежского", "норвежском"),
    ("is", "Íslenska", "Исландский", "Icelandic", "is-IS", "исландского", "исландском"),
    ("ga", "Gaeilge", "Ирландский", "Irish (Gaeilge)", "ga-IE", "ирландского", "ирландском"),
    ("mt", "Malti", "Мальтийский", "Maltese", "mt-MT", "мальтийского", "мальтийском"),
    ("be", "Беларуская", "Белорусский", "Belarusian", "be-BY", "белорусского", "белорусском"),
]
CODES = [x[0] for x in LANGS]
BUILTIN = ("ru", "uk", "en", "sk", "de")          # тексты в коде; остальные — из файлов deploy/i18n
BY = {x[0]: x for x in LANGS}
# коды Telegram и браузера, которых нет в списке, → ближайший язык из списка
ALIASES = {"nb": "no", "nn": "no", "cnr": "sr", "sh": "hr", "lb": "de", "gsw": "de", "rm": "de", "ca": "es", "eu": "es",
           "gl": "es", "fy": "nl", "cy": "en", "gd": "en", "fo": "da", "kl": "da", "se": "no", "az": "tr", "kk": "ru",
           "ky": "ru", "uz": "ru", "tg": "ru", "hy": "ru", "ka": "ru"}


def ui_lang(code):
    """Язык кабинета по коду Telegram или выбранному: из списка LANGS; похожие — к ближайшему; остальное — английский."""
    c = (code or "").lower().replace("_", "-")
    if c.startswith("sr-latn") or c in ("sr-me",):
        return "sr"
    c = c.split("-")[0]
    return c if c in BY else ALIASES.get(c, "en")


def native(code):
    return BY.get(code, BY["en"])[1]


def ru_name(code):
    return BY[code][2] if code in BY else code


def en_name(code):
    return BY[code][3] if code in BY else "English"


def locale(code):
    return BY.get(code, BY["en"])[4]


_cache = {}


def pack(code):
    """Переводы для языка из файла deploy/i18n/<код>.json ({"ui", "bot", "fixed"}); нет файла — пусто."""
    if code in _cache:
        return _cache[code]
    data = {}
    if code in BY and code not in BUILTIN:
        try:
            with open(os.path.join(I18N_DIR, f"{code}.json"), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
    _cache[code] = data if isinstance(data, dict) else {}
    return _cache[code]


def public_list():
    """Для кабинета: [[код, название на этом языке, формат чисел и дат], …] — основные пять сначала, остальные по алфавиту."""
    first = [BY[c] for c in BUILTIN]
    rest = sorted((x for x in LANGS if x[0] not in BUILTIN), key=lambda x: x[1].lower())
    return [[x[0], x[1], x[4]] for x in first + rest]


def studio_list():
    """Для «Студии»: [[код, по-русски, «с …ого», «на …ом»], …] — основные пять сначала, остальные по-русски по алфавиту."""
    first = [BY[c] for c in BUILTIN]
    rest = sorted((x for x in LANGS if x[0] not in BUILTIN), key=lambda x: x[2])
    return [[x[0], x[2], x[5], x[6]] for x in first + rest]
