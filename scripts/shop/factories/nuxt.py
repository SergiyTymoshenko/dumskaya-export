import json, re
def nuxt_data(html):
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m: return None
    data = json.loads(m.group(1)); memo = {}
    def r(i, depth=0):
        if not isinstance(i, int) or i < 0 or i >= len(data): return None
        if i in memo: return memo[i]
        v = data[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in ('Reactive', 'ShallowReactive', 'Ref', 'ShallowRef', 'EmptyRef', 'EmptyShallowRef', 'NuxtError', 'Date', 'Set', 'Map', 'BigInt', 'RegExp'):
                if v[0] in ('Reactive', 'ShallowReactive', 'Ref', 'ShallowRef'): out = r(v[1], depth + 1)
                elif v[0] == 'Set': out = [r(x, depth + 1) for x in v[1:]]
                else: out = v[1] if len(v) > 1 else None
            else:
                out = []; memo[i] = out
                out.extend(r(x, depth + 1) for x in v)
            memo[i] = out; return out
        if isinstance(v, dict):
            out = {}; memo[i] = out
            for k, x in v.items(): out[k] = r(x, depth + 1)
            return out
        memo[i] = v; return v
    return r(0)
