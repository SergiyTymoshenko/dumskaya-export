"""Правка русского исходника с переносом памяти переводов: старая строка → новая строка
(и новые переводы). Используется из других скриптов: rekey(changes) где changes —
список (старый_RU, новый_RU, {'ua': перевод, 'en': перевод}) или None для перевода «как был»."""
import json, glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

def rekey(changes):
    tms = {l: load_tm(l) for l in LANGS}
    for old, new, tr in changes:
        for l in LANGS:
            if tr and l in tr: tms[l][new] = tr[l]
            elif old in tms[l]: tms[l][new] = tms[l][old]
    for l in LANGS: save_tm(l, tms[l])
