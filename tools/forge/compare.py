"""Compare two plugins: byte-identical, record-identical (order aside), or different."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

import tes4_plugin as tp


def _records(path: Path):
    hdr = tp.read_header(path)
    recs = Counter()
    order = []
    for p, r in tp.iter_records(path):
        parent = p.global_key(r.parent) if r.parent is not None else None
        key = (r.sig, p.global_key(r.form_id), parent, r.group_path[-1] if r.group_path else "")
        body = (r.flags & ~tp.FLAG_COMPRESSED, hashlib.sha256(r.data).hexdigest())
        recs[(key, body)] += 1
        order.append(key)
    return hdr, recs, order


def compare(a: str | Path, b: str | Path) -> dict:
    a, b = Path(a), Path(b)
    ba, bb = a.read_bytes(), b.read_bytes()
    res = {"a": str(a), "b": str(b), "a_sha256": hashlib.sha256(ba).hexdigest(),
           "b_sha256": hashlib.sha256(bb).hexdigest(), "byte_identical": ba == bb}
    if res["byte_identical"]:
        res["verdict"] = "byte-identical"
        return res
    ha, ra, oa = _records(a)
    hb, rb, ob = _records(b)
    header_diff = [f for f, x, y in (
        ("masters", ha.masters, hb.masters), ("author", ha.author, hb.author),
        ("description", ha.description, hb.description), ("esm_flag", ha.is_esm_flag, hb.is_esm_flag),
        ("num_records", ha.num_records, hb.num_records)) if x != y]
    only_a, only_b = ra - rb, rb - ra
    res.update({
        "header_differences": header_diff,
        "records_a": sum(ra.values()), "records_b": sum(rb.values()),
        "only_in_a": [_fmt(k) for k in list(only_a)[:25]], "only_in_b": [_fmt(k) for k in list(only_b)[:25]],
        "only_in_a_count": sum(only_a.values()), "only_in_b_count": sum(only_b.values()),
        "same_order": oa == ob,
    })
    if not header_diff and not only_a and not only_b:
        res["verdict"] = "record-identical (same records and header; record order differs)"
    elif "masters" in header_diff:
        res["verdict"] = "different (master lists differ, so FormIDs are not comparable byte-for-byte)"
    else:
        res["verdict"] = "different"
    return res


def _fmt(item) -> str:
    (sig, key, parent, grp), (flags, digest) = item
    k = f"{key[0]}:{key[1]:06X}" if key else "?"
    return f"{sig} {k} flags={flags:#x} data={digest[:12]}" + (f" in {grp}" if grp else "")
