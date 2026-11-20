"""Evaluate every configlib patch at the user's current yaml values and emit static JsonPatch ops
for each one whose result differs from the base asset. Usage: bake_all.py <outdir>
Prints a summary only. Writes report.csv and patch files under <outdir>/assets/configlibbake/patches/."""
import ast, csv, glob, json, os, re, sys, operator
import pyjson5

UNPACK = r'C:\Work\vs\master-unpack'
VANILLA = os.path.join(os.environ.get('APPDATA', ''), 'Vintagestory', 'assets')
MODCFG = os.path.join(os.environ.get('APPDATA', ''), 'VintagestoryData', 'ModConfig')
out = sys.argv[1]

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos,
       ast.Gt: operator.gt, ast.Lt: operator.lt, ast.GtE: operator.ge, ast.LtE: operator.le,
       ast.Eq: operator.eq, ast.NotEq: operator.ne}
FUNCS = {'min': min, 'max': max, 'abs': abs, 'round': round, 'floor': lambda x: float(int(x // 1)),
         'ceiling': lambda x: -float(int(-x // 1)), 'sqrt': lambda x: x ** 0.5, 'clamp': lambda x, a, b: max(a, min(b, x))}

def ev(node, env):
    if isinstance(node, ast.Expression): return ev(node.body, env)
    if isinstance(node, ast.Constant): return node.value
    if isinstance(node, ast.Name):
        if node.id in env: return env[node.id]
        if node.id.lower() in ('true', 'false'): return node.id.lower() == 'true'
        raise KeyError(node.id)
    if isinstance(node, ast.BinOp): return OPS[type(node.op)](ev(node.left, env), ev(node.right, env))
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not): return not ev(node.operand, env)
        return OPS[type(node.op)](ev(node.operand, env))
    if isinstance(node, ast.Compare):
        l = ev(node.left, env)
        for op, r in zip(node.ops, node.comparators):
            rv = ev(r, env)
            if not OPS[type(op)](l, rv): return False
            l = rv
        return True
    if isinstance(node, ast.BoolOp):
        vals = [ev(v, env) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.IfExp): return ev(node.body, env) if ev(node.test, env) else ev(node.orelse, env)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.lower() in FUNCS:
        return FUNCS[node.func.id.lower()](*[ev(a, env) for a in node.args])
    raise ValueError('unsupported ' + type(node).__name__)

def to_py(expr):
    e = str(expr).strip()
    m = re.match(r'^\((.*)\)\s*\?\s*(.*?)\s*:\s*(.*)$', e)  # configlib ternary
    if m: e = f'({m[2]}) if ({m[1]}) else ({m[3]})'
    e = e.replace('&&', ' and ').replace('||', ' or ').replace('^', '**')
    e = re.sub(r'!(?!=)', ' not ', e)
    return e

def read_yaml(domain):
    p = os.path.join(MODCFG, domain + '.yaml')
    if not os.path.exists(p): return None
    vals = {}
    for ln in open(p, encoding='utf-8', errors='replace'):
        m = re.match(r'^([A-Za-z0-9_\-\.]+):\s*(.*?)\s*(#.*)?$', ln.rstrip('\n'))
        if not m or m[2] == '': continue
        v = m[2].strip().strip('"').strip("'")
        if v.lower() in ('true', 'false'): vals[m[1]] = v.lower() == 'true'
        else:
            try: vals[m[1]] = float(v) if re.search(r'[.eE]', v) else int(v)
            except ValueError: vals[m[1]] = v
    return vals

def settings_of(d):
    s = d.get('settings') or {}
    res = {}
    if isinstance(s, dict):
        for cat, items in s.items():
            if isinstance(items, dict):
                for code, it in items.items():
                    if isinstance(it, dict): res[code] = it
    else:
        for it in s:
            if isinstance(it, dict) and it.get('code'): res[it['code']] = it
    return res

asset_index = {}
def find_asset(loc, mod_root):
    dom, path = loc.split(':', 1)
    cands = [os.path.join(mod_root, 'assets', dom, path)]
    cands += glob.glob(os.path.join(UNPACK, '*', 'assets', dom, path))
    cands += glob.glob(os.path.join(VANILLA, dom, path))
    for c in cands:
        if os.path.exists(c): return c
    return None

def get_path(doc, segs):
    cur, res = doc, []
    for s in segs:
        if isinstance(cur, list):
            if '=' in s:
                k, v = s.split('=', 1)
                idx = next((i for i, e in enumerate(cur) if isinstance(e, dict) and str(e.get(k)) == v), None)
                if idx is None: return ('MISSING', None, res)
            else:
                try: idx = int(s)
                except ValueError: return ('MISSING', None, res)
                if idx >= len(cur): return ('MISSING', None, res)
            cur = cur[idx]; res.append(str(idx))
        elif isinstance(cur, dict):
            if s not in cur: return ('MISSING', None, res + [s])
            cur = cur[s]; res.append(s)
        else: return ('MISSING', None, res)
    return ('OK', cur, res)


import fnmatch
def expand_glob(node, pat):
    if isinstance(node, dict):
        return [k for k in node if fnmatch.fnmatchcase(k, pat)]
    if isinstance(node, list):
        return [str(i) for i, e in enumerate(node) if isinstance(e, dict) and fnmatch.fnmatchcase(str(e.get('code')), pat)]
    return []

rows, ops_by_file = [], {}
cfgs = glob.glob(os.path.join(UNPACK, '*', 'assets', '*', 'config', 'configlib-patches.json'))
for cf in cfgs:
    parts = cf.split(os.sep)
    mod_root = os.sep.join(parts[:parts.index('assets')])
    domain = parts[parts.index('assets') + 1]
    try: d = pyjson5.decode(open(cf, encoding='utf-8-sig').read())
    except Exception as e:
        rows.append(dict(domain=domain, status='CFG_PARSE_FAIL', note=str(e)[:80])); continue
    sets = settings_of(d)
    yaml = read_yaml(domain) or {}
    env_cur, env_def = {}, {}
    for code, it in sets.items():
        name = it.get('name', code)
        dv = it.get('default')
        env_def[code] = dv
        env_cur[code] = yaml.get(name, yaml.get(code, dv))
    for k, v in (d.get('constants') or {}).items():
        env_cur.setdefault(k, v); env_def.setdefault(k, v)
    for cat, targets in (d.get('patches') or {}).items():
        if not isinstance(targets, dict): continue
        for tgt, paths in targets.items():
            if not isinstance(paths, dict): continue
            if tgt.startswith('@'):
                rows.append(dict(domain=domain, cat=cat, target=tgt, status='WILDCARD_SKIPPED')); continue
            loc = tgt if ':' in tgt else domain + ':' + tgt
            ap = find_asset(loc, mod_root)
            doc = None
            if ap:
                try: doc = pyjson5.decode(open(ap, encoding='utf-8-sig').read())
                except Exception as e: doc = None
            items = []
            for jp0, expr in paths.items():
                segs0 = jp0.strip('/').split('/')
                if doc is not None and any(x.startswith('@@') for x in segs0):
                    partial = [[]]
                    for sg in segs0:
                        nxt = []
                        for pre in partial:
                            if sg.startswith('@@'):
                                st_, node, rs = get_path(doc, pre) if pre else ('OK', doc, [])
                                if st_ == 'OK':
                                    nxt += [rs + [k] for k in expand_glob(node, sg[2:])]
                            else:
                                nxt.append(pre + [sg])
                        partial = nxt
                    items += [('/'.join(x), expr) for x in partial]
                else:
                    items.append((jp0, expr))
            for jp, expr in items:
                r = dict(domain=domain, cat=cat, target=loc, path=jp, expr=str(expr)[:80])
                if doc is None:
                    r['status'] = 'ASSET_MISSING' if not ap else 'ASSET_PARSE_FAIL'; rows.append(r); continue
                st, base, rseg = get_path(doc, jp.strip('/').split('/'))
                r['base'] = json.dumps(base)[:40]
                try:
                    if cat == 'const': cur = defv = expr
                    elif cat == 'string' and isinstance(expr, str) and re.match(r'^\(.*\)\s*\?.*:', expr):
                        m3 = re.match(r'^\((.*)\)\s*\?\s*(.*?)\s*:\s*(.*)$', expr.strip())
                        def pick(env):
                            br = m3[2] if ev(ast.parse(to_py(m3[1]), mode='eval'), env) else m3[3]
                            return base if br == 'value' else env.get(br, br)
                        cur, defv = pick(dict(env_cur, value=base)), pick(dict(env_def, value=base))
                    elif cat == 'string' or (cat == 'other' and not isinstance(expr, str)):
                        cur = env_cur.get(expr, expr) if isinstance(expr, str) else expr
                        defv = env_def.get(expr, expr) if isinstance(expr, str) else expr
                    else:
                        tree = ast.parse(to_py(expr), mode='eval')
                        cur = ev(tree, dict(env_cur, value=base))
                        defv = ev(tree, dict(env_def, value=base))
                    if cat == 'integer' and isinstance(cur, (int, float)) and not isinstance(cur, bool):
                        cur, defv = int(cur), int(defv)  # configlib casts (truncates)
                    elif cat in ('float', 'number') and isinstance(cur, (int, float)) and not isinstance(cur, bool):
                        cur, defv = round(float(cur), 9), round(float(defv), 9)
                except Exception as e:
                    if st != 'OK' and 'value' in str(expr):
                        r['status'] = 'SKIP_PATH_MISSING'; rows.append(r); continue
                    r['status'] = 'EVAL_FAIL'; r['note'] = str(e)[:60]; rows.append(r); continue
                def same(a, b):
                    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
                        return abs(a - b) <= 1e-6 * max(1, abs(b))
                    return a == b
                r['cur'] = json.dumps(cur)[:40]; r['def'] = json.dumps(defv)[:40]
                r['default_identity'] = same(defv, base) if st == 'OK' else False
                if st == 'OK' and same(cur, base):
                    r['status'] = 'NOOP'
                else:
                    r['status'] = 'BAKE'
                    ops_by_file.setdefault((domain, loc), []).append(
                        {'op': 'replace' if st == 'OK' else 'add', 'path': '/' + '/'.join(rseg) if st == 'OK' else '/' + jp.strip('/'), 'value': cur})
                rows.append(r)

os.makedirs(os.path.join(out, 'assets', 'configlibbake', 'patches'), exist_ok=True)
for (domain, loc), ops in ops_by_file.items():
    fn = re.sub(r'[^A-Za-z0-9]+', '_', loc).strip('_') + '.json'
    dep = loc.split(':')[0]
    patch = [dict(o, file=loc, side='Server' if 'worldgen' in loc else None) for o in ops]
    for p in patch:
        if p['side'] is None: del p['side']
        if dep not in ('game', 'survival', 'creative'): p['dependsOn'] = [{'modid': domain}]
    json.dump(patch, open(os.path.join(out, 'assets', 'configlibbake', 'patches', fn), 'w', encoding='utf-8'), indent=1)

keys = ['domain', 'cat', 'target', 'path', 'expr', 'base', 'def', 'cur', 'default_identity', 'status', 'note']
with open(os.path.join(out, 'report.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore'); w.writeheader(); w.writerows(rows)

from collections import Counter
print('configs', len(cfgs), 'patch rows', len(rows))
print('status', dict(Counter(r['status'] for r in rows)))
print('BAKE ops', sum(len(v) for v in ops_by_file.values()), 'in', len(ops_by_file), 'files')
print('BAKE by domain', dict(Counter(r['domain'] for r in rows if r['status'] == 'BAKE')))
nonid = [r for r in rows if r['status'] in ('BAKE', 'NOOP') and not r.get('default_identity')]
print('non-identity at defaults (configlib changes asset even at defaults):', len(nonid))
print(' by domain', dict(Counter(r['domain'] for r in nonid)))
print('fail rows by domain', dict(Counter((r['domain'], r['status']) for r in rows if r['status'] not in ('BAKE', 'NOOP'))))
