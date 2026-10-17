# OLEV: разбор техлистов (PDF) → коды исполнений, мощность, люмены, температура, вес
import json, re, io, pdfplumber
from concurrent.futures import ThreadPoolExecutor
from common import get, save
data = json.load(open('olev.json'))
def parse_pdf(b):
    pdf = pdfplumber.open(io.BytesIO(b)); out = []
    for pg in pdf.pages:
        t = pg.extract_text() or ''; L = [l.strip() for l in t.splitlines() if l.strip()]
        if not L: continue
        place_type = L[0] if re.match(r'^(INDOOR|OUTDOOR)\s*-', L[0]) else ''
        name = next((l for l in L[1:4] if re.match(r'^[A-Z0-9][A-Z0-9 \'’.&/Ø×x\-]{2,}$', l) and not l.startswith('-')), '')
        items = []
        for i, l in enumerate(L):
            if l.startswith('Item') and i + 1 < len(L):
                m = re.match(r'^([0-9][0-9A-Z./\-]{2,})', L[i + 1])
                if m: items.append(m.group(1))
        items += [m.group(1) for m in re.finditer(r'(?m)^(\d{3,5}[A-Z]?)\s+(?:M|W|\d{4}K)\b', t)]
        power = sorted(set(re.findall(r'(\d+(?:[.,]\d+)?)\s*W\b', next((l for l in L if l.startswith('Power')), ''))), key=lambda x: float(x.replace(',', '.')))
        lumen = sorted(set(re.findall(r'(\d+(?:[.,]\d+)?)\s*lm', ' '.join(l for l in L if 'lumen' in l.lower()))), key=lambda x: float(x.replace(',', '.')))
        cct = sorted(set(re.findall(r'\b(2200|2400|2700|3000|3500|4000|5000|6500)K\b', t)))
        beam = sorted(set(re.findall(r'(\d{1,3})°', ' '.join(l for l in L if l.lower().startswith('beam')))))
        supply = next((m.group(0) for m in re.finditer(r'\d{2,3}(?:-\d{2,3})?\s*V(?:dc|ac)?\b', ' '.join(l for l in L if l.lower().startswith('supply')))), '')
        w = re.search(r'net weight\s*([\d.,]+)\s*kg', t)
        ip = re.search(r'\bIP\s?(\d{2})\b', t)
        out.append({'place_type': place_type, 'name': name, 'items': list(dict.fromkeys(items)), 'power_w': power, 'lumen': lumen, 'cct': cct,
                    'beam': beam, 'supply': supply, 'net_kg': w.group(1) if w else '', 'ip': ip.group(1) if ip else '', 'cri90': '>90' in t})
    return out
def one(p):
    res = []
    for f in p['files']:
        if f['kind'] != 'datasheet': continue
        b = get(f['url'].replace('|', '%7C'), delay=0.5, binary=True)
        if not b: res.append({'url': f['url'], 'error': 'download'}); continue
        try: res.append({'url': f['url'], 'bytes': len(b), 'pages': parse_pdf(b)})
        except Exception as e: res.append({'url': f['url'], 'error': str(e)})
    return p['slug'], res
with ThreadPoolExecutor(3) as ex: ds = dict(ex.map(one, data))
save('olev_ds.json', ds)
items = sum(len(set(i for d in v if 'pages' in d for pg in d['pages'] for i in pg['items'])) for v in ds.values())
print('products', len(ds), 'pdf', sum(len(v) for v in ds.values()), 'errors', [(k, d.get('error')) for k, v in ds.items() for d in v if 'error' in d][:10], 'items', items,
      'no items', [k for k, v in ds.items() if not any(pg['items'] for d in v if 'pages' in d for pg in d['pages'])][:30])
