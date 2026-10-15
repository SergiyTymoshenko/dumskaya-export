#!/usr/bin/env python3
"""Совмещение двух версий одного фото: свет и цвет — из улучшенной (обычно меньшего размера,
например после обработки нейросетью), мелкая фактура и резкость — из оригинала в полном размере.
Фото должны быть одного кадра (допускается сдвиг на 1–2 пикселя — выравнивается автоматически).

  pip install opencv-python-headless numpy
  python3 scripts/photo_combine.py улучшенное.png оригинал.jpg результат.jpg
"""
import cv2, numpy as np
import sys
if len(sys.argv)!=4: sys.exit(__doc__)
ENH,HI,OUT=sys.argv[1:]
enh=cv2.imread(ENH).astype(np.float32)/255
hi=cv2.imread(HI).astype(np.float32)/255
Hh,Wh=hi.shape[:2]; He,We=enh.shape[:2]
# 1) выравнивание: ECC на масштабе 1448
lo=cv2.resize(hi,(We,He),interpolation=cv2.INTER_AREA)
g=lambda im: cv2.GaussianBlur(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),(0,0),1.5)
warp=np.eye(2,3,dtype=np.float32)
_,warp=cv2.findTransformECC(g(lo),g(enh),warp,cv2.MOTION_AFFINE,(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,300,1e-7),None,5)
# 2) «улучшенное» фото на сетку 3000 px с учётом сдвига
sx,sy=We/Wh,He/Hh
X,Y=np.meshgrid(np.arange(Wh,dtype=np.float32),np.arange(Hh,dtype=np.float32))
xl=(X+0.5)*sx-0.5; yl=(Y+0.5)*sy-0.5
mx=warp[0,0]*xl+warp[0,1]*yl+warp[0,2]; my=warp[1,0]*xl+warp[1,1]*yl+warp[1,2]
up=cv2.remap(enh,mx,my,cv2.INTER_LANCZOS4,borderMode=cv2.BORDER_REFLECT)
up=np.clip(up,0,1)
# 3) перенос мелкой фактуры из оригинала (в линейной яркости, отношением)
lin=lambda c: np.where(c<=0.04045,c/12.92,((c+0.055)/1.055)**2.4)
srgb=lambda c: np.where(c<=0.0031308,c*12.92,1.055*np.power(np.clip(c,0,None),1/2.4)-0.055)
Y=lambda im: 0.0722*im[...,0]+0.7152*im[...,1]+0.2126*im[...,2]   # BGR
hl=lin(hi); ul=lin(up)
Yh=Y(hl)+1e-4; Yu=Y(ul)+1e-4
sigma=1.6
ratio=Yh/(cv2.GaussianBlur(Yh,(0,0),sigma)+1e-4)
ratio=np.clip(ratio,0.6,1.6)
# мелкий шум рендера не переносим: отклонения меньше ~1.5% обнуляются (coring)
dev=ratio-1; t=0.015
dev=np.sign(dev)*np.maximum(np.abs(dev)-t,0)
ratio=1+dev
# 4) «чёткость» фактур: локальный контраст с сохранением краёв (без ореолов у контрастных границ)
Yr=Yu*ratio
L=np.log(Yr+1e-3).astype(np.float32)
base=cv2.bilateralFilter(L,d=0,sigmaColor=0.25,sigmaSpace=10)
Yr=np.exp(base+(L-base)*1.12)-1e-3
Yr=np.clip(Yr,0,None)
out=ul*(Yr/Yu)[...,None]
out=np.clip(srgb(np.clip(out,0,1)),0,1)
cv2.imwrite(OUT,(out*255+0.5).astype(np.uint8),[cv2.IMWRITE_JPEG_QUALITY,95,cv2.IMWRITE_JPEG_SAMPLING_FACTOR,cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444])
print('готово:',OUT,out.shape[1],'x',out.shape[0])
