import sys,json,os,collections
sys.path.insert(0,'/home/claude/modscan'); sys.path.insert(0,'/home/claude/Games/tools')
import tes4_plugin as tp
from patchlib import NRec, units, q_parts
lo=json.load(open('out/load_order.json'))
INST='/mnt/user-data/uploads/Games/_audit/installed_plugins'; VAN='/mnt/user-data/uploads/common--Oblivion/Data/Oblivion.esm'
def path(n):
    if n=='Oblivion.esm': return VAN
    if os.path.exists(INST+'/'+n): return INST+'/'+n
    if n.startswith('Rebirth Plus'): return 'out/'+n
    for l in open('selpaths.txt').read().split('\n')+["/mnt/user-data/uploads/Games/_audit/rar/AFK_Weye Version 2_32-22828-2-32/02 Compatibility/Rumare-AFK_Weye Patch.esp"]:
        if os.path.basename(l)==n: return l
def get(n, sig, edid):
    for p,r in tp.iter_records(path(n), want={sig}):
        try:
            if r.editor_id==edid: return NRec(p,r)
        except Exception: pass
sig,edid=sys.argv[1],sys.argv[2]; plugs=sys.argv[3:]
P=get('Rebirth Plus - New Mods Patch.esp',sig,edid)
src={n:get(n,sig,edid) for n in plugs}
pu=units(P)
for u,ss in pu.items():
    m=[n for n,r in src.items() if r and units(r).get(u)==ss]
    print(f'  {u:6} n={len(ss):3} matches: {m}')
if '--acbs' in sys.argv[0:1] or os.environ.get('ACBS'):
    import struct
    for n,r in list(src.items())+[('PATCH',P)]:
        if r:
            a=[s for s in r.subs if s[0]=='ACBS'][0][1]; print(n, struct.unpack('<IHHHhHH',a[:16]))
