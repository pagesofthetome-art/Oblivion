"""Read side of the knowledge store: ranked full-text search and exact lookups.

Every result carries `source` and `confidence`. Text output labels HYPOTHESIS rows as such.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from forge.kb.build import DEFAULT_DB

STOP = set("""a an and are as at be by can could did do does for from has have how i if in into is it its
make made makes me mod mods my of on or our should so some than that the their them then there these this
those to use used uses using was what when where which who why will with would you your oblivion research
function functions obse""".split())


# modding vocabulary: a question's word -> words our notes and the sources use for it
SYNONYMS = {
    "near": ["nearby"], "nearby": ["near"], "find": ["scan"], "scan": ["find"], "search": ["scan", "find"],
    "owner": ["source"], "shooter": ["source"], "freeze": ["stop", "frozen"], "teleport": ["position", "move"],
    "key": ["keyboard"], "hotkey": ["key", "pressed"], "button": ["key"],
    "hang": ["freeze", "stuck"], "stuck": ["hang"], "crash": ["ctd"], "ctd": ["crash"],
    "weather": ["wthr"], "storm": ["thunderstorm"], "dimension": ["worldspace", "pocket"],
    "master": ["dependency"], "dependency": ["master"],
}


class KBError(RuntimeError):
    pass


_CONN: dict[str, sqlite3.Connection] = {}


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    p = Path(db_path or DEFAULT_DB)
    if not p.is_file():
        raise KBError(f"{p} not found: run `forge kb build` first")
    key = f"{p.resolve()}:{p.stat().st_mtime_ns}"   # a rebuilt file gets a fresh connection
    if key not in _CONN:
        db = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        _CONN[key] = db
    return _CONN[key]


def close_all() -> None:
    for c in _CONN.values():
        c.close()
    _CONN.clear()


def _terms(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_]+", text.replace("'s", ""))
    out = []
    for w in words:
        lw = w.lower()
        if lw in STOP or len(lw) < 2:
            continue
        out.append(lw)
        # CamelCase words in the question also match their parts (SetPos -> set pos)
        parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", w).lower().split()
        if len(parts) > 1:
            out += [x for x in parts if x not in STOP and len(x) > 1]
    out += [syn for t in list(out) for syn in SYNONYMS.get(t, [])]
    return list(dict.fromkeys(out))


def _detail(db, kind: str, key: str) -> dict:
    if kind == "function":
        r = db.execute("SELECT * FROM functions WHERE name = ?", (key,)).fetchone()
    elif kind == "record":
        r = db.execute("SELECT * FROM record_types WHERE sig = ?", (key,)).fetchone()
    elif kind == "technique":
        r = db.execute("SELECT * FROM techniques WHERE id = ?", (int(key),)).fetchone()
    elif kind == "crash":
        r = db.execute("SELECT * FROM crash_signatures WHERE id = ?", (key,)).fetchone()
    elif kind == "test":
        r = db.execute("SELECT * FROM test_results WHERE id = ?", (key,)).fetchone()
    elif kind == "form":
        plugin, fid = key.rsplit(":", 1)
        r = db.execute("SELECT * FROM vanilla_forms WHERE plugin = ? AND formid = ?", (plugin, fid)).fetchone()
    else:
        r = None
    return dict(r) if r else {}


def _is_form_lookup(db, text: str) -> list[str]:
    """Tokens that name a vanilla form exactly: an EditorID written as such (CamelCase or with
    digits, e.g. WeapDaedricLongsword, Gold001) or a FormID. Plain words like 'thunderstorm' don't count."""
    out = []
    for w in re.findall(r"[A-Za-z0-9_:.]+", text):
        if re.fullmatch(r"(?:\S+\.es[mp]:)?(?:0x)?[0-9A-Fa-f]{8}", w):
            out.append(w)
        elif len(w) >= 4 and (re.search(r"[a-z][A-Z]", w) or re.search(r"[A-Za-z]\d", w)) and \
                db.execute("SELECT 1 FROM vanilla_forms WHERE edid = ? LIMIT 1", (w,)).fetchone():
            out.append(w)
    return out


def _search_knowledge(db, terms, text, limit, kinds):
    match = " OR ".join('"' + t.replace('"', "") + '"' for t in terms)
    if kinds:
        match = f"({match}) AND kind:(" + " OR ".join(kinds) + ")"
    # columns: kind, key, title, notes (our write-ups), body (signatures, params, source text)
    rows = db.execute(
        "SELECT kind, key, title, snippet(fts, -1, '[', ']', ' … ', 18) AS snip, "
        "bm25(fts, 0.0, 0.0, 4.0, 3.0, 1.0) AS score FROM fts WHERE fts MATCH ? ORDER BY score LIMIT ?",
        (match, max(limit * 5, 50))).fetchall()
    # names written exactly in the question (INFO, PositionWorld) are what the asker means
    exact = {w for w in re.findall(r"[A-Za-z0-9_]+", text) if len(w) >= 4}
    exact_ci = {w.lower() for w in exact}
    out = []
    for r in rows:
        d = _detail(db, r["kind"], r["key"])
        score = -r["score"]
        if r["kind"] == "record" and r["key"] in exact:
            score += 25
        elif r["kind"] == "function" and r["key"].lower() in exact_ci:
            score += 15
        if d.get("summary") or r["kind"] in ("technique", "crash"):
            score += 5          # our own write-up exists, not just a signature
        if d.get("confidence") == "HYPOTHESIS":
            score -= 2
        out.append({"kind": r["kind"], "key": r["key"], "title": r["title"], "snippet": r["snip"],
                    "score": round(score, 3), "confidence": d.get("confidence"),
                    "source": d.get("source"), "detail": d})
    out.sort(key=lambda x: -x["score"])
    return out


def _search_forms(db, terms, limit):
    match = " OR ".join('"' + t.replace('"', "") + '"' for t in terms)
    rows = db.execute(
        "SELECT key, title, snippet(fts_forms, -1, '[', ']', ' … ', 12) AS snip, "
        "bm25(fts_forms, 0.0, 4.0, 1.0) AS score FROM fts_forms WHERE fts_forms MATCH ? ORDER BY score LIMIT ?",
        (match, limit)).fetchall()
    out = []
    for r in rows:
        d = _detail(db, "form", r["key"])
        out.append({"kind": "form", "key": r["key"], "title": r["title"], "snippet": r["snip"],
                    "score": round(-r["score"], 3), "confidence": d.get("confidence"),
                    "source": d.get("source"), "detail": d})
    return out


def search(text: str, limit: int = 10, kinds: list[str] | None = None, db_path=None) -> list[dict]:
    """Ranked search. Knowledge (functions, records, techniques, crashes, tests) and vanilla forms
    are ranked separately: forms lead only when the question names one exactly; otherwise they
    take at most limit // 3 slots after the knowledge results."""
    db = connect(db_path)
    terms = _terms(text)
    if not terms:
        return []
    want_forms = kinds is None or "form" in kinds
    other = [k for k in (kinds or []) if k != "form"]
    know = [] if kinds and not other else _search_knowledge(db, terms, text, limit, other or None)
    forms = []
    if want_forms and db.execute("SELECT 1 FROM vanilla_forms LIMIT 1").fetchone():
        lookups = _is_form_lookup(db, text)
        if lookups:
            for w in lookups:
                for f in form(w, db_path, limit):
                    if not f["override"]:
                        key = f"{f['plugin']}:{f['formid']}"
                        forms.append({"kind": "form", "key": key, "title": f"{f['edid']} {f['full']}".strip(),
                                      "snippet": f"{f['sig']} {f['edid']}", "score": 100.0,
                                      "confidence": f["confidence"], "source": f["source"], "detail": f})
            return (forms + know)[:limit]
        forms = _search_forms(db, terms, limit)
    if kinds == ["form"]:
        return forms[:limit]
    room = limit // 3 if forms else 0
    return know[:limit - min(room, len(forms))] + forms[:room]


def func(name: str, db_path=None) -> dict | None:
    db = connect(db_path)
    r = db.execute("SELECT * FROM functions WHERE name = ? OR alias = ? ORDER BY name = ? DESC LIMIT 1",
                   (name, name, name)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["params"] = [dict(p) for p in db.execute(
        "SELECT name, type, optional FROM function_params WHERE func = ? ORDER BY ord", (d["name"],))]
    return d


def record(sig: str, db_path=None) -> dict | None:
    db = connect(db_path)
    r = db.execute("SELECT * FROM record_types WHERE sig = ?", (sig.upper(),)).fetchone()
    if not r:
        return None
    d = dict(r)
    subs = []
    for s in db.execute("SELECT * FROM subrecords WHERE sig = ? ORDER BY ord", (d["sig"],)):
        s = dict(s)
        s["fields"] = [dict(f) for f in db.execute(
            "SELECT name, type, offset, size, formid FROM subrecord_fields WHERE sig = ? AND ord = ? "
            "ORDER BY field_ord", (d["sig"], s["ord"]))]
        subs.append(s)
    d["subrecords"] = subs
    d["formid_subrecords"] = list(dict.fromkeys(s["sub_sig"] for s in subs if s["formid"]))
    if any(s["sub_sig"] == "CTDA" for s in subs):
        d["formid_subrecords"].append("CTDA")
        d["note"] = ("CTDA (conditions) holds FormIDs in its two parameter slots when the condition "
                     "function takes a form (offsets 12 and 16).")
    d["required_subrecords"] = [s["sub_sig"] for s in subs if s["required"]]
    return d


def form(query: str, db_path=None, limit: int = 20) -> list[dict]:
    db = connect(db_path)
    if db.execute("SELECT COUNT(*) FROM vanilla_forms").fetchone()[0] == 0:
        raise KBError("no vanilla index loaded: run `forge kb export-vanilla` on the PC, then `forge kb build`")
    q = query.strip()
    m = re.fullmatch(r"(?:(.+\.es[mp]):)?(?:0x)?([0-9A-Fa-f]{6,8})", q)
    if m:
        hexid = m.group(2).upper().rjust(8, "0")
        if m.group(1):
            rows = db.execute("SELECT * FROM vanilla_forms WHERE plugin = ? COLLATE NOCASE AND "
                              "(formid = ? OR objid = ?)", (m.group(1), hexid, hexid[-6:]))
        else:
            rows = db.execute("SELECT * FROM vanilla_forms WHERE formid = ?", (hexid,))
        out = [dict(r) for r in rows]
        if out:
            return out
    return [dict(r) for r in db.execute(
        "SELECT * FROM vanilla_forms WHERE edid = ? ORDER BY override, plugin LIMIT ?", (q, limit))]


def forms_of_type(sig: str, db_path=None) -> list[dict]:
    db = connect(db_path)
    return [dict(r) for r in db.execute(
        "SELECT * FROM vanilla_forms WHERE sig = ? AND override = 0 ORDER BY plugin, formid", (sig.upper(),))]


def technique(keyword: str, db_path=None) -> list[dict]:
    db = connect(db_path)
    like = f"%{keyword}%"
    return [dict(r) for r in db.execute(
        "SELECT * FROM techniques WHERE specimen LIKE ? OR technique LIKE ? OR notes LIKE ? "
        "OR functions_used LIKE ? OR runtime LIKE ? ORDER BY nexus_id IS NULL, id",
        (like, like, like, like, like))]


def crash(keyword: str = "", db_path=None) -> list[dict]:
    db = connect(db_path)
    like = f"%{keyword}%"
    return [dict(r) for r in db.execute(
        "SELECT * FROM crash_signatures WHERE title LIKE ? OR symptoms LIKE ? OR cause LIKE ? OR components LIKE ?",
        (like, like, like, like))]


def stats(db_path=None) -> dict:
    db = connect(db_path)
    return {k: v for k, v in db.execute("SELECT key, value FROM meta")}
