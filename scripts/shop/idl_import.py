#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Первичный импорт номенклатуры светильников IDL 1987 (каталог 2024 + Novelties 2025) в content/shop/catalog/idl.json.

idl-index.txt — указатель кодов из каталогов (код;коллекция;тип по фото;страницы;n — Novelties 2025), снятый
с PDF фабрики. Артикулы сайта: DL-<тип><номер>, у каждой коллекции свой блок из 50 номеров (см. README, «Магазин»).
Скрипт для первичной загрузки: он заново раздаёт номера по порядку. Когда товары будут на сайте, новые позиции
добавлять в idl.json вручную (или отдельным скриптом) — выданные артикулы не менять.
   python3 scripts/shop/idl_import.py"""
import json, re, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = [';'.join(m) for m in re.findall(r'(\d{3}[A-Z]?/[^;]+);([^;]+);([^;]*);([\d,]+);(n?)', open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'idl-index.txt')).read())]
FIN = {
 'acropora': 'Металлический каркас: сталь, тёмный кортен, светлое золото, чёрный никель, глянцевое античное золото, матовое античное золото. Рассеиватель — сатинированный Plexiglas.',
 'amalfi': 'Металлическое основание: глянцевый белый или чёрный, окисленный кортен, эффект ржавчины; внутренняя часть — золотая или серебряная фольга либо белый матовый. Рассеиватель — сатинированный поликарбонат.',
 'artic': 'Металлическое основание: светлое золото, чёрный никель, матовая бронза, сталь.',
 'bamboo': 'Металлический каркас: хром, золото 24 карата, сатинированный чёрный никель, чёрный никель. Плафоны из муранского стекла: прозрачные с хромированным или золотым декором, прозрачные. Абажур из ткани chinette или lamé золотого или серебряного цвета.',
 'cesare': 'Металлическое основание: сатинированный никель, сатинированный чёрный никель, сатинированное золото, сатинированная бронза. Муранское стекло с гравировкой: бронзовое, дымчатое, прозрачное.',
 'collier': 'Металлический каркас в окрашенных отделках: gold, rame yamana (медь). Диффузор — силиконовая трубка 3D Flex LED.',
 'dp': 'Металлический каркас: блестящий кварц с деталями из матовой бронзы, блестящий песочный с деталями из матового золота, брашированная латунь. Диффузоры — матовое муранское стекло белого или бронзового цвета.',
 'ekle': 'Металлическое основание в сочетаниях: сатинированное золото и сталь, сатинированное золото и бронза, сатинированное золото и тёмный кортен, сатинированное золото. Диффузор — сатинированный Plexiglas.',
 'endless': 'Металлический каркас: красный матовый, зелёный матовый, синий матовый, бронза матовая, белый матовый. Диффузор — светодиодная лента 3D.',
 'flower-miu': 'Металлический каркас: сталь, светлое золото, матовое античное золото. Диффузор — прозрачное муранское стекло.',
 'galaxy': 'Металлический каркас: окрашенный Shiny Sand, окрашенный Matt White, гальванический матовый чёрный никель, гальванический Pure Steel. Диффузоры — прозрачный и сатинированный Plexiglas.',
 'loop': 'Металлический каркас: красный матовый, зелёный матовый, синий матовый, бронза матовая, белый матовый. Диффузор — светодиодная лента 3D.',
 'mangrove': 'Металлический каркас: окрашенный Colombia, окрашенный Shiny Sand, брашированная латунь. Диффузоры — сатинированный Plexiglas.',
 'marea': 'Металлический каркас: блестящий песочный, тёмно-серый (grigio Danimarca), сатинированное светлое золото. Диффузор — прозрачное муранское стекло pulegoso.',
 'miox': 'Металлический каркас: матовое светлое золото, сталь, чёрный никель. Рассеиватель — прозрачное муранское стекло pulegoso.',
 'miu': 'Металлический каркас: тёмный кортен, матовое античное золото, сталь, светлое золото.',
 'nature': 'Металлический каркас: окрашенный Colombia, матовое светлое золото. Диффузоры — выдувное стекло по муранской технологии: прозрачное, бронзовое, дымчатое, жемчужное.',
 'paradise': 'Металлический каркас: хром или светлое золото. Муранское стекло: белое, прозрачное, аквамарин, бронза, с эффектом золотой или серебряной фольги. Основание настольной лампы и торшера — сатинированный никель.',
 'roma': 'Металлическое основание: хром. Стеклянные подвески. Возможны размеры на заказ.',
 'charme': 'Металлическое основание: чёрный никель, сталь, бронза, медь, светлое золото. Абажуры тёмного или светлого оттенка из джута или chinette либо цветной plissé. Декоративное муранское стекло: прозрачное, янтарное, дымчатое, голубое, зелёное, белое.',
 'chrysalis': 'Металлическое основание: светлое золото, сталь, слоновая кость, тёмный баклажан, чёрный никель. Декоративные элементы из прозрачного хрусталя. Возможны размеры на заказ.',
 'corten': 'Металлическое основание: кортен серебристого цвета с хромированными цепочками или кортен коричневого цвета с золотыми цепочками. Декоративные элементы из прозрачного хрусталя.',
 'crystal-blade': 'Металлический каркас: светлое золото, тёмный баклажан, хром. Плафоны — прозрачное муранское стекло, декоративные элементы из прозрачного хрусталя.',
 'crystalline': 'Металлический каркас: хром или светлое золото. Хрустальные подвески и стеклянные элементы: прозрачные, белые, чёрные, красные.',
 'diamante': 'Металлический каркас: хром. Прозрачные кристаллы Asfour.',
 'groovy': 'Металлическое основание в сочетаниях: белый матовый, чёрный матовый или чёрная фольга со светлым золотом или сталью; полностью светлое золото; полностью сталь. Декоративные элементы из прозрачного хрусталя; у бра — рассеиватель из сатинированного Plexiglas.',
 'ice-rain': 'Металлическое основание цвета слоновой кости. Листья из прозрачного или белого муранского стекла либо мультиколор — сочетание стеклянных и металлических (золото или сталь) листьев.',
 'leaves': 'Металлическое основание в сочетаниях: светлое золото, бронза и чёрный никель; светлое золото и бронза; светлое золото и чёрный никель; бронза и чёрный никель; чёрный никель и сталь. Декоративные подвески из прозрачного стекла.',
 'ninfea': 'Металлическое основание: хром или светлое золото. Подвески из белого муранского жемчуга или прозрачного хрусталя.',
 'tribu': 'Металлический каркас: глянцевое античное золото, светлое золото, сталь, бархатный белый. Чеканное прозрачное муранское стекло.',
 'vanity': 'Абажуры из джута светлого или тёмного оттенка, chinette слоновой кости или серо-бежевого цвета, белый или слоновой кости plissé.',
 'weave': 'Металлическое основание: сталь, светлое золото, бронза. Абажуры настольных ламп из джута или chinette тёмного и светлого оттенка.',
 'angel': 'Металлический каркас: сталь. Прозрачное муранское стекло pulegoso. Абажуры настольных ламп: джут светлый или тёмный, chinette слоновой кости или серо-бежевая.',
 'crystal-moon': 'Металлический каркас: светлое золото. Белые плафоны из муранского стекла, декоративные кристаллы.',
 'crystal-rock': 'Металлический каркас: светлое золото с золотыми цепочками, ржавчина, бархатный чёрный. Абажуры chinette слоновой кости или серо-бежевые.',
 'elite': 'Металлический каркас: сталь, светлое золото, бронза. Листья из муранского стекла: белые или прозрачные. Возможны размеры на заказ.',
 'floritude': 'Металлический каркас: сталь. Цветы из кристаллов Asfour.',
 'grace': 'Металлический каркас: бархатный белый, бархатный чёрный, брашированный чёрный никель, брашированный хром, брашированное золото. Абажуры из ткани lamé золотого или серебряного цвета.',
}
COLS = [  # (название, слуг на сайте фабрики, линия, дизайнер)
 ('Acropora','acropora','contemporary','Cristian Feltrin'), ('Amalfi','amalfi','contemporary','Cristian Feltrin'),
 ('Artic','artic','contemporary','Cristian Feltrin'), ('Bamboo','bamboo','contemporary','Cristian Feltrin'),
 ('Cesare','cesare','contemporary','Cristian Feltrin'), ('Collier','collier','contemporary','Alessandro Masturzo'),
 ('DP','dp','contemporary','Cristian Feltrin'), ('Eklè','ekle','contemporary','Cristian Feltrin'),
 ('Endless','endless','contemporary','IDL Studio'), ('Flower Miù','flower-miu','contemporary','Cristian Feltrin'),
 ('Galaxy','galaxy','contemporary','Alessandro Masturzo'), ('Loop','loop','contemporary','IDL Studio'),
 ('Mangrove','mangrove','contemporary','Alessandro Masturzo'), ('Marea','marea','contemporary','Cristian Feltrin'),
 ('Miox','miox','contemporary','Cristian Feltrin'), ('Miu','miu','contemporary','Cristian Feltrin'),
 ('Nature','nature','contemporary','IDL Studio'), ('Paradise','paradise','contemporary','Cristian Feltrin'),
 ('Roma','roma','contemporary','Antonio Piva'),
 ('Charme','charme','luxury','Cristian Feltrin'), ('Chrysalis','chrysalis','luxury','Cristian Feltrin'),
 ('Corten','corten','luxury','Cristian Feltrin'), ('Crystal Blade','crystal-blade','luxury','Cristian Feltrin'),
 ('Crystalline','crystalline','luxury','Cristian Feltrin'), ('Diamante','diamante','luxury','Cristian Feltrin'),
 ('Groovy','groovy','luxury','Cristian Feltrin'), ('Ice Rain','ice-rain','luxury','Cristian Feltrin'),
 ('Leaves','leaves','luxury','Cristian Feltrin'), ('Ninfea','ninfea','luxury','Cristian Feltrin'),
 ('Tribù','tribu','luxury','Cristian Feltrin'), ('Vanity','vanity','luxury','Cristian Feltrin'),
 ('Weave','weave','luxury','Cristian Feltrin'),
 ('Angel','angel','catalog','IDL Staff'), ('Crystal Moon','crystal-moon','catalog','Cristian Feltrin'),
 ('Crystal Rock','crystal-rock','catalog','Cristian Feltrin'), ('Elite','elite','catalog','Cristian Feltrin'),
 ('Floritude','floritude','catalog','Cristian Feltrin'), ('Grace','grace','catalog','IDL Staff'),
]
ALIAS = {'Dp': 'DP', 'Flower Miu': 'Flower Miù'}
LETTER = {'suspension': 'S', 'ceiling': 'C', 'wall': 'W', 'table': 'T', 'floor': 'F', 'spot': 'C'}

def kind(code, photo):
    s = code.split('/', 1)[1].upper()
    s = re.sub(r'/E$', '', s)
    if s == 'SPOT': return 'spot'
    if 'PF' in s: return 'ceiling'
    if re.search(r'(^|\d|\+\d+)P$', s) or re.search(r'\dP$', s): return 'floor'
    if re.search(r'(^|\d)L[GMP]?$', s) or s in ('L', 'LP'): return 'table'
    if re.search(r'(^|\d|\+\d)A([GP]|DX|SX|-[GM])?$', s) or s in ('A', 'AG', 'AP') or 'A-' in s or re.search(r'\dA[GP]-PF[GP]$', s): return 'wall'
    if re.search(r'\dS[GMPL]?$', s) or re.search(r'\dSLED$', s) or re.search(r'\dS$', s): return 'suspension'
    return photo or 'suspension'

col_by = {c[0]: c for c in COLS}
items = []
for tok in RAW:
    tok = tok.strip()
    if not tok: continue
    code, col, photo, pages, src = (tok.split(';') + [''] * 5)[:5]
    if code == '669/12' and col == 'Galaxy': continue   # опечатка в Novelties 2025 (на листе с размерами — 689/12)
    col = ALIAS.get(col, col)
    items.append({'mfr_code': code, 'collection': col, 'type': kind(code, photo), 'catalog': 'IDL Novelties 2025' if src == 'n' else 'IDL 2024',
                  'catalog_pages': [int(x) for x in pages.split(',') if x]})
seen = set(); uniq = []
for it in items:
    if it['mfr_code'] in seen: continue
    seen.add(it['mfr_code']); uniq.append(it)
# артикулы: блок по 50 номеров на коллекцию, порядок коллекций — COLS, внутри — порядок кодов в каталоге
products = []
for bi, c in enumerate(COLS):
    base = 1000 + 50 * bi
    group = [it for it in uniq if it['collection'] == c[0]]
    assert len(group) < 50, c
    for n, it in enumerate(group, 1):
        sku = f"DL-{LETTER[it['type']]}{base + n}"
        products.append({'sku': sku, **it})
missing = [it for it in uniq if it['collection'] not in col_by]
assert not missing, missing
collections = {c[1]: {'name': c[0], 'line': c[2], 'designer': c[3], 'sku_block': f'{1000 + 50 * i}–{1000 + 50 * i + 49}',
                      'mfr_url': f'https://www.idl1987.it/ru/collezioni/illuminazione/{c[1]}/' if c[2] != 'catalog' else None,
                      'finishes': {'ru': FIN[c[1]]}, 'products': sum(1 for p in products if p['collection'] == c[0])}
               for i, c in enumerate(COLS)}
slug_of = {c[0]: c[1] for c in COLS}
for p in products: p['collection'] = slug_of[p['collection']]
data = {
 'manufacturer': 'idl',
 'sources': [
   {'title': 'IDL — каталог 2024 (388 стр.)', 'url': 'https://www.idl1987.it/file-download/IDL-luce1987-2024.pdf'},
   {'title': 'IDL — Novelties 2025 (49 стр.)', 'url': 'https://www.idl1987.it/wp-content/uploads/2025/04/IDL-2025-novelties-1.pdf'},
   {'title': 'IDL — коллекции на сайте фабрики', 'url': 'https://www.idl1987.it/ru/collezioni/illuminazione/'}],
 'status': 'черновик: номенклатура и артикулы готовы; фото, размеры, свет и тексты карточек — при выкладке на сайт',
 'collections': collections,
 'products': products,
}
dst = os.path.join(ROOT, 'content/shop/catalog/idl.json')
json.dump(data, open(dst, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
from collections import Counter
print('товаров', len(products), 'коллекций', len(collections))
print(Counter(p['type'] for p in products))
print(Counter(c['line'] for c in collections.values()))
