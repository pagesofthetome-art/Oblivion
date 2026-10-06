# executed inside build_patch.py (uses w, load_order, paths, hdr, local_ids, NRec, tp, CFG)
import struct as _st

TAMRIEL = ('oblivion.esm', 0x3C)

def _scan_cells(plugin_name, grids):
    """Return {grid: {'cell':NRec,'land':NRec,'refs':[(NRec, gtype)]}} for the Tamriel cells in `grids`."""
    out = {}
    cellgrid = {}
    recs = []
    for p, r in tp.iter_records(paths[plugin_name]):
        if r.sig == 'CELL' and r.parent is not None and p.global_key(r.parent) == TAMRIEL:
            x = r.first('XCLC')
            g = 'P' if (r.group_path and r.group_path[-1] == 'World Children') else (_st.unpack('<ii', x[:8]) if x else 'P')
            cellgrid[r.form_id] = g
            if g in grids or g == 'P':
                out.setdefault(g, {'cell': None, 'land': None, 'refs': []})['cell'] = NRec(p, r)
        recs.append((p, r))
    for p, r in recs:
        if r.parent in cellgrid and r.sig in ('REFR', 'ACHR', 'ACRE', 'LAND'):
            g = cellgrid[r.parent]
            if g == 'P':
                d = r.first('DATA') if r.sig != 'LAND' else None
                if not d:
                    continue
                x, y = _st.unpack('<ff', d[:8]); gg = (int(x // 4096), int(y // 4096))
                if gg not in grids:
                    continue
                out.setdefault('P', {'cell': None, 'land': None, 'refs': []})['refs'].append((NRec(p, r), 8, gg))
                continue
            if g not in grids:
                continue
            e = out.setdefault(g, {'cell': None, 'land': None, 'refs': []})
            if r.sig == 'LAND':
                e['land'] = NRec(p, r)
            else:
                gt = {'Cell Temporary Children': 9, 'Cell Visible Distant Children': 10, 'Cell Persistent Children': 8}.get(r.group_path[-1] if r.group_path else '', 9)
                e['refs'].append((NRec(p, r), gt, g))
    return out

def _winner_cell(cellkey):
    best = None
    for n in load_order:
        want = local_ids(n, {cellkey})
        if not want:
            continue
        for p, r in tp.iter_records(paths[n], want_ids=set(want)):
            if r.sig == 'CELL':
                best = NRec(p, r)
    return best

def _winner_wrld():
    best = None
    for n in load_order:
        want = local_ids(n, {TAMRIEL})
        if not want:
            continue
        for p, r in tp.iter_records(paths[n], want={'WRLD'}, want_ids=set(want)):
            best = NRec(p, r)
    return best

def _world_entry():
    if TAMRIEL not in w.world:
        w.world[TAMRIEL] = {'rec': _winner_wrld(), 'cells': {}, 'pcell': None}
    return w.world[TAMRIEL]

def _cell_slot(g, vanilla_cells):
    we = _world_entry()
    ck = vanilla_cells[g]['cell'].key
    if ck not in we['cells']:
        we['cells'][ck] = (_winner_cell_cached(ck), g, [], [], [])
    return we['cells'][ck]

edits_log = []
_allgrids = [tuple(g) for job in CFG.get('world_edits', []) for g in job['cells']]
_VAN = _scan_cells('Oblivion.esm', _allgrids)
_wc_cache = {}
def _winner_cell_cached(k):
    if k not in _wc_cache:
        _wc_cache[k] = _winner_cell(k)
    return _wc_cache[k]
for job in CFG.get('world_edits', []):
    grids = [tuple(g) for g in job['cells']]
    van = _VAN
    if job['type'] == 'restore_land_and_disable':
        src = _scan_cells(job['disable_from'], grids + ['P'])
        for g in grids:
            slot = _cell_slot(g, van)
            if van[g]['land'] is not None:
                slot[2].append(van[g]['land'])
            n_dis = 0
            for nr, gt, gg in src.get(g, {'refs': []})['refs']:
                if nr.key[0] != job['disable_from'].lower():
                    continue
                d = nr.copy(); d.flags |= 0x800
                (slot[2] if gt == 9 else slot[4] if gt == 10 else slot[3]).append(d); n_dis += 1
            edits_log.append(f"{job['disable_from']} cell {g}: land restored to vanilla, {n_dis} objects disabled")
        # persistent refs of the camp (map markers etc.)
        pe = src.get('P')
        if pe:
            we = _world_entry()
            pc = _VAN['P']['cell']
            if we['pcell'] is None:
                we['pcell'] = (_winner_cell_cached(pc.key), [])
            for nr, gt, gg in pe['refs']:
                if nr.key[0] == job['disable_from'].lower() and gg in grids:
                    d = nr.copy(); d.flags |= 0x800; we['pcell'][1].append(d)
                    edits_log.append(f"{job['disable_from']} persistent object at {gg} disabled")
    elif job['type'] == 'land_from':
        src = _scan_cells(job['plugin'], grids)
        for g in grids:
            if src.get(g, {}).get('land') is None:
                continue
            slot = _cell_slot(g, van)
            slot[2].append(src[g]['land'])
            edits_log.append(f"cell {g}: terrain taken from {job['plugin']}")
print('\n'.join(edits_log))

# ---- port a third-party patch onto a different master (e.g. a V4.1 patch onto the V3 file)
def _remap_key(k, rm):
    return (rm[k[0]], k[1]) if k and k[0] in rm else k

def _remap(nr, rm):
    c = nr.copy()
    c.key = _remap_key(c.key, rm)
    c.subs = [(s, d, tuple((o, _remap_key(kk, rm)) for o, kk in ks)) for s, d, ks in c.subs]
    return c

_GT = {'Cell Temporary Children': 9, 'Cell Visible Distant Children': 10, 'Cell Persistent Children': 8}
for job in CFG.get('world_edits', []):
    if job['type'] != 'port_patch':
        continue
    rm = dict(job['remap']); rm[os.path.basename(job['path']).lower()] = PATCH.lower()
    recs = list(tp.iter_records(job['path']))
    cellinfo = {}   # local cell formid -> ('int', key) | ('pers',) | ('ext', grid)
    for p, r in recs:
        if r.sig != 'CELL':
            continue
        gp = r.group_path[-1] if r.group_path else ''
        if gp == 'World Children':
            cellinfo[r.form_id] = ('pers',)
        elif r.first('XCLC'):
            cellinfo[r.form_id] = ('ext', _st.unpack('<ii', r.first('XCLC')[:8]))
        else:
            cellinfo[r.form_id] = ('int', _remap_key(p.global_key(r.form_id), rm))
    n = collections.Counter()
    for p, r in recs:
        if r.sig not in ('REFR', 'ACHR', 'ACRE', 'LAND', 'PGRD') or r.parent not in cellinfo:
            continue
        ci = cellinfo[r.parent]
        nr = _remap(NRec(p, r), rm)
        gt = _GT.get(r.group_path[-1] if r.group_path else '', 9)
        if ci[0] == 'pers':
            we = _world_entry()
            if we['pcell'] is None:
                we['pcell'] = (_winner_cell_cached(_VAN['P']['cell'].key), [])
            we['pcell'][1].append(nr)
        elif ci[0] == 'ext':
            slot = _cell_slot(ci[1], _VAN)
            (slot[2] if gt == 9 else slot[4] if gt == 10 else slot[3]).append(nr)
        else:
            ent = next((e for e in w.cells_int if e[0].key == ci[1]), None)
            if ent is None:
                ent = (_winner_cell_cached(ci[1]), []); w.cells_int.append(ent)
            ent[1].append((nr, gt))
        n[ci[0]] += 1
    edits_log.append(f"ported {os.path.basename(job['path'])} onto {list(job['remap'].values())}: {dict(n)}")
print('\n'.join(edits_log[-1:]))
