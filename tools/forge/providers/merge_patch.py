"""Provider for `record.merge`: the Rebirth+ Bash-style merge patch.

This is `tools/merge-patch/build_patch.py` with its hard-coded cloud paths turned
into parameters. The merge itself still comes from `patchlib.py` (unchanged), and
`world_edits.py` (unchanged) is still executed in the same namespace it expects.

One intentional difference from the legacy script: the legacy script walked the
new plugins as a Python `set`, so record order in the output depended on the
interpreter's string-hash seed and two runs could write different bytes.
Here the new plugins are walked in load order, so the same inputs always give
the same file.
"""

from __future__ import annotations

import collections
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
MERGE_DIR = TOOLS / "merge-patch"
for _p in (str(TOOLS), str(MERGE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import tes4_plugin as tp  # noqa: E402
import patchlib  # noqa: E402
from patchlib import NRec, Writer, field_merge, quest_merge, units  # noqa: E402

WORLD_EDITS = MERGE_DIR / "world_edits.py"


@dataclass
class MergeInputs:
    """Everything the merge needs; paths are already absolute."""
    output_name: str                 # e.g. "Rebirth Plus - New Mods Patch.esp"
    vanilla: Path                    # Oblivion.esm
    installed_dir: Path              # folder holding the installed (load-order) plugins
    plugins_txt: Path                # live Plugins.txt that defines the order
    cfg: dict                        # build_cfg.json content (new_order, merge_types, world_edits, ...)
    new_mod_paths: list[Path] = field(default_factory=list)   # where new-mod plugins are found, by file name
    extra_plugins: dict[str, Path] = field(default_factory=dict)  # name -> path, counted as "new"
    insert_after: dict[str, str] = field(default_factory=dict)    # "X.esp": "DLC.esp" -> add DLC.esp right after X.esp
    author: str = "Claude for Yuri"


@dataclass
class MergeResult:
    data: bytes
    load_order: list[str]
    report: dict
    stats: dict
    masters: list[str]
    world_log: list[str]
    roundtrip: dict
    inputs_used: dict[str, Path]     # plugin name -> path actually read


class MergeError(RuntimeError):
    pass


def _log(msg: str, quiet: bool) -> None:
    if not quiet:
        print(msg)


def build(inp: MergeInputs, quiet: bool = False) -> MergeResult:
    cfg = inp.cfg
    PATCH = inp.output_name
    INST = Path(inp.installed_dir)
    EXTRA = {k: str(v) for k, v in inp.extra_plugins.items()}

    def find_new(name):
        for l in inp.new_mod_paths:
            if os.path.basename(str(l)) == name:
                return str(l)
        raise MergeError(f"new plugin {name!r} not found in merge_patch.new_mod_paths")

    # ---- load order: Plugins.txt order + DLC esps before their unofficial patches
    lines = Path(inp.plugins_txt).read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    _pl = [l.strip().lstrip('*') for l in lines if l.strip() and not l.startswith('#')]
    _order: list[str] = []
    for n in _pl:
        if n == 'Oblivion.esm' or n == PATCH:
            continue
        if n.endswith(' - Unofficial Patch.esp'):
            dlc = n.replace(' - Unofficial Patch.esp', '.esp')
            if os.path.exists(str(INST / dlc)) and dlc not in _order:
                _order.append(dlc)
        _order.append(n)
        if n in inp.insert_after:
            _order.append(inp.insert_after[n])

    def _path(n):
        if n in EXTRA:
            return EXTRA[n]
        if n in cfg['new_order']:
            return find_new(n)
        p = str(INST / n)
        if os.path.exists(p):
            return p
        raise MergeError(f"plugin {n!r} from Plugins.txt not found in {INST}")

    paths = {'Oblivion.esm': str(inp.vanilla)}
    for n in _order:
        paths[n] = _path(n)
    load_order = (['Oblivion.esm'] + [n for n in _order if n.lower().endswith('.esm')]
                  + [n for n in _order if not n.lower().endswith('.esm')])
    NEW = set(cfg['new_order']) | set(EXTRA)
    missing = sorted(n for n in NEW if n not in load_order)
    if missing:
        raise MergeError(f"new plugins not active in Plugins.txt: {missing}")
    new_in_order = sorted(NEW, key=load_order.index)   # deterministic (legacy used set order)
    LOW = set(cfg.get('low_priority', []))
    prio = [n for n in load_order if n in LOW] + [n for n in load_order if n not in LOW]
    pri = {n: i for i, n in enumerate(prio)}
    MERGE = set(cfg['merge_types'])

    # ---- pass 1: candidate keys = records new plugins override
    hdr = {n: tp.read_header(paths[n]) for n in load_order}
    cand = collections.defaultdict(set)
    info_parent = {}
    for n in new_in_order:
        for p, r in tp.iter_records(paths[n], want=MERGE):
            if not p.is_override(r):
                continue
            if r.sig == 'CELL' and r.first('XCLC'):
                continue  # exterior cell headers handled separately
            k = p.global_key(r.form_id)
            cand[k].add(n)
            if r.sig == 'INFO' and r.parent is not None:
                info_parent[k] = p.global_key(r.parent)
    _log(f'candidate keys {len(cand)}', quiet)

    # ---- pass 2: who else overrides them (and fetch all versions)
    def local_ids(n, keys):
        h = hdr[n]
        names = [m.lower() for m in h.masters] + [n.lower()]
        out = {}
        for (own, oid) in keys:
            if own in names:
                out[(names.index(own) << 24) | oid] = (own, oid)
        return out

    versions = collections.defaultdict(dict)
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
    _log('fetched', quiet)

    # ---- merge
    w = Writer(PATCH, load_order + [PATCH])
    stats = collections.Counter()
    report = collections.defaultdict(list)

    def _seq(r):
        return list(units(r).keys())

    def _order_ok(ms, ref):
        pos = {n: i for i, n in enumerate(ref)}
        known = [pos[n] for n in ms if n in pos]
        return known == sorted(known)

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
        m.flags = winner.flags
        ms = _seq(m)
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
            del w.infos[dk]
            continue
        d = field_merge(base, [vers[n] for n in others]) if others else base.copy()
        w.add(d)

    # ---- extra world edits from cfg: run the unchanged world_edits.py in the namespace it expects
    ns = {
        '__name__': 'world_edits', '__file__': str(WORLD_EDITS),
        'os': os, 'sys': sys, 'json': json, 'collections': collections,
        'tp': tp, 'NRec': NRec, 'patchlib': patchlib,
        'w': w, 'load_order': load_order, 'paths': paths, 'hdr': hdr, 'local_ids': local_ids,
        'CFG': cfg, 'PATCH': PATCH,
    }
    if quiet:
        ns['print'] = lambda *a, **k: None
    if cfg.get('world_edits'):
        exec(compile(WORLD_EDITS.read_text(encoding='utf-8'), str(WORLD_EDITS), 'exec'), ns)
    world_log = list(ns.get('edits_log', []))

    data = w.build(author=inp.author, desc=cfg['description'])
    _log(f"{dict(stats)} {len(w.mast)} masters {len(data)} bytes", quiet)

    return MergeResult(
        data=data, load_order=load_order,
        report={s: [[list(k), o] for k, o in v] for s, v in report.items()},
        stats=dict(stats), masters=list(w.mast), world_log=world_log,
        roundtrip=_roundtrip(w, data, PATCH),
        inputs_used={n: Path(paths[n]) for n in load_order},
    )


def _roundtrip(w: Writer, data: bytes, name: str) -> dict:
    """Re-read the written bytes and check every record matches what the merge produced."""
    import tempfile
    expect = {}
    for lst in w.top.values():
        for r in lst:
            expect[(r.sig, r.key)] = r.subs
    for c, _ch in w.cells_int:
        expect[('CELL', c.key)] = c.subs
    for lst in w.infos.values():
        for r in lst:
            expect[('INFO', r.key)] = r.subs
    seen = bad = 0
    mismatches = []
    errors: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / name
        f.write_bytes(data)
        p = None
        for p, r in tp.iter_records(f):
            k = (r.sig, p.global_key(r.form_id))
            if k in expect:
                seen += 1
                if NRec(p, r).subs != expect[k]:
                    bad += 1
                    mismatches.append([k[0], list(k[1])])
        if p is not None:
            errors = list(p.errors)
    return {'checked': seen, 'mismatches': bad, 'mismatched': mismatches[:50], 'parse_errors': errors}
