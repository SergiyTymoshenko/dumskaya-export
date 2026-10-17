import re, json
def rsc_text(h):
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', h)
    return ''.join(json.loads('"' + c + '"') for c in chunks)
def json_at(s, start):
    """JSON-объект, начинающийся в s[start] ('{'), с учётом строк."""
    depth = 0; i = start; ins = False; esc = False
    while i < len(s):
        ch = s[i]
        if ins:
            if esc: esc = False
            elif ch == '\\': esc = True
            elif ch == '"': ins = False
        else:
            if ch == '"': ins = True
            elif ch in '{[': depth += 1
            elif ch in '}]':
                depth -= 1
                if depth == 0: return json.loads(s[start:i + 1])
        i += 1
    return None
def find_obj(s, key):
    i = s.find(key)
    if i < 0: return None
    j = s.rfind('{', 0, i + 1) if not s[i] == '{' else i
    return json_at(s, i if s[i] == '{' else j)
