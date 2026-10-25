#!/usr/bin/env python3
# Логотип DUMSKAYA HOME из того же знака и тех же букв, что у DUMSKAYA DESIGN (assets/brand/logo-parts.json,
# трассировка — scripts/logo.py): «DUMSKAYA» — буквы названия студии как есть, «HOME»: M и E — из названия студии,
# H — две вертикали толщиной буквы I и перекладина, O — кольцо той же толщины по высоте круглых букв (S, G).
#   python3 scripts/home_logo.py      → home/public/logo-h.svg (в строку) и home/public/logo.svg (знак над названием)
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = json.load(open(os.path.join(ROOT, "assets/brand/logo-parts.json")))
subs = re.findall(r"M[^M]*", P["word"]["d"])


def bbox(s):
    n = list(map(float, re.findall(r"-?\d+\.?\d*", s)))
    return min(n[0::2]), min(n[1::2]), max(n[0::2]), max(n[1::2])


order = sorted(range(len(subs)), key=lambda i: bbox(subs[i])[0])
dumskaya = [i for i in order if bbox(subs[i])[2] < 700]           # D U M S KA Y A (с внутренними контурами)
x_of = lambda i: bbox(subs[i])[0]
M = next(i for i in order if 230 < x_of(i) < 240)                 # M в DUMSKAYA
E = next(i for i in order if 830 < x_of(i) < 840)                 # E в DESIGN
I = next(i for i in order if 990 < x_of(i) < 1000)                # I в DESIGN — толщина штриха
ix0, iy0, ix1, iy1 = bbox(subs[I])
stroke, top, bot = ix1 - ix0, iy0, iy1                            # 9.5, 1566.6–1640.5
round_top, round_bot = 1565.4, 1642.3                             # круглые буквы чуть выше и ниже
gap = 16.0                                                        # расстояние между буквами в названии

parts = ['<path d="' + "".join(subs[i] for i in dumskaya) + '"/>']      # одним контуром: внутренние у D и A — дыры
x = 751.0                                                         # там же, где у студии начинается DESIGN
w = 60.0                                                          # H
parts.append(f'<path d="M{x} {top}h{stroke}v{(top + bot) / 2 - top - stroke / 2:.2f}h{w - 2 * stroke}V{top}h{stroke}V{bot}h{-stroke}'
             f'V{(top + bot) / 2 + stroke / 2:.2f}h{-(w - 2 * stroke)}V{bot}h{-stroke}Z"/>')
x += w + gap
R = (round_bot - round_top) / 2; cy = (round_top + round_bot) / 2; cx = x + R; r = R - stroke * 1.05
ring = lambda c, rr, sweep: f"M{c - rr:.2f} {cy:.2f}a{rr:.2f} {rr:.2f} 0 1 {sweep} {2 * rr:.2f} 0a{rr:.2f} {rr:.2f} 0 1 {sweep} {-2 * rr:.2f} 0Z"
parts.append(f'<path d="{ring(cx, R, 1)}{ring(cx, r, 0)}"/>')
x += 2 * R + gap
for i in (M, E):
    bx0, _, bx1, _ = bbox(subs[i])
    parts.append(f'<g transform="translate({x - bx0:.2f} 0)"><path d="{subs[i]}"/></g>')
    x += bx1 - bx0 + gap
word_end = x - gap
mark = P["mark"]["d"]
out = os.path.join(ROOT, "home/public")
os.makedirs(out, exist_ok=True)
W = word_end + 299.66
h = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.2f} 240" role="img" aria-label="DUMSKAYA HOME">'
     f'<g fill="#000" fill-rule="evenodd"><g transform="translate(-115.96 -504.24) scale(0.47525)"><path d="{mark}"/></g>'
     f'<g transform="translate(299.66 -1483.50)">{"".join(parts)}</g></g></svg>')
open(os.path.join(out, "logo-h.svg"), "w").write(h)
mx0, my0, mx1, my1 = P["mark"]["bbox"]
shift = (70 + word_end) / 2 - (mx0 + mx1) / 2                     # знак по центру над названием
v = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="70 1061 {word_end - 70:.2f} 582" role="img" aria-label="DUMSKAYA HOME">'
     f'<g fill="#000" fill-rule="evenodd"><g transform="translate({shift:.2f} 0)"><path d="{mark}"/></g>{"".join(parts)}</g></svg>')
open(os.path.join(out, "logo.svg"), "w").write(v)
print(f"logo-h.svg: ширина {W:.0f}; logo.svg: {word_end - 70:.0f}×582")
