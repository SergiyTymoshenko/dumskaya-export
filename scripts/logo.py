#!/usr/bin/env python3
# Логотип: исходник assets/brand/logo-source.png (белый на чёрном) → векторные файлы в public/.
#   pip install potracer scipy pillow numpy
#   python3 scripts/logo.py [исходник.png]
# Шаг 1 — трассировка знака, названия и подписи (компоненты ищутся автоматически по номерам
# связных областей; при другом исходнике их нужно проверить), шаг 2 — сборка SVG-вариантов.

# --- шаг 1: трассировка ---
import numpy as np, potrace, json
from PIL import Image
from scipy import ndimage
import os, sys
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC=sys.argv[1] if len(sys.argv)>1 else os.path.join(ROOT,'assets/brand/logo-source.png')
g=np.asarray(Image.open(SRC).convert('L')).astype(float)
lab,n=ndimage.label(g>128)
parts={'mark':[1,2],'word':list(range(3,16)),'tag':list(range(16,30))}
S=4  # трассировка в 4x для гладких кривых
out={}
for name,ids in parts.items():
    m=np.isin(lab,ids)
    m=ndimage.binary_dilation(m,iterations=2)
    ys,xs=np.where(m); y0,y1,x0,x1=ys.min()-3,ys.max()+4,xs.min()-3,xs.max()+4
    crop=(g*m)[y0:y1,x0:x1]
    big=np.asarray(Image.fromarray(crop.astype(np.uint8)).resize(((x1-x0)*S,(y1-y0)*S),Image.LANCZOS))
    bm=potrace.Bitmap(~(big>128))  # potracer считает «чернилами» тёмные пиксели
    path=bm.trace(turdsize=8,turnpolicy=potrace.POTRACE_TURNPOLICY_MINORITY,alphamax=1.0,opticurve=True,opttolerance=0.2)
    f=lambda p:f"{(p.x/S+x0):.2f} {(p.y/S+y0):.2f}"
    d=[]
    for c in path:
        d.append('M'+f(c.start_point))
        for seg in c:
            if seg.is_corner: d.append('L'+f(seg.c)+'L'+f(seg.end_point))
            else: d.append('C'+f(seg.c1)+' '+f(seg.c2)+' '+f(seg.end_point))
        d.append('Z')
    # точные границы по исходным пикселям частей
    ys,xs=np.where(np.isin(lab,ids))
    out[name]={'d':''.join(d),'bbox':[int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1],'curves':len(path)}
    print(name,out[name]['bbox'],'curves',len(path),'len',len(out[name]['d']))
json.dump(out,open(os.path.join(ROOT,'assets/brand/logo-parts.json'),'w'))


# --- шаг 2: сборка SVG ---
import re
import os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P=json.load(open(os.path.join(ROOT,'assets/brand/logo-parts.json')))
PUB=os.path.join(ROOT,'public')
def r1(d): return re.sub(r'-?\d+\.\d+', lambda m: f"{float(m.group()):.1f}".rstrip('0').rstrip('.'), d)
for k in P: P[k]['d']=r1(P[k]['d'])
def svg(vb, body, title='DUMSKAYA DESIGN', fill='#000'):
    x,y,w,h=vb
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:g} {y:g} {w:g} {h:g}" role="img" aria-label="{title}">'
            f'<g fill="{fill}" fill-rule="evenodd">{body}</g></svg>\n')
path=lambda k: f'<path d="{P[k]["d"]}"/>'
m,wd,t=P['mark']['bbox'],P['word']['bbox'],P['tag']['bbox']
# 1) полный логотип (как в оригинале): знак, название, подпись
x0=min(m[0],wd[0],t[0]); y0=m[1]; x1=max(m[2],wd[2],t[2]); y1=t[3]
open(os.path.join(PUB,'logo.svg'),'w').write(svg((x0,y0,x1-x0,y1-y0), path('mark')+path('word')+path('tag')))
# 2) знак
open(os.path.join(PUB,'logo-mark.svg'),'w').write(svg((m[0],m[1],m[2]-m[0],m[3]-m[1]), path('mark')))
# 3) горизонтальный: знак слева, название справа по центру знака
MH=240; s=MH/(m[3]-m[1]); mw=(m[2]-m[0])*s; gap=56
ww=wd[2]-wd[0]; wh=wd[3]-wd[1]
body=(f'<g transform="translate({-m[0]*s:.2f} {-m[1]*s:.2f}) scale({s:.5f})">{path("mark")}</g>'
      f'<g transform="translate({mw+gap-wd[0]:.2f} {(MH-wh)/2-wd[1]:.2f})">{path("word")}</g>')
open(os.path.join(PUB,'logo-h.svg'),'w').write(svg((0,0,mw+gap+ww,MH), body))
# 4) белый знак на чёрном квадрате — для значка вкладки и иконок
side=max(m[2]-m[0],m[3]-m[1])*1.3; cx=(m[0]+m[2])/2; cy=(m[1]+m[3])/2
fav=(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{cx-side/2:.1f} {cy-side/2:.1f} {side:.1f} {side:.1f}">'
     f'<rect x="{cx-side/2:.1f}" y="{cy-side/2:.1f}" width="{side:.1f}" height="{side:.1f}" fill="#000"/>'
     f'<g fill="#fff" fill-rule="evenodd">{path("mark")}</g></svg>\n')
open(os.path.join(PUB,'favicon.svg'),'w').write(fav)
import os
for f in ['logo.svg','logo-mark.svg','logo-h.svg','favicon.svg']: print(f, os.path.getsize(os.path.join(PUB,f)))
print('h ratio', (mw+gap+ww)/MH)
