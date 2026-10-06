import json,os,collections,struct
d=json.load(open('/mnt/user-data/uploads/common--Oblivion/Data/vortex.deployment.json'))
dep={f['relPath'].replace('\\','/').lower():f['source'] for f in d['files']}
# map each new mod -> data-relative files (strip known wrapper dirs)
roots={}
skipdirs=('docs','images','omod conversion data','fomod')
def data_rel(mod,root,rel):
    parts=rel.replace('\\','/').split('/')
    low=[p.lower() for p in parts]
    for k,p in enumerate(low):
        if p in ('meshes','textures','sound','music','menus','fonts','shaders','distantlod','trees','obse','ini') : return '/'.join(parts[k:]).lower()
    if low[-1].endswith(('.esp','.esm','.bsa')): return low[-1]
    return None
SEL={'Bounty Quests Version 3.0':None}
newfiles=collections.defaultdict(dict)
base='x'
for mod in os.listdir(base):
    for dp,dn,fn in os.walk(os.path.join(base,mod)):
        for f in fn:
            rel=os.path.relpath(os.path.join(dp,f),os.path.join(base,mod))
            if 'Cobl' in mod and not rel.startswith(('00 Cobl Core','01 StableCore')): continue
            if 'TL_1_3' in mod: continue
            if 'Patches' in mod or 'KOTNR' in mod or 'Milewood' in mod or 'Weynon' in mod or 'Better Cities' in mod or 'Lush Woodlands' in mod: continue
            r=data_rel(mod,base,rel)
            if r and not r.endswith(('.esp','.esm','.txt')) and not '/sound/voice/' in '/'+r: newfiles[r][mod]=1
for rr in ['/mnt/user-data/uploads/Games/_audit/rar']:
    pass
conf=collections.defaultdict(list); nn=collections.defaultdict(list)
for r,mods in newfiles.items():
    if r in dep:
        for m in mods: conf[(m,dep[r])].append(r)
    if len(mods)>1: nn[tuple(sorted(mods))].append(r)
print('NEW loose files overriding / overridden by deployed files:')
for (m,s),l in sorted(conf.items(),key=lambda x:-len(x[1])): print(f'  {m[:40]} <-> {s[:50]}: {len(l)}  e.g. {l[:3]}')
print('NEW vs NEW same path:')
for ms,l in sorted(nn.items(),key=lambda x:-len(x[1]))[:20]: print('  ',[m[:30] for m in ms],len(l),l[:3])
