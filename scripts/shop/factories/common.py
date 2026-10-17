# Общее для сборщиков данных фабрик: вежливые запросы с кешем на диске
import os, time, hashlib, threading, re, json, requests
from urllib.parse import urljoin
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36 DumskayaCatalog/1.0'
HERE = os.path.dirname(os.path.abspath(__file__))
_s = requests.Session(); _s.headers.update({'User-Agent': UA, 'Accept-Language': 'en,ru;q=0.8'})
_lock = threading.Lock(); _last = {}
def get(url, delay=1.0, cache=True, binary=False, tries=3):
    os.makedirs(os.path.join(HERE, 'cache'), exist_ok=True)
    fn = os.path.join(HERE, 'cache', hashlib.sha1(url.encode()).hexdigest() + ('.bin' if binary else '.html'))
    if cache and os.path.exists(fn):
        return open(fn, 'rb').read() if binary else open(fn, encoding='utf-8', errors='replace').read()
    host = re.sub(r'^https?://([^/]+).*', r'\1', url)
    for k in range(tries):
        with _lock:
            wait = _last.get(host, 0) + delay - time.time()
            if wait > 0: time.sleep(wait)
            _last[host] = time.time()
        try:
            r = _s.get(url, timeout=40)
            if r.status_code == 200:
                data = r.content if binary else r.text
                if cache:
                    (open(fn, 'wb').write(data) if binary else open(fn, 'w', encoding='utf-8').write(data))
                return data
            if r.status_code in (404, 410, 403): return None
        except Exception as e:
            print('ERR', url, e, flush=True)
        time.sleep(3 * (k + 1))
    return None
def sitemap_urls(url, delay=1.0, depth=0):
    t = get(url, delay=delay, cache=False) or ''
    locs = re.findall(r'<loc>\s*(?:<!\[CDATA\[)?\s*([^<\s\]]+)', t)
    if '<sitemapindex' in t and depth < 3:
        out = []
        for l in locs: out += sitemap_urls(l, delay, depth + 1)
        return out
    return locs
def save(name, data):
    json.dump(data, open(os.path.join(HERE, name), 'w'), ensure_ascii=False, indent=1)
