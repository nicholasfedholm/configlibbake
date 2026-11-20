import json, os, glob, zipfile, hashlib, csv, collections
src = 'build/assets/configlibbake/patches'
out = 'brbake'; pd = os.path.join(out, 'assets', 'configlibbake', 'patches')
os.makedirs(pd, exist_ok=True)
n = 0; files = []
for f in glob.glob(src + '/*.json'):
    ops = json.load(open(f, encoding='utf-8'))
    ops = [o for o in ops if o['file'].startswith('betterruins:')]
    if not ops: continue
    for o in ops: o['dependsOn'] = [{'modid': 'betterruins'}]
    json.dump(ops, open(os.path.join(pd, os.path.basename(f)), 'w', encoding='utf-8'), indent=1)
    n += len(ops); files.append(os.path.basename(f))
mi = {"type": "content", "modid": "configlibbake", "name": "Configlib Bake (Better Ruins)", "version": "0.1.0",
      "authors": ["Nick"], "side": "Universal", "requiredOnClient": False,
      "description": "Static JsonPatches with Nick's Better Ruins configlib values (structures x3, villages x2, megastructure min distance 3000). Do not run together with configlib.",
      "dependencies": {"game": "", "betterruins": ""}}
json.dump(mi, open(os.path.join(out, 'modinfo.json'), 'w', encoding='utf-8'), indent=1)
z = 'configlibbake-0.1.0.zip'
with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, _, fs in os.walk(out):
        for x in fs:
            p = os.path.join(root, x); zf.write(p, os.path.relpath(p, out))
print('ops', n, 'files', files, 'zip', os.path.getsize(z), hashlib.sha256(open(z,'rb').read()).hexdigest()[:16])
for o in json.load(open(os.path.join(pd, files[0]), encoding='utf-8'))[:2]: print(o)
