import os, sys, glob, json, struct, collections, pickle
sys.path.insert(0, '/home/claude/modscan'); sys.path.insert(0, '/home/claude/Games/tools')
import tes4_plugin as tp
from patchlib import NRec, field_merge, quest_merge, Writer, units

INST = '/mnt/user-data/uploads/Games/_audit/installed_plugins'
VAN = '/mnt/user-data/uploads/common--Oblivion/Data/Oblivion.esm'
PATCH = 'Rebirth Plus - New Mods Patch.esp'
CFG = json.load(open('/home/claude/modscan/build_cfg.json'))


UDR_STAT_KEY = 'undeleted_INFO'
def _undelete(m, winner, sig, stats):
    """A plugin deleted a master record. Deleting master records can CTD, so keep the
    record and, for INFO, add a never-true condition (GetRandomPercent < 0) instead."""
    import struct as _s
    m.flags = winner.flags & ~0x20
    if sig == 'INFO':
        ctda = ('CTDA', bytes([0x80, 0, 0, 0]) + _s.pack('<fIIII', 0.0, 77, 0, 0, 0), ())
        subs = list(m.subs)
        idx = [i for i, s in enumerate(subs) if s[0] == 'CTDA']
        if idx:
            pos = idx[-1] + 1
        else:
            pos = next((i for i, s in enumerate(subs) if s[0] in ('TCLT', 'TCLF', 'SCHR', 'SCDA', 'SCTX', 'SCRO', 'NEXT')), len(subs))
        subs.insert(pos, ctda)
        m.subs = subs
        stats[UDR_STAT_KEY] += 1
    else:
        stats['undeleted_' + sig] += 1

def find_new(name):
    for l in open('/home/claude/modscan/selpaths.txt').read().split('\n') + CFG.get('extra_paths', []):
        if l and os.path.basename(l) == name:
            return l
    raise KeyError(name)

# ---- load order: the live Plugins.txt order (Vortex/LOOT sets matching timestamps) + DLC esps
EXTRA = {'ElsweyrAnequina.esp': '/mnt/user-data/uploads/Games/_audit/installed_plugins/ElsweyrAnequina.esp'}
_pl = [l.strip().lstrip('*') for l in open('/mnt/user-data/uploads/Local--Oblivion/Plugins.txt', encoding='utf-8', errors='replace') if l.strip() and not l.startswith('#')]
_order = []
for n in _pl:
    if n == 'Oblivion.esm' or n == PATCH:
        continue
    if n.endswith(' - Unofficial Patch.esp'):
        dlc = n.replace(' - Unofficial Patch.esp', '.esp')
        if os.path.exists(INST + '/' + dlc) and dlc not in _order:
            _order.append(dlc)
    _order.append(n)
    if n == 'Oblivion Citadel Door Fix.esp':
        _order.append('DLCShiveringIsles.esp')
def _path(n):
    if n in EXTRA: return EXTRA[n]
    if n in CFG['new_order']: return find_new(n)
    p = INST + '/' + n
    if os.path.exists(p): return p
    raise KeyError(n)
paths = {'Oblivion.esm': VAN}
for n in _order:
    paths[n] = _path(n)
load_order = ['Oblivion.esm'] + [n for n in _order if n.lower().endswith('.esm')] + [n for n in _order if not n.lower().endswith('.esm')]
json.dump(load_order, open('/home/claude/modscan/out/load_order.json', 'w'), indent=0)
NEW = set(CFG['new_order']) | set(EXTRA)
LOW = set(CFG.get('low_priority', []))   # new mods whose changes yield to installed ones
prio = [n for n in load_order if n in LOW] + [n for n in load_order if n not in LOW]
pri = {n: i for i, n in enumerate(prio)}
MERGE = set(CFG['merge_types'])

# ---- pass 1: candidate keys = records new plugins override
hdr = {n: tp.read_header(paths[n]) for n in load_order}
cand = collections.defaultdict(set)   # key -> set of plugins
info_parent = {}
for n in NEW:
    for p, r in tp.iter_records(paths[n], want=MERGE):
        if not p.is_override(r):
            continue
        if r.sig == 'CELL' and r.first('XCLC'):
            continue  # exterior cell headers handled separately
        k = p.global_key(r.form_id)
        cand[k].add(n)
        if r.sig == 'INFO' and r.parent is not None:
            info_parent[k] = p.global_key(r.parent)
print('candidate keys', len(cand))

# ---- pass 2: who else overrides them (and fetch all versions)
def local_ids(n, keys):
    h = hdr[n]; names = [m.lower() for m in h.masters] + [n.lower()]
    out = {}
    for (own, oid) in keys:
        if own in names:
            out[(names.index(own) << 24) | oid] = (own, oid)
    return out

versions = collections.defaultdict(dict)   # key -> {plugin: NRec}
dials_needed = set(info_parent.values())
allkeys = set(cand) | dials_needed
for n in load_order:
    want = local_ids(n, allkeys)
    if not want:
        continue
    for p, r in tp.iter_records(paths[n], want_ids=set(want)):
        if r.sig not in MERGE and r.sig != 'DIAL':
            continue
        k = want[r.form_id]
        versions[k][n] = NRec(p, r)
        if r.sig == 'INFO' and r.parent is not None and k not in info_parent:
            info_parent[k] = p.global_key(r.parent)
print('fetched')

# ---- merge
w = Writer(PATCH, load_order + [PATCH])
stats = collections.Counter(); report = collections.defaultdict(list)
for k, plugs in cand.items():
    vers = versions.get(k, {})
    owner = k[0]
    base = None
    for n in load_order:
        if n.lower() == owner and n in vers:
            base = vers[n]
    others = [n for n in vers if n.lower() != owner]
    if base is None or len(others) < 2:
        continue           # only one overrider: nothing to merge
    ordered = sorted(others, key=lambda n: pri[n])
    sig = base.sig
    vs = [vers[n] for n in ordered]
    if sig == 'QUST':
        m = quest_merge(base, vs)
    else:
        app = None
        if sig == 'NPC_':
            inst_vs = [vers[n] for n in ordered if n not in NEW]
            app = inst_vs[-1] if inst_vs else None
        m = field_merge(base, vs, appearance_from=app)
    winner = vers[max(others, key=lambda n: load_order.index(n))]
    if m.subs == winner.subs:
        stats['same_as_winner'] += 1
        continue
    if winner.flags & 0x20:
        _undelete(m, winner, sig, stats)
    else:
        m.flags = winner.flags
    def _seq(r):
        out = []
        for name in units(r).keys():
            out.append(name)
        return out
    ms = _seq(m)
    def _order_ok(ms, ref):
        pos = {n: i for i, n in enumerate(ref)}
        known = [pos[n] for n in ms if n in pos]
        return known == sorted(known)
    if sig != 'QUST' and not any(_order_ok(ms, _seq(v)) for v in vs + [base]):
        stats['ORDER_WARN'] += 1
        report['ORDER_WARN'].append((k, [ms, _seq(winner)]))
    stats[sig] += 1
    report[sig].append((k, ordered))
    if sig == 'CELL':
        w.cells_int.append((m, []))
    elif sig == 'INFO':
        w.infos.setdefault(info_parent[k], []).append(m)
    else:
        w.add(m)

# DIAL parents for INFOs (union of quests)
for dk in list(w.infos):
    vers = versions.get(dk, {})
    owner = dk[0]
    base = next((vers[n] for n in load_order if n.lower() == owner and n in vers), None)
    others = sorted([n for n in vers if n.lower() != owner], key=lambda n: pri[n])
    if base is None:
        del w.infos[dk]; continue
    d = field_merge(base, [vers[n] for n in others]) if others else base.copy()
    w.add(d)

# ---- extra world edits from cfg
exec(open('/home/claude/modscan/world_edits.py').read())

data = w.build(desc=CFG['description'])
open('/home/claude/modscan/out/' + PATCH, 'wb').write(data)
json.dump({'stats': stats, 'masters': w.mast, 'report': {s: [[list(k), o] for k, o in v] for s, v in report.items()}},
          open('/home/claude/modscan/out/patch_report.json', 'w'), indent=1)
print(stats, len(w.mast), 'masters', len(data), 'bytes')

# ---- round-trip verification
_expect = {}
for l in w.top.values():
    for r in l: _expect[(r.sig, r.key)] = r.subs
for c, ch in w.cells_int: _expect[('CELL', c.key)] = c.subs
for l in w.infos.values():
    for r in l: _expect[('INFO', r.key)] = r.subs
_bad = 0; _seen = 0
for p, r in tp.iter_records('/home/claude/modscan/out/' + PATCH):
    k = (r.sig, p.global_key(r.form_id))
    if k in _expect:
        _seen += 1
        if NRec(p, r).subs != _expect[k]:
            _bad += 1
print('round-trip checked', _seen, 'mismatches', _bad, 'errors', p.errors)
for p, r in tp.iter_records('/home/claude/modscan/out/' + PATCH):
    k = (r.sig, p.global_key(r.form_id))
    if k in _expect and NRec(p, r).subs != _expect[k]:
        a = NRec(p, r).subs; b = _expect[k]
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                print('MISMATCH', k, i, x[0], y[0], x[2], y[2], x[1][:24].hex(), y[1][:24].hex()); break
        else:
            print('MISMATCH len', k, len(a), len(b))
