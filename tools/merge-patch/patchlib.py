"""Bash-style merge patch builder for Oblivion (TES4) plugins.

Normalises FormIDs to (owner-file, objid) keys so records from plugins with
different master lists can be compared and merged, then writes a new .esp whose
master list is built from every file actually referenced.
"""
import struct, zlib, os, sys, collections
sys.path.insert(0, '/home/claude/Games/tools')
import tes4_plugin as tp

# ---------------------------------------------------------------- FormID field specs
# (record type, subrecord) -> list of byte offsets holding FormIDs ; 'all4' = every 4 bytes
F = {}
def spec(rt, sig, offs): F[(rt, sig)] = offs
for rt in ('NPC_', 'CREA'):
    for s in ('INAM', 'RNAM', 'SPLO', 'SCRI', 'PKID', 'CNAM', 'HNAM', 'ENAM', 'ZNAM', 'CSCR'):
        spec(rt, s, [0])
    spec(rt, 'SNAM', [0]); spec(rt, 'CNTO', [0])
spec('CREA', 'CSDI', [0]); spec('CREA', 'CNAM', [])  # creature CNAM is not a form
spec('CREA', 'RNAM', [])   # attack reach byte
spec('CREA', 'ENAM', [])
for rt in ('CLOT', 'ARMO', 'WEAP', 'BOOK', 'MISC', 'ALCH', 'AMMO', 'INGR', 'KEYM', 'LIGH', 'APPA', 'SGST', 'SLGM', 'CONT', 'ACTI', 'FURN', 'DOOR', 'FLOR'):
    spec(rt, 'SCRI', [0])
for rt in ('CLOT', 'ARMO', 'WEAP', 'BOOK', 'AMMO'):
    spec(rt, 'ENAM', [0])
spec('CONT', 'CNTO', [0]); spec('CONT', 'SNAM', [0]); spec('CONT', 'QNAM', [0])
spec('DOOR', 'SNAM', [0]); spec('DOOR', 'ANAM', [0]); spec('DOOR', 'BNAM', [0]); spec('DOOR', 'TNAM', [0])
spec('ACTI', 'SNAM', [0]); spec('LIGH', 'SNAM', [0]); spec('FLOR', 'PFIG', [0])
spec('FACT', 'XNAM', [0])
spec('IDLE', 'DATA', [0, 4])
for rt in ('SPEL', 'ENCH', 'ALCH', 'INGR', 'SGST', 'SCPT'):
    spec(rt, 'SCIT', [0])
spec('LVLI', 'LVLO', [4]); spec('LVLC', 'LVLO', [4]); spec('LVSP', 'LVLO', [4]); spec('LVLC', 'SCRI', [0]); spec('LVLC', 'TNAM', [0])
spec('QUST', 'SCRI', [0]); spec('QUST', 'QSTA', [0])
for s in ('QSTI', 'TPIC', 'NAME', 'TCLT', 'TCLF', 'PNAM'):
    spec('INFO', s, [0])
spec('DIAL', 'QSTI', [0]); spec('DIAL', 'QSTR', [0])
for s in ('XOWN', 'XGLB', 'XCCM', 'XCWT'):
    spec('CELL', s, [0])
spec('CELL', 'XCLR', 'all4')
for rt in ('REFR', 'ACHR', 'ACRE'):
    for s in ('NAME', 'XOWN', 'XGLB', 'XTRG', 'XMRC', 'XHRS', 'XPCI'):
        spec(rt, s, [0])
    spec(rt, 'XTEL', [0]); spec(rt, 'XESP', [0]); spec(rt, 'XLOC', [4])
spec('LAND', 'BTXT', [0]); spec('LAND', 'ATXT', [0]); spec('LAND', 'VTEX', 'all4')
spec('WRLD', 'WNAM', [0]); spec('WRLD', 'CNAM', [0]); spec('WRLD', 'NAM2', [0])
spec('PACK', 'PLDT', 'pldt'); spec('PACK', 'PTDT', 'ptdt')
SCRIPTED = {'QUST', 'INFO', 'SCPT'}  # SCRO lists


def fid_offsets(rt, sig, data, nmast):
    if sig == 'SCRO':
        return [0]
    if sig == 'CTDA' and len(data) >= 20:
        out = []
        for o in (12, 16):
            v = struct.unpack_from('<I', data, o)[0]
            if v and 1 <= (v >> 24) <= nmast:
                out.append(o)
        return out
    s = F.get((rt, sig))
    if s is None:
        return []
    if s == 'all4':
        return list(range(0, len(data) - len(data) % 4, 4))
    if s == 'pldt':
        t = struct.unpack_from('<i', data, 0)[0] if len(data) >= 8 else -1
        return [4] if t in (0, 1, 4) else []
    if s == 'ptdt':
        t = struct.unpack_from('<i', data, 0)[0] if len(data) >= 8 else -1
        return [4] if t in (0, 1) else []
    return [o for o in s if o + 4 <= len(data)]


class NRec:
    """A record with FormIDs normalised to global keys."""
    def __init__(self, plugin, rec):
        self.src = plugin.name
        self.sig = rec.sig
        self.flags = rec.flags & ~tp.FLAG_COMPRESSED
        self.key = plugin.global_key(rec.form_id)
        n = len(plugin.masters)
        self.subs = []  # list of (sig, data_with_zeroed_slots, ((off,key),...))
        for s in rec.subrecords():
            offs = fid_offsets(rec.sig, s.sig, s.data, n)
            keys = []
            d = bytearray(s.data)
            for o in offs:
                v = struct.unpack_from('<I', d, o)[0]
                if v == 0:
                    continue
                gk = plugin.global_key(v)
                if gk is None:   # index past the master list: the engine resolves it to the file itself
                    gk = (plugin.name.lower(), v & 0xFFFFFF)
                keys.append((o, gk))
                struct.pack_into('<I', d, o, 0)
            self.subs.append((s.sig, bytes(d), tuple(keys)))

    def copy(self):
        c = NRec.__new__(NRec)
        c.src, c.sig, c.flags, c.key, c.subs = self.src, self.sig, self.flags, self.key, list(self.subs)
        return c


def units(rec):
    """Split a record's subrecords into merge units: [(unitname, [subs])]."""
    out = []
    subs = rec.subs
    i = 0
    rt = rec.sig
    while i < len(subs):
        sig = subs[i][0]
        if rt == 'INFO' and sig == 'TRDT':
            j = i
            while j < len(subs) and subs[j][0] in ('TRDT', 'NAM1', 'NAM2'):
                j += 1
            out.append(('RESP', subs[i:j])); i = j; continue
        if sig in ('SCHR',) and rt in ('INFO', 'QUST'):
            j = i + 1
            while j < len(subs) and subs[j][0] in ('SCDA', 'SCTX', 'SCRO', 'SCRV'):
                j += 1
            out.append(('SCRIPT', subs[i:j])); i = j; continue
        if rt in ('SPEL', 'ENCH', 'ALCH', 'INGR', 'SGST', 'SCPT') and sig == 'EFID':
            out.append(('EFFECTS', subs[i:])); i = len(subs); continue
        if rt == 'FACT' and sig == 'RNAM':
            j = i + 1
            while j < len(subs) and subs[j][0] in ('MNAM', 'FNAM', 'INAM'):
                j += 1
            out.append(('RANKS', subs[i:j])); i = j; continue
        out.append((sig, [subs[i]])); i += 1
    # collapse repeated simple sigs into list units
    merged = collections.OrderedDict()
    for name, ss in out:
        merged.setdefault(name, []).extend(ss)
    return merged


LISTS = {('NPC_', 'SNAM'), ('NPC_', 'SPLO'), ('NPC_', 'CNTO'), ('NPC_', 'PKID'),
         ('CREA', 'SNAM'), ('CREA', 'SPLO'), ('CREA', 'CNTO'), ('CREA', 'PKID'),
         ('CONT', 'CNTO'), ('LVLI', 'LVLO'), ('LVLC', 'LVLO'), ('DIAL', 'QSTI'), ('CELL', 'XCLR')}


def list_merge(base, changes):
    """base: list of subs; changes: list of lists (each plugin's version, in priority order)."""
    def ident(s):
        return (s[0], s[2][0][1] if s[2] else s[1])
    result = list(base)
    bset = collections.Counter(ident(s) for s in base)
    for ver in changes:
        vset = collections.Counter(ident(s) for s in ver)
        removed = bset - vset
        added = [s for s in ver if ident(s) not in bset]
        # apply removals
        for r in removed:
            result = [s for s in result if ident(s) != r] if removed[r] >= bset[r] else result
        # replace changed entries (same ident, different data e.g. CNTO count / SNAM rank)
        vmap = {ident(s): s for s in ver}
        result = [vmap.get(ident(s), s) if ident(s) in vmap else s for s in result]
        have = {ident(s) for s in result}
        for s in added:
            if ident(s) not in have:
                result.append(s); have.add(ident(s))
    return result


STRUCTS = {('NPC_', 'ACBS'): [('flags', 0, 4), ('spell', 4, 2), ('fat', 6, 2), ('barter', 8, 2), ('lvl', 10, 2), ('cmin', 12, 2), ('cmax', 14, 2)],
           ('CREA', 'ACBS'): [('flags', 0, 4), ('spell', 4, 2), ('fat', 6, 2), ('barter', 8, 2), ('lvl', 10, 2), ('cmin', 12, 2), ('cmax', 14, 2)],
           ('NPC_', 'AIDT'): [('aggr', 0, 1), ('conf', 1, 1), ('energy', 2, 1), ('resp', 3, 1), ('buys', 4, 4), ('train', 8, 1), ('tlvl', 9, 1), ('pad', 10, 2)],
           ('CREA', 'AIDT'): [('aggr', 0, 1), ('conf', 1, 1), ('energy', 2, 1), ('resp', 3, 1), ('buys', 4, 4), ('train', 8, 1), ('tlvl', 9, 1), ('pad', 10, 2)]}


def struct_merge(layout, base, vers):
    """Per-field merge of a fixed-layout subrecord (no FormIDs inside). Flags merge bit-wise."""
    sig, bd, bk = base
    out = bytearray(bd)
    if any(len(v[1]) != len(bd) for v in vers):
        return vers[-1]
    for name, o, ln in layout:
        bseg = bd[o:o + ln]
        if name == 'flags':
            bv = int.from_bytes(bseg, 'little'); cur = bv
            for v in vers:
                vv = int.from_bytes(v[1][o:o + ln], 'little')
                cur = (cur & ~(bv ^ vv)) | (vv & (bv ^ vv))
            out[o:o + ln] = cur.to_bytes(ln, 'little')
            continue
        for v in vers:
            if v[1][o:o + ln] != bseg:
                out[o:o + ln] = v[1][o:o + ln]
    return (sig, bytes(out), bk)


def field_merge(base, versions, appearance_from=None):
    """Merge records: base = master record, versions = NRecs in ascending priority."""
    rt = base.sig
    bu = units(base)
    vus = [units(v) for v in versions]
    names = list(bu.keys())
    for vu in vus:
        for n in vu:
            if n not in names:
                names.append(n)
    final = collections.OrderedDict()
    for n in names:
        b = bu.get(n, [])
        if (rt, n) in STRUCTS and len(b) == 1 and all(len(vu.get(n, [])) == 1 for vu in vus):
            final[n] = [struct_merge(STRUCTS[(rt, n)], b[0], [vu[n][0] for vu in vus])]
            continue
        if (rt, n) in LISTS:
            final[n] = list_merge(b, [vu.get(n, []) for vu in vus])
            continue
        cur = b
        for vu in vus:
            v = vu.get(n, [])
            if v != b:
                cur = v
        final[n] = cur
    if appearance_from is not None:
        au = units(appearance_from)
        for n in ('HNAM', 'LNAM', 'ENAM', 'HCLR', 'FGGS', 'FGGA', 'FGTS', 'FNAM'):
            if n in au:
                final[n] = au[n]
    out = versions[-1].copy()
    order = canonical(rt, list(final.keys()), [list(units(v).keys()) for v in reversed(versions)] + [list(bu.keys())])
    out.subs = [s for n in order for s in final[n]]
    out.flags = versions[-1].flags
    return out


CANON = {
    'NPC_': 'EDID FULL MODL MODB MODT ACBS SNAM INAM RNAM SPLO SCRI CNTO AIDT PKID KFFZ CNAM DATA HNAM LNAM ENAM HCLR ZNAM FGGS FGGA FGTS FNAM'.split(),
    'CREA': 'EDID FULL MODL MODB MODT SPLO NIFZ NIFT ACBS SNAM INAM SCRI CNTO AIDT PKID KFFZ DATA RNAM ZNAM TNAM BNAM WNAM CSCR NAM0 NAM1 CSDT CSDI CSDC'.split(),
    'INFO': 'DATA QSTI TPIC PNAM NAME RESP CTDA TCLT TCLF SCRIPT'.split(),
    'CELL': 'EDID FULL DATA XCLL XCMT XCLW XOWN XRNK XGLB XCCM XCLC XCWT XCLR'.split(),
    'PACK': 'EDID PKDT PLDT PSDT PTDT CTDA'.split(),
}


def canonical(rt, names, orders):
    if False and rt in CANON:
        c = CANON[rt]
        known = [n for n in c if n in names]
        rest = [n for n in names if n not in c]
        return known + rest
    # sequence merge: winner's order, other versions' extra units inserted after their predecessor
    seq = []
    for o in orders:
        for i, n in enumerate(o):
            if n not in names or n in seq:
                continue
            prev = [p for p in o[:i] if p in seq]
            if prev:
                seq.insert(seq.index(prev[-1]) + 1, n)
            else:
                nxt = [p for p in o[i + 1:] if p in seq]
                seq.insert(seq.index(nxt[0]) if nxt else len(seq), n)
    for n in names:
        if n not in seq:
            seq.append(n)
    return seq


# ---------------------------------------------------------------- QUST stage merge
def q_parts(rec):
    head, stages, targets, mode, cur = [], collections.OrderedDict(), [], 'head', None
    for s in rec.subs:
        if s[0] == 'INDX':
            cur = struct.unpack('<h', s[1][:2])[0]; stages[cur] = [s]; mode = 'stage'; continue
        if s[0] == 'QSTA':
            mode = 'target'; targets.append([s]); continue
        if mode == 'head':
            head.append(s)
        elif mode == 'stage':
            stages[cur].append(s)
        else:
            targets[-1].append(s)
    return head, stages, targets


def quest_merge(base, versions):
    bh, bs, bt = q_parts(base)
    h, st, tg = bh, collections.OrderedDict(bs), bt
    for v in versions:
        vh, vs, vt = q_parts(v)
        if vh != bh:
            # merge head per subrecord sig
            hu_b = collections.OrderedDict(); hu_v = collections.OrderedDict()
            for s in bh: hu_b.setdefault(s[0], []).append(s)
            for s in vh: hu_v.setdefault(s[0], []).append(s)
            hu_c = collections.OrderedDict()
            for s in h: hu_c.setdefault(s[0], []).append(s)
            for k in list(hu_v.keys()) + [k for k in hu_b if k not in hu_v]:
                if hu_v.get(k, []) != hu_b.get(k, []):
                    hu_c[k] = hu_v.get(k, [])
            h = [s for k in hu_c for s in hu_c[k]]
        for k, ss in vs.items():
            if bs.get(k) != ss:
                st[k] = ss
        for k in list(st.keys()):
            if k in bs and k not in vs:
                del st[k]
        if vt != bt:
            tg = vt
    out = versions[-1].copy()
    out.subs = h + [s for k in sorted(st) for s in st[k]] + [s for t in tg for s in t]
    return out


# ---------------------------------------------------------------- writer
class Writer:
    def __init__(self, name, load_order):
        self.name = name
        self.lo = [x.lower() for x in load_order]  # every plugin in load order (for master ordering)
        self.lo_case = {x.lower(): x for x in load_order}
        self.top = collections.OrderedDict()      # sig -> list of NRec (top level, non-world)
        self.cells_int = []                       # (CELL NRec, children NRecs)
        self.world = collections.OrderedDict()    # wrld key -> {'rec':NRec, 'cells':{cellkey: (cellrec, grid, [children temp], [children persist])}}
        self.used = set()
        self.infos = {}

    def add(self, nrec):
        self.top.setdefault(nrec.sig, []).append(nrec)

    def _collect(self, rec):
        self.used.add(rec.key[0])
        for s in rec.subs:
            for o, k in s[2]:
                self.used.add(k[0])

    def masters(self):
        u = {m for m in self.used if m != self.name.lower()}
        return [self.lo_case[m] for m in self.lo if m in u]

    def build(self, author='Claude for Yuri', desc=''):
        allrecs = [r for l in self.top.values() for r in l]
        for c, ch in self.cells_int:
            allrecs += [c] + [x for x, t in ch]
        for w in self.world.values():
            allrecs.append(w['rec'])
            for c in w['cells'].values():
                allrecs += [c[0]] + c[2] + c[3] + c[4]
            if w.get('pcell'):
                allrecs += [w['pcell'][0]] + w['pcell'][1]
        for l in self.infos.values():
            allrecs += l
        for r in allrecs:
            self._collect(r)
        mast = self.masters()
        missing = {m for m in self.used if m != self.name.lower() and m not in self.lo}
        if missing:
            raise ValueError(f'referenced files not in load order: {missing}')
        idx = {m.lower(): i for i, m in enumerate(mast)}
        idx[self.name.lower()] = len(mast)   # records new in this patch
        self.mast = mast

        def fid(key):
            owner, oid = key
            return (idx[owner] << 24) | oid

        def rec_bytes(r):
            body = bytearray()
            for sig, d, keys in r.subs:
                d = bytearray(d)
                for o, k in keys:
                    struct.pack_into('<I', d, o, fid(k))
                if len(d) > 0xFFFF:
                    body += b'XXXX' + struct.pack('<H', 4) + struct.pack('<I', len(d))
                    body += sig.encode() + struct.pack('<H', 0) + d
                else:
                    body += sig.encode() + struct.pack('<H', len(d)) + d
            return r.sig.encode() + struct.pack('<IIII', len(body), r.flags, fid(r.key), 0) + bytes(body)

        def grup(label, gtype, content):
            return b'GRUP' + struct.pack('<I', 20 + len(content)) + label + struct.pack('<iI', gtype, 0) + content

        out = bytearray()
        nrec = 0
        for sig, recs in self.top.items():
            if sig in ('DIAL',):
                continue
            body = b''.join(rec_bytes(r) for r in recs); nrec += len(recs)
            out += grup(sig.encode(), 0, body)
        # DIAL + INFO children
        if 'DIAL' in self.top:
            body = bytearray()
            for d in self.top.get('DIAL', []):
                body += rec_bytes(d); nrec += 1
                kids = [i for i in self.infos.get(d.key, [])]
                if kids:
                    body += grup(struct.pack('<I', fid(d.key)), 7, b''.join(rec_bytes(i) for i in kids)); nrec += len(kids)
            out += grup(b'DIAL', 0, bytes(body))
        if self.cells_int:
            blocks = collections.defaultdict(lambda: collections.defaultdict(list))
            for c, ch in self.cells_int:
                oid = c.key[1]
                blocks[oid % 10][(oid // 10) % 10].append((c, ch))
            body = bytearray()
            for b in sorted(blocks):
                bb = bytearray()
                for sb in sorted(blocks[b]):
                    sbb = bytearray()
                    for c, ch in blocks[b][sb]:
                        sbb += rec_bytes(c); nrec += 1
                        if ch:   # interior children: (NRec, group type 8/9/10)
                            cg = bytearray()
                            for gt in (8, 9, 10):
                                lst = [x for x, t in ch if t == gt]
                                if lst:
                                    cg += grup(struct.pack('<I', fid(c.key)), gt, b''.join(rec_bytes(x) for x in lst)); nrec += len(lst)
                            sbb += grup(struct.pack('<I', fid(c.key)), 6, bytes(cg))
                    bb += grup(struct.pack('<i', sb), 3, bytes(sbb))
                body += grup(struct.pack('<i', b), 2, bytes(bb))
            out += grup(b'CELL', 0, bytes(body))
        if self.world:
            body = bytearray()
            for wk, w in self.world.items():
                body += rec_bytes(w['rec']); nrec += 1
                blocks = collections.defaultdict(lambda: collections.defaultdict(list))
                for ck, ent in w['cells'].items():
                    c, (gx, gy), temp, pers, vdt = ent
                    blocks[(gy // 32, gx // 32)][(gy // 8, gx // 8)].append((c, temp, pers, vdt))
                wb = bytearray()
                if w.get('pcell'):
                    pc, prefs = w['pcell']
                    wb += rec_bytes(pc); nrec += 1
                    if prefs:
                        wb += grup(struct.pack('<I', fid(pc.key)), 6, grup(struct.pack('<I', fid(pc.key)), 8, b''.join(rec_bytes(x) for x in prefs))); nrec += len(prefs)
                for (by, bx) in sorted(blocks):
                    bb = bytearray()
                    for (sy, sx) in sorted(blocks[(by, bx)]):
                        sbb = bytearray()
                        for c, temp, pers, vdt in blocks[(by, bx)][(sy, sx)]:
                            sbb += rec_bytes(c); nrec += 1
                            ch = bytearray()
                            for gt, lst in ((8, pers), (9, temp), (10, vdt)):
                                if lst:
                                    ch += grup(struct.pack('<I', fid(c.key)), gt, b''.join(rec_bytes(x) for x in lst)); nrec += len(lst)
                            if ch:
                                sbb += grup(struct.pack('<I', fid(c.key)), 6, bytes(ch))
                        bb += grup(struct.pack('<hh', sy, sx), 5, bytes(sbb))
                    wb += grup(struct.pack('<hh', by, bx), 4, bytes(bb))
                body += grup(struct.pack('<I', fid(wk)), 1, bytes(wb))
            out += grup(b'WRLD', 0, bytes(body))
        hdr = bytearray()
        hdr += b'HEDR' + struct.pack('<H', 12) + struct.pack('<fiI', 1.0, nrec, 0xD00)
        hdr += b'CNAM' + struct.pack('<H', len(author) + 1) + author.encode() + b'\0'
        if desc:
            d = desc.encode('cp1252', 'replace')[:500]
            hdr += b'SNAM' + struct.pack('<H', len(d) + 1) + d + b'\0'
        for m in mast:
            mb = m.encode('cp1252')
            hdr += b'MAST' + struct.pack('<H', len(mb) + 1) + mb + b'\0'
            hdr += b'DATA' + struct.pack('<H', 8) + b'\0' * 8
        tes4 = b'TES4' + struct.pack('<IIII', len(hdr), 0, 0, 0) + bytes(hdr)
        return tes4 + bytes(out)
